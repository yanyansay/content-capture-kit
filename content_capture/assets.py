from __future__ import annotations

import mimetypes
import re
import hashlib
import http.client
import subprocess
import shutil
import urllib.parse
import urllib.error
import urllib.request
from pathlib import Path

from .files import atomic_write_text
from .naming import safe_filename


MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\((https?://[^)\s]+)\)")
HTML_VIDEO_PATTERN = re.compile(r'<video\s+src="(https?://[^"]+)"([^>]*)></video>')


def localize_markdown_assets(
    markdown_path: Path,
    timeout: float = 120.0,
    absolute_paths: bool = False,
    image_dir: Path | None = None,
    video_dir: Path | None = None,
) -> list[Path]:
    content = markdown_path.read_text(encoding="utf-8")
    default_asset_dir = markdown_path.with_suffix("")
    image_dir = image_dir or default_asset_dir
    video_dir = video_dir or default_asset_dir
    image_dir.mkdir(parents=True, exist_ok=True)
    video_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []
    url_to_path: dict[str, Path] = {}
    warnings: list[str] = []

    def local_path_for(url: str, index: int, fallback_ext: str, target_dir: Path, asset_kind: str) -> Path:
        if url in url_to_path:
            return url_to_path[url]
        parsed = urllib.parse.urlparse(url)
        name = Path(parsed.path).name
        ext = Path(name).suffix
        if not ext:
            ext = fallback_ext
        stem = _ascii_asset_stem(Path(name).stem, fallback=f"asset-{index:02d}")
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
        path = target_dir / f"{asset_kind}-{index:02d}-{digest}-{stem}{ext}"
        url_to_path[url] = path
        return path

    counter = 0

    def download(url: str, fallback_ext: str, target_dir: Path, asset_kind: str) -> Path:
        nonlocal counter
        if url in url_to_path and url_to_path[url].exists():
            return url_to_path[url]
        counter += 1
        path = local_path_for(url, counter, fallback_ext, target_dir, asset_kind)
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 twitter-crawling/0.1"},
        )
        last_error: BaseException | None = None
        for _ in range(5):
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    expected_length = response.headers.get("content-length")
                    chunks: list[bytes] = []
                    while True:
                        chunk = response.read(1024 * 256)
                        if not chunk:
                            break
                        chunks.append(chunk)
                    data = b"".join(chunks)
                    content_type = response.headers.get("content-type", "").split(";")[0].strip()
                    if expected_length and len(data) != int(expected_length):
                        raise http.client.IncompleteRead(data, int(expected_length) - len(data))
                break
            except (http.client.IncompleteRead, TimeoutError, urllib.error.URLError) as error:
                last_error = error
        else:
            raise OSError(f"failed to download {url}: {last_error}")
        if path.suffix == fallback_ext and content_type:
            guessed = mimetypes.guess_extension(content_type)
            if guessed and guessed not in {".jpe"}:
                path = path.with_suffix(guessed)
                url_to_path[url] = path
        path.write_bytes(data)
        downloaded.append(path)
        return path

    def image_repl(match: re.Match[str]) -> str:
        alt, url = match.groups()
        try:
            path = download(url, ".jpg", image_dir, "image")
        except OSError as error:
            warnings.append(str(error))
            return match.group(0)
        return f"![{alt}]({_markdown_path(path, markdown_path, absolute_paths)})"

    def video_repl(match: re.Match[str]) -> str:
        url, attrs = match.groups()
        try:
            path = download(url, ".mp4", video_dir, "video")
            path = ensure_previewable_video(path)
        except OSError as error:
            warnings.append(str(error))
            return match.group(0)
        return f'<video src="{_markdown_path(path, markdown_path, absolute_paths)}"{attrs}></video>'

    content = MARKDOWN_IMAGE_PATTERN.sub(image_repl, content)
    content = HTML_VIDEO_PATTERN.sub(video_repl, content)
    if warnings:
        content += "\n\n<!-- Asset download warnings:\n"
        content += "\n".join(f"- {warning}" for warning in warnings)
        content += "\n-->\n"
    atomic_write_text(markdown_path, content)
    return downloaded


def _markdown_path(path: Path, markdown_path: Path, absolute_paths: bool) -> str:
    if absolute_paths:
        return path.resolve().as_posix()
    return path.relative_to(markdown_path.parent).as_posix()


def _ascii_asset_stem(value: str, fallback: str) -> str:
    stem = safe_filename(value, fallback=fallback, max_length=80)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(" .-_")
    return stem or fallback


def absolutize_local_asset_links(markdown_path: Path) -> None:
    content = markdown_path.read_text(encoding="utf-8")

    def to_absolute(value: str) -> str:
        if value.startswith(("http://", "https://", "/", "file://")):
            return value
        return (markdown_path.parent / value).resolve().as_posix()

    content = re.sub(
        r"!\[([^\]]*)\]\(([^)\s]+)\)",
        lambda match: f"![{match.group(1)}]({to_absolute(match.group(2))})",
        content,
    )
    content = re.sub(
        r'<video\s+src="([^"]+)"([^>]*)></video>',
        lambda match: f'<video src="{to_absolute(match.group(1))}"{match.group(2)}></video>',
        content,
    )
    atomic_write_text(markdown_path, content)


def ensure_previewable_video(path: Path) -> Path:
    if path.suffix.lower() in {".mp4", ".webm", ".ogg"}:
        return path
    if not shutil.which("ffmpeg"):
        return path
    output_path = path.with_suffix(".mp4")
    completed = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(path),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if completed.returncode != 0 or not output_path.exists():
        return path
    if output_path != path:
        try:
            path.unlink()
        except OSError:
            pass
    return output_path
