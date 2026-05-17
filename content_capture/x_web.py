from __future__ import annotations

import datetime as dt
import http.client
import json
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .archive import write_article_output
from .files import atomic_write_text
from .longform import LongformPost, longform_from_tweet
from .naming import safe_filename
from .x_utils import XArticleError


X_WEB_BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOjxbCyk6G5G6k6z8s%3D"
    "K2RGmifP8FHK6p4B5nM1bNiR2M7RAB8vJv7Qf4A0YH3HjD6k"
)
X_WEB_HOME = "https://x.com"
X_GRAPHQL_BASE = "https://x.com/i/api/graphql"


@dataclass(frozen=True)
class XUserFilters:
    min_views: int | None = None
    min_likes: int | None = None
    min_retweets: int | None = None
    since: dt.date | None = None
    until: dt.date | None = None
    limit: int = 0


@dataclass(frozen=True)
class XUserExportResult:
    index_path: Path
    article_paths: list[Path]


@dataclass(frozen=True)
class XWebSession:
    bearer_token: str
    guest_token: str | None
    cookie_header: str | None
    csrf_token: str | None
    user_by_screen_name_query_id: str
    user_articles_tweets_query_id: str
    user_by_screen_name_features: dict[str, bool]
    user_by_screen_name_field_toggles: dict[str, bool]
    user_articles_tweets_features: dict[str, bool]
    user_articles_tweets_field_toggles: dict[str, bool]


@dataclass(frozen=True)
class TimelinePage:
    posts: list[LongformPost]
    cursor: str | None


def normalize_handle(value: str) -> str:
    text = value.strip()
    if not text:
        raise XArticleError("X user is required.")
    parsed = urllib.parse.urlparse(text)
    if parsed.netloc.lower() in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
        parts = [part for part in parsed.path.split("/") if part]
        if not parts:
            raise XArticleError(f"Could not parse X handle from {value!r}.")
        text = parts[0]
    text = text.lstrip("@").strip()
    if not re.fullmatch(r"[A-Za-z0-9_]{1,15}", text):
        raise XArticleError(f"Invalid X handle: {value!r}.")
    return text


def parse_count_value(value: str) -> int:
    text = value.strip().lower().replace(",", "").replace("_", "")
    if not text:
        raise XArticleError("Count value cannot be empty.")
    multipliers = {"k": 1_000, "w": 10_000, "万": 10_000, "m": 1_000_000}
    suffix = text[-1]
    multiplier = multipliers.get(suffix, 1)
    number_text = text[:-1] if suffix in multipliers else text
    try:
        number = float(number_text)
    except ValueError as error:
        raise XArticleError(f"Invalid count value: {value!r}.") from error
    if number < 0:
        raise XArticleError(f"Count value must be non-negative: {value!r}.")
    return int(number * multiplier)


def parse_date_value(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as error:
        raise XArticleError(f"Invalid date {value!r}; expected YYYY-MM-DD.") from error


def export_x_user_articles(
    user: str,
    output_dir: Path,
    filters: XUserFilters,
    max_pages: int = 20,
    article_markdown_fetcher: Callable[[str], str] | None = None,
    cookie_header: str | None = None,
) -> XUserExportResult:
    if max_pages < 1:
        raise XArticleError("--max-pages must be at least 1.")
    if filters.limit < 0:
        raise XArticleError("--limit must be at least 0.")

    handle = normalize_handle(user)
    client = XWebClient()
    session = client.create_session(handle, cookie_header=cookie_header)
    user_result = client.fetch_user_by_screen_name(session, handle)
    user_id, author = _parse_user_result(user_result, fallback_username=handle)

    seen_ids: set[str] = set()
    article_list: list[LongformPost] = []
    cursor: str | None = None
    for _ in range(max_pages):
        page = parse_timeline_page(client.fetch_user_articles_tweets(session, user_id, cursor), fallback_author=author)
        for post in page.posts:
            if post.tweet_id in seen_ids:
                continue
            seen_ids.add(post.tweet_id)
            article_list.append(post)
        if not page.cursor:
            break
        cursor = page.cursor

    selected = [post for post in article_list if post_matches_filters(post, filters)]
    if filters.limit:
        selected = selected[: filters.limit]
    return _write_user_export(
        article_list,
        selected,
        output_dir,
        fallback_author=author,
        article_markdown_fetcher=article_markdown_fetcher,
    )


def parse_timeline_page(payload: dict[str, Any], fallback_author: dict[str, Any] | None = None) -> TimelinePage:
    posts: list[LongformPost] = []
    cursor: str | None = None
    for entry in _timeline_entries(payload):
        entry_id = str(entry.get("entryId") or entry.get("entry_id") or "")
        content = entry.get("content") if isinstance(entry.get("content"), dict) else {}
        if entry_id.startswith("cursor-bottom") or content.get("cursorType") == "Bottom":
            value = content.get("value")
            if isinstance(value, str) and value:
                cursor = value
            continue
        result = _entry_tweet_result(entry)
        if not result:
            continue
        tweet, author = tweet_from_result(result, fallback_author=fallback_author)
        post = longform_from_tweet(tweet, author=author, fallback_username=(fallback_author or {}).get("username"))
        if post:
            posts.append(post)
    return TimelinePage(posts=posts, cursor=cursor)


def tweet_from_result(result: dict[str, Any], fallback_author: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    result = _unwrap_tweet_result(result)
    legacy = result.get("legacy") if isinstance(result.get("legacy"), dict) else {}
    tweet_id = str(result.get("rest_id") or legacy.get("id_str") or legacy.get("id") or "").strip()
    tweet: dict[str, Any] = {
        "id": tweet_id,
        "created_at": legacy.get("created_at") or result.get("created_at"),
        "text": legacy.get("full_text") or legacy.get("text") or result.get("text"),
        "views": result.get("views") or legacy.get("views"),
        "favorite_count": legacy.get("favorite_count"),
        "retweet_count": legacy.get("retweet_count"),
        "reply_count": legacy.get("reply_count"),
        "quote_count": legacy.get("quote_count"),
        "bookmark_count": legacy.get("bookmark_count"),
    }

    note_text = _first_nested_string(result, ("note_tweet",), ("text", "full_text"))
    if note_text:
        tweet["note_tweet"] = {"text": note_text}

    article = _extract_article_payload(result)
    if article:
        tweet["article"] = article

    author = _author_from_tweet_result(result) or fallback_author
    return tweet, author


def post_matches_filters(post: LongformPost, filters: XUserFilters) -> bool:
    if filters.min_views is not None and _metric_int(post.metrics.get("impression_count")) < filters.min_views:
        return False
    if filters.min_likes is not None and _metric_int(post.metrics.get("like_count")) < filters.min_likes:
        return False
    if filters.min_retweets is not None and _metric_int(post.metrics.get("retweet_count")) < filters.min_retweets:
        return False
    published = _post_date(post)
    if filters.since and (not published or published < filters.since):
        return False
    if filters.until and (not published or published > filters.until):
        return False
    return True


def discover_graphql_query_ids(document: str, bundles: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for source in [document, *bundles]:
        for operation in ("UserByScreenName", "UserArticlesTweets"):
            query_id = _find_operation_query_id(source, operation)
            if query_id:
                found[operation] = query_id
    return found


def discover_graphql_operation_options(document: str, bundles: list[str]) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for source in [document, *bundles]:
        for operation in ("UserByScreenName", "UserArticlesTweets"):
            if operation in found:
                continue
            options = _find_operation_options(source, operation)
            if options:
                found[operation] = options
    return found


def discover_web_bearer_token(document: str, bundles: list[str]) -> str | None:
    for source in [document, *bundles]:
        match = re.search(r"Bearer\s+([A-Za-z0-9%_-]{80,})", source)
        if match:
            return match.group(1)
        match = re.search(r'authorization["\']?\s*:\s*["\']Bearer\s+([A-Za-z0-9%_-]{80,})', source, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


class XWebClient:
    def create_session(self, handle: str, cookie_header: str | None = None) -> XWebSession:
        last_error: XArticleError | None = None
        for attempt in range(3):
            try:
                return self._create_session_once(handle, cookie_header=cookie_header)
            except XArticleError as error:
                last_error = error
                retryable = "Could not discover X web GraphQL operation" in str(error)
                if not retryable or attempt == 2:
                    raise
                time.sleep(0.5 * (attempt + 1))
        assert last_error is not None
        raise last_error

    def _create_session_once(self, handle: str, cookie_header: str | None = None) -> XWebSession:
        html = self._fetch_text(f"{X_WEB_HOME}/{handle}/articles", cookie_header=cookie_header)
        script_urls = _script_urls_from_html(html)
        bundles = []
        for url in script_urls[:30]:
            try:
                bundles.append(self._fetch_text(url, cookie_header=cookie_header))
            except XArticleError:
                continue
        ids = discover_graphql_query_ids(html, bundles)
        options = discover_graphql_operation_options(html, bundles)
        missing = [name for name in ("UserByScreenName", "UserArticlesTweets") if name not in ids]
        if missing:
            raise XArticleError(f"Could not discover X web GraphQL operation: {', '.join(missing)}.")
        bearer_token = discover_web_bearer_token(html, bundles) or X_WEB_BEARER_TOKEN
        guest_token = _guest_token_from_cookie(cookie_header) or _guest_token_from_html(html)
        if not guest_token and not cookie_header:
            guest_token = self._activate_guest(bearer_token)
        elif guest_token and not cookie_header:
            try:
                guest_token = self._activate_guest(bearer_token)
            except XArticleError:
                pass
        return XWebSession(
            bearer_token=bearer_token,
            guest_token=guest_token,
            cookie_header=cookie_header,
            csrf_token=_cookie_value(cookie_header, "ct0"),
            user_by_screen_name_query_id=ids["UserByScreenName"],
            user_articles_tweets_query_id=ids["UserArticlesTweets"],
            user_by_screen_name_features=options.get("UserByScreenName", {}).get("features") or _default_graphql_features(),
            user_by_screen_name_field_toggles=options.get("UserByScreenName", {}).get("field_toggles") or {},
            user_articles_tweets_features=options.get("UserArticlesTweets", {}).get("features") or _default_graphql_features(),
            user_articles_tweets_field_toggles=options.get("UserArticlesTweets", {}).get("field_toggles") or {},
        )

    def fetch_user_by_screen_name(self, session: XWebSession, handle: str) -> dict[str, Any]:
        variables = {"screen_name": handle, "withSafetyModeUserFields": True}
        return self._fetch_graphql(
            session,
            session.user_by_screen_name_query_id,
            "UserByScreenName",
            variables,
            session.user_by_screen_name_features,
            session.user_by_screen_name_field_toggles,
        )

    def fetch_user_articles_tweets(self, session: XWebSession, user_id: str, cursor: str | None = None) -> dict[str, Any]:
        variables: dict[str, Any] = {
            "userId": user_id,
            "count": 20,
            "includePromotedContent": False,
            "withQuickPromoteEligibilityTweetFields": False,
            "withVoice": False,
            "withV2Timeline": True,
        }
        if cursor:
            variables["cursor"] = cursor
        return self._fetch_graphql(
            session,
            session.user_articles_tweets_query_id,
            "UserArticlesTweets",
            variables,
            session.user_articles_tweets_features,
            session.user_articles_tweets_field_toggles,
        )

    def _fetch_graphql(
        self,
        session: XWebSession,
        query_id: str,
        operation: str,
        variables: dict[str, Any],
        features: dict[str, Any],
        field_toggles: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query_params = {
            "variables": json.dumps(variables, separators=(",", ":")),
            "features": json.dumps(features, separators=(",", ":")),
        }
        if field_toggles:
            query_params["fieldToggles"] = json.dumps(field_toggles, separators=(",", ":"))
        params = urllib.parse.urlencode(query_params)
        url = f"{X_GRAPHQL_BASE}/{query_id}/{operation}?{params}"
        try:
            for attempt in range(3):
                text = self._fetch_text(
                    url,
                    bearer_token=session.bearer_token,
                    guest_token=session.guest_token,
                    cookie_header=session.cookie_header,
                    csrf_token=session.csrf_token,
                )
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    if attempt == 2:
                        raise
                    time.sleep(0.5 * (attempt + 1))
        except json.JSONDecodeError as error:
            raise XArticleError(f"X web returned invalid JSON for {operation}.") from error

    def _activate_guest(self, bearer_token: str) -> str:
        request = urllib.request.Request(
            "https://api.x.com/1.1/guest/activate.json",
            method="POST",
            headers=_request_headers(bearer_token=bearer_token),
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8", errors="replace"))
        except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as error:
            raise XArticleError(f"Could not activate X web guest token: {error}") from error
        token = data.get("guest_token")
        if not isinstance(token, str) or not token:
            raise XArticleError("X web guest activation returned no guest token.")
        return token

    def _fetch_text(
        self,
        url: str,
        bearer_token: str = X_WEB_BEARER_TOKEN,
        guest_token: str | None = None,
        cookie_header: str | None = None,
        csrf_token: str | None = None,
    ) -> str:
        last_error: XArticleError | None = None
        for attempt in range(3):
            try:
                return self._fetch_text_once(
                    url,
                    bearer_token=bearer_token,
                    guest_token=guest_token,
                    cookie_header=cookie_header,
                    csrf_token=csrf_token,
                )
            except XArticleError as error:
                last_error = error
                message = str(error)
                retryable = (
                    "Tunnel connection failed" in message
                    or "closed the connection" in message
                    or "response ended before" in message
                    or "handshake operation timed out" in message
                )
                if not retryable or attempt == 2:
                    if retryable:
                        return self._fetch_text_curl(
                            url,
                            bearer_token=bearer_token,
                            guest_token=guest_token,
                            cookie_header=cookie_header,
                            csrf_token=csrf_token,
                        )
                    raise
                time.sleep(0.5 * (attempt + 1))
        assert last_error is not None
        raise last_error

    def _fetch_text_once(
        self,
        url: str,
        bearer_token: str = X_WEB_BEARER_TOKEN,
        guest_token: str | None = None,
        cookie_header: str | None = None,
        csrf_token: str | None = None,
    ) -> str:
        request = urllib.request.Request(
            url,
            headers=_request_headers(
                bearer_token=bearer_token,
                guest_token=guest_token,
                cookie_header=cookie_header,
                csrf_token=csrf_token,
            ),
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status = getattr(response, "status", 200)
                if status in {401, 403, 429}:
                    raise XArticleError(f"X web returned HTTP {status}; login, verification, or rate limiting may be required.")
                try:
                    data = response.read()
                except http.client.IncompleteRead as error:
                    if not error.partial:
                        raise XArticleError("X web response ended before any data was read.") from error
                    raise XArticleError("X web response ended before the full body was read.") from error
                return data.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            if error.code in {401, 403, 429}:
                raise XArticleError(f"X web returned HTTP {error.code}; login, verification, or rate limiting may be required.") from error
            detail = error.read().decode("utf-8", errors="replace")[:300]
            raise XArticleError(f"X web request failed with HTTP {error.code}: {detail}") from error
        except urllib.error.URLError as error:
            raise XArticleError(f"X web request failed: {error}") from error
        except http.client.RemoteDisconnected as error:
            raise XArticleError("X web closed the connection; verification or rate limiting may be required.") from error

    def _fetch_text_curl(
        self,
        url: str,
        bearer_token: str = X_WEB_BEARER_TOKEN,
        guest_token: str | None = None,
        cookie_header: str | None = None,
        csrf_token: str | None = None,
    ) -> str:
        headers = _request_headers(
            bearer_token=bearer_token,
            guest_token=guest_token,
            cookie_header=cookie_header,
            csrf_token=csrf_token,
        )
        command = ["curl", "-L", "-sS", "--max-time", "30", "-w", "\n%{http_code}", url]
        for key, value in headers.items():
            command.extend(["-H", f"{key}: {value}"])
        completed = None
        for attempt in range(3):
            try:
                completed = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=35,
                )
            except (OSError, subprocess.SubprocessError) as error:
                if attempt == 2:
                    raise XArticleError(f"X web request failed after urllib fallback: {error}") from error
                time.sleep(0.5 * (attempt + 1))
                continue
            if completed.returncode == 0:
                break
            if attempt == 2:
                detail = (completed.stderr or completed.stdout).strip()[:300]
                raise XArticleError(f"X web request failed after urllib fallback: {detail}")
            time.sleep(0.5 * (attempt + 1))
        assert completed is not None
        body, separator, status_text = completed.stdout.rpartition("\n")
        if not separator:
            raise XArticleError("X web request failed after urllib fallback: missing HTTP status.")
        try:
            status = int(status_text)
        except ValueError as error:
            raise XArticleError(f"X web request failed after urllib fallback: invalid HTTP status {status_text!r}.") from error
        if status in {401, 403, 429}:
            raise XArticleError(f"X web returned HTTP {status}; login, verification, or rate limiting may be required.")
        if status >= 400:
            raise XArticleError(f"X web request failed with HTTP {status}: {body[:300]}")
        return body


def _write_user_export(
    article_list: list[LongformPost],
    selected_posts: list[LongformPost],
    output_dir: Path,
    *,
    fallback_author: dict[str, Any] | None = None,
    article_markdown_fetcher: Callable[[str], str] | None,
) -> XUserExportResult:
    fallback_name = (fallback_author or {}).get("username") or (fallback_author or {}).get("name") or "unknown-author"
    author_source = selected_posts[0] if selected_posts else article_list[0] if article_list else None
    author = (author_source.author_username or author_source.author_name) if author_source else fallback_name
    author_dir = output_dir / safe_filename(author or "unknown-author", fallback="unknown-author")
    static_dir = author_dir / "static"
    article_paths: list[Path] = []
    for post in selected_posts:
        markdown = _markdown_for_post(post, article_markdown_fetcher)
        path = write_article_output(
            markdown,
            static_dir,
            source_url=post.url,
            title=post.title,
            author=post.author_username or post.author_name,
            published_at=post.created_at,
            local_assets=False,
            fallback_filename=post.tweet_id,
            group_by_author=False,
        )
        article_paths.append(path)
    index_path = author_dir / "index.md"
    atomic_write_text(index_path, _render_index(selected_posts, article_paths, author=author))
    return XUserExportResult(index_path=index_path, article_paths=article_paths)


def _markdown_for_post(post: LongformPost, article_markdown_fetcher: Callable[[str], str] | None) -> str:
    text = post.text.strip()
    if article_markdown_fetcher:
        try:
            fetched = article_markdown_fetcher(post.url).strip()
            if fetched:
                return fetched
        except (OSError, ValueError, XArticleError):
            pass
    title = post.title or f"X Longform {post.tweet_id}"
    return f"# {title}\n\n{text}\n"


def _render_index(posts: list[LongformPost], paths: list[Path], *, author: str) -> str:
    title_author = author or "unknown-author"
    lines = [
        f"# X 用户命中文章索引 - {title_author}",
        "",
        "| 标题 | 发布时间 | 浏览量 | 点赞 | 转发 | 回复 |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for post, path in zip(posts, paths):
        title = (post.title or f"X Longform {post.tweet_id}").replace("|", "\\|")
        local_href = _markdown_link_target(path.relative_to(path.parent.parent).as_posix())
        views = _metric_int(post.metrics.get("impression_count"))
        lines.append(
            "| "
            f"[{title}]({local_href}) | "
            f"{_format_post_datetime(post.created_at)} | "
            f"[{_format_count(views)}]({post.url}) | "
            f"{_metric_int(post.metrics.get('like_count')) or ''} | "
            f"{_metric_int(post.metrics.get('retweet_count')) or ''} | "
            f"{_metric_int(post.metrics.get('reply_count')) or ''} | "
        )
    return "\n".join(lines) + "\n"


def _markdown_link_target(value: str) -> str:
    return f"<{value.replace('>', '%3E')}>"


def _parse_user_result(payload: dict[str, Any], fallback_username: str) -> tuple[str, dict[str, Any]]:
    result = payload.get("data", {}).get("user", {}).get("result") if isinstance(payload.get("data"), dict) else None
    if not isinstance(result, dict):
        raise XArticleError(f"Could not find X user @{fallback_username}.")
    user_id = str(result.get("rest_id") or "").strip()
    legacy = result.get("legacy") if isinstance(result.get("legacy"), dict) else {}
    if not user_id:
        raise XArticleError(f"X user @{fallback_username} has no web user id.")
    return user_id, {"username": legacy.get("screen_name") or fallback_username, "name": legacy.get("name")}


def _timeline_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for node in _walk(payload):
        if not isinstance(node, dict):
            continue
        value = node.get("entries")
        if isinstance(value, list):
            entries.extend(item for item in value if isinstance(item, dict))
        value = node.get("entry")
        if isinstance(value, dict):
            entries.append(value)
    return entries


def _entry_tweet_result(entry: dict[str, Any]) -> dict[str, Any] | None:
    for node in _walk(entry):
        if not isinstance(node, dict):
            continue
        result = node.get("tweet_results")
        if isinstance(result, dict) and isinstance(result.get("result"), dict):
            return result["result"]
    return None


def _unwrap_tweet_result(result: dict[str, Any]) -> dict[str, Any]:
    if isinstance(result.get("tweet"), dict):
        return _unwrap_tweet_result(result["tweet"])
    if isinstance(result.get("tweet_result"), dict):
        return _unwrap_tweet_result(result["tweet_result"])
    return result


def _extract_article_payload(result: dict[str, Any]) -> dict[str, Any] | None:
    for node in _walk(result):
        if not isinstance(node, dict):
            continue
        article = node.get("article")
        if isinstance(article, dict):
            article = _unwrap_article(article)
            title = _first_value(article, ("title", "name", "headline"))
            text = (
                _first_value(article, ("text", "body", "content", "markdown", "plain_text", "description"))
                or _article_content_state_markdown(article)
            )
            if title or text:
                payload: dict[str, Any] = {}
                if title:
                    payload["title"] = title
                if text:
                    media = _media_markdown(article)
                    payload["text"] = "\n\n".join(part for part in (text, media) if part).strip()
                return payload
    return None


def _article_content_state_markdown(article: dict[str, Any]) -> str | None:
    content_state = article.get("content_state")
    if not isinstance(content_state, dict):
        return None
    blocks = content_state.get("blocks")
    if not isinstance(blocks, list):
        return None
    parts: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        text = block.get("text")
        if isinstance(text, str) and text.strip():
            parts.append(text.strip())
    return "\n\n".join(parts).strip() or None


def _media_markdown(value: Any) -> str:
    image_urls: list[str] = []
    video_urls: list[str] = []
    seen: set[str] = set()
    for node in _walk(value):
        if not isinstance(node, dict):
            continue
        for key in ("media_url_https", "media_url"):
            url = node.get(key)
            if isinstance(url, str):
                _append_media_url(url, image_urls, video_urls, seen)
        variants = node.get("variants")
        if isinstance(variants, list):
            best_video = _best_video_variant(variants)
            if best_video:
                _append_media_url(best_video, image_urls, video_urls, seen)
        for key in ("url", "expanded_url"):
            url = node.get(key)
            if isinstance(url, str) and _looks_like_x_media(url):
                _append_media_url(url, image_urls, video_urls, seen)
    lines = [f"![image]({url})" for url in image_urls]
    lines.extend(f'<video src="{url}" controls></video>' for url in video_urls)
    return "\n\n".join(lines)


def _append_media_url(url: str, image_urls: list[str], video_urls: list[str], seen: set[str]) -> None:
    clean = url.strip()
    if not clean or clean in seen:
        return
    parsed = urllib.parse.urlparse(clean)
    host = parsed.netloc.lower()
    if not host.endswith(("twimg.com", "x.com", "twitter.com")):
        return
    seen.add(clean)
    if "video.twimg.com" in host or Path(parsed.path).suffix.lower() in {".mp4", ".mov", ".m4v"}:
        video_urls.append(clean)
    else:
        image_urls.append(clean)


def _best_video_variant(variants: list[Any]) -> str | None:
    candidates: list[tuple[int, str]] = []
    for variant in variants:
        if not isinstance(variant, dict):
            continue
        url = variant.get("url")
        if not isinstance(url, str) or not url:
            continue
        content_type = str(variant.get("content_type") or "")
        if "mp4" not in content_type and ".mp4" not in urllib.parse.urlparse(url).path:
            continue
        bitrate = variant.get("bitrate")
        candidates.append((bitrate if isinstance(bitrate, int) else 0, url))
    if not candidates:
        return None
    return sorted(candidates, reverse=True)[0][1]


def _looks_like_x_media(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    return "pbs.twimg.com" in host or "video.twimg.com" in host


def _unwrap_article(article: dict[str, Any]) -> dict[str, Any]:
    for key in ("article_results", "note_tweet_results", "tweet_results", "result"):
        value = article.get(key)
        if isinstance(value, dict):
            return _unwrap_article(value)
    return article


def _author_from_tweet_result(result: dict[str, Any]) -> dict[str, Any] | None:
    for node in _walk(result):
        if not isinstance(node, dict):
            continue
        user_results = node.get("user_results")
        if not isinstance(user_results, dict):
            continue
        user = user_results.get("result")
        if not isinstance(user, dict):
            continue
        legacy = user.get("legacy") if isinstance(user.get("legacy"), dict) else {}
        username = legacy.get("screen_name")
        name = legacy.get("name")
        if username or name:
            return {"username": username, "name": name}
    return None


def _first_nested_string(root: dict[str, Any], key_path: tuple[str, ...], fields: tuple[str, ...]) -> str | None:
    for node in _walk(root):
        if not isinstance(node, dict):
            continue
        value: Any = node
        for key in key_path:
            value = value.get(key) if isinstance(value, dict) else None
        if isinstance(value, dict):
            result = _unwrap_article(value)
            text = _first_value(result, fields)
            if text:
                return text
    return None


def _first_value(value: dict[str, Any], fields: tuple[str, ...]) -> str | None:
    for field in fields:
        candidate = value.get(field)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _walk(value: Any) -> list[Any]:
    found = [value]
    if isinstance(value, dict):
        for nested in value.values():
            found.extend(_walk(nested))
    elif isinstance(value, list):
        for item in value:
            found.extend(_walk(item))
    return found


def _metric_int(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.replace(",", ""))
        except ValueError:
            return 0
    return 0


def _format_count(value: int) -> str:
    if value <= 0:
        return ""
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}".rstrip("0").rstrip(".") + "m"
    if value >= 1_000:
        return f"{value / 1_000:.1f}".rstrip("0").rstrip(".") + "k"
    return str(value)


def _format_post_datetime(value: str | None) -> str:
    parsed = _post_datetime(value)
    if parsed:
        return parsed.strftime("%Y-%m-%d %H:%M")
    return value or ""


def _post_date(post: LongformPost) -> dt.date | None:
    parsed = _post_datetime(post.created_at)
    if parsed:
        return parsed.date()
    return None


def _post_datetime(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    text = value.strip()
    for fmt in ("%a %b %d %H:%M:%S %z %Y", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(text.replace("Z", "+0000"), fmt)
        except ValueError:
            continue
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if match:
        return dt.datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return None


def _find_operation_query_id(source: str, operation: str) -> str | None:
    quoted_operation = re.escape(operation)
    patterns = [
        rf"\{{\s*(?:queryId|['\"]queryId['\"])\s*:\s*['\"]([A-Za-z0-9_-]{{10,}})['\"]\s*,\s*(?:operationName|['\"]operationName['\"])\s*:\s*['\"]{quoted_operation}['\"]",
        rf"\{{\s*(?:operationName|['\"]operationName['\"])\s*:\s*['\"]{quoted_operation}['\"]\s*,\s*(?:queryId|['\"]queryId['\"])\s*:\s*['\"]([A-Za-z0-9_-]{{10,}})['\"]",
        rf"/i/api/graphql/([A-Za-z0-9_-]+)/{re.escape(operation)}",
        rf"(?:queryId|['\"]queryId['\"])\s*:\s*['\"]([A-Za-z0-9_-]{{10,}})['\"].{{0,4000}}(?:operationName|['\"]operationName['\"])\s*:\s*['\"]{quoted_operation}['\"]",
        rf"(?:operationName|['\"]operationName['\"])\s*:\s*['\"]{quoted_operation}['\"].{{0,4000}}(?:queryId|['\"]queryId['\"])\s*:\s*['\"]([A-Za-z0-9_-]{{10,}})['\"]",
        rf"(?:queryId|['\"]queryId['\"])\s*:\s*['\"]([A-Za-z0-9_-]{{10,}})['\"].{{0,4000}}(?:operation|['\"]operation['\"])\s*:\s*['\"]{quoted_operation}['\"]",
        rf"(?:operation|['\"]operation['\"])\s*:\s*['\"]{quoted_operation}['\"].{{0,4000}}(?:queryId|['\"]queryId['\"])\s*:\s*['\"]([A-Za-z0-9_-]{{10,}})['\"]",
    ]
    for pattern in patterns:
        match = re.search(pattern, source, flags=re.DOTALL)
        if match:
            return match.group(1)
    return None


def _find_operation_options(source: str, operation: str) -> dict[str, Any] | None:
    query_id = _find_operation_query_id(source, operation)
    if not query_id:
        return None
    quoted_operation = re.escape(operation)
    patterns = [
        rf"(?:queryId|['\"]queryId['\"])\s*:\s*['\"]{re.escape(query_id)}['\"].{{0,12000}}?(?:operationName|['\"]operationName['\"])\s*:\s*['\"]{quoted_operation}['\"].{{0,12000}}?metadata\s*:\s*\{{(?P<meta>.*?)\}}\s*\}}",
        rf"(?:operationName|['\"]operationName['\"])\s*:\s*['\"]{quoted_operation}['\"].{{0,12000}}?(?:queryId|['\"]queryId['\"])\s*:\s*['\"]{re.escape(query_id)}['\"].{{0,12000}}?metadata\s*:\s*\{{(?P<meta>.*?)\}}\s*\}}",
    ]
    meta = ""
    for pattern in patterns:
        match = re.search(pattern, source, flags=re.DOTALL)
        if match:
            meta = match.group("meta")
            break
    return {
        "query_id": query_id,
        "features": {name: True for name in _metadata_string_list(meta, "featureSwitches")},
        "field_toggles": {name: True for name in _metadata_string_list(meta, "fieldToggles")},
    }


def _metadata_string_list(metadata_source: str, key: str) -> list[str]:
    if not metadata_source:
        return []
    match = re.search(rf"(?:{re.escape(key)}|['\"]{re.escape(key)}['\"])\s*:\s*\[(.*?)\]", metadata_source, flags=re.DOTALL)
    if not match:
        return []
    return re.findall(r'["\']([^"\']+)["\']', match.group(1))


def _script_urls_from_html(html: str) -> list[str]:
    urls = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    urls.extend(re.findall(r'<link[^>]+as=["\']script["\'][^>]+href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE))
    seen: set[str] = set()
    script_urls: list[str] = []
    for url in urls:
        absolute_url = urllib.parse.urljoin(X_WEB_HOME, url)
        if absolute_url in seen:
            continue
        seen.add(absolute_url)
        if "/client-web/" in absolute_url or absolute_url.endswith(".js"):
            script_urls.append(absolute_url)
    return script_urls


def _guest_token_from_html(html: str) -> str | None:
    match = re.search(r'(?:document\.cookie=["\']|Set-Cookie:\s*)gt=([0-9]+)', html)
    if match:
        return match.group(1)
    match = re.search(r'\bgt=([0-9]{8,})', html)
    if match:
        return match.group(1)
    return None


def _guest_token_from_cookie(cookie_header: str | None) -> str | None:
    return _cookie_value(cookie_header, "gt")


def _cookie_value(cookie_header: str | None, name: str) -> str | None:
    if not cookie_header:
        return None
    for part in cookie_header.split(";"):
        key, separator, value = part.strip().partition("=")
        if separator and key == name and value:
            return value
    return None


def _request_headers(
    bearer_token: str = X_WEB_BEARER_TOKEN,
    guest_token: str | None = None,
    cookie_header: str | None = None,
    csrf_token: str | None = None,
) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "User-Agent": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
        "Accept": "*/*",
        "Accept-Encoding": "identity",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://x.com/",
        "X-Twitter-Active-User": "yes",
        "X-Twitter-Client-Language": "en",
    }
    if guest_token:
        headers["X-Guest-Token"] = guest_token
    if cookie_header:
        headers["Cookie"] = cookie_header
    elif guest_token:
        headers["Cookie"] = f"gt={guest_token}"
    if csrf_token:
        headers["X-CSRF-Token"] = csrf_token
    return headers


def _default_graphql_features() -> dict[str, Any]:
    return {
        "responsive_web_graphql_exclude_directive_enabled": True,
        "verified_phone_label_enabled": False,
        "creator_subscriptions_tweet_preview_api_enabled": True,
        "responsive_web_graphql_timeline_navigation_enabled": True,
        "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
        "tweetypie_unmention_optimization_enabled": True,
        "responsive_web_edit_tweet_api_enabled": True,
        "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
        "view_counts_everywhere_api_enabled": True,
        "longform_notetweets_consumption_enabled": True,
        "responsive_web_twitter_article_tweet_consumption_enabled": True,
        "tweet_awards_web_tipping_enabled": False,
        "freedom_of_speech_not_reach_fetch_enabled": True,
        "standardized_nudges_misinfo": True,
        "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
        "longform_notetweets_rich_text_read_enabled": True,
        "longform_notetweets_inline_media_enabled": True,
        "responsive_web_media_download_video_enabled": False,
        "responsive_web_enhance_cards_enabled": False,
    }
