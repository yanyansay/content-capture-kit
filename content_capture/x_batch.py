from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from .archive import write_article_output
from .files import atomic_write_text
from .metrics import parse_count
from .metadata import ArticleMetadata, metadata_from_markdown, metadata_with_fallback
from .sessions import LoginError, configure_feedgrab_data_dir, require_feedgrab
from .twitter_cli_fallback import fetch_x_markdown_with_twitter_cli
from .x_utils import XArticleError
from .xtomd import fetch_x_markdown


class XBatchError(Exception):
    pass


@dataclass(frozen=True)
class XBatchResult:
    index_path: Path
    discovered: int
    matched: int
    saved: int
    failed: int
    unknown_metrics: int


def export_x_user(
    handle: str,
    output_dir: Path,
    *,
    min_views: str | None = None,
    original_only: bool = False,
    no_replies: bool = False,
    limit: int = 0,
    max_pages: int = 20,
    local_assets: bool = True,
    absolute_asset_paths: bool = False,
    html_preview: bool = False,
    include_unknown_metrics: bool = False,
) -> XBatchResult:
    min_view_count = parse_count(min_views) if min_views else None
    tweets = discover_x_user_tweets(handle, max_pages=max_pages)
    filtered, unknown_metrics = _filter_tweets(
        tweets,
        min_views=min_view_count,
        original_only=original_only,
        no_replies=no_replies,
        include_unknown_metrics=include_unknown_metrics,
    )
    if limit > 0:
        filtered = filtered[:limit]

    screen_name = _normalize_handle(handle)
    batch_dir = output_dir / screen_name
    batch_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = batch_dir / "manifest.json"
    atomic_write_text(
        manifest_path,
        json.dumps({"handle": screen_name, "filters": {
            "min_views": min_view_count,
            "original_only": original_only,
            "no_replies": no_replies,
            "limit": limit,
            "max_pages": max_pages,
            "include_unknown_metrics": include_unknown_metrics,
        }, "discovered": tweets, "matched": filtered}, ensure_ascii=False, indent=2),
    )

    saved_paths: list[Path] = []
    failures: list[dict[str, str]] = []
    for tweet in filtered:
        tweet_id = tweet.get("id") or tweet.get("rest_id") or ""
        author = tweet.get("author") or screen_name
        tweet_url = f"https://x.com/{author}/status/{tweet_id}"
        try:
            markdown = _hydrate_tweet_markdown(tweet, tweet_url)
            metadata = metadata_with_fallback(
                metadata_from_markdown(markdown),
                ArticleMetadata(
                    title=(tweet.get("article") or {}).get("title") or tweet.get("text", "")[:80],
                    author=author,
                    published_at=tweet.get("created_at", ""),
                ),
            )
            saved_paths.append(
                write_article_output(
                    markdown,
                    batch_dir,
                    source_url=tweet_url,
                    title=metadata.title,
                    author=metadata.author,
                    published_at=metadata.published_at,
                    local_assets=local_assets,
                    absolute_asset_paths=absolute_asset_paths,
                    html_preview=html_preview,
                    fallback_filename=tweet_id or "tweet",
                    group_by_author=False,
                    image_dir=batch_dir / "image",
                    video_dir=batch_dir / "video",
                )
            )
        except Exception as error:
            failures.append({"url": tweet_url, "error": str(error)})

    index_path = _write_index(
        batch_dir,
        screen_name=screen_name,
        discovered=len(tweets),
        matched=len(filtered),
        saved_paths=saved_paths,
        failures=failures,
        unknown_metrics=unknown_metrics,
        manifest_path=manifest_path,
    )
    return XBatchResult(
        index_path=index_path,
        discovered=len(tweets),
        matched=len(filtered),
        saved=len(saved_paths),
        failed=len(failures),
        unknown_metrics=unknown_metrics,
    )


def discover_x_user_tweets(handle: str, *, max_pages: int = 20) -> list[dict]:
    require_feedgrab()
    configure_feedgrab_data_dir()
    from feedgrab.fetchers.twitter_cookies import load_twitter_cookies
    from feedgrab.fetchers.twitter_graphql import (
        extract_tweet_data,
        fetch_user_by_screen_name,
        fetch_user_tweets_page,
        parse_user_tweets_entries,
    )

    cookies = load_twitter_cookies()
    if not cookies:
        raise LoginError("X login is required. Run: content-capture login x")

    screen_name = _normalize_handle(handle)
    user_info = fetch_user_by_screen_name(screen_name, cookies)
    user_id = user_info.get("user_id", "")
    if not user_id:
        raise XBatchError(f"Could not resolve X user: {handle}")

    tweets: list[dict] = []
    cursor = None
    seen: set[str] = set()
    for _ in range(max_pages):
        response = fetch_user_tweets_page(user_id, cookies, cursor=cursor)
        if not response:
            break
        entries, cursors = parse_user_tweets_entries(response)
        if not entries:
            break
        for entry in entries:
            data = extract_tweet_data(entry)
            if not data:
                continue
            tweet_id = data.get("id") or data.get("rest_id")
            if tweet_id and tweet_id not in seen:
                tweets.append(_jsonable(data))
                seen.add(tweet_id)
        cursor = cursors.get("bottom")
        if not cursor:
            break
    return tweets


def _filter_tweets(
    tweets: list[dict],
    *,
    min_views: int | None,
    original_only: bool,
    no_replies: bool,
    include_unknown_metrics: bool,
) -> tuple[list[dict], int]:
    filtered: list[dict] = []
    unknown_metrics = 0
    for tweet in tweets:
        if original_only and _is_retweet(tweet):
            continue
        if no_replies and tweet.get("in_reply_to_user_id"):
            continue
        views = parse_count(tweet.get("views"))
        if min_views is not None:
            if views is None:
                unknown_metrics += 1
                if not include_unknown_metrics:
                    continue
            elif views < min_views:
                continue
        filtered.append(tweet)
    return filtered, unknown_metrics


def _hydrate_tweet_markdown(tweet: dict, tweet_url: str) -> str:
    try:
        return fetch_x_markdown_with_twitter_cli(tweet_url)
    except XArticleError:
        pass
    try:
        return fetch_x_markdown(tweet_url)
    except XArticleError:
        text = tweet.get("text", "").strip()
        title = (tweet.get("article") or {}).get("title") or text[:80] or tweet.get("id", "X 内容")
        lines = [f"# {title}", "", text]
        views = parse_count(tweet.get("views"))
        if views is not None:
            lines.extend(["", f"- Views: {views}"])
        return "\n".join(lines).strip() + "\n"


def _write_index(
    batch_dir: Path,
    *,
    screen_name: str,
    discovered: int,
    matched: int,
    saved_paths: list[Path],
    failures: list[dict[str, str]],
    unknown_metrics: int,
    manifest_path: Path,
) -> Path:
    lines = [
        f"# X 博主内容 - @{screen_name}",
        "",
        f"- 导出时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 发现内容: {discovered}",
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
            lines.append(f"- {failure['url']}: {failure['error']}")
    index_path = batch_dir / "index.md"
    atomic_write_text(index_path, "\n".join(lines).strip() + "\n")
    return index_path


def _normalize_handle(handle: str) -> str:
    value = handle.strip()
    if value.startswith("@"):
        return value[1:]
    if "://" in value:
        return value.rstrip("/").split("/")[-1]
    return value


def _is_retweet(tweet: dict) -> bool:
    raw = tweet.get("_raw_result") or {}
    legacy = raw.get("legacy") if isinstance(raw, dict) else {}
    return bool(isinstance(legacy, dict) and legacy.get("retweeted_status_result"))


def _jsonable(value):
    try:
        json.dumps(value)
        return value
    except TypeError:
        return json.loads(json.dumps(value, default=str))
