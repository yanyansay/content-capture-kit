from __future__ import annotations

import re
import time
import urllib.parse
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from .archive import write_article_output
from .defuddle import fetch_url_html
from .files import atomic_write_text
from .html_markdown import decode_wechat_document, extract_article_markdown
from .metadata import metadata_from_html
from .naming import compact_filename, html_title


WECHAT_HOSTS = {"mp.weixin.qq.com"}


class WechatExportError(Exception):
    pass


@dataclass(frozen=True)
class WechatArticleLink:
    url: str
    title: str
    section: str | None = None


@dataclass(frozen=True)
class WechatExportResult:
    index_path: Path
    article_paths: list[Path]
    failed: list[tuple[str, str]]


class _WechatLinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.in_article = False
        self.done = False
        self.depth = 0
        self.current_href: str | None = None
        self.current_parts: list[str] = []
        self.current_heading_tag: str | None = None
        self.current_heading_parts: list[str] = []
        self.current_section: str | None = None
        self.links: list[WechatArticleLink] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        if self.done:
            return

        if not self.in_article:
            if tag == "div" and attrs_dict.get("id") == "js_content":
                self.in_article = True
                self.depth = 1
            return

        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}:
            self.depth += 1

        if tag == "a":
            href = attrs_dict.get("href") or attrs_dict.get("data-link")
            if href:
                self.current_href = urllib.parse.urljoin(self.base_url, href.replace("&amp;", "&"))
                self.current_parts = []
        elif tag == "img" and self.current_href:
            alt = attrs_dict.get("alt")
            if alt:
                self.current_parts.append(alt)
        elif tag in {"h1", "h2", "h3"}:
            self.current_heading_tag = tag
            self.current_heading_parts = []

    def handle_endtag(self, tag: str) -> None:
        if not self.in_article or self.done:
            return

        if tag == "a" and self.current_href:
            url = normalize_wechat_article_url(self.current_href)
            title = re.sub(r"\s+", " ", "".join(self.current_parts)).strip()
            if url:
                self.links.append(WechatArticleLink(url=url, title=title or "微信文章", section=self.current_section))
            self.current_href = None
            self.current_parts = []
        elif tag == self.current_heading_tag:
            heading = re.sub(r"\s+", " ", "".join(self.current_heading_parts)).strip()
            if heading:
                self.current_section = heading
            self.current_heading_tag = None
            self.current_heading_parts = []

        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}:
            self.depth -= 1
            if self.depth <= 0:
                self.done = True
                self.in_article = False

    def handle_data(self, data: str) -> None:
        if self.current_href:
            self.current_parts.append(data)
        if self.current_heading_tag:
            self.current_heading_parts.append(data)


def is_wechat_article_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    return parsed.netloc.lower() in WECHAT_HOSTS and (
        parsed.path.startswith("/s/")
        or parsed.path == "/s"
        or parsed.path.startswith("/mp/appmsg/show")
    )


def normalize_wechat_article_url(url: str) -> str | None:
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.netloc.lower() not in WECHAT_HOSTS:
        return None
    if not is_wechat_article_url(url):
        return None
    parsed = parsed._replace(fragment="")
    if parsed.path.startswith("/s/") or parsed.path == "/s":
        parsed = parsed._replace(query="")
    elif parsed.path.startswith("/mp/appmsg/show"):
        allowed = {"__biz", "mid", "idx", "sn"}
        query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        parsed = parsed._replace(query=urllib.parse.urlencode([(key, value) for key, value in query if key in allowed]))
    return urllib.parse.urlunparse(parsed)


def extract_wechat_article_links(document: str, base_url: str) -> list[WechatArticleLink]:
    parser = _WechatLinkParser(base_url)
    parser.feed(decode_wechat_document(document))

    links: list[WechatArticleLink] = []
    seen: set[str] = set()
    for link in parser.links:
        if link.url not in seen:
            links.append(link)
            seen.add(link.url)
    return links


def export_wechat_knowledge_base(
    url: str,
    output_dir: Path,
    *,
    max_links: int = 0,
    local_assets: bool = True,
    absolute_asset_paths: bool = False,
    html_preview: bool = False,
) -> WechatExportResult:
    seed_html = fetch_url_html(url)
    _raise_if_wechat_verify_page(seed_html, url)
    seed_title = html_title(seed_html)
    seed_metadata = metadata_from_html(seed_html)
    author_dir = output_dir / compact_filename(seed_metadata.author or "unknown-author", fallback="unknown-author")
    category_dir = author_dir / compact_filename(seed_title or "微信文章知识库", fallback="微信文章知识库")
    category_dir.mkdir(parents=True, exist_ok=True)
    seed_markdown = extract_article_markdown(seed_html, url)
    seed_path = write_article_output(
        seed_markdown,
        category_dir,
        source_url=url,
        title=compact_filename(seed_metadata.title or seed_title or "入口文章", fallback="入口文章"),
        author=seed_metadata.author,
        published_at=seed_metadata.published_at,
        local_assets=local_assets,
        absolute_asset_paths=absolute_asset_paths,
        html_preview=html_preview,
        group_by_author=False,
    )

    links = [link for link in extract_wechat_article_links(seed_html, url) if link.url != normalize_wechat_article_url(url)]
    discovered_count = len(links)
    if max_links > 0:
        links = links[:max_links]

    article_paths = [seed_path]
    local_links: dict[str, Path] = {}
    failed: list[tuple[str, str]] = []
    index_lines = [
        f"# 微信文章知识库 - {seed_title or '合集'}",
        "",
        f"- 来源: {url}",
        f"- 导出时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 发现子文章: {discovered_count}",
        f"- 计划导出子文章: {len(links)}",
        "",
        "## 文章",
        "",
        f"- [[{_wiki_link_target(seed_path, category_dir)}|{seed_path.stem}]]",
    ]

    current_section: str | None = None
    for link in links:
        section_name = compact_filename(link.section or "未分类", fallback="未分类")
        section_dir = category_dir / section_name
        if link.section != current_section:
            current_section = link.section
            index_lines.extend(["", f"## {link.section or '未分类'}", ""])
        try:
            article_html = fetch_url_html(link.url)
            _raise_if_wechat_verify_page(article_html, link.url)
            title = html_title(article_html) or link.title
            metadata = metadata_from_html(article_html)
            markdown = extract_article_markdown(article_html, link.url)
            path = write_article_output(
                markdown,
                section_dir,
                source_url=link.url,
                title=compact_filename(metadata.title or title, fallback=link.title),
                author=metadata.author or seed_metadata.author,
                published_at=metadata.published_at,
                local_assets=local_assets,
                absolute_asset_paths=absolute_asset_paths,
                html_preview=html_preview,
                fallback_filename=compact_filename(link.title, fallback="微信文章"),
                group_by_author=False,
            )
            article_paths.append(path)
            normalized_url = normalize_wechat_article_url(link.url)
            if normalized_url:
                local_links[normalized_url] = path
            index_lines.append(f"- [[{_wiki_link_target(path, category_dir)}|{path.stem}]]")
        except Exception as error:
            failed.append((link.url, str(error)))
            index_lines.append(f"- 未导出: [{link.title}]({link.url}) - {error}")

    _rewrite_wechat_links_to_local(seed_path, local_links)

    if failed:
        index_lines.extend(["", "## 失败", ""])
        for failed_url, reason in failed:
            index_lines.append(f"- {failed_url}: {reason}")

    index_path = category_dir / "微信文章知识库.md"
    atomic_write_text(index_path, "\n".join(index_lines).strip() + "\n")
    return WechatExportResult(index_path=index_path, article_paths=article_paths, failed=failed)


def export_wechat_article(
    url: str,
    output_dir: Path,
    *,
    local_assets: bool = True,
    absolute_asset_paths: bool = False,
    html_preview: bool = False,
) -> Path:
    document = fetch_url_html(url)
    _raise_if_wechat_verify_page(document, url)
    title = html_title(document)
    metadata = metadata_from_html(document)
    markdown = extract_article_markdown(document, url)
    return write_article_output(
        markdown,
        output_dir,
        source_url=url,
        title=compact_filename(metadata.title or title or "微信文章", fallback="微信文章"),
        author=compact_filename(metadata.author or "unknown-author", fallback="unknown-author"),
        published_at=metadata.published_at,
        local_assets=local_assets,
        absolute_asset_paths=absolute_asset_paths,
        html_preview=html_preview,
    )


def _raise_if_wechat_verify_page(document: str, url: str) -> None:
    if "环境异常" in document and "去验证" in document:
        raise WechatExportError(f"WeChat verification page returned for {url}. Open it in a browser/WeChat first or retry later.")


def _wiki_link_target(path: Path, base_dir: Path) -> str:
    return path.relative_to(base_dir).with_suffix("").as_posix()


def _rewrite_wechat_links_to_local(markdown_path: Path, local_links: dict[str, Path]) -> None:
    content = markdown_path.read_text(encoding="utf-8")

    def replace(match: re.Match[str]) -> str:
        label, url = match.groups()
        normalized = normalize_wechat_article_url(url)
        if not normalized:
            return match.group(0)
        target = local_links.get(normalized)
        if not target:
            return match.group(0)
        relative = target.relative_to(markdown_path.parent).as_posix()
        return f"[{label}]({relative})"

    content = re.sub(r"\[([^\]]+)\]\((https?://mp\.weixin\.qq\.com[^)]+)\)", replace, content)
    atomic_write_text(markdown_path, content)
