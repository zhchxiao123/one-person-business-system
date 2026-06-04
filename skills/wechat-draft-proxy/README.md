# wechat-draft-proxy

微信公众号草稿箱创建工具（**Node.js 重写版**）。

通过固定 IP 代理服务器创建微信公众号草稿，无需客户端配置微信 IP 白名单。

**v2.0**：纯 Node.js 实现，零运行时依赖。

## 快速开始

阅读完整文档、触发条件、参数表、推荐工作流，请直接查看：

**→ [SKILL.md](SKILL.md)**

## 核心命令

```bash
# 已排版 HTML（推荐）
node ~/.grok/skills/wechat-draft-proxy/scripts/create_draft.js \
  --title "文章标题" --file styled.html --html

# 带封面 + 原文链接
node scripts/create_draft.js \
  --title "标题" \
  --file article.html --html \
  --cover-path cover.jpg \
  --content-source-url "https://example.com/origin"
```

## 目录结构

```
wechat-draft-proxy/
├── SKILL.md                 # 完整使用文档（Agent 入口）
├── README.md                # 本文件
├── package.json             # Node 项目定义
├── requirements.txt         # 旧版 Python 依赖（过渡期保留）
└── scripts/
    ├── create_draft.js      # ✅ 新版核心 CLI（推荐）
    └── create_draft.py      # 旧版 Python CLI（保留兼容）
```

## 相关组件

- 代理服务端：`/workspace/wechat-proxy-server/`（Docker 一键部署，推荐 Node.js 纯净版）
- 搭配排版：`wechat-styler` skill（强烈推荐先排版再发布）

## License

MIT
