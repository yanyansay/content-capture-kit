from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

from .files import atomic_write_text
from .x_api import XApiError, extract_tweet_id


XTOMD_MARKDOWN_ENDPOINT = "https://xtomd.com/api/markdown"


def fetch_x_markdown(url: str, timeout: float = 60.0) -> str:
    body = json.dumps({"url": url}).encode("utf-8")
    request = urllib.request.Request(
        XTOMD_MARKDOWN_ENDPOINT,
        data=body,
        method="POST",
        headers={
            "Accept": "text/markdown",
            "Content-Type": "application/json",
            "User-Agent": "twitter-crawling/0.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8").strip()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise XApiError(f"xtomd failed with HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise XApiError(f"xtomd request failed: {error}") from error


def fetch_x_markdown_to_file(url_or_id: str, output_dir: Path) -> Path:
    if url_or_id.strip().isdigit():
        url = f"https://x.com/i/status/{url_or_id.strip()}"
        filename = f"{url_or_id.strip()}.md"
    else:
        url = url_or_id
        filename = f"{extract_tweet_id(url_or_id)}.md"

    markdown = fetch_x_markdown(url)
    if not markdown:
        raise XApiError("xtomd returned empty Markdown.")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename
    atomic_write_text(output_path, markdown)
    return output_path
