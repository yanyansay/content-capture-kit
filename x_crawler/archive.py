from __future__ import annotations

from pathlib import Path

from .assets import localize_markdown_assets
from .files import atomic_write_text
from .naming import markdown_title, safe_filename
from .preview import markdown_to_preview_html


def write_article_output(
    markdown: str,
    output_dir: Path,
    source_url: str,
    title: str | None = None,
    mirror_url: str | None = None,
    local_assets: bool = False,
    absolute_asset_paths: bool = False,
    html_preview: bool = False,
    fallback_filename: str = "article",
) -> Path:
    resolved_title = title or markdown_title(markdown) or fallback_filename
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{safe_filename(resolved_title, fallback=fallback_filename)}.md"
    header = f"来源: {source_url}\n\n"
    if mirror_url:
        header += f"镜像: {mirror_url}\n\n"
    header += "---\n\n"
    atomic_write_text(output_path, header + markdown)
    if local_assets:
        localize_markdown_assets(
            output_path,
            absolute_paths=absolute_asset_paths,
            image_dir=output_dir / "image",
            video_dir=output_dir / "video",
        )
    if html_preview:
        markdown_to_preview_html(output_path)
    return output_path
