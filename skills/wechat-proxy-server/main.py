"""
微信公众号代理服务器
- 固定 IP 部署，加入微信白名单后统一代理所有 API 调用
- 客户端通过 API Key 鉴权，无需持有微信凭据
"""

import base64
import logging
import os
import re
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import wechat_client as wx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── 配置（从环境变量读取）──────────────────────────────────────────────────
WECHAT_APPID = os.environ["WECHAT_APPID"]
WECHAT_APPSECRET = os.environ["WECHAT_APPSECRET"]
API_KEY = os.environ["PROXY_API_KEY"]  # 客户端鉴权密钥，自行设置

app = FastAPI(title="WeChat Proxy Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


# ── 鉴权 ──────────────────────────────────────────────────────────────────
def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


# ── 请求/响应模型 ─────────────────────────────────────────────────────────
class DraftRequest(BaseModel):
    title: str
    content: str                        # 已排版的 HTML body 内容
    cover_url: Optional[str] = None     # 封面图远程 URL（与 cover_base64 二选一）
    cover_base64: Optional[str] = None  # 封面图 base64（本地文件场景）
    cover_filename: str = "cover.jpg"   # cover_base64 对应的文件名（推断 mime 用）
    content_source_url: str = ""        # 原文链接（可选）


class DraftResponse(BaseModel):
    success: bool
    media_id: str = ""
    failed_images: list[dict] = []
    error: str = ""


# ── 健康检查 ──────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}


# ── 创建草稿 ──────────────────────────────────────────────────────────────
@app.post("/api/draft", response_model=DraftResponse, dependencies=[Depends(verify_api_key)])
def create_draft(req: DraftRequest):
    try:
        log.info(f"创建草稿: {req.title!r}")

        # 1. 获取 access_token
        token = wx.get_access_token(WECHAT_APPID, WECHAT_APPSECRET)
        log.info("access_token 获取成功")

        # 2. 处理正文图片（外链 → 微信 CDN）
        html, failures = wx.process_content_images(token, req.content)
        if failures:
            log.warning(f"{len(failures)} 张图片处理失败: {failures}")

        # 3. 上传封面图
        thumb_media_id = ""
        if req.cover_base64:
            img_data = base64.b64decode(req.cover_base64)
            thumb_media_id = wx.upload_permanent_image(token, img_data, req.cover_filename)
            log.info(f"封面图（base64）上传成功: {thumb_media_id[:20]}...")
        elif req.cover_url:
            img_data, _ = wx.download_image(req.cover_url)
            thumb_media_id = wx.upload_permanent_image(token, img_data, "cover.jpg")
            log.info(f"封面图（URL）上传成功: {thumb_media_id[:20]}...")
        else:
            thumb_media_id = wx.get_fallback_thumb_media_id(token)
            log.info(f"使用素材库封面: {thumb_media_id[:20] if thumb_media_id else '(空)'}")

        # 4. 生成摘要（纯文本前 120 字）
        plain = re.sub(r"<[^>]+>", "", html)
        plain = re.sub(r"\s+", " ", plain).strip()
        digest = plain[:120]

        # 5. 创建草稿
        result = wx.create_draft(
            token=token,
            title=req.title,
            content=html,
            thumb_media_id=thumb_media_id,
            content_source_url=req.content_source_url,
            digest=digest,
        )

        if result.get("media_id"):
            log.info(f"草稿创建成功: {result['media_id']}")
            return DraftResponse(success=True, media_id=result["media_id"], failed_images=failures)
        else:
            log.error(f"草稿创建失败: {result}")
            return DraftResponse(success=False, error=str(result), failed_images=failures)

    except Exception as e:
        log.exception("创建草稿异常")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
