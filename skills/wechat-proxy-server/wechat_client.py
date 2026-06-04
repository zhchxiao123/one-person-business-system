"""
微信 API 封装层：token 管理、图片上传、草稿创建
此模块运行在代理服务器上，拥有固定 IP，已加入微信白名单。
"""

import json
import os
import re
import time
from typing import Optional

import requests

_TOKEN_CACHE: dict = {}  # {appid: {token, expires_at}}
_TOKEN_CACHE_FILE = "/tmp/wechat_token_cache.json"


def _load_cache() -> dict:
    if os.path.exists(_TOKEN_CACHE_FILE):
        try:
            with open(_TOKEN_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_cache(cache: dict) -> None:
    try:
        with open(_TOKEN_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass


def get_access_token(appid: str, appsecret: str) -> str:
    cache = _load_cache()
    entry = cache.get(appid, {})
    if entry.get("token") and entry.get("expires_at", 0) > time.time() + 300:
        return entry["token"]

    resp = requests.get(
        "https://api.weixin.qq.com/cgi-bin/token",
        params={"grant_type": "client_credential", "appid": appid, "secret": appsecret},
        timeout=15,
    )
    data = resp.json()
    if "access_token" not in data:
        raise Exception(f"获取 access_token 失败: {data.get('errmsg', str(data))}")

    token = data["access_token"]
    cache[appid] = {"token": token, "expires_at": time.time() + data.get("expires_in", 7200) - 300}
    _save_cache(cache)
    return token


_MIME_MAP = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "png": "image/png", "gif": "image/gif", "webp": "image/webp",
}


def _guess_mime(url: str, content_type: str = "") -> tuple[str, str]:
    ext = url.rstrip("/").rsplit(".", 1)[-1].lower().split("?")[0]
    if ext in _MIME_MAP:
        return _MIME_MAP[ext], ext
    for e, m in _MIME_MAP.items():
        if content_type and m in content_type:
            return m, e
    return "image/png", "png"


def download_image(url: str, timeout: int = 30) -> tuple[bytes, str]:
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
    if resp.status_code != 200:
        raise Exception(f"下载失败: HTTP {resp.status_code}")
    return resp.content, resp.headers.get("Content-Type", "")


def upload_content_image(token: str, image_data: bytes, filename: str, mime: str) -> str:
    """上传正文图片（uploadimg 接口），返回 https URL。"""
    resp = requests.post(
        f"https://api.weixin.qq.com/cgi-bin/media/uploadimg?access_token={token}",
        files={"media": (filename, image_data, mime)},
        timeout=60,
    )
    result = resp.json()
    if "url" not in result:
        raise Exception(f"上传正文图片失败: {result}")
    url = result["url"]
    return url.replace("http://", "https://", 1) if url.startswith("http://") else url


def upload_permanent_image(token: str, image_data: bytes, filename: str = "cover.jpg") -> str:
    """上传永久素材图片，返回 media_id（用于封面）。"""
    resp = requests.post(
        f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={token}&type=image",
        files={"media": (filename, image_data, "image/jpeg")},
        timeout=60,
    )
    result = resp.json()
    if "media_id" not in result:
        raise Exception(f"上传封面图失败: {result}")
    return result["media_id"]


def get_fallback_thumb_media_id(token: str) -> str:
    """从素材库取第一张图片的 media_id 作为封面 fallback。"""
    resp = requests.post(
        f"https://api.weixin.qq.com/cgi-bin/material/batchget_material?access_token={token}",
        json={"type": "image", "offset": 0, "count": 1},
        timeout=15,
    )
    items = resp.json().get("item", [])
    return items[0]["media_id"] if items else ""


def process_content_images(token: str, html: str) -> tuple[str, list[dict]]:
    """
    将 HTML 中所有外链图片下载后上传到微信，替换为 data-src 微信 URL。
    返回 (处理后的 HTML, 失败列表[{url, error}])
    """
    urls = list(dict.fromkeys(re.findall(r'<img[^>]+src="([^"]+)"[^>]*>', html)))
    if not urls:
        return html, []

    url_map: dict[str, str] = {}
    failures: list[dict] = []

    for i, url in enumerate(urls):
        try:
            data, ct = download_image(url)
            mime, ext = _guess_mime(url, ct)
            wechat_url = upload_content_image(token, data, f"img_{i}.{ext}", mime)
            url_map[url] = wechat_url
        except Exception as e:
            failures.append({"url": url, "error": str(e)})

    for orig, wx in url_map.items():
        html = re.sub(
            rf'<img([^>]*)src="{re.escape(orig)}"([^>]*)>',
            rf'<img\1data-src="{wx}"\2>',
            html,
        )

    return html, failures


def create_draft(
    token: str,
    title: str,
    content: str,
    thumb_media_id: str = "",
    content_source_url: str = "",
    digest: str = "",
) -> dict:
    """创建草稿，返回微信 API 响应。"""
    payload = {
        "articles": [{
            "title": title,
            "content": content,
            "thumb_media_id": thumb_media_id,
            "content_source_url": content_source_url,
            "digest": digest,
            "author": "",
            "need_open_comment": 1,
            "only_fans_can_comment": 0,
        }]
    }
    resp = requests.post(
        f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=30,
    )
    return resp.json()
