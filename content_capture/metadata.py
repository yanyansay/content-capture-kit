from __future__ import annotations

import datetime as dt
import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse

from .naming import markdown_title


@dataclass(frozen=True)
class ArticleMetadata:
    title: str | None = None
    author: str | None = None
    published_at: str | None = None


class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.values: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta":
            return
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        key = attrs_dict.get("property") or attrs_dict.get("name") or attrs_dict.get("itemprop")
        content = attrs_dict.get("content")
        if key and content and key not in self.values:
            self.values[key] = html.unescape(content).strip()


def metadata_from_markdown(markdown: str) -> ArticleMetadata:
    return ArticleMetadata(
        title=markdown_title(markdown),
        author=_first_markdown_value(markdown, ("Author", "作者")),
        published_at=_first_markdown_value(markdown, ("Published", "发布时间", "发表时间", "Date")),
    )


def metadata_from_html(document: str) -> ArticleMetadata:
    parser = _MetaParser()
    parser.feed(document)
    values = parser.values
    return ArticleMetadata(
        title=_first_value(values, ("og:title", "twitter:title")),
        author=(
            _first_value(values, ("author", "article:author", "byl", "weixin:author"))
            or _wechat_script_value(document, "nickname")
            or _first_value(values, ("og:site_name",))
        ),
        published_at=(
            _first_value(values, ("article:published_time", "datePublished", "date", "pubdate", "publishdate"))
            or _wechat_publish_time(document)
        ),
    )


def metadata_with_fallback(primary: ArticleMetadata, fallback: ArticleMetadata) -> ArticleMetadata:
    return ArticleMetadata(
        title=primary.title or fallback.title,
        author=primary.author or fallback.author,
        published_at=primary.published_at or fallback.published_at,
    )


def author_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host in {"x.com", "twitter.com", "www.x.com", "www.twitter.com"}:
        parts = [part for part in parsed.path.split("/") if part]
        if parts and parts[0] not in {"i"}:
            return parts[0]
    return parsed.netloc.replace("www.", "") or None


def published_for_filename(value: str | None) -> str:
    if not value:
        return "unknown-date"
    text = value.strip()
    if not text:
        return "unknown-date"
    if text.isdigit():
        timestamp = int(text)
        if timestamp > 10_000_000_000:
            timestamp //= 1000
        return dt.datetime.fromtimestamp(timestamp, tz=dt.UTC).strftime("%Y-%m-%d")
    match = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text)
    if match:
        year, month, day = match.groups()
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return text[:40]


def _first_markdown_value(markdown: str, labels: tuple[str, ...]) -> str | None:
    labels_pattern = "|".join(re.escape(label) for label in labels)
    pattern = re.compile(
        rf"^\s*[-*]?\s*(?:\*\*)?(?:{labels_pattern})(?:\*\*)?\s*[:：]\s*(.+?)\s*$",
        re.IGNORECASE,
    )
    for line in markdown.splitlines():
        match = pattern.match(line)
        if match:
            return _clean_value(match.group(1))
    return None


def _first_value(values: dict[str, str], keys: tuple[str, ...]) -> str | None:
    lower_values = {key.lower(): value for key, value in values.items()}
    for key in keys:
        value = lower_values.get(key.lower())
        if value:
            return _clean_value(value)
    return None


def _wechat_script_value(document: str, name: str) -> str | None:
    match = re.search(rf"var\s+{re.escape(name)}\s*=\s*['\"]([^'\"]+)['\"]", document)
    if not match:
        return None
    return _clean_value(match.group(1))


def _wechat_publish_time(document: str) -> str | None:
    ct = _wechat_script_value(document, "ct")
    if ct:
        return ct
    match = re.search(r"publish_time\s*[:=]\s*['\"]([^'\"]+)['\"]", document)
    if match:
        return _clean_value(match.group(1))
    return None


def _clean_value(value: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", html.unescape(value)).strip()
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"\(@[^)]+\)", "", cleaned)
    cleaned = cleaned.strip(" -*_")
    return cleaned or None
