---
name: wechat-styler
description: 微信公众号文章排版工具，支持多种专业主题、内联样式和微信兼容性处理
triggers:
  - wechat styler
  - 微信公众号 排版
  - 文章样式
---

# Wechat Styler - 微信公众号文章排版工具

基于 [WeWrite](https://github.com/oaker-io/wewrite) 设计理念的微信公众号文章排版工具。

## 功能

| 功能 | 说明 |
|-----|------|
| **Markdown 转微信兼容 HTML** | 支持表格、代码块、列表等 |
| **YAML 主题系统** | 主题定义与代码分离，便于管理 |
| **CJK 兼容性处理** | 中英混排自动加空格、标点位置修正 |
| **列表转 section** | 微信原生列表渲染不稳定，用 section 更可靠 |
| **外链转脚注** | 微信不允许外部链接跳转，自动转脚注 |
| **暗黑模式支持** | data-darkmode-* 属性，微信自动适配 |
| **BeautifulSoup 解析** | 比正则更可靠的 HTML 处理 |
| **容器语法** | 支持 :::dialogue, :::timeline, :::callout, :::quote |
| **代码块换行修复** | 微信不支持 white-space: pre-wrap，自动将 `\n` 转为 `<br>`，缩进转为 `&nbsp;` |
| **无标题行表格修复** | 自动检测缺少分隔行的 Markdown 表格并插入 `\|---\|`，确保正确渲染为 HTML 表格 |

## 可用主题

| 主题 | 配色 | 适用文章类型 |
|-----|------|------|
| `sspai` | 暖白底 + 红色点缀 | **安利/种草文**（默认推荐）|
| `deep-tech` | 浅灰底 + 深青色 | **深度技术解析、源码解读** |
| `data-compare` | 白底 + 靛紫色，表格样式精细 | **横向对比选型** |
| `tutorial-steps` | 白底 + 绿色，步骤/列表特化 | **教程实战** |
| `professional-clean` | 白底 + 蓝色，万能款 | 通用技术文章 |
| `warm-editorial` | 暖色调 | 生活/情感类内容 |

### 主题与 wechat-tech-article 模板对照

| wechat-tech-article 风格 | 推荐主题 |
|---|---|
| template-1 安利/种草文 | `sspai` |
| template-2 深度技术解析 | `deep-tech` |
| template-3 横向对比选型 | `data-compare` |
| template-4 教程实战 | `tutorial-steps` |
| template-5 源码解读 | `deep-tech` |

## 使用方法

```bash
# 列出所有主题
python3 ~/.claude/skills/wechat-styler/scripts/style_html.py --list

# 转换 Markdown 文件
python3 ~/.claude/skills/wechat-styler/scripts/style_html.py \
  --file article.md \
  --theme sspai \
  --output preview.html
```

## 容器语法（高级）

```markdown
:::dialogue
> 这是回复气泡
这是普通气泡
:::

:::timeline
第一步
第二步
第三步
:::

:::callout tip
这是提示框
:::

:::quote
这是一段引用
:::
```

## 预览文件

- /workspace/new_preview_sspai.html

## 技术要点

1. **内联样式** - 微信会过滤 `<style>` 标签，所有样式必须内联
2. **图片 URL** - 必须使用 `https://`，`http://` 不会显示
3. **列表** - 用 section + span 替代原生 ul/ol
4. **外链** - 自动转为脚注，微信会阻止外部链接跳转
5. **CJK** - 中英混排时自动加空格避免粘连
6. **暗黑模式** - data-darkmode-* 属性告诉微信如何适配深色模式
7. **代码块换行** - 微信客户端完全忽略 `white-space: pre-wrap`，必须将换行符转为 `<br>` 标签、缩进空格转为 U+00A0（不换行空格），由 `_enhance_code_blocks` 处理
8. **表格识别** - 标准 Markdown 表格需要分隔行（`|---|`），无分隔行时 python-markdown 不识别，由 `_preprocess_tables` 自动插入