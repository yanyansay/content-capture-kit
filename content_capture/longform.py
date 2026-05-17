from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LongformPost:
    tweet_id: str
    text: str
    source_kind: str
    url: str
    title: str | None = None
    created_at: str | None = None
    author_name: str | None = None
    author_username: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)


def _first_string(value: Any, keys: tuple[str, ...]) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in keys:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return ""


def _walk_dicts(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        found.append(value)
        for nested in value.values():
            found.extend(_walk_dicts(nested))
    elif isinstance(value, list):
        for item in value:
            found.extend(_walk_dicts(item))
    return found


def _extract_article(tweet: dict[str, Any]) -> tuple[str | None, str | None]:
    article = tweet.get("article")
    if not isinstance(article, dict):
        return None, None

    title = _first_string(article, ("title", "name", "headline"))
    body_keys = ("text", "body", "content", "markdown", "description")
    body = _first_string(article, body_keys)
    if body:
        return title or None, body

    parts: list[str] = []
    for node in _walk_dicts(article):
        text = _first_string(node, body_keys)
        if text and text not in parts:
            parts.append(text)
    return title or None, "\n\n".join(parts).strip() or None


def _extract_note_tweet(tweet: dict[str, Any]) -> str | None:
    note_tweet = tweet.get("note_tweet")
    if not isinstance(note_tweet, dict):
        return None

    text = _first_string(note_tweet, ("text", "full_text"))
    if text:
        return text

    for node in _walk_dicts(note_tweet):
        text = _first_string(node, ("text", "full_text"))
        if text:
            return text
    return None


def normalize_metrics(tweet: dict[str, Any]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    source = tweet.get("public_metrics")
    if isinstance(source, dict):
        metrics.update(source)

    aliases = {
        "favorite_count": "like_count",
        "favourites_count": "like_count",
        "retweet_count": "retweet_count",
        "reply_count": "reply_count",
        "quote_count": "quote_count",
        "bookmark_count": "bookmark_count",
        "view_count": "impression_count",
        "views": "impression_count",
        "impression_count": "impression_count",
    }
    for source_key, target_key in aliases.items():
        if source_key in tweet and target_key not in metrics and not isinstance(tweet[source_key], dict):
            metrics[target_key] = tweet[source_key]

    views = tweet.get("views")
    if isinstance(views, dict) and "impression_count" not in metrics:
        count = views.get("count") or views.get("view_count")
        if count is not None:
            metrics["impression_count"] = count
    return metrics


def longform_from_tweet(
    tweet: dict[str, Any],
    author: dict[str, Any] | None = None,
    fallback_username: str | None = None,
) -> LongformPost | None:
    tweet_id = str(tweet.get("id") or "").strip()
    if not tweet_id:
        return None

    title, article_text = _extract_article(tweet)
    if article_text:
        text = article_text
        source_kind = "article"
    else:
        note_text = _extract_note_tweet(tweet)
        if not note_text:
            return None
        text = note_text
        source_kind = "note_tweet"

    username = (
        str(author.get("username")).strip()
        if isinstance(author, dict) and author.get("username")
        else fallback_username
    )
    url_username = username or "i"
    return LongformPost(
        tweet_id=tweet_id,
        title=title,
        text=text,
        source_kind=source_kind,
        url=f"https://x.com/{url_username}/status/{tweet_id}",
        created_at=tweet.get("created_at"),
        author_name=author.get("name") if isinstance(author, dict) else None,
        author_username=username,
        metrics=normalize_metrics(tweet),
    )
