# 文章知识库获取工具

中文 | [English](README.en.md)

`content-capture-kit` 用于把 X/Twitter 长文、微信公众号文章、普通网页文章导出成适合放进 Obsidian 的 Markdown 知识库。

默认目标不是做网页备份，而是把文章整理成可阅读、可链接、可长期维护的本地资料。

## 功能概览

- 获取单篇 X 长文，保存为 Markdown。
- 按 X 用户筛选长文，例如按浏览量、点赞数、转发数和发布时间保存命中文章。
- 获取普通网页 URL，并使用 Defuddle 转 Markdown。
- 获取单篇微信公众号文章。
- 获取微信公众号合集文章，并按入口文章中的章节标题自动创建分类目录。
- 单篇文章和普通网页默认下载图片到本地 `image/` 目录。
- 微信公众号视频默认不下载。
- X 单篇文章视频会尽量下载到本地 `video/` 目录；X 用户长文筛选保留远程媒体链接。
- 文件名和路径会做清理，适合放进 Obsidian。

## 平台支持状态

| 平台 | 状态 | 当前支持 | 命令入口 | 说明 |
| --- | --- | --- | --- | --- |
| X/Twitter | 已完成 | 单篇长文获取、用户长文筛选获取；单篇支持图片本地化和视频尽量本地化 | `content-capture x article` / `content-capture x user` | 用户长文筛选依赖 X 网页接口，媒体链接保留远程地址，接口变化时可能需要更新工具。 |
| 微信公众号 | 已完成 | 单篇文章、合集文章、子文章目录归类、图片本地化 | `content-capture wechat` | 微信视频不下载；遇到验证页需要稍后重试。 |
| 普通网页 | 已完成 | 网页正文转 Markdown，图片本地化，Defuddle 兜底 | `content-capture web` | 适合静态文章页；动态页面效果取决于页面结构。 |
| 小红书 | 未完成 | 暂不支持 | 暂无 | 后续计划支持图文/视频资源获取。 |
| 抖音 | 未完成 | 暂不支持 | 暂无 | 后续计划支持视频资源获取。 |
| B 站 | 未完成 | 暂不支持 | 暂无 | 后续计划支持视频、专栏或合集资源获取。 |
| 视频号 | 未完成 | 暂不支持 | 暂无 | 后续计划支持公开视频资源获取。 |
| YouTube | 未完成 | 暂不支持 | 暂无 | 后续计划支持视频、字幕和描述信息获取。 |

## 安装

### npx

如果你只想临时运行，不需要全局安装：

```bash
npx content-capture-kit --help
npx content-capture-kit x article https://x.com/example_author/status/1234567890123456789 --out output
npx content-capture-kit x user @example_author --min-views 1w --out output
```

也可以用 npm 全局安装，安装后会提供 `content-capture` 命令：

```bash
npm install -g content-capture-kit
content-capture --help
```

环境要求：Node.js 18 或更新版本；本机需要能运行 Python 3.11 或更新版本。npm 包会携带 Python 源码并通过本机 Python 执行，不会自动安装 Python。普通网页获取的 Defuddle 兜底仍需要你本机已安装 `defuddle`。

### Homebrew

推荐用 Homebrew 安装：

```bash
brew tap yanyansay/content-capture-kit https://github.com/yanyansay/content-capture-kit
brew install content-capture-kit
```

安装完成后使用统一命令：

```bash
content-capture --help
```

### 本地开发

```bash
python3 -m pip install -e .
```

普通网页获取依赖本机 Defuddle，安装后工具会在需要时调用：

```bash
defuddle parse https://example.com/article --md
```

X 单篇文章默认走免费转换路径；X 用户长文筛选获取走本地网页接口。

## 新用户先看这里

如果你只是想把一篇内容放进 Obsidian，通常只需要选择一个平台入口，再指定输出目录：

| 你要获取的内容 | 使用命令 |
| --- | --- |
| X 单篇长文 | `content-capture x article <x-url-or-id> --out <output-dir>` |
| X 用户长文筛选 | `content-capture x user <handle-or-profile-url> --min-views 1w --out <output-dir>` |
| 微信公众号单篇文章 | `content-capture wechat <mp.weixin-url> --out <output-dir>` |
| 微信公众号合集知识库 | `content-capture wechat <mp.weixin-url> --deep --out <output-dir>` |
| 普通网页文章 | `content-capture web <url> --out <output-dir>` |

建议第一次使用时，把 `--out` 指向一个临时目录，例如 `output/test`。确认 Markdown、媒体链接和目录结构符合预期后，再把 `--out` 指向 Obsidian vault 里的正式目录。

## 当前边界

- 未完成的平台还没有命令入口，传入这些平台的链接不会自动获取出完整内容。
- 微信公众号请优先使用 `content-capture wechat`，不要用 `content-capture web` 处理公众号文章。
- `content-capture wechat` 默认只获取单篇文章；只有加 `--deep` 或 `--knowledge-base` 时才按知识库逻辑获取入口文章里的公众号链接。
- 普通网页的 Defuddle 兜底依赖你本机已经安装 `defuddle`。
- X 单篇文章会优先使用网页/Defuddle Markdown，以尽量保留代码块；失败时回退公开转换路径。
- X 用户长文筛选获取只保存 X longform article 或长 note，不保存普通短帖；浏览量筛选使用 X 网页返回的 views/impressions 字段；媒体链接保留远程地址，不创建本地 `image/` 或 `video/` 目录。
- 微信公众号视频当前不下载，输出重点是文字、图片和文章目录结构。
- 资源默认使用相对路径，适合放进 Obsidian vault；如果你的预览器不识别相对路径，再使用 `--absolute-asset-paths`。

## 基本命令

### 1. 获取单篇 X 长文

```bash
content-capture x article https://x.com/example_author/status/1234567890123456789 --out output
```

如果有镜像页，并且镜像页内容更完整，可以指定镜像：

```bash
content-capture x article https://x.com/example_author/status/1234567890123456789 \
  --mirror-url https://example.com/mirrored-post \
  --out output
```

输出规则：

- 会先按作者昵称创建目录。
- Markdown 文件名使用 `文章标题_文章发布时间.md`。
- 图片保存到该作者目录下的 `image/`。
- 视频保存到该作者目录下的 `video/`。
- 默认只生成 Markdown；加 `--html` 时才生成同名 HTML 预览文件。
- 如果本机已安装 `defuddle`，X 长文里的代码块通常会被保留；如果回退到公开转换路径，部分代码块可能缺失。

### 2. 按用户筛选获取 X 长文

```bash
content-capture x user @example_author --min-views 1w --out output
```

也可以传入主页 URL：

```bash
content-capture x user https://x.com/example_author --min-views 10000 --out output
```

常用筛选条件：

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

输出规则：

- 只保存长文或长 note。
- 文章列表来自 `https://x.com/<handle>/articles` 页面对应的网页接口。
- `1w`、`10k`、`10000` 都可以作为数量条件。
- 默认最多扫描 20 页时间线；可用 `--max-pages` 调整。
- 命中文章会保存到作者目录的 `static/` 子目录，并生成作者目录下的 `index.md` 命中文章索引。
- `index.md` 标题链接指向对应本地 Markdown；浏览量链接指向原始 X 地址。
- X 用户长文筛选保留文章内远程图片和视频链接，不下载到本地。
- `--limit` 只限制最终保存正文的命中文章数量，不会提前停止文章列表获取。
- 该功能依赖 X 网页接口；如果 X 返回验证、限流或页面结构变化，工具会直接报错。

### 3. 获取普通网页

```bash
content-capture web https://example.com/article --out output
```

说明：

- 普通网页会优先尝试内置 HTML 提取。
- 如果失败，会调用 `defuddle parse <url> --md`。
- 图片会下载到本地 `image/` 目录。

### 4. 获取微信公众号单篇文章

```bash
content-capture wechat 'https://mp.weixin.qq.com/s/example_article_id' --out output
```

说明：

- 正文会导出为 Markdown。
- 会先按作者昵称创建目录。
- Markdown 文件名使用 `文章标题_文章发布时间.md`。
- 图片会下载到作者目录下的 `image/`。
- 微信视频不会下载。
- 默认不会生成 `微信文章知识库.md`。
- 如果微信返回“环境异常/去验证”，工具会报错并停止该篇文章导出。

### 5. 获取微信公众号合集为知识库

适合入口文章中包含很多篇文章链接的情况。

```bash
content-capture wechat 'https://mp.weixin.qq.com/s/example_collection_id' --deep --out output/wechat-kb
```

如果只想导出前 20 个子文章：

```bash
content-capture wechat 'https://mp.weixin.qq.com/s/example_collection_id' \
  --deep \
  --max-links 20 \
  --out output/wechat-kb
```

输出结构示例：

```text
output/wechat-kb/
  作者昵称/
    入口文章标题/
      微信文章知识库.md
      入口文章标题_2026-05-13.md
      需求/
        子文章标题A_2026-05-14.md
        子文章标题B_2026-05-15.md
      数据分析/
        子文章标题C_2026-05-15.md
      开发/
        子文章标题D_2026-05-16.md
      image/
        image-01-xxxxxxxxxx-640.png
```

目录规则：

- 第一层目录使用作者昵称。
- 微信合集会在作者目录下再使用入口文章标题创建合集目录。
- 入口文章本身保存为一个 Markdown 文件。
- 入口文章中的在线公众号链接会替换为本地 Markdown 相对路径。
- 子文章会根据入口文章中的二级/三级标题归类。
- 例如入口文章里有 `## 需求`，其下链接获取回来的文章会进入 `需求/`。
- 文件名使用 `文章标题_文章发布时间.md`，无法识别发布时间时使用 `unknown-date`。
- 文件名和路径里的空格会被去掉。
- 未能获取的文章会保留在索引文件的失败区。

## 常用参数

### `--deep`

把微信公众号入口文章按知识库处理：导出入口文章，并继续获取正文里链接到的公众号子文章。

```bash
content-capture wechat 'https://mp.weixin.qq.com/s/example_collection_id' --deep
```

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

### `--html`

额外生成同名 HTML 预览文件。默认只生成 Markdown。

```bash
content-capture x article https://x.com/example_author/status/1234567890123456789 --html
```

## Obsidian 使用建议

- 推荐把 `--out` 指向 Obsidian vault 里的资料目录。
- 微信合集建议单独放一个目录，例如 `Sources/WeChat/`。
- X 单篇文章建议放入 `Sources/X/`。
- 默认使用相对资源路径，方便迁移 vault。
- 入口文章可作为目录页，子文章通过本地 Markdown 链接进入。

## 注意事项

- X 只支持单篇文章获取，不支持按用户批量获取。
- 单篇 X 获取默认走免费路径，但不同文章的可用性取决于公开转换服务。
- 微信公众号可能返回环境验证页，这种情况下需要稍后重试或在浏览器/微信中完成验证。
- 微信视频不下载；当前工具重点保留文字和图片。
- 普通网页获取依赖页面结构，遇到动态渲染网页时可能需要 Defuddle 兜底。
