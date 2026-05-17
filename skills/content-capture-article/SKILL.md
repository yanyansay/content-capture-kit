---
name: content-capture-article
description: Use content-capture-kit to get articles into Obsidian-friendly Markdown. Trigger when the user asks in Chinese or English to 获取文章, 保存文章, 把这篇文章放到 Obsidian, get an X/Twitter article, get a WeChat Official Account article, get a normal web article, export a WeChat collection as a knowledge base, or save article media locally.
---

# Content Capture Article

## Overview

Use the `content-capture` CLI to save supported article URLs as Markdown with local assets. Prefer this skill over ad hoc web fetching when the user wants a durable Obsidian note rather than a chat summary.

## Destination Rules

- If the user says `根目录` in this workflow, treat it as the computer user root, usually `/Users/renlimin`, not the current repository root.
- If the user says to save under the root `obsidian` folder, use `/Users/renlimin/obsidian/...` unless they provide another absolute path.
- Create missing destination folders before running the command.
- Keep generated Markdown and downloaded assets in the requested destination; do not commit generated article outputs.

## Command Selection

- X/Twitter single article: `content-capture x article <x-url-or-id> --out <dir>`
- WeChat Official Account single article: `content-capture wechat <mp.weixin-url> --out <dir>`
- WeChat collection-style knowledge base: `content-capture wechat <mp.weixin-url> --deep --out <dir>`
- Normal web article: `content-capture web <url> --out <dir>`

Use platform-specific commands rather than compatibility aliases. X/Twitter support is single-article only; do not invent user timeline or batch-user commands.

## Execution Workflow

1. Resolve the output directory from the user's wording.
2. Run the appropriate `content-capture` command.
3. If `content-capture` is not installed, try `npx content-capture-kit ...` with the same arguments.
4. For X/Twitter articles, the current CLI tries web/Defuddle Markdown first so code blocks are preserved when possible, then falls back to the public conversion path. If an X article with code comes back without code blocks, confirm `defuddle` is installed and use the newest package.
5. If X/Twitter conversion falls back and hits invalid UTF-8, use the current package version because it decodes the conversion response with replacement characters instead of failing the entire article.
6. Verify the final files with `find <dir> -maxdepth 3 -type f -print`.
7. Open the generated Markdown head with `sed -n '1,30p' <file>` and confirm the `来源:` line matches the requested URL.
8. For localized assets, confirm links such as `image/...` or `video/...` are relative and that the asset files exist.

## Defaults

- Leave asset localization enabled unless the user asks for remote links only.
- Use relative asset paths by default for Obsidian portability.
- Use `--html` only when the user asks for an HTML preview.
- Use Chinese wording `获取` in user-facing explanations.

## Example

For `获取这篇文章 https://x.com/example/status/123，存到根目录下 obsidian 文件夹下，创建规则/x`, run:

```bash
content-capture x article https://x.com/example/status/123 --out /Users/renlimin/obsidian/规则/x
```
