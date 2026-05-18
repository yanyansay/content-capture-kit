from __future__ import annotations

import re


def parse_count(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)

    text = str(value).strip().lower().replace(",", "")
    if not text or text in {"-", "none", "null"}:
        return None
    text = text.replace("views", "").replace("view", "").strip()

    multiplier = 1
    if text.endswith("万") or text.endswith("w"):
        multiplier = 10_000
        text = text[:-1]
    elif text.endswith("k"):
        multiplier = 1_000
        text = text[:-1]
    elif text.endswith("m"):
        multiplier = 1_000_000
        text = text[:-1]

    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return None
    return int(float(match.group(0)) * multiplier)
