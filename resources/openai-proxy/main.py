import os
import random
import time
import logging
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse
from starlette.responses import Response
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="OpenAI API Proxy", version="1.0.0")

OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com")

# 支持多个 OpenAI API Key，逗号分隔
_raw_keys = os.getenv("OPENAI_API_KEYS", os.getenv("OPENAI_API_KEY", ""))
OPENAI_API_KEYS = [k.strip() for k in _raw_keys.split(",") if k.strip()]

# 代理服务器自己的鉴权 key（留空则不做鉴权）
PROXY_API_KEYS = set(
    k.strip()
    for k in os.getenv("PROXY_API_KEYS", "").split(",")
    if k.strip()
)

TIMEOUT = float(os.getenv("TIMEOUT", "120"))


def pick_openai_key() -> str:
    if not OPENAI_API_KEYS:
        raise HTTPException(status_code=500, detail="No OpenAI API key configured")
    return random.choice(OPENAI_API_KEYS)


def verify_proxy_auth(request: Request):
    if not PROXY_API_KEYS:
        return  # 未配置则不鉴权
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    if token not in PROXY_API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid proxy API key")


async def stream_response(response: httpx.Response) -> AsyncGenerator[bytes, None]:
    async for chunk in response.aiter_bytes():
        yield chunk


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
)
async def proxy(request: Request, path: str, _=Depends(verify_proxy_auth)):
    openai_key = pick_openai_key()

    # 构造目标 URL
    target_url = f"{OPENAI_BASE_URL}/{path}"
    if request.url.query:
        target_url += f"?{request.url.query}"

    # 透传 headers，替换 Authorization
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in ("host", "authorization", "content-length")
    }
    headers["Authorization"] = f"Bearer {openai_key}"

    body = await request.body()

    start = time.time()
    logger.info("→ %s /%s key=...%s", request.method, path, openai_key[-6:])

    try:
        client = httpx.AsyncClient(timeout=TIMEOUT)
        upstream = await client.send(
            client.build_request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
            ),
            stream=True,
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Upstream timeout")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Upstream error: {e}")

    elapsed = time.time() - start
    content_type = upstream.headers.get("content-type", "")
    logger.info(
        "← %s /%s status=%d %.2fs",
        request.method,
        path,
        upstream.status_code,
        elapsed,
    )

    # 透传响应 headers（过滤 hop-by-hop）
    skip = {"transfer-encoding", "connection", "keep-alive", "content-encoding"}
    response_headers = {
        k: v for k, v in upstream.headers.items() if k.lower() not in skip
    }

    # 流式响应（SSE / stream=true）
    if "text/event-stream" in content_type:
        return StreamingResponse(
            stream_response(upstream),
            status_code=upstream.status_code,
            headers=response_headers,
            media_type="text/event-stream",
        )

    # 普通响应
    content = await upstream.aread()
    await upstream.aclose()
    await client.aclose()
    return Response(
        content=content,
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=content_type or "application/json",
    )

