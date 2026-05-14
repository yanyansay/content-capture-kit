from __future__ import annotations

import re
import html


def safe_filename(value: str, fallback: str = "article", max_length: int = 120) -> str:
    name = value.strip()
    name = re.sub(r"[\\/:*?\"<>|\r\n\t]+", "-", name)
    name = re.sub(r"\s+", " ", name)
    name = name.strip(" .-_")
    if not name:
        name = fallback
    return name[:max_length].strip(" .-_") or fallback


def compact_filename(value: str, fallback: str = "article", max_length: int = 120) -> str:
    name = safe_filename(value, fallback=fallback, max_length=max_length)
    name = re.sub(r"\s+", "", name)
    return name[:max_length].strip(" .-_") or fallback


def markdown_title(markdown: str) -> str | None:
    for line in markdown.splitlines():
        match = re.match(r"^#\s+(.+?)\s*$", line)
        if match:
            return match.group(1).strip()
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(("<!--", "![", "<video", "---")):
            return stripped[:60].strip()
    return None


def html_title(document: str) -> str | None:
    patterns = [
        r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']',
        r'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:title["\']',
        r"<title>(.*?)</title>",
    ]
    for pattern in patterns:
        match = re.search(pattern, document, re.IGNORECASE | re.DOTALL)
        if match:
            title = re.sub(r"\s+", " ", html.unescape(match.group(1))).strip()
            title = re.sub(r"\s+-\s+极境$", "", title)
            if title:
                return title
    return None
