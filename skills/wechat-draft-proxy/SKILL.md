---
name: wechat-draft-proxy
description: 微信公众号草稿箱创建 + 视频素材上传工具（代理服务器版）。通过固定 IP 的代理服务器中转微信 API 调用，客户端不需要加入微信 IP 白名单。支持直接提交已排版 HTML、封面图、原文链接；支持上传视频到公众号【永久素材库】（material/add_material?type=video），便于后续在公众号后台手动群发或嵌入图文。推荐与 wechat-styler 搭配使用发布公众号文章。
triggers:
  - 微信草稿
  - 发公众号
  - 发布到微信
  - wechat draft
  - 创建公众号草稿
  - 投稿微信
  - 草稿箱
  - 微信公众号发布
  - 上传视频到公众号
  - 公众号视频
  - 视频素材
  - upload video to wechat
---
# Wechat Draft Proxy - 微信公众号草稿箱工具（Node.js 代理版）

通过固定 IP 的代理服务器中转微信 API 调用，客户端不需要加入微信 IP 白名单。

> **v2.0 重写**：纯 Node.js 实现（零运行时依赖），推荐直接使用 `node` 命令。

## 架构

```
Claude / Grok 客户端（任意 IP）
    ↓ POST /api/draft（API Key 鉴权）
代理服务器（固定 IP，已加入微信白名单）
    ↓ 调用微信 API
微信服务器
```

## 何时使用此技能

- 用户要求将文章发布到微信公众号草稿箱
- 用户说“发公众号”、“投稿微信”、“创建草稿”、“发布到微信”等
- 已使用 wechat-styler 排版好 HTML，需要一键创建草稿
- 需要带封面图或原文链接的公众号文章
- 客户端 IP 不固定，无法直接加入微信 IP 白名单

## 安装与配置（推荐做法，一次性搞定）

这是 skill 使用最顺滑的方式，**无需 export 环境变量**：

```bash
# 1. 进入 skill 目录（以 grok 为例，claude 同理）
cd ~/.grok/skills/wechat-draft-proxy

# 2. 复制配置模板
cp .env.example .env

# 3. 编辑 .env，填入你的代理服务器信息
#    WECHAT_PROXY_URL=你的服务器地址
#    WECHAT_PROXY_API_KEY=服务端设置的 PROXY_API_KEY
```

之后直接运行脚本即可，**脚本会自动加载同目录 `.env`**。

### 配置优先级（从高到低）

1. 命令行参数 `--server` / `--api-key`（单次覆盖）
2. 技能目录下的 `.env` 文件
3. 环境变量 `WECHAT_PROXY_URL` / `WECHAT_PROXY_API_KEY`

这种文件方式让 skill 安装和日常使用都非常干净。

## 使用方式（Node.js 推荐）

### 1. 发布已排版的 HTML（最常用）

```bash
node ~/.grok/skills/wechat-draft-proxy/scripts/create_draft.js \
  --title "文章标题" \
  --file styled_article.html \
  --html
```

Claude 环境同样支持：

```bash
node ~/.claude/skills/wechat-draft-proxy/scripts/create_draft.js \
  --title "文章标题" \
  --file styled_article.html \
  --html
```

### 2. 带封面图（本地文件）

```bash
node ~/.grok/skills/wechat-draft-proxy/scripts/create_draft.js \
  --title "文章标题" \
  --file styled_article.html \
  --html \
  --cover-path cover.jpg
```

### 3. 带封面图（远程 URL）

```bash
node ~/.grok/skills/wechat-draft-proxy/scripts/create_draft.js \
  --title "文章标题" \
  --file styled_article.html \
  --html \
  --cover-url "https://example.com/cover.jpg"
```

### 4. 推荐完整工作流（搭配 wechat-styler）

```bash
# 第一步：专业排版（推荐 sspai / professional-clean 主题）
python3 ~/.grok/skills/wechat-styler/scripts/style_html.py \
  --file article.md --theme sspai --output styled.html

# 第二步：通过代理创建草稿（自动提取 body 内容）
node ~/.grok/skills/wechat-draft-proxy/scripts/create_draft.js \
  --title "文章标题" \
  --file styled.html \
  --html
```

### 5. 上传视频到永久素材库 🆕

适用于播客视频、教程视频等产物的分发。**仅认证服务号可用**，单公众号最多 1000 条非图文永久素材；视频建议 MP4 格式，体积 ≤ 20MB 最稳。

```bash
# 基本用法
python3 ~/.grok/skills/wechat-draft-proxy/scripts/upload_video.py \
  --file /path/to/episode-01.mp4 \
  --title "EP01 主题" \
  --introduction "本期简介：xxx"

# 大文件 / 慢网络可加大超时
python3 scripts/upload_video.py \
  --file big.mp4 --title "标题" --introduction "简介" --timeout 1200

# 脚本化调用（只输出 JSON）
python3 scripts/upload_video.py --file v.mp4 --title "x" --json
```

输出示例：

```
✅ 视频上传成功
   media_id: STUB_MEDIA_ID
   url:      https://stub.video/test.mp4
   大小:     0.00 MB
```

**上传成功后，media_id 可用于**：
- 手动在公众号后台「素材管理 → 视频」查看
- 配合 `create_draft.js` 把视频嵌入到图文（用 `<iframe>`/`<video>` 引用 `url` 字段，或用 `mpnews` 文章类型）
- 调 `/cgi-bin/media/uploadvideo` 转群发素材后用 `mpvideo` 类型群发（需服务号，每月 4 次群发配额）

## 快速命令（技能目录内）

```bash
cd ~/.grok/skills/wechat-draft-proxy

# 查看帮助
node scripts/create_draft.js --help
python3 scripts/upload_video.py --help

# 安装后首次配置（只需一次）
cp .env.example .env
# 编辑 .env 填入服务器地址和 Key 即可

# 之后直接运行，无需传 server/api-key
node scripts/create_draft.js --title "测试" --content "# Hello" --html
python3 scripts/upload_video.py --file demo.mp4 --title "测试视频"
```

## 参数说明

| 参数                  | 必填 | 说明                                      |
|-----------------------|------|-------------------------------------------|
| `--title`             | 是   | 文章标题                                  |
| `--file`              | 否*  | 从文件读取内容（优先级高于 `--content`）  |
| `--content`           | 否*  | 直接传入字符串内容                        |
| `--html`              | 否   | 内容已是 HTML，跳过 Markdown 转换         |
| `--server`            | 否   | 代理服务器地址（最高优先，可覆盖 .env）   |
| `--api-key`           | 否   | API Key（最高优先，可覆盖 .env）          |
| `--cover-path`        | 否   | 封面图本地路径                            |
| `--cover-url`         | 否   | 封面图远程 URL                            |
| `--content-source-url`| 否   | 原文链接                                  |
| `--theme`             | 否   | 排版主题（仅记录，Node 版不调用 Python styler） |

## 行为说明

- 内容来源优先级：`--file` > `--content`
- 封面图优先级：`--cover-path` > `--cover-url`
- 检测到完整 HTML 含 `<body>` 时自动提取内部内容
- 非 `--html` 模式使用内置简易 Markdown 转换器（支持标题、加粗、列表、链接、图片、代码块）。**专业排版请先用 wechat-styler 生成 HTML 再加 `--html`**

## 与 Python 版的区别（v2.0）

| 项目             | Python 旧版                  | Node.js 新版（推荐）          |
|------------------|------------------------------|-------------------------------|
| 运行时           | Python + requests            | 纯 Node.js（>=18），零依赖    |
| Markdown 转换    | 尝试调用 wechat-styler       | 内置简易转换 + 强烈推荐 --html |
| 安装/配置        | pip install + export 变量    | cp .env.example .env（推荐）  |
| 执行命令         | python3 ...create_draft.py   | node ...create_draft.js       |
| 兼容性           | 保留（过渡期）               | 主要维护版本                  |

旧版 `scripts/create_draft.py` 仍保留在目录中，过渡期可用。

## 服务端部署

服务端（推荐 Node.js 版）位于仓库根目录 `wechat-proxy-server/`，提供 Dockerfile + docker-compose 一键部署（纯 Node.js，零依赖）。

部署后务必将服务器出口 IP 加入微信公众平台「设置 → 开发设置 → IP 白名单」。

**已实现的接口：**
- `GET  /health` — 健康检查
- `POST /api/draft` — 创建公众号草稿（图文章）
- `POST /api/video/upload-permanent` — 上传视频到永久素材库（新增）

详细说明见 [wechat-proxy-server/README.md](/workspace/wechat-proxy-server/README.md)。

## 安装与环境

Node.js 版本：

```bash
node -v   # 要求 >= 18
```

1. 把 skill 放到 `~/.grok/skills/wechat-draft-proxy`（或 claude 对应路径）
2. 按上方「安装与配置」一节执行 `cp .env.example .env` 并填写
3. 无需额外依赖即可运行

未来如需增强 Markdown 解析可按需 `npm install marked`。

## 安全与最佳实践

- API Key 仅用于代理鉴权，服务端才持有微信 AppID/Secret
- 封面图本地文件以 base64 传输，建议控制在 2MB 以内
- 生产环境建议配置 HTTPS + 反向代理
- 客户端脚本绝不接触微信 AppID/Secret

## 相关技能

- `wechat-styler` — 专业公众号 HTML 排版（强烈推荐搭配使用）
- `wechat-tech-article` — GitHub 开源项目转技术文章（生成后用本工具发布）

## 输出示例

成功：

```
✅ 成功! 草稿已创建!
media_id: xxxxxxxxxxxxxxxxx
请到微信公众号后台 -> 内容与互动 -> 草稿箱 查看
```

失败会输出具体错误原因（API Key 无效、服务器异常、图片处理失败等）。
