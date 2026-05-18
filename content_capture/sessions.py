from __future__ import annotations

import os
from pathlib import Path


class LoginError(Exception):
    pass


def content_capture_home() -> Path:
    raw = os.environ.get("CONTENT_CAPTURE_HOME")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".content-capture-kit"


def session_dir() -> Path:
    return content_capture_home() / "sessions"


def configure_feedgrab_data_dir() -> Path:
    path = session_dir()
    path.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("FEEDGRAB_DATA_DIR", str(path))
    return path


def require_feedgrab() -> None:
    configure_feedgrab_data_dir()
    try:
        import feedgrab  # noqa: F401
    except ImportError as error:
        raise LoginError(
            'feedgrab is required for login and batch discovery. Install this package with its runtime dependencies, or run: pip install "feedgrab[browser,twitter,wechat]"'
        ) from error


def login_platform(platform: str, *, headless: bool = False) -> None:
    require_feedgrab()
    canonical = {"x": "twitter", "twitter": "twitter", "wechat": "wechat"}.get(platform, platform)
    if canonical not in {"twitter", "wechat"}:
        raise LoginError(f"Unsupported login platform: {platform}")
    from feedgrab.login import login

    login(canonical, headless=headless)
