# WeChat Proxy Server

固定 IP 的微信 API 代理服务器，解决客户端 IP 不固定导致无法加入微信白名单的问题。

> **v2.0 推荐**：纯 Node.js 实现（零运行时依赖），与客户端 `wechat-draft-proxy` 完全一致的技术栈。

## 架构

```
客户端（任意 IP，Node / Python / 任意语言）
    ↓ POST /api/draft（仅需 API Key）
代理服务器（固定 IP，已加入微信白名单）
    ↓ 安全调用微信 API
微信公众号后台
```

## 快速部署（推荐 Node.js 版）

### 1. 克隆并配置

```bash
cd wechat-proxy-server
cp .env.example .env
```

编辑 `.env`：

```env
WECHAT_APPID=你的微信AppID
WECHAT_APPSECRET=你的微信AppSecret
PROXY_API_KEY=一个长随机字符串（客户端鉴权用）
```

生成随机 API Key（推荐）：

```bash
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
```

### 2. Docker 一键启动

```bash
docker-compose up -d
```

- 默认使用 Node.js 版（Dockerfile）
- 如需 Python 旧版：`docker-compose build --build-arg DOCKERFILE=Dockerfile.python ...`（或直接 `docker build -f Dockerfile.python .`）

### 3. 将服务器出口 IP 加入微信白名单

微信公众平台 → 设置与开发 → 公众号设置 → 功能设置 → **IP 白名单** → 添加服务器公网 IP

### 4. 验证服务

```bash
curl http://your-server-ip:8000/health
# 返回: {"status":"ok"}
```

## 本地开发（Node.js）

```bash
# 1. 配置环境变量
cp .env.example .env   # 编辑填写真实值

# 2. 直接运行（零依赖）
node server.js
```

服务监听 `http://localhost:8000`

支持热重载调试（Node 20+）：

```bash
node --watch server.js
```

## API

### POST /api/draft

创建微信公众号草稿（与 Python 版 100% 兼容）。

**Headers**
```
X-API-Key: your_proxy_api_key
Content-Type: application/json
```

**Body**
```json
{
  "title": "文章标题",
  "content": "<section>...已排版的HTML...</section>",
  "cover_url": "https://example.com/cover.jpg",
  "cover_base64": "base64编码的图片数据（与cover_url二选一）",
  "cover_filename": "cover.jpg",
  "content_source_url": ""
}
```

**成功响应**
```json
{
  "success": true,
  "media_id": "draft_media_id",
  "failed_images": []
}
```

**失败响应示例**
```json
{
  "success": false,
  "error": "...",
  "failed_images": []
}
```

### POST /api/video/upload-permanent 🆕

将本地视频上传到公众号【永久素材库】(`material/add_material?type=video`)，返回 `media_id`，可在公众号后台「素材管理 → 视频」中查看。仅认证服务号可用；建议 MP4 格式、≤ 20MB。

**Headers**
```
X-API-Key: your_proxy_api_key
Content-Type: multipart/form-data; boundary=...
```

**Form 字段**
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `video` | file | 是 | 视频文件 |
| `title` | text | 否 | 视频标题（写入素材库 description） |
| `introduction` | text | 否 | 视频简介（写入素材库 description） |

**cURL 示例**
```bash
curl -X POST -H "X-API-Key: $PROXY_API_KEY" \
  -F "video=@episode-01.mp4;type=video/mp4" \
  -F "title=EP01 主题" \
  -F "introduction=本期简介" \
  https://your-proxy.example.com/api/video/upload-permanent
```

**成功响应**
```json
{
  "success": true,
  "media_id": "永久素材 media_id",
  "url": "https://...video source URL...",
  "size": 4321098,
  "filename": "episode-01.mp4"
}
```

**典型使用**
- 拿到 `media_id` 后可在公众号后台手动群发
- 调 `/cgi-bin/media/uploadvideo` 转成群发素材，用 `mpvideo` 群发（服务号每月 4 次配额）
- 配合 `create_draft.js` 把视频嵌入图文（用返回的 `url` 字段）

## 客户端配置

推荐搭配 `wechat-draft-proxy` skill 使用，**最顺滑的做法是文件配置**（无需 export）：

```bash
cd ~/.grok/skills/wechat-draft-proxy
cp .env.example .env
# 编辑填入 WECHAT_PROXY_URL 和 WECHAT_PROXY_API_KEY
```

脚本会自动加载 `.env`。命令行参数 `--server` / `--api-key` 优先级更高，适合脚本调用。

传统方式（仍支持）：直接 `export WECHAT_PROXY_URL=...` 和 `WECHAT_PROXY_API_KEY=...`

**安全特性**：微信 AppID / AppSecret 永远只存在于代理服务器环境变量，客户端零接触。

## Node.js 版 vs Python 版

| 项目           | Node.js 版（推荐）          | Python 版（保留）             |
|----------------|-----------------------------|-------------------------------|
| 运行时         | Node >= 18（零依赖）        | Python 3.11 + FastAPI         |
| 镜像大小       | 更小（node:20-slim）        | 较大                          |
| 代码维护       | 与客户端同栈                | 独立维护                      |
| 启动命令       | `node server.js`            | `python main.py`              |
| Docker         | 默认（Dockerfile）          | Dockerfile.python             |
| 功能一致性     | 完全一致                    | 完全一致                      |

**建议**：新部署全部使用 Node.js 版。Python 文件保留用于历史对比和极端场景回退。

## 生产建议

- 前置 Nginx / Caddy 提供 HTTPS + 域名
- 使用 `docker-compose` + `restart: unless-stopped`
- 定期检查 `/tmp/wechat_token_cache.json`（容器内）
- 监控 `/health` 端点
- API Key 建议 32 字节以上随机值，妥善保管

## 相关项目

- 客户端工具（推荐）：`../skills/wechat-draft-proxy/`
- 专业排版工具：`wechat-styler` skill

---

**License**: MIT
