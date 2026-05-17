# Article Knowledge Base Capture Tool

[中文](README.md) | English

`content-capture-kit` exports X/Twitter longform posts, WeChat Official Account articles, and normal web articles into Markdown files suitable for an Obsidian knowledge base.

The goal is not just page backup. The goal is to create readable, linkable, and maintainable local notes.

## Features

- Get a single X longform post as Markdown.
- Get X user longform posts by filters such as views, likes, retweets, and publish date.
- Export normal web pages with Defuddle fallback.
- Export a single WeChat Official Account article.
- Export a WeChat collection article and organize linked articles by the section headings in the entry article.
- Download images into a local `image/` directory for single-article and normal web exports.
- Skip WeChat videos by default.
- Download X single-article videos into a local `video/` directory when possible; X user longform exports keep remote media links.
- Clean filenames and paths for Obsidian usage.

## Platform Status

| Platform | Status | Current Support | Command | Notes |
| --- | --- | --- | --- | --- |
| X/Twitter | Done | Single longform article retrieval, filtered user longform retrieval; single articles support local images and best-effort local videos | `content-capture x article` / `content-capture x user` | User filtering depends on X web endpoints, keeps remote media links, and may need tool updates when X changes them. |
| WeChat Official Account | Done | Single articles, collection articles, child article grouping, local images | `content-capture wechat` | WeChat videos are not downloaded. Verification pages require retrying later. |
| Normal web pages | Done | Article Markdown extraction, local images, Defuddle fallback | `content-capture web` | Best for static article pages. Dynamic pages depend on page structure. |
| Xiaohongshu | Not done | Not supported yet | None | Planned for image/video resource retrieval. |
| Douyin | Not done | Not supported yet | None | Planned for video resource retrieval. |
| Bilibili | Not done | Not supported yet | None | Planned for video, article, or collection retrieval. |
| WeChat Channels | Not done | Not supported yet | None | Planned for public video resource retrieval. |
| YouTube | Not done | Not supported yet | None | Planned for videos, subtitles, and descriptions. |

## Installation

### npx

For one-off use without a global install:

```bash
npx content-capture-kit --help
npx content-capture-kit x article https://x.com/example_author/status/1234567890123456789 --out output
npx content-capture-kit x user @example_author --min-views 1w --out output
```

You can also install it globally with npm. The global install provides the `content-capture` command:

```bash
npm install -g content-capture-kit
content-capture --help
```

Environment requirements: Node.js 18 or newer, plus Python 3.11 or newer on your machine. The npm package includes the Python source and runs it through your local Python; it does not install Python for you. The Defuddle fallback for normal web pages still requires `defuddle` to be installed locally.

### Homebrew

Recommended Homebrew installation:

```bash
brew tap yanyansay/content-capture-kit https://github.com/yanyansay/content-capture-kit
brew install content-capture-kit
```

After installation, use the unified command:

```bash
content-capture --help
```

### Local Development

```bash
python3 -m pip install -e .
```

Normal web page extraction may require Defuddle. The tool calls it when needed:

```bash
defuddle parse https://example.com/article --md
```

X single-article retrieval uses the free conversion path; X user longform filtering uses local web endpoints.

## Start Here

If you only want to save one piece of content into Obsidian, choose the platform command and set an output directory:

| Content | Command |
| --- | --- |
| X longform article | `content-capture x article <x-url-or-id> --out <output-dir>` |
| X user longform filter | `content-capture x user <handle-or-profile-url> --min-views 1w --out <output-dir>` |
| Single WeChat article | `content-capture wechat <mp.weixin-url> --out <output-dir>` |
| WeChat collection knowledge base | `content-capture wechat <mp.weixin-url> --deep --out <output-dir>` |
| Normal web article | `content-capture web <url> --out <output-dir>` |

For a first run, point `--out` to a temporary directory such as `output/test`. After checking the Markdown, media links, and folder structure, point `--out` to the final folder inside your Obsidian vault.

## Current Limits

- Platforms marked as not done do not have command entries yet. Passing those links will not produce complete output.
- Use `content-capture wechat` for WeChat Official Account articles. Do not use `content-capture web` for WeChat articles.
- `content-capture wechat` gets one article by default. Use `--deep` or `--knowledge-base` only when the entry article should be treated as a collection-style knowledge base.
- The normal web page Defuddle fallback requires `defuddle` to be installed locally.
- X single-article retrieval tries web/Defuddle Markdown first to preserve code blocks, then falls back to the public conversion path.
- X user longform retrieval only saves X longform articles or long notes. It does not save normal short posts. View filtering uses views/impressions returned by X web. Media links stay remote; the command does not create local `image/` or `video/` directories.
- WeChat videos are not downloaded. The current output focuses on text, images, and article structure.
- Asset links are relative by default for Obsidian vault portability. Use `--absolute-asset-paths` only when your previewer cannot resolve relative paths.

## Usage

### 1. Get a Single X Longform Post

```bash
content-capture x article https://x.com/example_author/status/1234567890123456789 --out output
```

Use a mirror URL when the mirror contains more complete media or code blocks:

```bash
content-capture x article https://x.com/example_author/status/1234567890123456789 \
  --mirror-url https://example.com/mirrored-post \
  --out output
```

Output behavior:

- The tool first creates a folder from the author nickname.
- Markdown filenames use `article-title_published-date.md`.
- Images are stored in that author folder's `image/` directory.
- Videos are stored in that author folder's `video/` directory.
- By default, the tool only generates Markdown. Add `--html` to generate a sibling HTML preview.
- If `defuddle` is installed locally, code blocks in X longform posts are usually preserved. When the tool falls back to the public conversion path, some code blocks may be missing.

### 2. Get X User Longform Posts by Filter

```bash
content-capture x user @example_author --min-views 1w --out output
```

Profile URLs are also accepted:

```bash
content-capture x user https://x.com/example_author --min-views 10000 --out output
```

Common filters:

```bash
content-capture x user @example_author \
  --min-views 1w \
  --min-likes 500 \
  --min-retweets 100 \
  --since 2026-01-01 \
  --until 2026-05-17 \
  --limit 20 \
  --out output
```

Output behavior:

- Only longform articles or long notes are saved.
- The article list comes from the web endpoint behind `https://x.com/<handle>/articles`.
- `1w`, `10k`, and `10000` are all valid count values.
- The tool scans at most 20 timeline pages by default. Use `--max-pages` to adjust this.
- Matching articles are saved into the author folder's `static/` subdirectory, with an `index.md` matching-article index in the author folder.
- `index.md` title links point to local Markdown files, and view-count links point to the original X URLs.
- X user longform exports keep remote image and video links instead of downloading media locally.
- `--limit` only limits how many matching article bodies are saved. It does not stop article-list retrieval early.
- This feature depends on X web endpoints. If X returns verification, rate limiting, or changes page structure, the command fails clearly.

### 3. Get a Normal Web Page

```bash
content-capture web https://example.com/article --out output
```

Notes:

- The tool first tries built-in HTML extraction.
- If that fails, it calls `defuddle parse <url> --md`.
- Images are localized into the `image/` directory.

### 4. Get a Single WeChat Article

```bash
content-capture wechat 'https://mp.weixin.qq.com/s/example_article_id' --out output
```

Notes:

- The article body is exported as Markdown.
- The tool first creates a folder from the author nickname.
- Markdown filenames use `article-title_published-date.md`.
- Images are downloaded into that author folder's `image/` directory.
- WeChat videos are not downloaded.
- `微信文章知识库.md` is not generated by default.
- If WeChat returns a verification page, the tool reports a clear error.

### 5. Get a WeChat Collection as a Knowledge Base

Use this when an entry article contains many linked WeChat articles.

```bash
content-capture wechat 'https://mp.weixin.qq.com/s/example_collection_id' --deep --out output/wechat-kb
```

Limit the number of linked articles:

```bash
content-capture wechat 'https://mp.weixin.qq.com/s/example_collection_id' \
  --deep \
  --max-links 20 \
  --out output/wechat-kb
```

Example output:

```text
output/wechat-kb/
  AuthorNickname/
    EntryArticleTitle/
      微信文章知识库.md
      EntryArticleTitle_2026-05-13.md
      Ideas/
        ChildArticleA_2026-05-14.md
        ChildArticleB_2026-05-15.md
      Analytics/
        ChildArticleC_2026-05-15.md
      Development/
        ChildArticleD_2026-05-16.md
      image/
        image-01-xxxxxxxxxx-640.png
```

Directory rules:

- The first-level folder is named after the author nickname.
- WeChat collections create an entry-article folder inside the author folder.
- The entry article is saved as a Markdown file.
- Online WeChat links inside the entry article are rewritten to local Markdown paths.
- Linked articles are grouped by the second-level or third-level headings in the entry article.
- Filenames use `article-title_published-date.md`; when the published date cannot be detected, the tool uses `unknown-date`.
- Spaces are removed from filenames and paths.
- Failed articles are recorded in the index note.

## Common Options

### `--deep`

Treat the WeChat entry article as a knowledge base: export the entry article and get linked WeChat child articles from the body.

```bash
content-capture wechat 'https://mp.weixin.qq.com/s/example_collection_id' --deep
```

### `--out`

Set the output directory.

```bash
content-capture web https://example.com/article --out ~/Documents/Obsidian/Sources
```

### `--no-local-assets`

Skip image/video downloads and keep remote links.

```bash
content-capture web https://example.com/article --no-local-assets
```

### `--absolute-asset-paths`

Write asset links as absolute filesystem paths. This can help some Markdown previewers, but relative paths are better for long-term Obsidian vaults.

```bash
content-capture web https://example.com/article --absolute-asset-paths
```

### `--html`

Generate a sibling HTML preview file. By default, only Markdown is generated.

```bash
content-capture x article https://x.com/example_author/status/1234567890123456789 --html
```

## Obsidian Tips

- Point `--out` to a folder inside your Obsidian vault.
- Put WeChat collections under a dedicated folder such as `Sources/WeChat/`.
- Put X articles under a dedicated folder such as `Sources/X/`.
- Prefer relative asset paths for vault portability.
- Use the entry article as a directory note and navigate to child notes through local Markdown links.

## Notes

- X user longform filtering depends on X web endpoints and can fail when X changes them.
- Single X article retrieval uses the free path first, but availability depends on the public converter.
- WeChat may return a verification page. Retry later or complete verification in a browser/WeChat.
- WeChat videos are intentionally skipped. The tool focuses on text and images.
- Dynamic web pages may require Defuddle fallback.
