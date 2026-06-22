#!/usr/bin/env python3
"""
微信公众号视频一站式发布 CLI（方案 A）
======================================

完整链路:
  ① 上传 mp4 → 公众号永久素材库 (/api/video/upload-permanent)
  ② 转成「可群发」素材 (/api/video/convert-to-mass)
  ③ 创建 mpvideo 群发任务 (/api/video/mass-send, 进入 48h 预览期)
  ④ [人工] 公众号后台「群发消息」预览并点击"群发"
  ⑤ [人工] 视频号助手 App → 从公众号同步 (5 秒)

依赖: pip install requests
"""

import argparse
import json
import os
import sys

try:
    import requests
except ImportError:
    print("需要安装依赖: pip install requests")
    sys.exit(1)


# ==================== .env 自动加载 ====================
def _load_env_manual(env_path: str) -> None:
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key, value = key.strip(), value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        pass


def load_proxy_env() -> None:
    skill_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_file = os.path.join(skill_root, ".env")
    if not os.path.exists(env_file):
        return
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(dotenv_path=env_file, override=False)
    except ImportError:
        _load_env_manual(env_file)


load_proxy_env()


def _post_json(server_url: str, api_key: str, path: str, payload: dict, timeout: int = 60) -> dict:
    url = server_url.rstrip("/") + path
    resp = requests.post(url, json=payload,
                         headers={"X-API-Key": api_key, "Content-Type": "application/json"},
                         timeout=timeout)
    if resp.status_code == 401:
        raise Exception("API Key 无效，请检查 PROXY_API_KEY 配置")
    if resp.status_code != 200:
        raise Exception(f"服务器错误 {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def _post_multipart(server_url: str, api_key: str, path: str, video_path: str,
                    fields: dict, timeout: int = 600) -> dict:
    url = server_url.rstrip("/") + path
    with open(video_path, "rb") as f:
        files = {"video": (os.path.basename(video_path), f, "video/mp4")}
        resp = requests.post(url, files=files, data=fields,
                             headers={"X-API-Key": api_key},
                             timeout=timeout)
    if resp.status_code == 401:
        raise Exception("API Key 无效，请检查 PROXY_API_KEY 配置")
    if resp.status_code != 200:
        raise Exception(f"服务器错误 {resp.status_code}: {resp.text[:300]}")
    return resp.json()


# ==================== 三个子步骤 ====================

def step_upload(server_url: str, api_key: str, video_path: str,
                title: str, introduction: str, reencode: str, timeout: int) -> dict:
    """① 上传 mp4 到永久素材库"""
    final_path = video_path
    if reencode != "never":
        try:
            from upload_video import maybe_reencode_for_wechat
            final_path, did = maybe_reencode_for_wechat(video_path, mode=reencode)
            if did:
                print(f"  ✅ 自动重编码完成 → {final_path}")
        except ImportError:
            print("  ⚠️  未找到 upload_video.py 的 reencode 工具,跳过")
    size_mb = os.path.getsize(final_path) / 1024 / 1024
    print(f"  ① 上传 ({size_mb:.2f} MB)...")
    return _post_multipart(
        server_url, api_key, "/api/video/upload-permanent",
        final_path, {"title": title, "introduction": introduction}, timeout,
    )


def step_convert(server_url: str, api_key: str, media_id: str,
                 title: str, description: str) -> dict:
    """② 转成群发素材"""
    print(f"  ② 转换群发素材...")
    return _post_json(server_url, api_key, "/api/video/convert-to-mass", {
        "media_id": media_id,
        "title": title,
        "description": description,
    })


def step_mass_send(server_url: str, api_key: str, mass_media_id: str,
                   title: str, description: str, is_to_all: bool, tag_id: int) -> dict:
    """③ 创建 mpvideo 群发任务"""
    print(f"  ③ 创建群发任务 (48h 预览期)...")
    return _post_json(server_url, api_key, "/api/video/mass-send", {
        "media_id": mass_media_id,
        "title": title,
        "description": description,
        "is_to_all": is_to_all,
        "tag_id": tag_id,
    })


def main():
    p = argparse.ArgumentParser(
        description="微信公众号视频一站式发布：上传 → 转群发 → 创建群发任务 (方案 A)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 一站式 (上传 + 转 + 群发任务):
  python3 send_video.py --file ep01.mp4 --title "EP01" --introduction "本期导览"

  # 只上传到素材库 (不群发):
  python3 send_video.py --file ep01.mp4 --title "EP01" --no-convert

  # 用已有 media_id 只跑 convert + mass:
  python3 send_video.py --existing-media-id xxx --title "EP01" --no-upload

  # 按标签群发 (tag_id=2):
  python3 send_video.py --file ep01.mp4 --title "EP01" --tag-id 2
        """,
    )
    p.add_argument("--server", default=os.getenv("WECHAT_PROXY_URL"))
    p.add_argument("--api-key", default=os.getenv("WECHAT_PROXY_API_KEY"))

    # 内容
    p.add_argument("--file", default="", help="本地视频文件 (mp4 推荐 ≤ 20MB)")
    p.add_argument("--existing-media-id", default="",
                   help="跳过上传,直接使用已上传的永久素材 media_id")
    p.add_argument("--title", required=True, help="视频标题 (≤64 字)")
    p.add_argument("--introduction", default="", help="视频简介 (≤300 字)")

    # 行为控制
    p.add_argument("--no-upload", action="store_true", help="跳过上传(配合 --existing-media-id)")
    p.add_argument("--no-convert", action="store_true", help="上传后不转换/群发")
    p.add_argument("--no-mass", action="store_true", help="不上群发,只转群发素材")
    p.add_argument("--is-to-all", dest="is_to_all", action="store_true", default=True,
                   help="全员群发 (默认)")
    p.add_argument("--tag-only", dest="is_to_all", action="store_false",
                   help="按标签群发 (需配合 --tag-id)")
    p.add_argument("--tag-id", type=int, default=0, help="标签 ID (默认 0)")
    p.add_argument("--reencode", choices=["auto", "always", "never"], default="auto")
    p.add_argument("--timeout", type=int, default=600, help="HTTP 超时(秒)")
    p.add_argument("--json", action="store_true", help="只输出 JSON")

    args = p.parse_args()

    if not args.server:
        sys.exit("错误: 需要代理服务器地址 (--server 或 .env WECHAT_PROXY_URL)")
    if not args.api_key:
        sys.exit("错误: 需要 API Key (--api-key 或 .env WECHAT_PROXY_API_KEY)")
    if not args.no_upload and not args.file:
        sys.exit("错误: 需要 --file (本地视频) 或 --no-upload + --existing-media-id")
    if not args.title:
        sys.exit("错误: --title 必填 (≤64 字)")

    try:
        media_id_1 = args.existing_media_id
        if not args.no_upload:
            r = step_upload(args.server, args.api_key, args.file,
                            args.title, args.introduction, args.reencode, args.timeout)
            if not r.get("success"):
                raise Exception(f"上传失败: {r.get('error', r)}")
            media_id_1 = r["media_id"]
            print(f"     ✅ media_id (永久素材) = {media_id_1}")
        else:
            print(f"  ① 跳过上传,使用已有 media_id = {media_id_1}")

        if args.no_convert:
            print("\n✅ 完成 (未做转换和群发)")
            print(json.dumps({"media_id": media_id_1}, ensure_ascii=False, indent=2))
            return

        r = step_convert(args.server, args.api_key, media_id_1, args.title, args.introduction)
        if not r.get("success"):
            raise Exception(f"convert 失败: {r.get('error', r)}")
        media_id_2 = r["media_id"]
        url = r.get("url", "")
        print(f"     ✅ media_id (群发素材) = {media_id_2}")
        if url:
            print(f"        url = {url}")

        if args.no_mass:
            print("\n✅ 完成 (仅转群发素材,未创建群发任务)")
            print(json.dumps({"media_id": media_id_2, "url": url}, ensure_ascii=False, indent=2))
            return

        r = step_mass_send(args.server, args.api_key, media_id_2,
                           args.title, args.introduction, args.is_to_all, args.tag_id)
        if not r.get("success"):
            raise Exception(f"mass-send 失败: {r.get('error', r)}")

        msg_id = r.get("msg_id", "")
        msg_id_str = str(msg_id)
        print(f"     ✅ msg_id = {msg_id}")
        print(f"        {r.get('note', '')}")

        if args.json:
            print(json.dumps({
                "success": True,
                "permanent_media_id": media_id_1,
                "mass_media_id": media_id_2,
                "url": url,
                "msg_id": msg_id,
            }, ensure_ascii=False, indent=2))
            return

        print("\n🎉 一站式发布完成!\n")
        print("📋 接下来的操作 (人工):")
        print("   1) 打开公众号后台 → 内容与互动 → 群发消息")
        print(f"      找到 msg_id={msg_id_str[:24]}... 的 mpvideo 任务")
        print("   2) 预览 → 点击「群发」(48h 预览期内有效)")
        print("   3) 推送成功后,打开「视频号助手 App」")
        print("      → 找到该视频 → 「从公众号同步」 → 一键发到视频号")
        print()
        print("💡 全部耗时: 公众号 ~30 秒, 视频号 ~5 秒")

    except Exception as e:
        if args.json:
            print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2))
        else:
            print(f"\n❌ 失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()