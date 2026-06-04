#!/usr/bin/env python3
"""
微信公众号草稿箱创建工具（代理服务器版）
通过固定 IP 的代理服务器中转，无需在本机配置微信 IP 白名单。

配置优先级:
  1. 命令行 --server / --api-key
  2. 技能目录 .env 文件（cp .env.example .env 后编辑）
  3. 环境变量 WECHAT_PROXY_URL / WECHAT_PROXY_API_KEY

用法:
  python3 create_draft.py --title "标题" --file article.html --html
  python3 create_draft.py --title "标题" --file article.html --html --cover-path cover.jpg

作为标准 skill 使用时推荐从 skills/wechat-draft-proxy/ 目录调用（或安装到 ~/.grok/skills 或 ~/.claude/skills）。
"""

import argparse
import base64
import json
import os
import re
import sys

try:
    import requests
except ImportError:
    print("需要安装依赖: pip install -r requirements.txt (或 pip install requests)")
    sys.exit(1)


# ==================== .env 自动加载（零额外依赖，匹配 content-factory 风格） ====================
def _load_env_manual(env_path: str) -> None:
    """极简 .env 解析器（当没有 python-dotenv 时使用）"""
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
                # 不覆盖已存在的环境变量（shell export 优先）
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        pass


def load_proxy_env() -> None:
    """从 wechat-draft-proxy 根目录的 .env 加载配置（仅填充未设置的变量）"""
    # scripts/ 的父目录即 skill 根目录
    skill_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_file = os.path.join(skill_root, ".env")
    if not os.path.exists(env_file):
        return

    # 优先尝试 python-dotenv（用户可选安装）
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(dotenv_path=env_file, override=False)
    except ImportError:
        _load_env_manual(env_file)


# 导入时自动加载（最常见直接运行场景）
load_proxy_env()


# wechat-styler 路径（用于 Markdown → HTML 转换）
_STYLER_SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "wechat-styler", "scripts"
)
_STYLER_THEMES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "wechat-styler", "themes"
)


def markdown_to_html(markdown_text: str, theme: str = "professional-clean") -> str:
    if os.path.isdir(_STYLER_SCRIPTS_DIR):
        try:
            if _STYLER_SCRIPTS_DIR not in sys.path:
                sys.path.insert(0, _STYLER_SCRIPTS_DIR)
            from style_html import WeChatConverter, load_theme  # type: ignore
            converter = WeChatConverter(load_theme(theme, _STYLER_THEMES_DIR))
            result = converter.convert(markdown_text)
            print(f"  已使用 wechat-styler 排版（主题：{theme}）")
            return result.html
        except Exception as e:
            print(f"  wechat-styler 调用失败（{e}），fallback 到内置转换")

    # 内置简单转换（仅兜底）
    html = markdown_text
    for i in range(6, 0, -1):
        html = re.sub(rf'^#{i}\s+(.+)$', rf'<h{i}>\1</h{i}>', html, flags=re.MULTILINE)
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
    html = re.sub(r'`(.+?)`', r'<code>\1</code>', html)
    html = re.sub(r'!\[(.+?)\]\((.+?)\)', r'<img src="\2" alt="\1" />', html)
    html = html.replace('\n\n', '</p><p>')
    return f'<p>{html}</p>'


def create_draft_via_proxy(
    server_url: str,
    api_key: str,
    title: str,
    content: str,
    cover_url: str = "",
    cover_path: str = "",
    content_source_url: str = "",
) -> dict:
    """向代理服务器发送草稿创建请求。"""
    payload: dict = {
        "title": title,
        "content": content,
        "content_source_url": content_source_url,
    }

    if cover_path and os.path.exists(cover_path):
        with open(cover_path, "rb") as f:
            payload["cover_base64"] = base64.b64encode(f.read()).decode()
        payload["cover_filename"] = os.path.basename(cover_path)
        print(f"封面图（本地文件）: {cover_path}")
    elif cover_url:
        payload["cover_url"] = cover_url
        print(f"封面图（URL）: {cover_url}")

    endpoint = server_url.rstrip("/") + "/api/draft"
    resp = requests.post(
        endpoint,
        json=payload,
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        timeout=120,
    )

    if resp.status_code == 401:
        raise Exception("API Key 无效，请检查 PROXY_API_KEY 配置")
    if resp.status_code != 200:
        raise Exception(f"服务器错误 {resp.status_code}: {resp.text[:200]}")

    return resp.json()


def main():
    parser = argparse.ArgumentParser(description="通过代理服务器创建微信公众号草稿")
    parser.add_argument("--server", default=os.getenv("WECHAT_PROXY_URL"), help="代理服务器地址（优先级最高，覆盖 .env）")
    parser.add_argument("--api-key", default=os.getenv("WECHAT_PROXY_API_KEY"), help="代理服务器 API Key（优先级最高，覆盖 .env）")
    parser.add_argument("--title", required=True, help="文章标题")
    parser.add_argument("--content", default="", help="文章内容（Markdown 或 HTML）")
    parser.add_argument("--file", default="", help="从文件读取文章内容（优先级高于 --content）")
    parser.add_argument("--html", action="store_true", help="内容已是排版好的 HTML，跳过 Markdown 转换")
    parser.add_argument("--theme", default="professional-clean", help="排版主题（--html 时忽略）")
    parser.add_argument("--cover-url", default="", help="封面图 URL")
    parser.add_argument("--cover-path", default="", help="封面图本地路径（优先级高于 URL）")
    parser.add_argument("--content-source-url", default="", help="原文链接")

    args = parser.parse_args()

    if not args.server:
        print("错误: 需要代理服务器地址（--server 或 .env / WECHAT_PROXY_URL）")
        print("提示: cd ~/.grok/skills/wechat-draft-proxy && cp .env.example .env 然后编辑填写")
        sys.exit(1)
    if not args.api_key:
        print("错误: 需要 API Key（--api-key 或 .env / WECHAT_PROXY_API_KEY）")
        print("提示: cd ~/.grok/skills/wechat-draft-proxy && cp .env.example .env 然后编辑填写")
        sys.exit(1)

    # 读取内容
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            raw_content = f.read()
    elif args.content:
        raw_content = args.content
    else:
        print("错误: 需要通过 --content 或 --file 提供文章内容")
        sys.exit(1)

    # Markdown → HTML（如需要）
    if args.html:
        html_content = raw_content
        print("已跳过 Markdown 转换（--html 模式）")
    else:
        print(f"转换 Markdown（主题：{args.theme}）...")
        html_content = markdown_to_html(raw_content, theme=args.theme)

    # 如果是完整 HTML 文件，提取 <body> 内容
    if "<body>" in html_content and "</body>" in html_content:
        import re as _re
        m = _re.search(r"<body>(.*?)</body>", html_content, _re.DOTALL)
        if m:
            html_content = m.group(1).strip()
            print("已从完整 HTML 中提取 <body> 内容")

    print(f"正在通过代理服务器创建草稿...")
    result = create_draft_via_proxy(
        server_url=args.server,
        api_key=args.api_key,
        title=args.title,
        content=html_content,
        cover_url=args.cover_url,
        cover_path=args.cover_path,
        content_source_url=args.content_source_url,
    )

    if result.get("success"):
        print(f"\n✅ 成功! 草稿已创建!")
        print(f"media_id: {result['media_id']}")
        if result.get("failed_images"):
            print(f"\n⚠️  {len(result['failed_images'])} 张图片处理失败:")
            for item in result["failed_images"]:
                print(f"  - {item['url']}: {item['error']}")
        print("\n请到微信公众号后台 -> 内容与互动 -> 草稿箱 查看")
    else:
        print(f"\n❌ 创建失败: {result.get('error', result)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
