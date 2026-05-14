from __future__ import annotations

import re
import html
import urllib.parse
from html.parser import HTMLParser


VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class ArticleMarkdownParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.in_article = False
        self.done = False
        self.depth = 0
        self.skip_depth = 0
        self.in_pre = False
        self.pre_parts: list[str] = []
        self.parts: list[str] = []
        self.heading_level: int | None = None
        self.link_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        if self.done:
            return

        if not self.in_article:
            classes = set(attrs_dict.get("class", "").split())
            if tag == "div" and ("markdown-body" in classes or attrs_dict.get("id") == "js_content"):
                self.in_article = True
                self.depth = 1
            return

        if tag not in VOID_TAGS:
            self.depth += 1

        if tag in {"script", "style", "svg"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return

        if re.fullmatch(r"h[1-6]", tag):
            self.heading_level = int(tag[1])
            self._break()
            self.parts.append("#" * self.heading_level + " ")
        elif tag == "p":
            self._break()
        elif tag == "br":
            self.parts.append("\n")
        elif tag == "hr":
            self._break()
            self.parts.append("---\n")
        elif tag == "li":
            self._break()
            self.parts.append("- ")
        elif tag == "blockquote":
            self._break()
            self.parts.append("> ")
        elif tag == "pre":
            self.in_pre = True
            self.pre_parts = []
        elif tag == "img":
            src = attrs_dict.get("src") or attrs_dict.get("data-src")
            if src:
                alt = attrs_dict.get("alt") or "image"
                self._break()
                self.parts.append(f"![{alt}]({self._absolute(src)})\n")
        elif tag == "video":
            src = attrs_dict.get("src")
            if src:
                self._break()
                self.parts.append(f'<video src="{self._absolute(src)}" controls></video>\n')
        elif tag == "a":
            href = attrs_dict.get("href") or attrs_dict.get("data-link")
            if href:
                self.link_stack.append(self._absolute(href))
                self.parts.append("[")
            else:
                self.link_stack.append("")
        elif tag == "code" and not self.in_pre:
            self.parts.append("`")

    def handle_endtag(self, tag: str) -> None:
        if not self.in_article or self.done:
            return
        if tag in {"script", "style", "svg"} and self.skip_depth:
            self.skip_depth -= 1
        elif not self.skip_depth:
            if tag == "pre" and self.in_pre:
                code = "".join(self.pre_parts).strip("\n")
                self._break()
                self.parts.append(f"```text\n{code}\n```\n")
                self.in_pre = False
                self.pre_parts = []
            elif re.fullmatch(r"h[1-6]", tag):
                self.parts.append("\n")
                self.heading_level = None
            elif tag in {"p", "li", "blockquote"}:
                self.parts.append("\n")
            elif tag == "code" and not self.in_pre:
                self.parts.append("`")
            elif tag == "a" and self.link_stack:
                href = self.link_stack.pop()
                if href:
                    self.parts.append(f"]({href})")

        if tag not in VOID_TAGS:
            self.depth -= 1
            if self.depth <= 0:
                self.done = True
                self.in_article = False

    def handle_data(self, data: str) -> None:
        if not self.in_article or self.done or self.skip_depth:
            return
        if self.in_pre:
            self.pre_parts.append(data)
            return
        text = re.sub(r"[ \t\r\n]+", " ", data)
        if text:
            self.parts.append(text)

    def markdown(self) -> str:
        content = "".join(self.parts)
        content = re.sub(r"[ \t]+\n", "\n", content)
        content = re.sub(r"\n{3,}", "\n\n", content)
        return content.strip() + "\n"

    def _absolute(self, url: str) -> str:
        return urllib.parse.urljoin(self.base_url, url.replace("&amp;", "&"))

    def _break(self) -> None:
        if not self.parts:
            return
        current = "".join(self.parts)
        if current.endswith("\n\n"):
            return
        if current.endswith("\n"):
            self.parts.append("\n")
        else:
            self.parts.append("\n\n")


def extract_article_markdown(html: str, base_url: str) -> str:
    document = decode_wechat_document(html)
    parser = ArticleMarkdownParser(base_url)
    parser.feed(document)
    markdown = parser.markdown()
    if not markdown.strip():
        raise ValueError("Could not find an article body in HTML.")
    return markdown


def decode_wechat_document(document: str) -> str:
    decoded = re.sub(r"\\x([0-9a-fA-F]{2})", lambda match: chr(int(match.group(1), 16)), document)
    return html.unescape(decoded)
