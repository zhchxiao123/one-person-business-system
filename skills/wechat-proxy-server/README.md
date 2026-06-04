# WeChat Proxy Server

固定 IP 的微信 API 代理服务器，解决客户端 IP 不固定导致无法加入微信白名单的问题。

## 快速部署

### 1. 克隆并配置

```bash
cp .env.example .env
```

编辑 `.env`：

```env
WECHAT_APPID=你的AppID
WECHAT_APPSECRET=你的AppSecret
PROXY_API_KEY=生成一个随机密钥
```

生成随机 API Key：

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 2. Docker 启动

```bash
docker-compose up -d
```

### 3. 将服务器 IP 加入微信白名单

微信公众平台 → 设置 → 开发设置 → IP 白名单 → 添加服务器 IP

### 4. 验证服务

```bash
curl https://your-server.com/health
# 返回: {"status":"ok"}
```

## API

### POST /api/draft

创建微信公众号草稿。

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

**Response**
```json
{
  "success": true,
  "media_id": "draft_media_id",
  "failed_images": []
}
```

## 本地开发

```bash
pip install -r requirements.txt
cp .env.example .env  # 填写真实凭据
python3 main.py
```

服务运行在 `http://localhost:8000`。

## 客户端配置

客户端（`wechat-draft-proxy` skill）只需配置：

```bash
export WECHAT_PROXY_URL="https://your-server.com"
export WECHAT_PROXY_API_KEY="your_proxy_api_key"
```

微信 AppID/AppSecret 仅存在服务端 `.env`，客户端完全不接触微信凭据。
