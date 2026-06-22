#!/usr/bin/env python3
"""
订阅号视频发布方案: 图文里嵌视频 (mpnews)
==========================================

订阅号没有 mpvideo 群发权限, 但 mpnews(图文)人人都能用。
本工具把视频上传到永久素材库, 然后生成一篇「视频卡片」图文草稿, 效果跟视频消息几乎一样。

工作流:
  ① 上传 mp4 → 永久素材库 (add_material?type=video)  ← 已实现
  ② 查询素材 URL (get_material) ← 拿到视频源地址
  ③ 生成嵌视频的 HTML 正文
  ④ 调 /api/draft 创建图文草稿
  ⑤ [人工] 公众号后台「群发」或「发布」

依赖: pip install requests
"""

import argparse
import base64
import json
import os
import sys
import urllib.parse

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
        raise Exception("API Key 无效")
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
        raise Exception("API Key 无效")
    if resp.status_code != 200:
        raise Exception(f"服务器错误 {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def upload_video(server_url: str, api_key: str, video_path: str,
                 title: str, introduction: str, reencode: str, timeout: int) -> dict:
    """上传视频到永久素材库"""
    final_path = video_path
    if reencode != "never":
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from upload_video import maybe_reencode_for_wechat
            final_path, did = maybe_reencode_for_wechat(video_path, mode=reencode)
            if did:
                print(f"  ✅ 自动重编码完成")
        except Exception as e:
            print(f"  ⚠️  重编码跳过: {e}")
    size_mb = os.path.getsize(final_path) / 1024 / 1024
    print(f"  ① 上传视频 ({size_mb:.2f} MB)...")
    return _post_multipart(
        server_url, api_key, "/api/video/upload-permanent",
        final_path, {"title": title, "introduction": introduction}, timeout,
    )


def get_material_url(server_url: str, api_key: str, media_id: str) -> dict:
    """查素材的 down_url"""
    print(f"  ② 查询视频源 URL...")
    return _post_json(server_url, api_key, "/api/video/get-material",
                      {"media_id": media_id, "type": "video"})


def create_video_draft(server_url: str, api_key: str, title: str, html_content: str,
                       cover_path: str = "") -> dict:
    """创建草稿"""
    print(f"  ④ 创建图文草稿...")
    payload = {"title": title, "content": html_content}
    if cover_path and os.path.exists(cover_path):
        with open(cover_path, "rb") as f:
            payload["cover_base64"] = base64.b64encode(f.read()).decode()
        payload["cover_filename"] = os.path.basename(cover_path)
    return _post_json(server_url, api_key, "/api/draft", payload, timeout=120)


def build_video_html(video_url: str, title: str, description: str,
                     extra_intro: str = "", poster: str = "") -> str:
    """生成嵌视频的 HTML 正文 —— 兼容微信编辑器"""
    # 微信对 video 标签限制较多,主流方案是 mpvideo 引用(只能在 mpnews 里)
    # 退而求其次:用 iframe 嵌入微信视频播放页(从 down_url 推断)
    # 最稳:用「mpvideo」引用块 —— 但需要先转群发素材
    # 这里用经典方案: 居中标题 + 视频卡片 + 文字说明
    safe_title = title.replace('"', '&quot;').replace('<', '&lt;')
    safe_desc = description.replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br/>')

    # 视频源 URL 是 down_url,微信里通常用 <iframe> + 微信视频播放页
    # 但 down_url 本身就是 mp.weixin.qq.com 域名,直接 <video src=...> 即可
    if not video_url:
        # 没拿到 url 时的 fallback —— 用一个占位 + 引导用户去素材库
        return f'''
<section style="margin: 20px 0; padding: 20px; background: #f7f7f7; border-radius: 8px; text-align: center;">
  <p style="color: #999; font-size: 14px;">📺 视频已上传至素材库</p>
  <p style="color: #999; font-size: 12px;">在公众号后台「素材管理 → 视频」中可见</p>
</section>
{("<p style='font-size:15px;line-height:1.8;color:#333;'>" + extra_intro + "</p>") if extra_intro else ""}
<p style="font-size:15px;line-height:1.8;color:#333;">{safe_desc}</p>
'''

    # 标准的"视频卡片" 样式
    return f'''
<section data-role="outer" style="max-width: 100%; margin: 0 auto; padding: 0;">
  <section data-role="video" style="margin: 24px 0; text-align: center;">
    <p style="font-size: 18px; font-weight: bold; color: #222; margin-bottom: 16px;">{safe_title}</p>
    <div style="position: relative; padding-bottom: 56.25%; height: 0; overflow: hidden; max-width: 100%; background: #000; border-radius: 8px;">
      <video
        controls
        playsinline
        preload="metadata"
        poster="{poster}"
        style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; border-radius: 8px;"
      >
        <source src="{video_url}" type="video/mp4" />
        您的浏览器不支持 video 标签。
      </video>
    </div>
  </section>
  {("<section style='margin: 20px 0; padding: 16px; background: #fafafa; border-left: 3px solid #07c160; border-radius: 4px;'>" + extra_intro + "</section>") if extra_intro else ""}
  <section style="margin: 20px 0; font-size: 15px; line-height: 1.8; color: #333;">
    <p>{safe_desc}</p>
  </section>
</section>
'''


def main():
    p = argparse.ArgumentParser(
        description="订阅号视频发布方案: 上传 + 查询 URL + 创建嵌视频的图文草稿",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 一条命令完成 (上传 + 查 url + 创建草稿)
  python3 publish_video_article.py --file ep01.mp4 \\
    --title "EP01 主题" --introduction "本期导览" --extra "00:00 开场 / 02:30 技术讨论"

  # 已有 media_id,直接创建草稿
  python3 publish_video_article.py --existing-media-id xxx \\
    --title "EP01" --introduction "..."

  # 自定义封面
  python3 publish_video_article.py --file ep01.mp4 --title "EP01" \\
    --introduction "..." --cover cover.jpg
        """,
    )
    p.add_argument("--server", default=os.getenv("WECHAT_PROXY_URL"))
    p.add_argument("--api-key", default=os.getenv("WECHAT_PROXY_API_KEY"))

    p.add_argument("--file", default="", help="本地视频文件")
    p.add_argument("--existing-media-id", default="",
                   help="跳过上传,直接用已有 media_id")
    p.add_argument("--title", required=True, help="文章标题")
    p.add_argument("--introduction", default="", help="视频简介(用作 description)")
    p.add_argument("--extra", default="",
                   help="额外的文章正文(章节标记/导览/链接等,可选)")

    p.add_argument("--cover", default="", help="封面图本地路径(可选)")
    p.add_argument("--no-upload", action="store_true", help="跳过上传")
    p.add_argument("--no-draft", action="store_true", help="只上传和查 URL,不创建草稿")
    p.add_argument("--reencode", choices=["auto", "always", "never"], default="auto")
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--json", action="store_true", help="只输出 JSON")
    p.add_argument("--print-html", action="store_true",
                   help="打印生成的 HTML 到 stdout(调试用)")

    args = p.parse_args()

    if not args.server:
        sys.exit("错误: 需要 --server 或 .env WECHAT_PROXY_URL")
    if not args.api_key:
        sys.exit("错误: 需要 --api-key 或 .env WECHAT_PROXY_API_KEY")
    if not args.no_upload and not args.file:
        sys.exit("错误: 需要 --file 或 --no-upload + --existing-media-id")

    try:
        # 1. 上传或用已有的 media_id
        media_id = args.existing_media_id
        if not args.no_upload:
            r = upload_video(args.server, args.api_key, args.file,
                             args.title, args.introduction, args.reencode, args.timeout)
            if not r.get("success"):
                raise Exception(f"上传失败: {r.get('error', r)}")
            media_id = r["media_id"]
            print(f"     ✅ media_id (永久素材) = {media_id}")
        else:
            print(f"  ① 跳过上传,使用已有 media_id = {media_id}")

        # 2. 查询 URL
        r = get_material_url(args.server, args.api_key, media_id)
        if not r.get("success"):
            print(f"  ⚠️  查询 URL 失败(将用占位 HTML): {r.get('error', r)}")
            video_url = ""
        else:
            video_url = r.get("down_url") or r.get("url") or ""
            title = r.get("title") or args.title
            desc = r.get("description") or args.introduction
            print(f"     ✅ down_url = {video_url[:80] if video_url else '(空)'}")

        # 3. 生成 HTML
        html = build_video_html(video_url, args.title, args.introduction, args.extra)
        if args.print_html:
            print(html)

        if args.no_draft:
            if args.json:
                print(json.dumps({
                    "success": True,
                    "media_id": media_id,
                    "down_url": video_url,
                    "html_length": len(html),
                }, ensure_ascii=False, indent=2))
            else:
                print(f"\n✅ 视频已就绪 (media_id={media_id})")
                print(f"   down_url: {video_url}")
                print(f"   HTML 长度: {len(html)} 字符")
            return

        # 4. 创建草稿
        r = create_video_draft(args.server, args.api_key, args.title, html, args.cover)
        if not r.get("success"):
            raise Exception(f"创建草稿失败: {r.get('error', r)}")

        draft_media_id = r.get("media_id", "")

        if args.json:
            print(json.dumps({
                "success": True,
                "video_media_id": media_id,
                "down_url": video_url,
                "draft_media_id": draft_media_id,
                "failed_images": r.get("failed_images", []),
            }, ensure_ascii=False, indent=2))
            return

        print(f"\n🎉 完成! 视频图文草稿已创建")
        print(f"   视频 media_id:   {media_id}")
        print(f"   草稿 media_id:   {draft_media_id}")
        print()
        print("📋 接下来:")
        print("   1) 登录公众号后台 → 「内容与互动」→ 「草稿箱」")
        print(f"      找到标题为「{args.title}」的草稿")
        print("   2) 可以预览效果,然后点「保存并群发」")
        print("   ⚠️  订阅号每天只能群发 1 次;若草稿不是今天的,可以定时群发")
        print()
        if r.get("failed_images"):
            print(f"   ⚠️  有 {len(r['failed_images'])} 张图片处理失败(草稿中可能用 data-src 占位)")

    except Exception as e:
        if args.json:
            print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False, indent=2))
        else:
            print(f"\n❌ 失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()