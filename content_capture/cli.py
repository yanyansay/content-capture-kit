from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .archive import write_article_output
from .defuddle import fetch_url_html, fetch_url_markdown, fetch_url_title
from .html_markdown import extract_article_markdown
from .metadata import ArticleMetadata, author_from_url, metadata_from_html, metadata_from_markdown, metadata_with_fallback
from .naming import html_title, markdown_title
from .sessions import LoginError, login_platform, session_dir
from .twitter_cli_fallback import fetch_x_markdown_with_twitter_cli
from .wechat import WechatExportError, export_wechat_article, export_wechat_knowledge_base
from .wechat_account import WechatAccountError, export_wechat_account
from .x_batch import XBatchError, export_x_user
from .x_utils import XArticleError, extract_tweet_id, is_x_url
from .xtomd import fetch_x_markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="content-capture",
        description="Get X, WeChat, and web articles as Markdown.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    x = subparsers.add_parser("x", help="Get X/Twitter articles.")
    x_subparsers = x.add_subparsers(dest="x_command", required=True)
    _add_article_parser(x_subparsers, aliases=False)
    _add_x_user_parser(x_subparsers)

    _add_wechat_parser(subparsers)
    _add_web_parser(subparsers)
    _add_login_parser(subparsers)

    _add_article_parser(subparsers, aliases=True)
    _add_url_parser(subparsers)

    return parser


def _add_article_parser(subparsers: argparse._SubParsersAction, *, aliases: bool) -> argparse.ArgumentParser:
    help_text = "Get one X article by URL or post id."
    if aliases:
        help_text += " Alias for: content-capture x article."
    article = subparsers.add_parser("article", help=help_text)
    article.add_argument("tweet", help="X status URL or numeric tweet id.")
    article.add_argument("--out", default="output", help="Output directory. Defaults to ./output.")
    article.add_argument(
        "--mirror-url",
        help="Get Markdown from a mirrored article URL but save it under the X tweet id filename.",
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
        "--html",
        "--html-preview",
        dest="html_preview",
        action="store_true",
        default=False,
        help="Generate a sibling HTML preview file that can play local video assets.",
    )
    return article


def _add_x_user_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    user = subparsers.add_parser("user", help="Get X posts from one user with filters. Requires login.")
    user.add_argument("handle", help="X handle, such as Khazix0918 or @Khazix0918.")
    user.add_argument("--out", default="output", help="Output directory. Defaults to ./output.")
    user.add_argument("--min-views", help="Minimum view count, such as 10w, 100k, or 100000.")
    user.add_argument("--original-only", action="store_true", help="Skip retweets.")
    user.add_argument("--no-replies", action="store_true", help="Skip replies.")
    user.add_argument("--limit", type=int, default=0, help="Maximum matched posts to save. 0 means no limit.")
    user.add_argument("--max-pages", type=int, default=20, help="Maximum X timeline pages to inspect. Defaults to 20.")
    user.add_argument(
        "--include-unknown-metrics",
        action="store_true",
        help="Keep posts whose view count is unavailable when metric filters are used.",
    )
    user.add_argument(
        "--local-assets",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Download remote images/videos next to the Markdown files and rewrite links to local paths.",
    )
    user.add_argument("--absolute-asset-paths", action="store_true", help="Use absolute filesystem paths for localized assets.")
    user.add_argument("--html", "--html-preview", dest="html_preview", action="store_true", default=False, help="Generate sibling HTML previews.")
    return user


def _add_web_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    web = subparsers.add_parser("web", help="Get a normal web URL with Defuddle fallback.")
    _add_url_arguments(web)
    return web


def _add_url_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    url = subparsers.add_parser("url", help="Get a URL. Alias for web URLs.")
    _add_url_arguments(url)
    return url


def _add_url_arguments(url: argparse.ArgumentParser) -> None:
    url.add_argument("url", help="URL to get.")
    url.add_argument("--out", default="output", help="Output directory. Defaults to ./output.")
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
        "--html",
        "--html-preview",
        dest="html_preview",
        action="store_true",
        default=False,
        help="Generate a sibling HTML preview file.",
    )


def _add_wechat_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    wechat = subparsers.add_parser("wechat", help="Get a WeChat article. Use --deep for collection-style knowledge bases.")
    wechat.add_argument("target", help="WeChat article URL, or 'account' for account batch export.")
    wechat.add_argument("account_name", nargs="?", help="WeChat Official Account name when target is 'account'.")
    wechat.add_argument("--out", default="output", help="Output directory. Defaults to ./output.")
    wechat.add_argument("--min-reads", help="Minimum read count for account mode, such as 10w, 100k, or 100000.")
    wechat.add_argument("--since", help="Only inspect account articles after this date, YYYY-MM-DD.")
    wechat.add_argument("--limit", type=int, default=0, help="Maximum matched account articles to save. 0 means no limit.")
    wechat.add_argument(
        "--include-unknown-metrics",
        action="store_true",
        help="Keep articles whose read count is unavailable when metric filters are used.",
    )
    wechat.add_argument(
        "--deep",
        "--knowledge-base",
        dest="deep",
        action="store_true",
        default=False,
        help="Export linked WeChat articles as a collection-style knowledge base.",
    )
    wechat.add_argument("--max-links", type=int, default=0, help="Maximum linked WeChat articles to export in --deep mode. 0 means no limit.")
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
        "--html",
        "--html-preview",
        dest="html_preview",
        action="store_true",
        default=False,
        help="Generate sibling HTML preview files.",
    )
    return wechat


def _add_login_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    login = subparsers.add_parser("login", help="Login to a platform and save browser session.")
    login.add_argument("platform", choices=["x", "twitter", "wechat"], help="Platform to login.")
    login.add_argument("--headless", action="store_true", help="Run login browser in headless mode when supported.")
    return login


def run(args: argparse.Namespace) -> Path:
    output_dir = Path(getattr(args, "out", "."))
    command = args.command
    if command == "x":
        command = args.x_command

    if command == "article":
        if args.mirror_url:
            tweet_id = extract_tweet_id(args.tweet)
            markdown = fetch_url_markdown(args.mirror_url)
            metadata = metadata_with_fallback(
                metadata_from_markdown(markdown),
                ArticleMetadata(title=fetch_url_title(args.mirror_url), author=author_from_url(args.tweet)),
            )
            title = metadata.title or markdown_title(markdown) or tweet_id
            return write_article_output(
                markdown,
                output_dir,
                source_url=args.tweet,
                title=title,
                author=metadata.author,
                published_at=metadata.published_at,
                mirror_url=args.mirror_url,
                local_assets=args.local_assets,
                absolute_asset_paths=args.absolute_asset_paths,
                html_preview=args.html_preview,
                fallback_filename=tweet_id,
            )
        source_url = args.tweet if not args.tweet.strip().isdigit() else f"https://x.com/i/status/{args.tweet.strip()}"
        markdown = _fetch_x_article_markdown(source_url)
        metadata = metadata_with_fallback(metadata_from_markdown(markdown), ArticleMetadata(author=author_from_url(source_url)))
        return write_article_output(
            markdown,
            output_dir,
            source_url=args.tweet,
            title=metadata.title,
            author=metadata.author,
            published_at=metadata.published_at,
            local_assets=args.local_assets,
            absolute_asset_paths=args.absolute_asset_paths,
            html_preview=args.html_preview,
            fallback_filename=extract_tweet_id(args.tweet),
        )

    if command == "user":
        if args.max_pages < 1:
            raise XBatchError("--max-pages must be at least 1.")
        if args.limit < 0:
            raise XBatchError("--limit must be at least 0.")
        result = export_x_user(
            args.handle,
            output_dir,
            min_views=args.min_views,
            original_only=args.original_only,
            no_replies=args.no_replies,
            limit=args.limit,
            max_pages=args.max_pages,
            include_unknown_metrics=args.include_unknown_metrics,
            local_assets=args.local_assets,
            absolute_asset_paths=args.absolute_asset_paths,
            html_preview=args.html_preview,
        )
        return result.index_path

    if command in {"url", "web"}:
        markdown, metadata = _fetch_web_markdown_and_metadata(args.url)
        return write_article_output(
            markdown,
            output_dir,
            source_url=args.url,
            title=metadata.title,
            author=metadata.author,
            published_at=metadata.published_at,
            local_assets=args.local_assets,
            absolute_asset_paths=args.absolute_asset_paths,
            html_preview=args.html_preview,
            fallback_filename=extract_tweet_id(args.url) if is_x_url(args.url) else "article",
        )

    if command == "wechat":
        if args.target == "account":
            if args.limit < 0:
                raise WechatAccountError("--limit must be at least 0.")
            if not args.account_name:
                raise WechatAccountError("wechat account requires an account name.")
            result = export_wechat_account(
                args.account_name,
                output_dir,
                min_reads=args.min_reads,
                since=args.since,
                limit=args.limit,
                include_unknown_metrics=args.include_unknown_metrics,
                local_assets=args.local_assets,
                absolute_asset_paths=args.absolute_asset_paths,
                html_preview=args.html_preview,
            )
            return result.index_path
        if args.max_links < 0:
            raise XArticleError("--max-links must be at least 0.")
        if args.max_links and not args.deep:
            raise XArticleError("--max-links requires --deep.")
        if not args.deep:
            return export_wechat_article(
                args.target,
                output_dir,
                local_assets=args.local_assets,
                absolute_asset_paths=args.absolute_asset_paths,
                html_preview=args.html_preview,
            )
        result = export_wechat_knowledge_base(
            args.target,
            output_dir,
            max_links=args.max_links,
            local_assets=args.local_assets,
            absolute_asset_paths=args.absolute_asset_paths,
            html_preview=args.html_preview,
        )
        return result.index_path

    if command == "login":
        login_platform(args.platform, headless=args.headless)
        return session_dir()

    raise XArticleError(f"Unsupported command: {command}")


def _fetch_web_markdown_and_metadata(url: str) -> tuple[str, ArticleMetadata]:
    try:
        document = fetch_url_html(url)
        markdown = extract_article_markdown(document, url)
        metadata = metadata_from_html(document)
        if not metadata.title:
            metadata = metadata_with_fallback(metadata, ArticleMetadata(title=html_title(document)))
        return markdown, metadata_with_fallback(metadata, ArticleMetadata(author=author_from_url(url)))
    except (OSError, ValueError):
        markdown = fetch_url_markdown(url)
        metadata = metadata_with_fallback(
            metadata_from_markdown(markdown),
            ArticleMetadata(title=fetch_url_title(url), author=author_from_url(url)),
        )
        return markdown, metadata


def _fetch_x_article_markdown(url: str) -> str:
    fallback_errors: list[str] = []
    try:
        return fetch_x_markdown_with_twitter_cli(url)
    except XArticleError as error:
        fallback_errors.append(str(error))
    try:
        return fetch_x_markdown(url)
    except XArticleError as error:
        raise XArticleError(f"{error}; twitter-cli failed first: {fallback_errors[0]}") from error


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        path = run(args)
    except (OSError, ValueError, XArticleError, WechatExportError, LoginError, XBatchError, WechatAccountError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(path)
    return 0
