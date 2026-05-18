from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .files import atomic_write_text
from .metrics import parse_count
from .sessions import LoginError, configure_feedgrab_data_dir, require_feedgrab
from .wechat import export_wechat_article, normalize_wechat_article_url


class WechatAccountError(Exception):
    pass


@dataclass(frozen=True)
class WechatAccountResult:
    index_path: Path
    discovered: int
    matched: int
    saved: int
    failed: int
    unknown_metrics: int


def export_wechat_account(
    account_name: str,
    output_dir: Path,
    *,
    min_reads: str | None = None,
    since: str | None = None,
    limit: int = 0,
    include_unknown_metrics: bool = False,
    local_assets: bool = True,
    absolute_asset_paths: bool = False,
    html_preview: bool = False,
) -> WechatAccountResult:
    articles = asyncio.run(discover_wechat_account_articles(account_name, since=since or ""))
    min_read_count = parse_count(min_reads) if min_reads else None
    filtered, unknown_metrics = _filter_articles(
        articles,
        min_reads=min_read_count,
        include_unknown_metrics=include_unknown_metrics,
    )
    if limit > 0:
        filtered = filtered[:limit]

    batch_dir = output_dir / _compact(account_name)
    batch_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = batch_dir / "manifest.json"
    atomic_write_text(
        manifest_path,
        json.dumps({"account": account_name, "filters": {
            "min_reads": min_read_count,
            "since": since or "",
            "limit": limit,
            "include_unknown_metrics": include_unknown_metrics,
        }, "discovered": articles, "matched": filtered}, ensure_ascii=False, indent=2),
    )

    saved_paths: list[Path] = []
    failures: list[dict[str, str]] = []
    for article in filtered:
        link = article.get("link") or article.get("url") or ""
        if not link:
            failures.append({"url": "", "title": article.get("title", ""), "error": "missing article URL"})
            continue
        try:
            saved_paths.append(
                export_wechat_article(
                    link,
                    batch_dir,
                    local_assets=local_assets,
                    absolute_asset_paths=absolute_asset_paths,
                    html_preview=html_preview,
                )
            )
        except Exception as error:
            failures.append({"url": link, "title": article.get("title", ""), "error": str(error)})

    index_path = _write_index(
        batch_dir,
        account_name=account_name,
        discovered=len(articles),
        matched=len(filtered),
        saved_paths=saved_paths,
        failures=failures,
        unknown_metrics=unknown_metrics,
        manifest_path=manifest_path,
    )
    return WechatAccountResult(
        index_path=index_path,
        discovered=len(articles),
        matched=len(filtered),
        saved=len(saved_paths),
        failed=len(failures),
        unknown_metrics=unknown_metrics,
    )


async def discover_wechat_account_articles(account_name: str, *, since: str = "") -> list[dict]:
    require_feedgrab()
    configure_feedgrab_data_dir()
    from feedgrab.config import get_session_dir
    from feedgrab.fetchers.browser import get_async_playwright, get_stealth_context_options, setup_resource_blocking, stealth_launch
    from feedgrab.fetchers.mpweixin_account import _fetch_article_list, _find_account

    session_path = get_session_dir() / "wechat.json"
    if not session_path.exists():
        raise LoginError("WeChat login is required. Run: content-capture login wechat")

    since_ts = 0
    if since:
        try:
            since_ts = int(datetime.strptime(since, "%Y-%m-%d").timestamp())
        except ValueError as error:
            raise WechatAccountError("--since must use YYYY-MM-DD") from error

    discovered: list[dict] = []
    seen: set[str] = set()
    async_pw = get_async_playwright()
    async with async_pw() as p:
        browser = await stealth_launch(p, headless=True)
        ctx_opts = get_stealth_context_options()
        ctx_opts["storage_state"] = str(session_path)
        context = await browser.new_context(**ctx_opts)
        page = await context.new_page()
        await setup_resource_blocking(page)
        try:
            await page.goto("https://mp.weixin.qq.com/", wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(1000)
            if "token=" not in page.url:
                raise LoginError("WeChat session expired. Run: content-capture login wechat")

            account = await _find_account(page, account_name)
            if not account:
                raise WechatAccountError(f"WeChat account not found: {account_name}")
            fakeid = account.get("fakeid", "")
            begin = 0
            page_size = 5
            while True:
                page_articles, is_complete, _total = await _fetch_article_list(page, fakeid, begin=begin, size=page_size)
                if not page_articles:
                    break
                stop = False
                for article in page_articles:
                    create_time = int(article.get("create_time") or 0)
                    if since_ts and create_time and create_time < since_ts:
                        stop = True
                        break
                    link = normalize_wechat_article_url(article.get("link", "")) or article.get("link", "")
                    if link and link in seen:
                        continue
                    item = _jsonable(article)
                    item["link"] = link
                    item["account_name"] = account.get("nickname", account_name)
                    discovered.append(item)
                    if link:
                        seen.add(link)
                if is_complete or stop:
                    break
                begin += page_size
                await asyncio.sleep(0.5)
        finally:
            await context.close()
            await browser.close()
    return discovered


def _filter_articles(
    articles: list[dict],
    *,
    min_reads: int | None,
    include_unknown_metrics: bool,
) -> tuple[list[dict], int]:
    filtered: list[dict] = []
    unknown_metrics = 0
    for article in articles:
        reads = _article_reads(article)
        if min_reads is not None:
            if reads is None:
                unknown_metrics += 1
                if not include_unknown_metrics:
                    continue
            elif reads < min_reads:
                continue
        filtered.append(article)
    return filtered, unknown_metrics


def _article_reads(article: dict) -> int | None:
    for key in ("read_num", "read_count", "reads", "readNum", "read"):
        value = parse_count(article.get(key))
        if value is not None:
            return value
    return None


def _write_index(
    batch_dir: Path,
    *,
    account_name: str,
    discovered: int,
    matched: int,
    saved_paths: list[Path],
    failures: list[dict[str, str]],
    unknown_metrics: int,
    manifest_path: Path,
) -> Path:
    lines = [
        f"# 微信公众号账号内容 - {account_name}",
        "",
        f"- 导出时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 发现文章: {discovered}",
        f"- 命中筛选: {matched}",
        f"- 成功保存: {len(saved_paths)}",
        f"- 失败: {len(failures)}",
        f"- 指标未知: {unknown_metrics}",
        f"- Manifest: [{manifest_path.name}]({manifest_path.name})",
        "",
        "## 文章",
        "",
    ]
    for path in saved_paths:
        target = path.relative_to(batch_dir).with_suffix("").as_posix()
        lines.append(f"- [[{target}|{path.stem}]]")
    if failures:
        lines.extend(["", "## 失败", ""])
        for failure in failures:
            title = failure.get("title") or failure.get("url") or "unknown"
            lines.append(f"- {title}: {failure['error']}")
    index_path = batch_dir / "index.md"
    atomic_write_text(index_path, "\n".join(lines).strip() + "\n")
    return index_path


def _compact(value: str) -> str:
    return "".join(char for char in value if not char.isspace()) or "wechat-account"


def _jsonable(value):
    try:
        json.dumps(value)
        return value
    except TypeError:
        return json.loads(json.dumps(value, default=str))
