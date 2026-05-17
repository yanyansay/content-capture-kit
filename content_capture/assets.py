from __future__ import annotations

import mimetypes
import re
import hashlib
import http.client
import concurrent.futures
import subprocess
import shutil
import os
import urllib.parse
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .files import atomic_write_text
from .naming import safe_filename


MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\((https?://[^)\s]+)\)")
HTML_VIDEO_PATTERN = re.compile(r'<video\s+src="(https?://[^"]+)"([^>]*)></video>')
ASSET_TIMEOUT_SECONDS = 30.0
ASSET_DOWNLOAD_WORKERS = 6


@dataclass(frozen=True)
class AssetTask:
    url: str
    path: Path
    fallback_ext: str
    kind: str


@dataclass(frozen=True)
class AssetResult:
    path: Path | None = None
    error: str | None = None


def localize_markdown_assets(
    markdown_path: Path,
    timeout: float = ASSET_TIMEOUT_SECONDS,
    absolute_paths: bool = False,
    image_dir: Path | None = None,
    video_dir: Path | None = None,
    source_url: str | None = None,
) -> list[Path]:
    content = markdown_path.read_text(encoding="utf-8")
    default_asset_dir = markdown_path.with_suffix("")
    image_dir = image_dir or default_asset_dir
    video_dir = video_dir or default_asset_dir
    image_dir.mkdir(parents=True, exist_ok=True)
    video_dir.mkdir(parents=True, exist_ok=True)
    url_to_path: dict[str, Path] = {}

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

    ordered_tasks: list[AssetTask] = []
    for match in MARKDOWN_IMAGE_PATTERN.finditer(content):
        url = match.group(2)
        path = local_path_for(url, len(ordered_tasks) + 1, ".jpg", image_dir, "image")
        if not any(task.url == url for task in ordered_tasks):
            ordered_tasks.append(AssetTask(url, path, ".jpg", "image"))
    for match in HTML_VIDEO_PATTERN.finditer(content):
        url = match.group(1)
        path = local_path_for(url, len(ordered_tasks) + 1, ".mp4", video_dir, "video")
        if not any(task.url == url for task in ordered_tasks):
            ordered_tasks.append(AssetTask(url, path, ".mp4", "video"))

    results = _download_assets(ordered_tasks, timeout=timeout, source_url=source_url)
    downloaded = [result.path for task in ordered_tasks if (result := results.get(task.url)) and result.path]
    warnings = [result.error for task in ordered_tasks if (result := results.get(task.url)) and result.error]

    def image_repl(match: re.Match[str]) -> str:
        alt, url = match.groups()
        result = results.get(url)
        if not result or not result.path:
            return match.group(0)
        return f"![{alt}]({_markdown_path(result.path, markdown_path, absolute_paths)})"

    def video_repl(match: re.Match[str]) -> str:
        url, attrs = match.groups()
        result = results.get(url)
        if not result or not result.path:
            return match.group(0)
        return f'<video src="{_markdown_path(result.path, markdown_path, absolute_paths)}"{attrs}></video>'

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
    return os.path.relpath(path, markdown_path.parent).replace(os.sep, "/")


def _ascii_asset_stem(value: str, fallback: str) -> str:
    stem = safe_filename(value, fallback=fallback, max_length=80)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(" .-_")
    return stem or fallback


def _download_assets(tasks: list[AssetTask], timeout: float, source_url: str | None) -> dict[str, AssetResult]:
    if not tasks:
        return {}
    results: dict[str, AssetResult] = {}
    worker_count = min(ASSET_DOWNLOAD_WORKERS, len(tasks))
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {executor.submit(_download_asset, task, timeout, source_url): task for task in tasks}
        for future in concurrent.futures.as_completed(futures):
            task = futures[future]
            try:
                results[task.url] = AssetResult(path=future.result())
            except OSError as error:
                results[task.url] = AssetResult(error=str(error))
    return results


def _download_asset(task: AssetTask, timeout: float, source_url: str | None) -> Path:
    if task.path.exists():
        return ensure_previewable_video(task.path) if task.kind == "video" else task.path
    try:
        path = _download_url(task.url, task.path, task.fallback_ext, timeout=timeout, source_url=source_url)
    except OSError as error:
        raise OSError(f"failed to download {task.url}: {error}") from error
    return ensure_previewable_video(path) if task.kind == "video" else path


def _download_url(url: str, path: Path, fallback_ext: str, timeout: float, source_url: str | None) -> Path:
    if _prefer_curl(url):
        content_type = _download_with_curl(url, path, timeout=timeout, source_url=source_url)
        if content_type:
            return _finalize_downloaded_path(path, fallback_ext, content_type)

    try:
        content_type, data = _download_with_urllib(url, timeout=timeout, source_url=source_url)
    except OSError as error:
        content_type = _download_with_curl(url, path, timeout=timeout, source_url=source_url)
        if content_type:
            return _finalize_downloaded_path(path, fallback_ext, content_type)
        raise error

    path = _finalize_downloaded_path(path, fallback_ext, content_type)
    path.write_bytes(data)
    return path


def _download_with_urllib(url: str, timeout: float, source_url: str | None) -> tuple[str, bytes]:
    request = urllib.request.Request(url, headers=_asset_headers(source_url))
    last_error: BaseException | None = None
    for _ in range(2):
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
                return content_type, data
        except (http.client.IncompleteRead, TimeoutError, urllib.error.URLError) as error:
            last_error = error
    raise OSError(last_error)


def _finalize_downloaded_path(path: Path, fallback_ext: str, content_type: str | None) -> Path:
    if path.suffix == fallback_ext and content_type:
        guessed = mimetypes.guess_extension(content_type)
        if guessed and guessed not in {".jpe"}:
            original_path = path
            path = path.with_suffix(guessed)
            if original_path != path and original_path.exists():
                original_path.replace(path)
    return path


def _prefer_curl(url: str) -> bool:
    host = urllib.parse.urlparse(url).netloc.lower()
    return host.endswith("twimg.com") or host.endswith("x.com") or host.endswith("twitter.com")


def _asset_headers(source_url: str | None) -> dict[str, str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if source_url:
        headers["Referer"] = source_url
    return headers


def _download_with_curl(url: str, path: Path, timeout: float, source_url: str | None = None) -> str | None:
    if not shutil.which("curl"):
        return None
    headers_path = path.with_suffix(path.suffix + ".headers")
    headers = _asset_headers(source_url)
    command = [
        "curl",
        "-L",
        "--fail",
        "--silent",
        "--show-error",
        "--compressed",
        "--retry",
        "2",
        "--retry-all-errors",
        "--retry-delay",
        "1",
        "--connect-timeout",
        "10",
        "--max-time",
        str(int(timeout)),
        "--http1.1",
        "-H",
        f"User-Agent: {headers['User-Agent']}",
        "-H",
        f"Accept: {headers['Accept']}",
        "-H",
        f"Accept-Language: {headers['Accept-Language']}",
    ]
    if source_url:
        command.extend(["-H", f"Referer: {headers['Referer']}"])
    command.extend(["-D", str(headers_path), "-o", str(path), url])
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout + 10,
        )
        if completed.returncode != 0 or not path.exists() or path.stat().st_size == 0:
            path.unlink(missing_ok=True)
            return None
        return _content_type_from_headers(headers_path)
    finally:
        headers_path.unlink(missing_ok=True)


def _content_type_from_headers(path: Path) -> str | None:
    if not path.exists():
        return None
    for line in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()):
        if line.lower().startswith("content-type:"):
            return line.split(":", 1)[1].split(";", 1)[0].strip()
    return None


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
