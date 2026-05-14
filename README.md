# 文章知识库抓取工具

这个工具用于把 X/Twitter 长文、微信公众号文章、普通网页文章导出成适合放进 Obsidian 的 Markdown 知识库。

默认目标不是做网页备份，而是把文章整理成可阅读、可链接、可长期维护的本地资料。

## 功能概览

- 抓取单篇 X 长文，保存为 Markdown。
- 抓取指定 X 用户最近 N 条长文。
- 抓取普通网页 URL，并使用 Defuddle 转 Markdown。
- 抓取单篇微信公众号文章。
- 抓取微信公众号合集文章，并按入口文章中的章节标题自动创建分类目录。
- 下载图片到本地 `image/` 目录。
- 微信公众号视频默认不下载。
- X 文章视频会尽量下载到本地 `video/` 目录。
- 文件名和路径会做清理，适合放进 Obsidian。

## 环境准备

进入项目目录：

```bash
cd /path/to/twitter_crawling
```

普通网页抓取依赖本机 Defuddle：

```bash
defuddle parse https://example.com/article --md
```

X 单篇文章默认优先走免费转换路径，不需要官方 API。只有在使用官方 API 兜底或抓取用户最近长文时，才需要设置：

```bash
export X_BEARER_TOKEN="your-token"
```

## 基本命令

### 1. 抓取单篇 X 长文

```bash
python3 -m x_crawler article https://x.com/example_author/status/1234567890123456789 --out out
```

如果有镜像页，并且镜像页内容更完整，可以指定镜像：

```bash
python3 -m x_crawler article https://x.com/example_author/status/1234567890123456789 \
  --mirror-url https://example.com/mirrored-post \
  --out out
```

输出规则：

- Markdown 文件按文章标题命名。
- 图片保存到 `out/image/`。
- 视频保存到 `out/video/`。
- 默认生成同名 HTML 预览文件。

### 2. 抓取 X 用户最近 N 条长文

这个命令需要官方 X API token。

```bash
python3 -m x_crawler user example_author --count 10 --out out
```

也可以传 numeric user id：

```bash
python3 -m x_crawler user 123456789 --count 5 --out out
```

说明：

- 只收集 `article` 或 `note_tweet` 这类长文。
- 普通短 tweet 会跳过。
- 不做全量历史抓取，只扫描最近 timeline，直到找到指定数量或没有更多页。

### 3. 抓取普通网页

```bash
python3 -m x_crawler url https://example.com/article --out out
```

说明：

- 普通网页会优先尝试内置 HTML 提取。
- 如果失败，会调用 `defuddle parse <url> --md`。
- 图片会下载到本地 `image/` 目录。

### 4. 抓取微信公众号单篇文章

```bash
python3 -m x_crawler url 'https://mp.weixin.qq.com/s/example_article_id' --out out
```

说明：

- 正文会导出为 Markdown。
- 图片会下载到本地 `image/`。
- 微信视频不会下载。
- 如果微信返回“环境异常/去验证”，工具会报错并停止该篇文章导出。

### 5. 抓取微信公众号合集为知识库

适合入口文章中包含很多篇文章链接的情况。

```bash
python3 -m x_crawler wechat 'https://mp.weixin.qq.com/s/example_collection_id' --out out/wechat-kb
```

如果只想导出前 20 个子文章：

```bash
python3 -m x_crawler wechat 'https://mp.weixin.qq.com/s/example_collection_id' \
  --max-links 20 \
  --out out/wechat-kb
```

输出结构示例：

```text
out/wechat-kb/
  入口文章标题/
    微信文章知识库.md
    入口文章标题.md
    需求/
      子文章标题A.md
      子文章标题B.md
    数据分析/
      子文章标题C.md
    开发/
      子文章标题D.md
    image/
      image-01-xxxxxxxxxx-640.png
```

目录规则：

- 第一层目录使用入口文章标题。
- 入口文章本身保存为一个 Markdown 文件。
- 入口文章中的在线公众号链接会替换为本地 Markdown 相对路径。
- 子文章会根据入口文章中的二级/三级标题归类。
- 例如入口文章里有 `## 需求`，其下链接抓回来的文章会进入 `需求/`。
- 文件名就是文章标题。
- 文件名和路径里的空格会被去掉。
- 未能抓取的文章会保留在索引文件的失败区。

## 常用参数

### `--out`

指定输出目录。

```bash
python3 -m x_crawler url https://example.com/article --out ~/Documents/Obsidian/Sources
```

### `--no-local-assets`

不下载图片/视频，只保留远程链接。

```bash
python3 -m x_crawler url https://example.com/article --no-local-assets
```

### `--absolute-asset-paths`

把资源链接写成绝对路径。适合某些 Markdown 预览器，但不建议作为 Obsidian 长期知识库默认格式。

```bash
python3 -m x_crawler url https://example.com/article --absolute-asset-paths
```

### `--no-html-preview`

不生成 HTML 预览文件。

```bash
python3 -m x_crawler article https://x.com/example_author/status/1234567890123456789 --no-html-preview
```

## Obsidian 使用建议

- 推荐把 `--out` 指向 Obsidian vault 里的资料目录。
- 微信合集建议单独放一个目录，例如 `Sources/WeChat/`。
- X 单篇文章建议放入 `Sources/X/`。
- 默认使用相对资源路径，方便迁移 vault。
- 入口文章可作为目录页，子文章通过本地 Markdown 链接进入。

## 注意事项

- X 用户批量抓取需要官方 X API token。
- 单篇 X 抓取默认走免费路径，但不同文章的可用性取决于公开转换服务。
- 微信公众号可能返回环境验证页，这种情况下需要稍后重试或在浏览器/微信中完成验证。
- 微信视频不下载；当前工具重点保留文字和图片。
- 普通网页抓取依赖页面结构，遇到动态渲染网页时可能需要 Defuddle 兜底。

---

# Article Knowledge Base Crawler

This tool exports X/Twitter longform posts, WeChat Official Account articles, and normal web articles into Markdown files suitable for an Obsidian knowledge base.

The goal is not just page backup. The goal is to create readable, linkable, and maintainable local notes.

## Features

- Export a single X longform post as Markdown.
- Fetch the latest N longform posts from an X user.
- Export normal web pages with Defuddle fallback.
- Export a single WeChat Official Account article.
- Export a WeChat collection article and organize linked articles by the section headings in the entry article.
- Download images into a local `image/` directory.
- Skip WeChat videos by default.
- Download X article videos into a local `video/` directory when possible.
- Clean filenames and paths for Obsidian usage.

## Setup

Go to the project directory:

```bash
cd /path/to/twitter_crawling
```

Normal web page extraction may require Defuddle:

```bash
defuddle parse https://example.com/article --md
```

Single X article fetching uses the free conversion path first. You only need an official X API token for API fallback or user timeline fetching:

```bash
export X_BEARER_TOKEN="your-token"
```

## Usage

### 1. Export a single X longform post

```bash
python3 -m x_crawler article https://x.com/example_author/status/1234567890123456789 --out out
```

Use a mirror URL when the mirror contains more complete media or code blocks:

```bash
python3 -m x_crawler article https://x.com/example_author/status/1234567890123456789 \
  --mirror-url https://example.com/mirrored-post \
  --out out
```

Output behavior:

- Markdown is named from the article title.
- Images are stored in `out/image/`.
- Videos are stored in `out/video/`.
- A sibling HTML preview is generated by default.

### 2. Fetch the latest N X longform posts from a user

This requires an official X API token.

```bash
python3 -m x_crawler user example_author --count 10 --out out
```

Numeric user IDs are also supported:

```bash
python3 -m x_crawler user 123456789 --count 5 --out out
```

Notes:

- Only `article` and `note_tweet` longform posts are collected.
- Short tweets are skipped.
- The command scans recent timeline pages only. It does not crawl the full history.

### 3. Export a normal web page

```bash
python3 -m x_crawler url https://example.com/article --out out
```

Notes:

- The tool first tries built-in HTML extraction.
- If that fails, it calls `defuddle parse <url> --md`.
- Images are localized into the `image/` directory.

### 4. Export a single WeChat article

```bash
python3 -m x_crawler url 'https://mp.weixin.qq.com/s/example_article_id' --out out
```

Notes:

- The article body is exported as Markdown.
- Images are downloaded locally.
- WeChat videos are not downloaded.
- If WeChat returns a verification page, the tool reports a clear error.

### 5. Export a WeChat collection as a knowledge base

Use this when an entry article contains many linked WeChat articles.

```bash
python3 -m x_crawler wechat 'https://mp.weixin.qq.com/s/example_collection_id' --out out/wechat-kb
```

Limit the number of linked articles:

```bash
python3 -m x_crawler wechat 'https://mp.weixin.qq.com/s/example_collection_id' \
  --max-links 20 \
  --out out/wechat-kb
```

Example output:

```text
out/wechat-kb/
  EntryArticleTitle/
    微信文章知识库.md
    EntryArticleTitle.md
    Ideas/
      ChildArticleA.md
      ChildArticleB.md
    Analytics/
      ChildArticleC.md
    Development/
      ChildArticleD.md
    image/
      image-01-xxxxxxxxxx-640.png
```

Directory rules:

- The first-level folder is named after the entry article.
- The entry article is saved as a Markdown file.
- Online WeChat links inside the entry article are rewritten to local Markdown paths.
- Linked articles are grouped by the second-level or third-level headings in the entry article.
- Filenames use article titles.
- Spaces are removed from filenames and paths.
- Failed articles are recorded in the index note.

## Common Options

### `--out`

Set the output directory.

```bash
python3 -m x_crawler url https://example.com/article --out ~/Documents/Obsidian/Sources
```

### `--no-local-assets`

Skip image/video downloads and keep remote links.

```bash
python3 -m x_crawler url https://example.com/article --no-local-assets
```

### `--absolute-asset-paths`

Write asset links as absolute filesystem paths. This can help some Markdown previewers, but relative paths are better for long-term Obsidian vaults.

```bash
python3 -m x_crawler url https://example.com/article --absolute-asset-paths
```

### `--no-html-preview`

Skip HTML preview generation.

```bash
python3 -m x_crawler article https://x.com/example_author/status/1234567890123456789 --no-html-preview
```

## Obsidian Tips

- Point `--out` to a folder inside your Obsidian vault.
- Put WeChat collections under a dedicated folder such as `Sources/WeChat/`.
- Put X articles under a dedicated folder such as `Sources/X/`.
- Prefer relative asset paths for vault portability.
- Use the entry article as a directory note and navigate to child notes through local Markdown links.

## Notes

- X user timeline fetching requires an official X API token.
- Single X article fetching uses the free path first, but availability depends on the public converter.
- WeChat may return a verification page. Retry later or complete verification in a browser/WeChat.
- WeChat videos are intentionally skipped. The tool focuses on text and images.
- Dynamic web pages may require Defuddle fallback.
