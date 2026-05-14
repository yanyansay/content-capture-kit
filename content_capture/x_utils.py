from __future__ import annotations

import re
import urllib.parse


class XArticleError(RuntimeError):
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
