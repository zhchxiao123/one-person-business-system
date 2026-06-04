---
name: design-doc-html
description: >
  Generate a single-file HTML design showcase document with left sidebar navigation and paginated
  slides — the kind that makes a technical spec or architecture RFC look like a polished product
  presentation. Use this skill whenever a user wants to: create a design doc / RFC / tech spec
  in HTML, turn a document outline or topic into a beautiful slide-based showcase, generate an
  architecture presentation as a self-contained HTML file, replace a PPT for technical review,
  or build an interactive HTML document with Mermaid diagrams and structured tables.
  Trigger on phrases like: "帮我做成设计文档", "生成HTML设计展台", "做成HTML格式的设计文档",
  "RFC文档", "架构展示文档", "技术评审文档", "PPT替代", "design doc html", "make a design doc",
  "create a tech spec as HTML", "design showcase", "architecture doc", "turn this into a slide deck".
  Even when the user doesn't say "HTML" explicitly but clearly wants a polished, navigable design
  document — use this skill.
---

# Design Doc HTML Generator

Generate a beautiful, self-contained HTML file: left sidebar with slide navigation, paginated
content area, Mermaid diagram support, and a full component library for technical content.

## Template

Read `assets/html_shell.html` for the complete boilerplate (CSS, JS, HTML shell with placeholder
comments). You will fill in the placeholders to produce the final HTML file.

**Placeholders to replace:**
| Placeholder | What to put |
|---|---|
| `<!-- DOC_TITLE -->` | `<title>` tag content (e.g. project + "设计文档") |
| `<!-- SIDEBAR_TITLE -->` | Short project/system name |
| `<!-- SIDEBAR_SUBTITLE -->` | One-line subtitle (e.g. "可观测性设计文档展台") |
| `<!-- NAV_ITEMS -->` | One `<li class="nav-item">` per slide |
| `<!-- SLIDES_HERE -->` | All `<section class="slide">` elements |

## Generation Process

1. **Understand the content** — what system/topic, what dimensions to cover.
2. **Plan slides** — aim for 8–16 slides. Start with a cover slide (overview/welcome), end with roadmap or future work if appropriate. One topic per slide; don't pack too much.
3. **Read `assets/html_shell.html`** — copy it, then fill in all five placeholders.
4. **Output a single `.html` file** to the project directory (or `./output.html` if no obvious location).
5. Tell the user the file path and remind them: keyboard ← → arrows navigate slides.

Slide count and nav items **must match exactly**. If you have 12 slides, you need exactly 12 `<li>` nav items.

---

## Component Reference

Use the right component for the right content. Each section below shows the HTML pattern.

### Cover Slide (Slide 0 — always first)

```html
<section class="slide">
  <div class="slide-content" style="padding-top: 60px;">
    <h1>系统名称 设计文档</h1>
    <p class="desc">一句话概括这份文档的目的和覆盖范围，突出关键技术决策或设计维度。</p>
    <div style="margin-top:100px;text-align:center;padding:40px;background:#f8fafc;border-radius:16px;border:1px dashed #cbd5e1;">
      <div style="font-size:4.5rem;color:#cbd5e1;margin-bottom:20px;">📊</div>
      <h3 style="color:#475569;font-weight:500;margin:0;">欢迎阅览，请从左侧提纲或底部按钮开始浏览文档</h3>
    </div>
  </div>
</section>
```

### Normal Slide Structure

Every non-cover slide follows this pattern:
```html
<section class="slide">
  <div class="slide-content">
    <h2>章节标题</h2>
    <p class="desc">该页的核心说明，1–2句话。</p>
    <!-- content components below -->
  </div>
</section>
```

The `h2` automatically gets a blue left-bar accent via CSS — no extra markup needed.

---

### Design Table (`.design-table`)
Use for: spec comparisons, goal/non-goal lists, API tables, decision matrices, data models.

```html
<div class="diagram-card roadmap-card">
  <table class="design-table">
    <thead><tr><th>列A</th><th>列B</th><th>列C</th></tr></thead>
    <tbody>
      <tr>
        <td><b>行标题</b></td>
        <td>内容，可用 <code>inline code</code></td>
        <td><span class="status-pill done">已完成</span></td>
      </tr>
    </tbody>
  </table>
</div>
```

### Roadmap Table (`.roadmap-table`)
Use for: phased delivery plans, weekly schedules. Has indigo header and week/time cell helpers.

```html
<div class="diagram-card roadmap-card">
  <table class="roadmap-table">
    <thead><tr><th>阶段</th><th>时间窗口</th><th>核心工作</th><th>里程碑</th></tr></thead>
    <tbody>
      <tr>
        <td class="roadmap-week-cell">第一周<br/>阶段名称</td>
        <td class="roadmap-time-cell">06/09 - 06/15</td>
        <td>具体工作内容描述。</td>
        <td>M1：交付物描述。</td>
      </tr>
    </tbody>
  </table>
</div>
```

### Mermaid Diagrams (`.mermaid` inside `.diagram-card`)
Use for: architecture graphs, sequence flows, flowcharts, state machines.

```html
<div class="diagram-card">
  <div class="mermaid">
  flowchart LR
      A["组件A"] --> B["组件B"]
      B --> C["组件C"]
  </div>
</div>
```

Supported diagram types: `flowchart`, `graph`, `sequenceDiagram`, `stateDiagram-v2`, `erDiagram`.

For wide sequence diagrams, add the helper class:
```html
<div class="mermaid execution-sequence">
sequenceDiagram
    ...
</div>
```
And add this CSS rule inside a `<style>` tag on that slide:
```html
<style>
.execution-sequence { justify-content: flex-start; min-width: 1120px; }
.execution-sequence svg { max-width: none !important; min-width: 1120px; height: auto; }
</style>
```

### Code Block (`.code-block`)
Use for: config snippets, data schemas, command examples, struct definitions.

```html
<pre class="code-block">key: value
another_key: another_value
list:
  - item1
  - item2</pre>
```

### Collapsible Detail Panels (`.detail-panel`)
Use for: supplementary content, expanded definitions, optional deep-dives.

```html
<div class="diagram-card roadmap-card">
  <details class="detail-panel" open>
    <summary>展开：核心概念</summary>
    <div class="detail-panel-content">
      <ul>
        <li><b>术语A</b>：定义说明。</li>
        <li><b>术语B</b>：定义说明。</li>
      </ul>
    </div>
  </details>
  <details class="detail-panel">
    <summary>展开：更多内容</summary>
    <div class="detail-panel-content">...</div>
  </details>
</div>
```

### Requirement Cards (`.req-group` / `.req-item`)
Use for: requirement dimensions, problem statements, design principles. Best for 2–4 groups, each with 1–3 items.

```html
<div class="req-group">
  <h3 class="req-group-title">🎯 维度一：标题</h3>
  <div class="requirements-list">
    <div class="req-item">
      <div class="req-number">R1</div>
      <div class="req-content">
        <h4>需求名称</h4>
        <p>需求描述，解释要解决的问题或满足的诉求。</p>
      </div>
    </div>
  </div>
</div>
```

### Status Pills (`.status-pill`)
Use inline in table cells to show progress status.

```html
<span class="status-pill done">已完成</span>
<span class="status-pill partial">进行中</span>
<span class="status-pill target">规划中</span>
```

---

## Slide Structure Patterns

### Technical Design Doc (typical 10–14 slides)
```
0. 文档概述 (cover)
1. 背景（Background）
2. 目标与非目标（Goals / Non-Goals）
3. 需求分析（Requirements）
4. 技术选型（Tech Selection）
5. 总体设计（Architecture）
6. 详细设计 A（模块/功能一）
7. 详细设计 B（模块/功能二）
8. 数据设计（Data Model）
9. 接口设计（API Design）
10. 异常处理（Error Handling）
11. 风险与对比（Risks & Tradeoffs）
12. 发布方案（Rollout Plan）
13. 未来规划（Future Work）
```

### Product/Feature Spec (typical 8–10 slides)
```
0. 方案概述 (cover)
1. 问题背景
2. 用户诉求
3. 方案设计
4. 核心流程
5. 数据模型
6. 里程碑
7. 成功指标
```

### Architecture Showcase (typical 6–8 slides)
```
0. 架构总览 (cover)
1. 现状与痛点
2. 整体架构图
3. 核心模块详解
4. 关键流程
5. 部署与运维
6. 演进路线
```

## Quality Guidelines

- Each slide should be self-contained: a reader can understand the point without reading surrounding slides.
- Mermaid node labels: keep under 6 words; use `<br/>` for line breaks inside `""`.
- Tables: 3–5 columns work best; more than 5 columns gets cramped.
- Don't use generic placeholder text. If you don't have specific content for a cell, make a reasonable inference or leave a minimal meaningful note.
- The cover slide's `h1` heading should NOT have the `h2::before` blue bar — it uses `h1` styling. All section slides use `h2`.
