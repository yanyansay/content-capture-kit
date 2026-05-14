from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from .longform import LongformPost, UserLongformResult, longform_from_tweet


X_API_BASE = "https://api.x.com/2"
X_API_FALLBACK_BASES = ("https://api.twitter.com/2",)
TWEET_FIELDS = ",".join(
    [
        "article",
        "note_tweet",
        "created_at",
        "entities",
        "public_metrics",
        "referenced_tweets",
        "lang",
        "author_id",
    ]
)
USER_FIELDS = "id,name,username"


class XApiError(RuntimeError):
    pass


def is_x_url(value: str) -> bool:
    parsed = urllib.parse.urlparse(value)
    host = parsed.netloc.lower()
    return host in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}


def extract_tweet_id(value: str) -> str:
    stripped = value.strip()
    if re.fullmatch(r"\d{5,}", stripped):
        return stripped

    parsed = urllib.parse.urlparse(stripped)
    match = re.search(r"/status(?:es)?/(\d+)", parsed.path)
    if match:
        return match.group(1)
    raise ValueError(f"Could not parse tweet id from {value!r}.")


def normalize_user_input(value: str) -> str:
    stripped = value.strip()
    parsed = urllib.parse.urlparse(stripped)
    if parsed.netloc:
        parts = [part for part in parsed.path.split("/") if part]
        if parts:
            stripped = parts[0]
    return stripped.lstrip("@").strip()


def _decode_error_body(error: urllib.error.HTTPError) -> str:
    try:
        body = error.read().decode("utf-8", errors="replace")
    except Exception:
        return ""
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body[:500]
    return json.dumps(payload, ensure_ascii=False)


@dataclass
class XApiClient:
    bearer_token: str
    base_url: str = X_API_BASE
    fallback_base_urls: tuple[str, ...] = X_API_FALLBACK_BASES
    timeout: float = 30.0
    max_retries: int = 4
    sleep: Callable[[float], None] = time.sleep
    now: Callable[[], float] = time.time

    def request_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        last_error: XApiError | None = None
        for base_url in (self.base_url, *self.fallback_base_urls):
            try:
                return self._request_json_from_base(base_url, path, params)
            except XApiError as error:
                last_error = error
                if not _should_try_fallback(error):
                    raise
        assert last_error is not None
        raise last_error

    def _request_json_from_base(self, base_url: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = urllib.parse.urlencode({key: value for key, value in (params or {}).items() if value is not None})
        url = f"{base_url}{path}"
        if query:
            url = f"{url}?{query}"

        attempt = 0
        while True:
            request = urllib.request.Request(
                url,
                headers={
                    "Authorization": f"Bearer {self.bearer_token}",
                    "Accept": "application/json",
                    "User-Agent": "twitter-crawling/0.1",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                retryable = error.code == 429 or 500 <= error.code <= 599
                if not retryable or attempt >= self.max_retries:
                    detail = _decode_error_body(error)
                    raise XApiError(f"X API request failed with HTTP {error.code}: {detail}") from error
                self.sleep(self._retry_delay(error, attempt))
            except (TimeoutError, urllib.error.URLError) as error:
                if attempt >= self.max_retries:
                    raise XApiError(f"X API request failed after retries: {error}") from error
                self.sleep(min(2**attempt, 60))
            attempt += 1

    def _retry_delay(self, error: urllib.error.HTTPError, attempt: int) -> float:
        reset_header = error.headers.get("x-rate-limit-reset") if error.headers else None
        if error.code == 429 and reset_header:
            try:
                reset_at = float(reset_header)
            except ValueError:
                reset_at = 0
            delay = reset_at - self.now() + 1
            if delay > 0:
                return delay
        return min(2**attempt, 60)

    def fetch_user_by_username(self, username: str) -> dict[str, Any]:
        payload = self.request_json(f"/users/by/username/{urllib.parse.quote(username)}", {"user.fields": USER_FIELDS})
        user = payload.get("data")
        if not isinstance(user, dict) or not user.get("id"):
            raise XApiError(f"Could not resolve X user {username!r}.")
        return user

    def fetch_post(self, tweet_id: str) -> LongformPost:
        payload = self.request_json(
            f"/tweets/{urllib.parse.quote(tweet_id)}",
            {
                "tweet.fields": TWEET_FIELDS,
                "user.fields": USER_FIELDS,
                "expansions": "author_id",
            },
        )
        tweet = payload.get("data")
        if not isinstance(tweet, dict):
            raise XApiError(f"Post {tweet_id} was not returned by X API.")
        users = _users_by_id(payload)
        post = longform_from_tweet(tweet, users.get(str(tweet.get("author_id"))))
        if not post:
            raise XApiError(f"Post {tweet_id} is not an article or note_tweet longform post.")
        return post

    def fetch_user_longform_posts(
        self,
        user_input: str,
        count: int,
        include_replies: bool = False,
        max_pages: int = 50,
    ) -> UserLongformResult:
        normalized = normalize_user_input(user_input)
        if not normalized:
            raise XApiError("User input cannot be empty.")
        if count < 1:
            raise XApiError("count must be at least 1.")
        if max_pages < 1:
            raise XApiError("max_pages must be at least 1.")

        if re.fullmatch(r"\d+", normalized):
            user = {"id": normalized, "username": normalized, "name": None}
        else:
            user = self.fetch_user_by_username(normalized)

        posts: list[LongformPost] = []
        scanned_count = 0
        skipped_short_count = 0
        pagination_token: str | None = None
        pages_scanned = 0

        for _ in range(max_pages):
            pages_scanned += 1
            params: dict[str, Any] = {
                "max_results": 100,
                "tweet.fields": TWEET_FIELDS,
                "user.fields": USER_FIELDS,
                "expansions": "author_id",
                "pagination_token": pagination_token,
                "exclude": "retweets" if include_replies else "retweets,replies",
            }
            payload = self.request_json(f"/users/{urllib.parse.quote(str(user['id']))}/tweets", params)
            users = _users_by_id(payload)
            tweets = payload.get("data") or []
            if not isinstance(tweets, list):
                tweets = []

            for tweet in tweets:
                if not isinstance(tweet, dict):
                    continue
                scanned_count += 1
                author = users.get(str(tweet.get("author_id"))) or user
                post = longform_from_tweet(tweet, author, fallback_username=str(user.get("username") or normalized))
                if post:
                    posts.append(post)
                    if len(posts) >= count:
                        return UserLongformResult(
                            user_input=user_input,
                            user_id=str(user["id"]),
                            username=str(user.get("username") or normalized),
                            display_name=user.get("name"),
                            requested_count=count,
                            posts=posts,
                            scanned_count=scanned_count,
                            skipped_short_count=skipped_short_count,
                            pages_scanned=pages_scanned,
                            complete=True,
                        )
                else:
                    skipped_short_count += 1

            meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
            pagination_token = meta.get("next_token")
            if not pagination_token:
                break

        return UserLongformResult(
            user_input=user_input,
            user_id=str(user["id"]),
            username=str(user.get("username") or normalized),
            display_name=user.get("name"),
            requested_count=count,
            posts=posts,
            scanned_count=scanned_count,
            skipped_short_count=skipped_short_count,
            pages_scanned=pages_scanned,
            complete=len(posts) >= count,
        )


def _users_by_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    includes = payload.get("includes")
    if not isinstance(includes, dict):
        return {}
    users = includes.get("users")
    if not isinstance(users, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for user in users:
        if isinstance(user, dict) and user.get("id"):
            result[str(user["id"])] = user
    return result


def _should_try_fallback(error: XApiError) -> bool:
    message = str(error).lower()
    fallback_markers = (
        "remote end closed connection without response",
        "nodename nor servname provided",
        "temporary failure in name resolution",
        "connection reset",
        "connection aborted",
    )
    return any(marker in message for marker in fallback_markers)
