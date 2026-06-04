#!/usr/bin/env python3
"""
微信公众号文章排版工具 - 基于 WeWrite 设计理念
功能：
- Markdown 转微信兼容 HTML
- YAML 主题系统
- CJK 兼容性处理
- 列表转 section（微信原生列表渲染不稳定）
- 外链转脚注
- 暗黑模式支持（data-darkmode-* 属性）
- 容器语法（dialogue/timeline/callout/quote）
- 内联样式 + 微信兼容修复

用法:
  python3 style_html.py --file input.md --theme sspai --output preview.html
  python3 style_html.py --list
"""

import argparse
import re
import os
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Tuple

try:
    import markdown
    from bs4 import BeautifulSoup
    import yaml
except ImportError:
    print("需要安装依赖: pip install markdown beautifulsoup4 pyyaml")
    sys.exit(1)


@dataclass
class Theme:
    """主题定义"""
    name: str
    description: str
    base_css: str
    colors: dict = field(default_factory=dict)
    darkmode: dict = field(default_factory=dict)


@dataclass
class ConvertResult:
    """转换结果"""
    html: str
    title: str
    digest: str
    images: List[str]


def load_theme(name: str, themes_dir: str = None) -> Theme:
    """加载 YAML 主题"""
    if themes_dir is None:
        themes_dir = str(Path(__file__).parent.parent / "themes")

    theme_path = os.path.join(themes_dir, f"{name}.yaml")
    if not os.path.exists(theme_path):
        raise FileNotFoundError(f"主题文件不存在: {theme_path}")

    with open(theme_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return Theme(
        name=data["name"],
        description=data.get("description", ""),
        base_css=data.get("base_css", ""),
        colors=data.get("colors", {}),
        darkmode=data.get("darkmode", {})
    )


def list_themes(themes_dir: str = None) -> List[Tuple[str, str]]:
    """列出可用主题"""
    if themes_dir is None:
        themes_dir = str(Path(__file__).parent.parent / "themes")

    if not os.path.isdir(themes_dir):
        return []

    names = []
    for filename in os.listdir(themes_dir):
        if filename.endswith(".yaml") or filename.endswith(".yml"):
            theme_name = filename.rsplit(".", 1)[0]
            try:
                theme = load_theme(theme_name, themes_dir)
                names.append((theme_name, theme.description))
            except:
                names.append((theme_name, ""))
    return names


def parse_css_to_rules(css_text: str, colors: dict) -> dict:
    """解析 CSS 为 selector -> {property: value} 字典"""
    rules = {}

    def resolve_var(match):
        var_name = match.group(1).strip()
        key = var_name.lstrip("-").replace("-", "_")
        if key in colors:
            return colors[key]
        return match.group(0)

    css_text = re.sub(r'var\(\s*--([a-zA-Z0-9_-]+)\s*\)', resolve_var, css_text)
    rule_pattern = r'([^{}]+)\{([^{}]+)\}'

    for match in re.finditer(rule_pattern, css_text):
        selector_raw = match.group(1).strip()
        props_text = match.group(2).strip()

        skip_chars = [":", "@", ">", "+", "~", "[", "*"]
        if any(c in selector_raw for c in skip_chars):
            continue

        props = {}
        for prop_match in re.finditer(r'([a-zA-z-]+):\s*([^;]+);?', props_text):
            props[prop_match.group(1).strip()] = prop_match.group(2).strip()

        if not props:
            continue

        # 逗号分隔的多选择器拆开单独存储
        for selector in selector_raw.split(","):
            selector = selector.strip()
            if selector:
                rules[selector] = props

    return rules


class WeChatConverter:
    """Markdown → 微信兼容 HTML 转换器（基于 WeWrite 设计）"""

    def __init__(self, theme: Theme):
        self.theme = theme
        self.css_rules = parse_css_to_rules(theme.base_css, theme.colors)

    def convert(self, markdown_text: str) -> ConvertResult:
        """转换 Markdown 为微信兼容 HTML"""
        # 提取标题
        title = self._extract_title(markdown_text)
        markdown_text = self._strip_h1(markdown_text)

        # 预处理容器块
        markdown_text = self._preprocess_containers(markdown_text)

        # 预处理无分隔行的表格
        markdown_text = self._preprocess_tables(markdown_text)

        # CJK 空格修正
        markdown_text = self._fix_cjk_spacing(markdown_text)

        # Markdown → HTML
        html = self._markdown_to_html(markdown_text)

        # 增强代码块
        html = self._enhance_code_blocks(html)

        # 处理图片
        html, images = self._process_images(html)

        # CJK 标点修正
        html = self._fix_cjk_bold_punctuation(html)

        # 列表转 section
        html = self._convert_lists_to_sections(html)

        # 外链转脚注
        html = self._convert_links_to_footnotes(html)

        # 应用内联样式
        html = self._apply_inline_styles(html)

        # 微信兼容性修复
        html = self._apply_wechat_fixes(html)

        # 暗黑模式
        html = self._inject_darkmode(html)

        # 生成摘要
        digest = self._generate_digest(html)

        return ConvertResult(html=html, title=title, digest=digest, images=images)

    def convert_file(self, input_path: str) -> ConvertResult:
        """转换 Markdown 文件"""
        path = Path(input_path)
        if not path.exists():
            raise FileNotFoundError(f"输入文件不存在: {input_path}")
        text = path.read_text(encoding="utf-8")
        return self.convert(text)

    def _extract_title(self, text: str) -> str:
        """提取第一个 H1 标题"""
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("## "):
                return stripped[2:].strip()
        return ""

    def _strip_h1(self, text: str) -> str:
        """移除 H1 行 - 微信有单独的标题字段"""
        lines = []
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("## "):
                continue
            lines.append(line)
        return "\n".join(lines)

    def _markdown_to_html(self, text: str) -> str:
        """Markdown → HTML。不使用 codehilite：其生成的 <span style="color:..."> 在微信客户端
        会被不稳定地过滤，改为输出干净的 <pre><code> 块，由主题 CSS 统一着色。"""
        extensions = [
            "markdown.extensions.fenced_code",
            "markdown.extensions.tables",
            "markdown.extensions.nl2br",
            "markdown.extensions.sane_lists",
        ]
        md = markdown.Markdown(extensions=extensions)
        return md.convert(text)

    def _enhance_code_blocks(self, html: str) -> str:
        """将代码块换行转为 <br>、缩进空格转为 &nbsp;，确保微信客户端正确渲染。
        微信不支持 white-space: pre-wrap，必须用显式标签替代空白符。"""
        soup = BeautifulSoup(html, "html.parser")
        for pre in soup.find_all("pre"):
            code = pre.find("code")
            if code:
                # 提取语言标签
                for cls in code.get("class", []):
                    if cls.startswith("language-"):
                        pre["data-lang"] = cls.replace("language-", "")
                        break

                text = code.get_text()
                code.clear()

                lines = text.split('\n')
                # 去掉首尾多余空行
                while lines and lines[0] == '':
                    lines = lines[1:]
                while lines and lines[-1] == '':
                    lines = lines[:-1]

                for i, line in enumerate(lines):
                    if i > 0:
                        code.append(soup.new_tag('br'))
                    # 展开 tab，再把行首空格换成不换行空格（U+00A0）供 WeChat 正确渲染缩进
                    expanded = line.expandtabs(4)
                    stripped = expanded.lstrip(' ')
                    leading = len(expanded) - len(stripped)
                    code.append('\u00a0' * leading + stripped)

        return str(soup)

    def _process_images(self, html: str) -> Tuple[str, List[str]]:
        """处理图片"""
        soup = BeautifulSoup(html, "html.parser")
        images = []
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if src:
                images.append(src)
            existing = img.get("style", "")
            if "max-width" not in existing:
                additions = "max-width: 100%; height: auto; display: block; margin: 24px auto"
                img["style"] = f"{existing}; {additions}" if existing else additions
        return str(soup), images

    def _apply_inline_styles(self, html: str) -> str:
        """应用主题样式为内联属性（按 CSS 特异性升序处理，确保更具体的规则覆盖一般规则）"""
        soup = BeautifulSoup(html, "html.parser")

        def specificity(selector: str) -> int:
            # 简单特异性：按空格分隔的部分数量计算
            return len(selector.split())

        sorted_rules = sorted(
            ((sel, styles) for sel, styles in self.css_rules.items() if sel.strip() != "body"),
            key=lambda x: specificity(x[0])
        )

        for selector, styles in sorted_rules:
            try:
                elements = soup.select(selector)
            except Exception:
                continue

            for elem in elements:
                existing = elem.get("style", "")
                style_dict = {}
                if existing:
                    for item in existing.split(";"):
                        if ":" in item:
                            key, val = item.split(":", 1)
                            style_dict[key.strip()] = val.strip()
                # 更具体的规则（后处理）直接覆盖同名属性
                style_dict.update(styles)
                elem["style"] = "; ".join(f"{k}: {v}" for k, v in style_dict.items())
        return str(soup)

    def _apply_wechat_fixes(self, html: str) -> str:
        """微信兼容性修复"""
        soup = BeautifulSoup(html, "html.parser")
        text_color = self.theme.colors.get("text", "#333333")

        for p in soup.find_all("p"):
            style = p.get("style", "")
            if "color" not in style:
                p["style"] = f"{style}; color: {text_color}" if style else f"color: {text_color}"

        for pre in soup.find_all("pre"):
            style = pre.get("style", "")
            if "white-space" not in style:
                pre["style"] = f"{style}; white-space: pre-wrap; word-wrap: break-word" if style else "white-space: pre-wrap; word-wrap: break-word"
            # WeChat 不继承 white-space，需在 <code> 上显式设置
            code = pre.find("code")
            if code:
                code_style = code.get("style", "")
                if "white-space" not in code_style:
                    code["style"] = f"{code_style}; white-space: pre-wrap; word-wrap: break-word; word-break: break-all" if code_style else "white-space: pre-wrap; word-wrap: break-word; word-break: break-all"

        return str(soup)

    def _fix_cjk_spacing(self, text: str) -> str:
        """中英混排自动加空格"""
        cjk = r'[\u4e00-\u9fff\u3400-\u4dbf\u3000-\u303f\uff00-\uffef]'
        latin = r'[A-Za-z0-9]'
        lines = text.split('\n')
        result = []
        in_code_block = False

        for line in lines:
            if line.strip().startswith('```'):
                in_code_block = not in_code_block
            if not in_code_block:
                line = re.sub(f'({cjk})({latin})', r'\1 \2', line)
                line = re.sub(f'({latin})({cjk})', r'\1 \2', line)
            result.append(line)
        return '\n'.join(result)

    def _fix_cjk_bold_punctuation(self, html: str) -> str:
        """中文标点放在 strong 外面"""
        pattern = r'(<strong>)(.*?)([，。！？；：、]+)(</strong>)'
        return re.sub(pattern, r'\1\2\4\3', html)

    def _convert_lists_to_sections(self, html: str) -> str:
        """列表转 section（微信原生列表渲染不稳定）"""
        soup = BeautifulSoup(html, "html.parser")
        text_color = self.theme.colors.get("text", "#333333")
        primary = self.theme.colors.get("primary", "#2563eb")

        for ul in soup.find_all("ul"):
            section = soup.new_tag("section")
            for li in ul.find_all("li", recursive=False):
                item = soup.new_tag("section")
                item["style"] = f"display: flex; align-items: flex-start; margin-bottom: 8px; color: {text_color}"
                bullet = soup.new_tag("span")
                bullet["style"] = f"color: {primary}; margin-right: 8px; flex-shrink: 0; font-size: 18px; line-height: 1.6"
                bullet.string = "•"
                content = soup.new_tag("span")
                content["style"] = "flex: 1"
                for child in list(li.children):
                    content.append(child.extract() if hasattr(child, 'extract') else str(child))
                item.append(bullet)
                item.append(content)
                section.append(item)
            ul.replace_with(section)

        for ol in soup.find_all("ol"):
            section = soup.new_tag("section")
            for num, li in enumerate(ol.find_all("li", recursive=False), 1):
                item = soup.new_tag("section")
                item["style"] = f"display: flex; align-items: flex-start; margin-bottom: 8px; color: {text_color}"
                number = soup.new_tag("span")
                number["style"] = f"color: {primary}; margin-right: 8px; flex-shrink: 0; font-weight: 700; line-height: 1.8"
                number.string = f"{num}."
                content = soup.new_tag("span")
                content["style"] = "flex: 1"
                for child in list(li.children):
                    content.append(child.extract() if hasattr(child, 'extract') else str(child))
                item.append(number)
                item.append(content)
                section.append(item)
            ol.replace_with(section)

        return str(soup)

    def _convert_links_to_footnotes(self, html: str) -> str:
        """外链转脚注"""
        soup = BeautifulSoup(html, "html.parser")
        footnotes = []
        counter = 0
        primary = self.theme.colors.get("primary", "#2563eb")

        for a in soup.find_all("a"):
            href = a.get("href", "")
            if not href or href.startswith("#"):
                continue

            counter += 1
            text = a.get_text()
            footnotes.append((counter, text, href))

            sup = soup.new_tag("sup")
            sup_link = soup.new_tag("span")
            sup_link["style"] = f"color: {primary}; font-size: 12px"
            sup_link.string = f"[{counter}]"
            sup.append(sup_link)
            a.replace_with(text, sup)

        if footnotes:
            hr = soup.new_tag("hr")
            hr["style"] = "border: none; border-top: 1px solid #e5e5e5; margin: 32px 0 16px"
            soup.append(hr)
            ref_title = soup.new_tag("p")
            ref_title["style"] = "font-size: 13px; color: #999999; margin-bottom: 8px; font-weight: 700"
            ref_title.string = "参考链接"
            soup.append(ref_title)
            for num, text, href in footnotes:
                ref = soup.new_tag("p")
                ref["style"] = "font-size: 12px; color: #999999; margin: 2px 0; word-break: break-all"
                ref.string = f"[{num}] {text}: {href}"
                soup.append(ref)

        return str(soup)

    def _inject_darkmode(self, html: str) -> str:
        """添加暗黑模式支持"""
        darkmode = self.theme.colors.get("darkmode", {})
        if not darkmode:
            return html

        soup = BeautifulSoup(html, "html.parser")
        dm_text = darkmode.get("text", "#c8c8c8")
        dm_bg = darkmode.get("background", "#1e1e1e")
        dm_primary = darkmode.get("primary", "#6aadff")
        dm_code_bg = darkmode.get("code_bg", "#2d2d2d")
        dm_code_color = darkmode.get("code_color", "#d4d4d4")
        dm_quote_bg = darkmode.get("quote_bg", "#2a2a2a")

        for tag_name in ("p", "span", "section"):
            for elem in soup.find_all(tag_name):
                style = elem.get("style", "")
                if "color" in style:
                    elem["data-darkmode-color"] = dm_text
                    elem["data-darkmode-bgcolor"] = "transparent"

        dm_heading = darkmode.get("text", "#e0e0e0")
        for tag_name in ("h1", "h2", "h3", "h4"):
            for elem in soup.find_all(tag_name):
                elem["data-darkmode-color"] = dm_heading
                elem["data-darkmode-bgcolor"] = "transparent"

        for pre in soup.find_all("pre"):
            pre["data-darkmode-bgcolor"] = dm_code_bg
            pre["data-darkmode-color"] = dm_code_color
        for code in soup.find_all("code"):
            code["data-darkmode-color"] = dm_code_color

        for bq in soup.find_all("blockquote"):
            bq["data-darkmode-bgcolor"] = dm_quote_bg
            bq["data-darkmode-color"] = dm_text

        for strong in soup.find_all("strong"):
            strong["data-darkmode-color"] = dm_primary

        return str(soup)

    def _preprocess_tables(self, text: str) -> str:
        """为无分隔行的 Markdown 表格插入分隔行，使 tables 扩展能识别"""
        lines = text.split('\n')
        result = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if re.match(r'^\s*\|', line):
                block = []
                while i < len(lines) and re.match(r'^\s*\|', lines[i]):
                    block.append(lines[i])
                    i += 1
                has_sep = any(re.match(r'^\s*\|[\s\-:|]+\|\s*$', b) for b in block)
                if not has_sep and len(block) >= 1:
                    cols = block[0].count('|') - 1
                    separator = '|' + '|'.join([' --- '] * max(cols, 1)) + '|'
                    block.insert(1, separator)
                result.extend(block)
            else:
                result.append(line)
                i += 1
        return '\n'.join(result)

    def _preprocess_containers(self, text: str) -> str:
        """预处理容器语法"""
        text = self._process_dialogue(text)
        text = self._process_timeline(text)
        text = self._process_callout(text)
        text = self._process_quote_block(text)
        return text

    def _process_dialogue(self, text: str) -> str:
        """对话框容器"""
        primary = self.theme.colors.get("primary", "#2563eb")

        def replace_dialogue(match):
            content = match.group(1).strip()
            bubbles = []
            for line in content.split('\n'):
                line = line.strip()
                if not line:
                    continue
                if line.startswith('> '):
                    msg = line[2:].strip()
                    bubbles.append(f'<section style="display: flex; justify-content: flex-end; margin-bottom: 12px">'
                                   f'<section style="background: {primary}; color: white; padding: 10px 14px; border-radius: 12px 12px 2px 12px; max-width: 80%; font-size: 15px; line-height: 1.6">{msg}</section></section>')
                else:
                    bubbles.append(f'<section style="display: flex; justify-content: flex-start; margin-bottom: 12px">'
                                   f'<section style="background: #f3f4f6; color: #333; padding: 10px 14px; border-radius: 12px 12px 12px 2px; max-width: 80%; font-size: 15px; line-height: 1.6">{line}</section></section>')
            return '\n'.join(bubbles)

        return re.sub(r':::dialogue\n(.*?)\n:::', replace_dialogue, text, flags=re.DOTALL)

    def _process_timeline(self, text: str) -> str:
        """时间线容器"""
        primary = self.theme.colors.get("primary", "#2563eb")

        def replace_timeline(match):
            content = match.group(1).strip()
            items = []
            for line in content.split('\n'):
                line = line.strip()
                if not line:
                    continue
                items.append(
                    f'<section style="display: flex; margin-bottom: 16px">'
                    f'<section style="flex-shrink: 0; width: 12px; display: flex; flex-direction: column; align-items: center">'
                    f'<section style="width: 10px; height: 10px; border-radius: 50%; background: {primary}; margin-top: 6px"></section>'
                    f'<section style="width: 2px; flex: 1; background: #e5e7eb; margin-top: 4px"></section>'
                    f'</section>'
                    f'<section style="flex: 1; padding-left: 12px; padding-bottom: 8px; font-size: 15px; line-height: 1.7">{line}</section>'
                    f'</section>'
                )
            return '\n'.join(items)

        return re.sub(r':::timeline\n(.*?)\n:::', replace_timeline, text, flags=re.DOTALL)

    def _process_callout(self, text: str) -> str:
        """提示框容器"""
        colors_map = {
            "tip": ("#059669", "#ecfdf5", "💡"),
            "warning": ("#d97706", "#fffbeb", "⚠️"),
            "info": ("#2563eb", "#eff6ff", "ℹ️"),
            "danger": ("#dc2626", "#fef2f2", "🚨"),
        }

        def replace_callout(match):
            ctype = match.group(1).strip().lower()
            content = match.group(2).strip()
            color, bg, icon = colors_map.get(ctype, colors_map["info"])
            return (f'<section style="background: {bg}; border-left: 4px solid {color}; '
                    f'padding: 14px 16px; border-radius: 4px; margin: 16px 0; font-size: 15px; line-height: 1.7">'
                    f'<section style="font-weight: 700; color: {color}; margin-bottom: 6px">{icon} {ctype.upper()}</section>'
                    f'{content}</section>')

        return re.sub(r':::callout\s+(\w+)\n(.*?)\n:::', replace_callout, text, flags=re.DOTALL)

    def _process_quote_block(self, text: str) -> str:
        """引用块容器"""
        primary = self.theme.colors.get("primary", "#2563eb")

        def replace_quote(match):
            content = match.group(1).strip()
            return (f'<section style="margin: 24px 0; padding: 20px 24px; border-left: 4px solid {primary}; '
                    f'background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%); border-radius: 0 8px 8px 0">'
                    f'<section style="font-size: 18px; line-height: 1.8; color: #333; font-style: italic">'
                    f'"{content}"</section></section>')

        return re.sub(r':::quote\n(.*?)\n:::', replace_quote, text, flags=re.DOTALL)

    def _generate_digest(self, html: str, max_bytes: int = 120) -> str:
        """生成摘要"""
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()

        ellipsis = "..."
        ellipsis_bytes = len(ellipsis.encode("utf-8"))
        target_bytes = max_bytes - ellipsis_bytes

        encoded = text.encode("utf-8")
        if len(encoded) <= max_bytes:
            return text

        truncated = encoded[:target_bytes].decode("utf-8", errors="ignore").rstrip()
        return truncated + ellipsis


def preview_html(body_html: str, theme: Theme) -> str:
    """生成完整 HTML 预览"""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>预览</title>
    <style>
{theme.base_css}
    </style>
</head>
<body>
    {body_html}
</body>
</html>"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='微信公众号文章排版工具')
    parser.add_argument('--content', help='HTML 内容')
    parser.add_argument('--file', help='Markdown 文件输入')
    parser.add_argument('--theme', default='professional-clean', help='主题名称')
    parser.add_argument('--output', help='输出文件')
    parser.add_argument('--list', action='store_true', help='列出所有主题')

    args = parser.parse_args()

    if args.list:
        themes_dir = str(Path(__file__).parent.parent / "themes")
        themes = list_themes(themes_dir)
        print("可用主题：")
        for name, desc in themes:
            print(f"  {name:24s} - {desc}")

    elif args.file:
        converter = WeChatConverter(load_theme(args.theme))
        result = converter.convert_file(args.file)
        full_html = preview_html(result.html, converter.theme)
        output = args.output or args.file.replace('.md', '_styled.html').replace('.html', '_styled.html')
        Path(output).write_text(full_html, encoding="utf-8")
        print(f"标题: {result.title}")
        print(f"摘要: {result.digest}")
        print(f"图片: {len(result.images)} 张")
        print(f"已保存到: {output}")

    elif args.content:
        converter = WeChatConverter(load_theme(args.theme))
        result = converter.convert(args.content)
        print(result.html)

    else:
        parser.print_help()