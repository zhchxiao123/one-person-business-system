#!/usr/bin/env python3
"""
微信公众号视频上传 CLI（代理服务器版）
==========================================

通过固定 IP 的代理服务器，把本地视频上传到公众号【永久素材库】。
上传后可在「公众号后台 → 素材管理 → 视频」看到，后续可：
  1. 手动群发
  2. 配合 wechat-styler 排版的图文，把视频嵌入文章
  3. 调 /cgi-bin/media/uploadvideo 转成群发素材后 mpvideo 群发

配置优先级（同 create_draft.py）:
  1. 命令行 --server / --api-key
  2. 技能目录 .env 文件
  3. 环境变量 WECHAT_PROXY_URL / WECHAT_PROXY_API_KEY

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


# ==================== .env 自动加载（与 create_draft.py 对齐） ====================
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
                key = key.strip()
                value = value.strip().strip('"').strip("'")
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


def _ffprobe_codecs(video_path: str) -> tuple[str, str] | None:
    """返回 (v_codec, a_codec),失败返回 None。需要 ffmpeg/ffprobe 在 PATH。"""
    import subprocess
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0", "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1",
                video_path,
            ],
            stderr=subprocess.STDOUT, timeout=10,
        ).decode().strip()
        v = out.splitlines()[0] if out else ""
        a_out = subprocess.check_output(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "a:0", "-show_entries", "stream=codec_name", "-of", "default=nw=1:nk=1",
                video_path,
            ],
            stderr=subprocess.STDOUT, timeout=10,
        ).decode().strip()
        a = a_out.splitlines()[0] if a_out else ""
        return v, a
    except Exception:
        return None


def maybe_reencode_for_wechat(video_path: str, mode: str = "auto") -> tuple[str, bool]:
    """
    必要时把视频重编码为 H.264 baseline + AAC(微信最稳的格式)。
    返回 (最终上传路径, 是否重编码了)。
      - mode="always": 总是重编码
      - mode="auto":   仅当不是 H.264 + AAC 时重编码
      - mode="never":  不重编码
    """
    if mode == "never":
        return video_path, False
    if mode == "always":
        return _reencode(video_path), True
    # auto
    codecs = _ffprobe_codecs(video_path)
    if codecs is None:
        # ffprobe 不可用,直接上传
        return video_path, False
    v, a = codecs
    if v == "h264" and a in ("aac", "mp3"):
        return video_path, False
    return _reencode(video_path), True


def _reencode(video_path: str) -> str:
    """用 ffmpeg 强制 H.264 baseline + AAC + faststart,返回新文件路径。"""
    import subprocess
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp.close()
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-c:v", "libx264", "-profile:v", "baseline", "-level", "4.0", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        "-f", "mp4", tmp.name,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=600)
    return tmp.name


def upload_video_via_proxy(
    server_url: str,
    api_key: str,
    video_path: str,
    title: str = "",
    introduction: str = "",
    timeout: int = 600,
) -> dict:
    """通过代理服务器上传视频到素材库。返回 {"success", "media_id", "url", "filename", "size"}"""
    if not os.path.exists(video_path):
        raise Exception(f"视频文件不存在: {video_path}")
    file_size = os.path.getsize(video_path)
    size_mb = file_size / 1024 / 1024
    filename = os.path.basename(video_path)

    endpoint = server_url.rstrip("/") + "/api/video/upload-permanent"
    print(f"  文件:   {filename}  ({size_mb:.2f} MB)")
    print(f"  标题:   {title or '(空,默认用文件名)'}")
    print(f"  简介:   {introduction or '(空)'}")
    print(f"  接口:   {endpoint}")
    print(f"  上传中 (timeout={timeout}s)...")

    with open(video_path, "rb") as f:
        files = {"video": (filename, f, "video/mp4")}
        data = {"title": title, "introduction": introduction}
        resp = requests.post(
            endpoint,
            files=files,
            data=data,
            headers={"X-API-Key": api_key},
            timeout=timeout,
        )

    if resp.status_code == 401:
        raise Exception("API Key 无效，请检查 PROXY_API_KEY 配置")
    if resp.status_code != 200:
        raise Exception(f"服务器错误 {resp.status_code}: {resp.text[:300]}")

    return resp.json()


def main():
    parser = argparse.ArgumentParser(
        description="上传视频到微信公众号【永久素材库】（通过代理服务器）",
    )
    parser.add_argument("--server", default=os.getenv("WECHAT_PROXY_URL"),
                        help="代理服务器地址（覆盖 .env）")
    parser.add_argument("--api-key", default=os.getenv("WECHAT_PROXY_API_KEY"),
                        help="代理服务器 API Key（覆盖 .env）")
    parser.add_argument("--file", required=True, help="本地视频文件路径（mp4 推荐 ≤ 20MB）")
    parser.add_argument("--title", default="", help="视频标题（写入素材库 description）")
    parser.add_argument("--introduction", default="", help="视频简介（写入素材库 description）")
    parser.add_argument("--timeout", type=int, default=600, help="HTTP 超时（秒），大文件请加大")
    parser.add_argument("--json", action="store_true", help="只输出 JSON 结果（适合脚本调用）")
    parser.add_argument("--reencode", choices=["auto", "always", "never"], default="auto",
                        help="auto: 仅在视频非 H.264 baseline 时重编码; always: 强制重编码; never: 不重编码")

    args = parser.parse_args()

    if not args.server:
        print("错误: 需要代理服务器地址（--server 或 .env / WECHAT_PROXY_URL）")
        sys.exit(1)
    if not args.api_key:
        print("错误: 需要 API Key（--api-key 或 .env / WECHAT_PROXY_API_KEY）")
        sys.exit(1)

    try:
        # 必要时先重编码(微信对 H.264 baseline + AAC + faststart 最友好)
        upload_path = args.file
        if args.reencode != "never":
            upload_path, did_reencode = maybe_reencode_for_wechat(args.file, mode=args.reencode)
            if did_reencode:
                print(f"  已自动重编码 → {upload_path}")

        result = upload_video_via_proxy(
            server_url=args.server,
            api_key=args.api_key,
            video_path=upload_path,
            title=args.title,
            introduction=args.introduction,
            timeout=args.timeout,
        )
    except Exception as e:
        if args.json:
            print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
        else:
            print(f"\n❌ 上传失败: {e}")
        sys.exit(1)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if result.get("success"):
        media_id = result.get("media_id", "")
        url = result.get("url", "")
        print(f"\n✅ 视频上传成功")
        print(f"   media_id: {media_id}")
        if url:
            print(f"   url:      {url}")
        print(f"   大小:     {result.get('size', 0) / 1024 / 1024:.2f} MB")
        print()
        print("💡 后续可:")
        print("   1) 在公众号后台「素材管理 → 视频」里查看")
        print("   2) 把 media_id 用于图文嵌入(需配合 create_draft.py)")
        print("   3) 调 /cgi-bin/media/uploadvideo 转群发素材后 mpvideo 群发")
    else:
        print(f"\n❌ 上传失败: {result.get('error', '未知错误')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
