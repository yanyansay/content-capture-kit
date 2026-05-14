# 文章知识库抓取工具

中文 | [English](README.en.md)

`content-capture-kit` 用于把 X/Twitter 长文、微信公众号文章、普通网页文章导出成适合放进 Obsidian 的 Markdown 知识库。

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

## 安装

推荐用 Homebrew 安装：

```bash
brew tap yanyansay/content-capture-kit https://github.com/yanyansay/content-capture-kit
brew install --HEAD content-capture-kit
```

安装完成后使用统一命令：

```bash
content-capture --help
```

也可以在项目目录中本地运行：

```bash
python3 -m pip install -e .
```

普通网页抓取依赖本机 Defuddle，安装后工具会在需要时调用：

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
content-capture x article https://x.com/example_author/status/1234567890123456789 --out out
```

如果有镜像页，并且镜像页内容更完整，可以指定镜像：

```bash
content-capture x article https://x.com/example_author/status/1234567890123456789 \
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
content-capture x user example_author --count 10 --out out
```

也可以传 numeric user id：

```bash
content-capture x user 123456789 --count 5 --out out
```

说明：

- 只收集 `article` 或 `note_tweet` 这类长文。
- 普通短 tweet 会跳过。
- 不做全量历史抓取，只扫描最近 timeline，直到找到指定数量或没有更多页。

### 3. 抓取普通网页

```bash
content-capture web https://example.com/article --out out
```

说明：

- 普通网页会优先尝试内置 HTML 提取。
- 如果失败，会调用 `defuddle parse <url> --md`。
- 图片会下载到本地 `image/` 目录。

### 4. 抓取微信公众号单篇文章

```bash
content-capture wechat 'https://mp.weixin.qq.com/s/example_article_id' --out out
```

说明：

- 正文会导出为 Markdown。
- 图片会下载到本地 `image/`。
- 微信视频不会下载。
- 如果微信返回“环境异常/去验证”，工具会报错并停止该篇文章导出。

### 5. 抓取微信公众号合集为知识库

适合入口文章中包含很多篇文章链接的情况。

```bash
content-capture wechat 'https://mp.weixin.qq.com/s/example_collection_id' --out out/wechat-kb
```

如果只想导出前 20 个子文章：

```bash
content-capture wechat 'https://mp.weixin.qq.com/s/example_collection_id' \
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
content-capture web https://example.com/article --out ~/Documents/Obsidian/Sources
```

### `--no-local-assets`

不下载图片/视频，只保留远程链接。

```bash
content-capture web https://example.com/article --no-local-assets
```

### `--absolute-asset-paths`

把资源链接写成绝对路径。适合某些 Markdown 预览器，但不建议作为 Obsidian 长期知识库默认格式。

```bash
content-capture web https://example.com/article --absolute-asset-paths
```

### `--no-html-preview`

不生成 HTML 预览文件。

```bash
content-capture x article https://x.com/example_author/status/1234567890123456789 --no-html-preview
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
