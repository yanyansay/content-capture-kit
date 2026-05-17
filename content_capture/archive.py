from __future__ import annotations

from pathlib import Path

from .assets import localize_markdown_assets
from .files import atomic_write_text
from .metadata import published_for_filename
from .naming import markdown_title, safe_filename
from .preview import markdown_to_preview_html


def write_article_output(
    markdown: str,
    output_dir: Path,
    source_url: str,
    title: str | None = None,
    author: str | None = None,
    published_at: str | None = None,
    mirror_url: str | None = None,
    local_assets: bool = False,
    absolute_asset_paths: bool = False,
    html_preview: bool = False,
    fallback_filename: str = "article",
    group_by_author: bool = True,
) -> Path:
    resolved_title = title or markdown_title(markdown) or fallback_filename
    author_name = safe_filename(author or "unknown-author", fallback="unknown-author")
    article_dir = output_dir / author_name if group_by_author else output_dir
    article_dir.mkdir(parents=True, exist_ok=True)
    published_name = published_for_filename(published_at)
    filename = safe_filename(f"{resolved_title}_{published_name}", fallback=fallback_filename)
    output_path = article_dir / f"{filename}.md"
    header = f"来源: {source_url}\n\n"
    if mirror_url:
        header += f"镜像: {mirror_url}\n\n"
    header += "---\n\n"
    atomic_write_text(output_path, header + markdown)
    if local_assets:
        localize_markdown_assets(
            output_path,
            absolute_paths=absolute_asset_paths,
            image_dir=article_dir / "image",
            video_dir=article_dir / "video",
        )
    if html_preview:
        markdown_to_preview_html(output_path)
    return output_path
