# OpenAI API Proxy

一个轻量、高性能的 OpenAI API 中转代理服务器，基于 FastAPI + httpx 实现。

## 功能特性

- **完全透明代理** — 支持所有 OpenAI API 路径，无需修改客户端代码
- **流式响应透传** — 自动识别并转发 SSE 流式输出（`stream=True`）
- **多 Key 负载均衡** — 配置多个 OpenAI API Key，请求随机分发，分摊用量限制
- **自定义鉴权** — 对外暴露独立的代理 Key，完全隐藏真实 OpenAI Key
- **请求日志** — 记录每次请求的方法、路径、状态码、耗时
- **Docker 支持** — 提供 Dockerfile 和 docker-compose，一键部署

## 快速开始

### 1. 克隆并配置

```bash
git clone <repo-url>
cd openai-proxy

cp .env.example .env
```

编辑 `.env`，填入你的配置：

```env
OPENAI_BASE_URL=https://api.openai.com
OPENAI_API_KEYS=sk-xxx,sk-yyy
PROXY_API_KEYS=my-proxy-key-1
TIMEOUT=120
```

### 2. 启动服务

**方式一：直接运行（Python 3.10+）**

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

**方式二：Docker Compose（推荐生产使用）**

```bash
docker compose up -d
```

服务默认监听 `http://0.0.0.0:8000`。

---

## 配置说明

所有配置通过环境变量或 `.env` 文件设置。

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `OPENAI_API_KEYS` | 是 | — | OpenAI API Key，多个用英文逗号分隔，随机负载均衡 |
| `OPENAI_BASE_URL` | 否 | `https://api.openai.com` | 上游 API 地址，可替换为第三方中转地址 |
| `PROXY_API_KEYS` | 否 | 空（不鉴权） | 代理服务器对外暴露的鉴权 Key，多个用逗号分隔；**留空则任何人都可访问** |
| `TIMEOUT` | 否 | `120` | 请求上游的超时时间（秒） |

### 多 Key 配置示例

```env
OPENAI_API_KEYS=sk-key1,sk-key2,sk-key3
```

每次请求随机选择一个 Key 转发，天然分摊 API 速率限制（RPM/TPM）。

### 自定义上游地址

如果你使用了第三方 OpenAI 兼容中转（如 Azure OpenAI、One API 等），修改 `OPENAI_BASE_URL` 即可：

```env
OPENAI_BASE_URL=https://your-relay.example.com
```

---

## 客户端接入

将客户端的 `base_url` 指向代理服务器即可，其余代码无需改动。

### Python（openai SDK）

```python
from openai import OpenAI

client = OpenAI(
    api_key="my-proxy-key-1",           # 填 PROXY_API_KEYS 中的 key
    base_url="http://your-server:8000/v1",
)

# 普通调用
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "你好"}],
)
print(response.choices[0].message.content)

# 流式调用
for chunk in client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "讲个故事"}],
    stream=True,
):
    print(chunk.choices[0].delta.content or "", end="", flush=True)
```

### Node.js（openai SDK）

```js
import OpenAI from "openai";

const client = new OpenAI({
  apiKey: "my-proxy-key-1",
  baseURL: "http://your-server:8000/v1",
});

const response = await client.chat.completions.create({
  model: "gpt-4o",
  messages: [{ role: "user", content: "Hello" }],
});
console.log(response.choices[0].message.content);
```

### curl

```bash
curl http://your-server:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer my-proxy-key-1" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

---

## 部署建议

### 使用 Nginx 反向代理 + HTTPS

生产环境建议在代理服务器前加 Nginx，配置 SSL 证书：

```nginx
server {
    listen 443 ssl;
    server_name api.yourdomain.com;

    ssl_certificate     /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;

        # 流式响应需要关闭缓冲
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 120s;
    }
}
```

### 多实例水平扩展

```yaml
# docker-compose.yml 扩展示例
services:
  openai-proxy:
    build: .
    deploy:
      replicas: 3
    ...
```

---

## 日志示例

```
2026-06-05 12:00:01 [INFO] → POST /v1/chat/completions key=...abc123
2026-06-05 12:00:03 [INFO] ← POST /v1/chat/completions status=200 2.13s
2026-06-05 12:00:05 [INFO] → POST /v1/embeddings key=...xyz789
2026-06-05 12:00:05 [INFO] ← POST /v1/embeddings status=200 0.38s
```

日志打印请求方向、路径、响应状态码、耗时，以及所用 Key 的后 6 位（方便排查 Key 问题，不泄露完整 Key）。

---

## 错误码说明

| HTTP 状态码 | 含义 |
|-------------|------|
| `401` | 代理 Key 鉴权失败（`PROXY_API_KEYS` 已配置但 Key 不匹配） |
| `500` | 服务器未配置 `OPENAI_API_KEYS` |
| `502` | 无法连接到上游 OpenAI API |
| `504` | 请求上游超时，可调大 `TIMEOUT` |

其余状态码由上游 OpenAI API 原样返回。

---

## 项目结构

```
openai-proxy/
├── main.py              # 代理服务器核心逻辑
├── requirements.txt     # Python 依赖
├── .env.example         # 配置模板
├── Dockerfile           # 容器镜像
├── docker-compose.yml   # 容器编排
└── README.md            # 本文档
```
