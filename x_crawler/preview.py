from __future__ import annotations

import html
import re
from pathlib import Path

from .files import atomic_write_text


IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
VIDEO_PATTERN = re.compile(r'<video\s+src="([^"]+)"[^>]*></video>')
FENCE_PATTERN = re.compile(r"```(\w+)?\n(.*?)\n```", re.DOTALL)


def markdown_to_preview_html(markdown_path: Path) -> Path:
    markdown = markdown_path.read_text(encoding="utf-8")
    body = _render_markdown_subset(markdown)
    output_path = markdown_path.with_suffix(".html")
    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(markdown_path.stem)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.7; max-width: 860px; margin: 40px auto; padding: 0 20px; color: #1f2933; }}
    img, video {{ max-width: 100%; height: auto; display: block; margin: 18px 0; border-radius: 8px; }}
    video {{ background: #111; }}
    pre {{ overflow-x: auto; padding: 14px 16px; border-radius: 8px; background: #111827; color: #f9fafb; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
    blockquote {{ border-left: 4px solid #d0d7de; margin-left: 0; padding-left: 16px; color: #57606a; }}
    a {{ color: #0969da; }}
  </style>
</head>
<body>
{body}
</body>
</html>
"""
    atomic_write_text(output_path, document)
    return output_path


def _render_markdown_subset(markdown: str) -> str:
    blocks: list[str] = []
    in_code = False
    code_lines: list[str] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            text = " ".join(paragraph).strip()
            if text:
                blocks.append(f"<p>{_inline(text)}</p>")
            paragraph.clear()

    for line in markdown.splitlines():
        fence = re.match(r"^```(\w+)?\s*$", line)
        if fence:
            if in_code:
                blocks.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
                code_lines.clear()
                in_code = False
            else:
                flush_paragraph()
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue

        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            continue
        if stripped.startswith("<!--"):
            continue
        if match := re.match(r"^(#{1,6})\s+(.+)$", stripped):
            flush_paragraph()
            level = len(match.group(1))
            blocks.append(f"<h{level}>{_inline(match.group(2))}</h{level}>")
            continue
        if match := IMAGE_PATTERN.fullmatch(stripped):
            flush_paragraph()
            alt, src = match.groups()
            blocks.append(f'<img src="{html.escape(src, quote=True)}" alt="{html.escape(alt, quote=True)}">')
            continue
        if match := VIDEO_PATTERN.fullmatch(stripped):
            flush_paragraph()
            src = match.group(1)
            blocks.append(f'<video src="{html.escape(src, quote=True)}" controls preload="metadata"></video>')
            blocks.append(f'<p><a href="{html.escape(src, quote=True)}">Open video file</a></p>')
            continue
        if stripped.startswith("- "):
            flush_paragraph()
            blocks.append(f"<ul><li>{_inline(stripped[2:])}</li></ul>")
            continue
        if stripped.startswith(">"):
            flush_paragraph()
            blocks.append(f"<blockquote>{_inline(stripped.lstrip('> ').strip())}</blockquote>")
            continue
        paragraph.append(stripped)

    flush_paragraph()
    if in_code:
        blocks.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
    return "\n".join(blocks)


def _inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    return escaped
