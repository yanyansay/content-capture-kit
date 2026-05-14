from __future__ import annotations

import re
import http.client
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from .files import atomic_write_text
from .html_markdown import extract_article_markdown
from .naming import html_title


def slug_from_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.replace("www.", "") or "article"
    path = parsed.path.strip("/").replace("/", "-")
    slug = f"{host}-{path}" if path else host
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", slug).strip("-")
    return slug[:120] or "article"


def parse_url_to_markdown(url: str, output_dir: Path) -> Path:
    markdown = fetch_url_markdown(url)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{slug_from_url(url)}.md"
    atomic_write_text(output_path, markdown)
    return output_path


def fetch_url_markdown(url: str) -> str:
    try:
        return fetch_url_markdown_from_html(url)
    except (OSError, ValueError):
        pass

    if not shutil.which("defuddle"):
        raise OSError("defuddle is not installed or not on PATH.")

    completed = subprocess.run(
        ["defuddle", "parse", url, "--md"],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise OSError(f"defuddle failed for {url}: {detail}")
    return completed.stdout


def fetch_url_markdown_from_html(url: str) -> str:
    html = fetch_url_html(url)
    return extract_article_markdown(html, url)


def fetch_url_html(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )
    last_error: BaseException | None = None
    partial: bytes = b""
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read().decode("utf-8", errors="replace")
        except http.client.IncompleteRead as error:
            last_error = error
            partial = error.partial or b""
            time.sleep(1 + attempt)
        except (TimeoutError, urllib.error.URLError) as error:
            last_error = error
            time.sleep(1 + attempt)
    if partial:
        return partial.decode("utf-8", errors="replace")
    raise OSError(f"failed to fetch {url}: {last_error}")


def fetch_url_title(url: str) -> str | None:
    try:
        return html_title(fetch_url_html(url))
    except OSError:
        return None
