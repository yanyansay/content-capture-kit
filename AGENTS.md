# AGENTS.md

This file gives Codex agents the current development context for `content-capture-kit`.

## Project Goal

`content-capture-kit` is a multi-platform content acquisition CLI for building an Obsidian-friendly knowledge base.

The product direction is not a one-off scraper. It should become a durable command line tool for getting articles and media resources from multiple platforms into local Markdown plus local assets.

Use "获取" in Chinese docs and user-facing wording. Avoid "抓取" and "爬取" in public documentation unless the user explicitly asks for those words.

## Current Repository

- Root: `/Users/renlimin/code/content-capture-kit`
- Python package: `content_capture`
- CLI command: `content-capture`
- GitHub repo: `https://github.com/yanyansay/content-capture-kit`
- Default branch: `main`
- Current Homebrew formula: `Formula/content-capture-kit.rb`
- Chinese README is default: `README.md`
- English README: `README.en.md`

## Supported Platforms

Keep this table aligned with both READMEs when platform support changes.

| Platform | Status | Command | Notes |
| --- | --- | --- | --- |
| X/Twitter | Done | `content-capture x article`, `content-capture x user` | Single article plus login-required user batch export with filters. |
| WeChat Official Account | Done | `content-capture wechat`, `content-capture wechat account` | Supports single articles, collection-style knowledge bases, and login-required account batch export. WeChat videos are intentionally not downloaded. |
| Normal web pages | Done | `content-capture web` | Uses built-in HTML extraction and Defuddle fallback. |
| Xiaohongshu | Not done | none | Planned for image/video resources. |
| Douyin | Not done | none | Planned for video resources. |
| Bilibili | Not done | none | Planned for video, article, or collection resources. |
| WeChat Channels | Not done | none | Planned for public video resources. |
| YouTube | Not done | none | Planned for videos, subtitles, and descriptions. |

## Non-Negotiable Product Boundaries

- X/Twitter supports single article retrieval and login-required user batch export with filters.
- Do not add a top-level `user` command, X official API token requirements, or a new official X API client path.
- WeChat video download is intentionally out of scope for now. Keep WeChat output focused on text, images, and article structure.
- Generated Markdown is meant for Obsidian. Prefer relative asset links by default.
- Filenames and paths should be stable and cleaned for Obsidian usage.
- Do not commit generated outputs such as `out/`, preview HTML, caches, or downloaded media.

## CLI Shape

Current public commands:

```bash
content-capture x article <x-url-or-id> --out out
content-capture x user <handle> --min-views 10w --original-only --out out
content-capture wechat <mp.weixin-url> --out out
content-capture wechat account <account-name> --min-reads 10w --out out
content-capture web <url> --out out
content-capture login x
content-capture login wechat
```

Compatibility aliases currently exist:

```bash
content-capture article <x-url-or-id>
content-capture url <url>
```

Prefer documenting the platform-specific commands, not the aliases.

## Code Map

- `content_capture/cli.py`: argparse command tree and command dispatch.
- `content_capture/archive.py`: final article Markdown writing and source metadata handling.
- `content_capture/assets.py`: downloads images/videos and rewrites Markdown asset links.
- `content_capture/defuddle.py`: normal URL fetching, HTML extraction, and Defuddle fallback.
- `content_capture/html_markdown.py`: HTML to Markdown conversion, including WeChat-specific behavior.
- `content_capture/wechat.py`: WeChat single/collection export and local link rewriting.
- `content_capture/wechat_account.py`: WeChat account batch discovery, filtering, and output index writing.
- `content_capture/x_batch.py`: X user batch discovery, filtering, hydration, and output index writing.
- `content_capture/sessions.py`: login/session helpers shared with feedgrab.
- `content_capture/metrics.py`: human count parsing for filters such as `10w` and `100k`.
- `content_capture/xtomd.py`: X single article conversion through the public conversion path.
- `content_capture/x_utils.py`: X URL detection and tweet id parsing only.
- `content_capture/naming.py`: title and path cleanup.
- `content_capture/preview.py`: optional HTML preview generation.
- `content_capture/files.py`: atomic file writes.
- `tests/test_content_capture.py`: unit and integration-style tests with mocks.

## Documentation Rules

- `README.md` is Chinese-first and should stay the default.
- `README.en.md` is the English equivalent.
- Keep the language switch links at the top of both README files.
- When adding a platform, update:
  - platform support table in both READMEs
  - quick-start table in both READMEs
  - current limits if the new platform has caveats
  - CLI examples
  - tests
- Use placeholder examples only. Do not include real test/development URLs, article titles, or personal data.
- Keep README examples practical for a new user. Prefer "which command should I run?" over implementation detail.

## Homebrew Release Flow

The repo includes an in-repo Homebrew formula:

```text
Formula/content-capture-kit.rb
```

When changing user-facing CLI behavior:

1. Bump `version` in `pyproject.toml`.
2. Commit the code/docs change.
3. Create an annotated tag matching the version, for example `v0.1.2`.
4. Update the formula `tag` and `revision` to the tagged commit.
5. Commit the formula update.
6. Push `main` and the tag.

If the sandbox blocks `git tag`, rerun the tag command with escalation.

## Verification

Run these before finalizing changes:

```bash
python3 -m py_compile content_capture/*.py tests/*.py
python3 -m unittest
ruby -c Formula/content-capture-kit.rb
python3 -m content_capture --help
python3 -m content_capture x --help
```

For README-only edits, at minimum run:

```bash
python3 -m py_compile content_capture/*.py tests/*.py
```

Search for forbidden or stale public wording after documentation changes:

```bash
rg -n "抓|爬|X API|X_BEARER_TOKEN|官方|content-capture user|--source|UserLongform|最近 N" README.md README.en.md content_capture tests
```

That search should return no matches unless the user explicitly changed direction.

## Known Risks

- X single article retrieval depends on `twitter-cli` first and the public conversion path in `xtomd.py` as fallback; availability can change.
- X user batch export depends on feedgrab's login session and X web GraphQL behavior. View counts can be absent in some responses.
- WeChat account batch export depends on feedgrab's MP backend session. Read counts may be absent; the tool should track unknown metrics clearly.
- WeChat can return verification or environment-error pages. The tool should fail clearly rather than writing bad Markdown.
- Normal web extraction can fail on heavily client-rendered pages. Defuddle is the fallback, but it must be installed locally.
- Local video preview in Markdown varies by renderer. The HTML preview exists because some Markdown previewers show raw `<video>` tags.

## Style

- Keep code conservative and standard-library-first unless a platform requires a proven external tool.
- Use atomic writes for final Markdown files.
- Keep generated asset names stable and ASCII-safe.
- Keep platform-specific behavior isolated in platform modules rather than adding special cases throughout the CLI.
- Prefer explicit errors over silent partial output.
