from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .archive import write_article_output
from .assets import localize_markdown_assets
from .defuddle import fetch_url_markdown, fetch_url_title
from .naming import markdown_title
from .preview import markdown_to_preview_html
from .render import render_longform_document, render_single_longform
from .wechat import WechatExportError, export_wechat_knowledge_base
from .x_api import XApiClient, XApiError, extract_tweet_id, is_x_url
from .xtomd import fetch_x_markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m x_crawler",
        description="Fetch X longform posts and web articles as Markdown.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    article = subparsers.add_parser("article", help="Fetch one X post by URL or post id.")
    article.add_argument("tweet", help="X status URL or numeric tweet id.")
    article.add_argument("--out", default="out", help="Output directory. Defaults to ./out.")
    article.add_argument(
        "--source",
        choices=("auto", "xtomd", "api"),
        default="auto",
        help="Fetch source. auto tries unpaid xtomd first, then X API when a token exists.",
    )
    article.add_argument(
        "--mirror-url",
        help="Fetch Markdown from a mirrored article URL but save it under the X tweet id filename.",
    )
    article.add_argument(
        "--local-assets",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Download remote images/videos next to the Markdown file and rewrite links to local paths.",
    )
    article.add_argument(
        "--absolute-asset-paths",
        action="store_true",
        help="Use absolute filesystem paths for localized assets. Useful for previewers that do not resolve relative links from the Markdown file.",
    )
    article.add_argument(
        "--html-preview",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Generate a sibling HTML preview file that can play local video assets.",
    )

    user = subparsers.add_parser("user", help="Fetch the latest N longform posts from a user.")
    user.add_argument("user", help="X handle, @handle, profile URL, or numeric user id.")
    user.add_argument("--count", type=int, default=10, help="Number of longform posts to collect.")
    user.add_argument("--out", default="out", help="Output directory. Defaults to ./out.")
    user.add_argument("--include-replies", action="store_true", help="Include replies in timeline scanning.")
    user.add_argument("--max-pages", type=int, default=50, help="Safety cap for timeline pages.")

    url = subparsers.add_parser("url", help="Fetch a normal web URL with Defuddle, or X URL via API.")
    url.add_argument("url", help="URL to fetch.")
    url.add_argument("--out", default="out", help="Output directory. Defaults to ./out.")
    url.add_argument(
        "--local-assets",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Download remote images/videos next to the Markdown file and rewrite links to local paths.",
    )
    url.add_argument(
        "--absolute-asset-paths",
        action="store_true",
        help="Use absolute filesystem paths for localized assets.",
    )
    url.add_argument(
        "--html-preview",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Generate a sibling HTML preview file.",
    )

    wechat = subparsers.add_parser("wechat", help="Export a WeChat article and linked WeChat articles as a knowledge base.")
    wechat.add_argument("url", help="WeChat article URL.")
    wechat.add_argument("--out", default="out/wechat-kb", help="Output directory. Defaults to ./out/wechat-kb.")
    wechat.add_argument("--max-links", type=int, default=0, help="Maximum linked WeChat articles to export. 0 means no limit.")
    wechat.add_argument(
        "--local-assets",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Download remote images next to the Markdown files and rewrite links to local paths.",
    )
    wechat.add_argument(
        "--absolute-asset-paths",
        action="store_true",
        help="Use absolute filesystem paths for localized assets.",
    )
    wechat.add_argument(
        "--html-preview",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Generate sibling HTML preview files.",
    )

    return parser


def _client_from_env() -> XApiClient:
    token = os.environ.get("X_BEARER_TOKEN", "").strip()
    if not token:
        raise XApiError("X_BEARER_TOKEN is required for X API commands.")
    return XApiClient(token)


def _ensure_count(value: int) -> None:
    if value < 1:
        raise XApiError("--count must be at least 1.")


def run(args: argparse.Namespace) -> Path:
    output_dir = Path(args.out)
    output_path: Path

    if args.command == "article":
        if args.mirror_url:
            tweet_id = extract_tweet_id(args.tweet)
            markdown = fetch_url_markdown(args.mirror_url)
            title = fetch_url_title(args.mirror_url) or markdown_title(markdown) or tweet_id
            return write_article_output(
                markdown,
                output_dir,
                source_url=args.tweet,
                title=title,
                mirror_url=args.mirror_url,
                local_assets=args.local_assets,
                absolute_asset_paths=args.absolute_asset_paths,
                html_preview=args.html_preview,
                fallback_filename=tweet_id,
            )
        if args.source in {"auto", "xtomd"}:
            try:
                markdown = fetch_x_markdown(args.tweet if not args.tweet.strip().isdigit() else f"https://x.com/i/status/{args.tweet.strip()}")
                return write_article_output(
                    markdown,
                    output_dir,
                    source_url=args.tweet,
                    local_assets=args.local_assets,
                    absolute_asset_paths=args.absolute_asset_paths,
                    html_preview=args.html_preview,
                    fallback_filename=extract_tweet_id(args.tweet),
                )
            except XApiError:
                if args.source == "xtomd" or not os.environ.get("X_BEARER_TOKEN", "").strip():
                    raise
        client = _client_from_env()
        tweet_id = extract_tweet_id(args.tweet)
        post = client.fetch_post(tweet_id)
        output_path = render_single_longform(post, output_dir)
        if args.local_assets:
            localize_markdown_assets(output_path, absolute_paths=args.absolute_asset_paths)
        if args.html_preview:
            markdown_to_preview_html(output_path)
        return output_path

    if args.command == "user":
        _ensure_count(args.count)
        client = _client_from_env()
        result = client.fetch_user_longform_posts(
            args.user,
            count=args.count,
            include_replies=args.include_replies,
            max_pages=args.max_pages,
        )
        return render_longform_document(result, output_dir)

    if args.command == "url":
        if is_x_url(args.url):
            try:
                markdown = fetch_x_markdown(args.url)
                return write_article_output(
                    markdown,
                    output_dir,
                    source_url=args.url,
                    local_assets=args.local_assets,
                    absolute_asset_paths=args.absolute_asset_paths,
                    html_preview=args.html_preview,
                    fallback_filename=extract_tweet_id(args.url),
                )
            except XApiError:
                if not os.environ.get("X_BEARER_TOKEN", "").strip():
                    raise
                client = _client_from_env()
                tweet_id = extract_tweet_id(args.url)
                post = client.fetch_post(tweet_id)
                output_path = render_single_longform(post, output_dir)
                if args.local_assets:
                    localize_markdown_assets(output_path, absolute_paths=args.absolute_asset_paths)
                if args.html_preview:
                    markdown_to_preview_html(output_path)
                return output_path
        markdown = fetch_url_markdown(args.url)
        title = fetch_url_title(args.url)
        return write_article_output(
            markdown,
            output_dir,
            source_url=args.url,
            title=title,
            local_assets=args.local_assets,
            absolute_asset_paths=args.absolute_asset_paths,
            html_preview=args.html_preview,
        )

    if args.command == "wechat":
        if args.max_links < 0:
            raise XApiError("--max-links must be at least 0.")
        result = export_wechat_knowledge_base(
            args.url,
            output_dir,
            max_links=args.max_links,
            local_assets=args.local_assets,
            absolute_asset_paths=args.absolute_asset_paths,
            html_preview=args.html_preview,
        )
        return result.index_path

    raise XApiError(f"Unsupported command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        path = run(args)
    except (OSError, ValueError, XApiError, WechatExportError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(path)
    return 0
