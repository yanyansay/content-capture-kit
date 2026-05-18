from __future__ import annotations

import shutil
import subprocess

from .x_utils import XArticleError, extract_tweet_id


def fetch_x_markdown_with_twitter_cli(url_or_id: str, timeout: float = 90.0) -> str:
    executable = shutil.which("twitter")
    if not executable:
        raise XArticleError("twitter-cli is not installed.")

    tweet_id = extract_tweet_id(url_or_id)
    try:
        completed = subprocess.run(
            [executable, "article", tweet_id, "--markdown"],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise XArticleError("twitter-cli timed out while fetching the X article.") from error
    except OSError as error:
        raise XArticleError(f"twitter-cli could not run: {error}") from error

    markdown = completed.stdout.strip()
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise XArticleError(f"twitter-cli failed with exit code {completed.returncode}: {detail}")
    if not markdown:
        raise XArticleError("twitter-cli returned empty Markdown.")
    return markdown
