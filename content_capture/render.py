from __future__ import annotations

from pathlib import Path
from typing import Any

from .files import atomic_write_text
from .longform import LongformPost


def _metric_lines(metrics: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for key in ("like_count", "reply_count", "retweet_count", "quote_count", "bookmark_count", "impression_count"):
        if key in metrics:
            label = key.replace("_count", "").replace("_", " ").title()
            lines.append(f"- {label}: {metrics[key]}")
    return lines


def render_post(post: LongformPost, heading_level: int = 1) -> str:
    marker = "#" * heading_level
    title = post.title or f"X Longform {post.tweet_id}"
    lines = [
        f"{marker} {title}",
        "",
        f"- Source: {post.url}",
        f"- Type: {post.source_kind}",
    ]
    if post.created_at:
        lines.append(f"- Published: {post.created_at}")
    if post.author_username:
        author = f"@{post.author_username}"
        if post.author_name:
            author = f"{post.author_name} ({author})"
        lines.append(f"- Author: {author}")

    metric_lines = _metric_lines(post.metrics)
    if metric_lines:
        lines.append("")
        lines.append("## Metrics" if heading_level == 1 else f"{marker}# Metrics")
        lines.extend(metric_lines)

    lines.extend(["", "## Content" if heading_level == 1 else f"{marker}# Content", "", post.text.strip(), ""])
    return "\n".join(lines)


def render_single_longform(post: LongformPost, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{post.tweet_id}.md"
    atomic_write_text(output_path, render_post(post))
    return output_path

