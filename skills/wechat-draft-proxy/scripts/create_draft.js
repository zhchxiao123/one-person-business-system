#!/usr/bin/env node
/**
 * 微信公众号草稿箱创建工具（Node.js 代理服务器版）
 * 
 * 通过固定 IP 的代理服务器中转微信 API 调用，客户端不需要加入微信 IP 白名单。
 * 支持已排版 HTML 直接提交、封面图（本地/URL）、原文链接。
 * 
 * 推荐搭配 wechat-styler 先排版生成 HTML，再使用 --html 提交。
 * 
 * 用法:
 *   node create_draft.js --title "标题" --file article.html --html
 *   node create_draft.js --title "标题" --file article.md --cover-path cover.jpg
 * 
 * 配置优先级:
 *   1. 命令行 --server / --api-key
 *   2. 技能目录下的 .env 文件（cp .env.example .env）
 *   3. 环境变量 WECHAT_PROXY_URL / WECHAT_PROXY_API_KEY
 */

const fs = require('fs');
const path = require('path');

// ==================== .env 自动加载（零依赖，技能目录优先） ====================
// 仅当对应环境变量尚未设置时才从 .env 填充，避免覆盖 shell export
function loadEnvFile() {
  const envPath = path.join(__dirname, '../.env');
  if (!fs.existsSync(envPath)) return;
  try {
    const content = fs.readFileSync(envPath, 'utf8');
    for (const rawLine of content.split(/\r?\n/)) {
      const line = rawLine.trim();
      if (!line || line.startsWith('#')) continue;
      const eqIdx = line.indexOf('=');
      if (eqIdx === -1) continue;
      const key = line.slice(0, eqIdx).trim();
      let val = line.slice(eqIdx + 1).trim();
      // 去除首尾引号
      if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
        val = val.slice(1, -1);
      }
      if (key && !process.env[key]) {
        process.env[key] = val;
      }
    }
  } catch (e) {
    // 静默，后面会给出清晰的错误提示
  }
}

// 模块加载时立即尝试加载（CLI 直接运行最常见场景）
loadEnvFile();

// ==================== 参数解析 ====================

function parseArgs() {
  const args = process.argv.slice(2);
  const options = {
    server: process.env.WECHAT_PROXY_URL || '',
    apiKey: process.env.WECHAT_PROXY_API_KEY || '',
    title: '',
    content: '',
    file: '',
    html: false,
    theme: 'professional-clean', // 保留参数但 Node 版不使用专业排版
    coverUrl: '',
    coverPath: '',
    contentSourceUrl: '',
  };

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    const next = args[i + 1];

    switch (arg) {
      case '--server':
        options.server = next || '';
        i++;
        break;
      case '--api-key':
        options.apiKey = next || '';
        i++;
        break;
      case '--title':
        options.title = next || '';
        i++;
        break;
      case '--content':
        options.content = next || '';
        i++;
        break;
      case '--file':
        options.file = next || '';
        i++;
        break;
      case '--html':
        options.html = true;
        break;
      case '--theme':
        options.theme = next || 'professional-clean';
        i++;
        break;
      case '--cover-url':
        options.coverUrl = next || '';
        i++;
        break;
      case '--cover-path':
        options.coverPath = next || '';
        i++;
        break;
      case '--content-source-url':
        options.contentSourceUrl = next || '';
        i++;
        break;
      case '-h':
      case '--help':
        printHelp();
        process.exit(0);
        break;
      default:
        if (arg.startsWith('-')) {
          console.error(`未知参数: ${arg}`);
          process.exit(1);
        }
    }
  }

  return options;
}

function printHelp() {
  console.log(`
微信公众号草稿创建工具 (Node.js 版)

用法:
  node create_draft.js --title "文章标题" --file article.html --html
  node create_draft.js --title "文章标题" --file content.md --cover-path cover.jpg

选项:
  --title <string>           文章标题（必填）
  --file <path>              从文件读取内容（优先级高于 --content）
  --content <string>         直接传入内容字符串
  --html                     内容已是排版好的 HTML，跳过 Markdown 转换
  --server <url>             代理服务器地址（最高优先，覆盖 .env）
  --api-key <key>            API Key（最高优先，覆盖 .env）
  --cover-path <path>        封面图本地路径
  --cover-url <url>          封面图远程 URL
  --content-source-url <url> 原文链接
  --theme <name>             排版主题（当前 Node 版仅记录，推荐先用 wechat-styler 处理）
  -h, --help                 显示帮助

配置:
  推荐做法（最顺滑）：
    cd ~/.grok/skills/wechat-draft-proxy
    cp .env.example .env
    # 编辑 .env 填入 WECHAT_PROXY_URL 和 WECHAT_PROXY_API_KEY

  命令行可覆盖：--server / --api-key
  环境变量也可使用（优先级低于 .env 和 CLI）

推荐流程:
  1. 使用 wechat-styler 排版生成 HTML
  2. node create_draft.js --title "xxx" --file styled.html --html
`);
}

// ==================== Markdown 转 HTML（内置简易转换） ====================

function markdownToHtml(markdown) {
  let html = markdown;

  // 1. 代码块（必须最先处理，避免内部被转义）
  html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (m, lang, code) => {
    return `\n<pre><code class="lang-${lang || 'text'}">${escapeHtml(code.trim())}</code></pre>\n`;
  });

  // 2. 行内代码
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

  // 3. 图片和链接
  html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1" />');
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');

  // 4. 粗体 / 斜体
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/__([^_]+)__/g, '<strong>$1</strong>');
  html = html.replace(/(^|[^*])\*([^*]+)\*(?!\*)/g, '$1<em>$2</em>');
  html = html.replace(/(^|[^_])_([^_]+)_(?!_)/g, '$1<em>$2</em>');

  // 5. 标题
  for (let i = 6; i >= 1; i--) {
    const re = new RegExp(`^#{${i}}\\s+(.+)$`, 'gm');
    html = html.replace(re, `<h${i}>$1</h${i}>`);
  }

  // 6. 列表（逐行状态机，较可靠）
  const lines = html.split('\n');
  const out = [];
  let listStack = []; // [{type: 'ul'|'ol'}]

  const isUl = (l) => /^(?:-|\*)\s+(.+)$/.exec(l);
  const isOl = (l) => /^\d+\.\s+(.+)$/.exec(l);

  for (let rawLine of lines) {
    const line = rawLine.trimEnd();
    const ul = isUl(line);
    const ol = isOl(line);

    if (ul || ol) {
      const type = ul ? 'ul' : 'ol';
      const content = ul ? ul[1] : ol[1];

      // 关闭不匹配的列表
      while (listStack.length && listStack[listStack.length - 1].type !== type) {
        const t = listStack.pop().type;
        out.push(`</${t}>`);
      }
      // 打开新列表
      if (!listStack.length || listStack[listStack.length - 1].type !== type) {
        listStack.push({ type });
        out.push(`<${type}>`);
      }
      out.push(`<li>${content}</li>`);
    } else {
      // 非列表行：关闭所有打开的列表
      while (listStack.length) {
        const t = listStack.pop().type;
        out.push(`</${t}>`);
      }
      out.push(line);
    }
  }
  while (listStack.length) {
    const t = listStack.pop().type;
    out.push(`</${t}>`);
  }
  html = out.join('\n');

  // 7. 段落（简单处理连续空行）
  html = html.replace(/\n{3,}/g, '\n\n');           // 压缩多空行
  html = html.replace(/\n\n/g, '</p>\n<p>');

  // 8. 包裹裸文本为段落（跳过已知块级开头）
  const blockStart = /^\s*<(h[1-6]|ul|ol|pre|blockquote|img|table|hr|div|p|li|\/(ul|ol))/i;
  const wrappedLines = html.split('\n').map(line => {
    const t = line.trim();
    if (!t) return '';
    if (blockStart.test(t)) return line;
    return `<p>${t}</p>`;
  });
  html = wrappedLines.join('\n');

  // 9. 最终大力清理：把错误包在 p 里的块级元素"救"出来
  html = html.replace(/<p>\s*<(ul|ol|h[1-6]|pre)>/gi, '<$1>');
  html = html.replace(/<\/(ul|ol|h[1-6]|pre)>\s*<\/p>/gi, '</$1>');
  html = html.replace(/<p>\s*<\/(ul|ol)>/gi, '</$1>');
  html = html.replace(/<p><\/p>/g, '');
  // 列表之间多余 p
  html = html.replace(/<\/(ul|ol)>\s*<p>\s*<\/p>\s*<(ul|ol)>/gi, '</$1><$2>');

  return html.trim();
}

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// ==================== HTML 处理 ====================

function extractBodyContent(html) {
  if (html.includes('<body') && html.includes('</body>')) {
    const match = html.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
    if (match) {
      console.log('已从完整 HTML 中提取 <body> 内容');
      return match[1].trim();
    }
  }
  return html;
}

// ==================== 代理服务器调用 ====================

async function createDraftViaProxy(serverUrl, apiKey, payload) {
  const endpoint = serverUrl.replace(/\/$/, '') + '/api/draft';

  const res = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': apiKey,
    },
    body: JSON.stringify(payload),
  });

  if (res.status === 401) {
    throw new Error('API Key 无效，请检查 PROXY_API_KEY 配置');
  }

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`服务器错误 ${res.status}: ${text.slice(0, 200)}`);
  }

  return res.json();
}

// ==================== 主流程 ====================

async function main() {
  const args = parseArgs();

  if (!args.server) {
    console.error('错误: 需要代理服务器地址（--server 或 .env / WECHAT_PROXY_URL）');
    console.error('提示: 在 wechat-draft-proxy 目录执行 "cp .env.example .env" 然后编辑填写');
    process.exit(1);
  }
  if (!args.apiKey) {
    console.error('错误: 需要 API Key（--api-key 或 .env / WECHAT_PROXY_API_KEY）');
    console.error('提示: 在 wechat-draft-proxy 目录执行 "cp .env.example .env" 然后编辑填写');
    process.exit(1);
  }
  if (!args.title) {
    console.error('错误: --title 是必填参数');
    process.exit(1);
  }

  // 读取内容
  let rawContent = '';
  if (args.file) {
    if (!fs.existsSync(args.file)) {
      console.error(`错误: 文件不存在: ${args.file}`);
      process.exit(1);
    }
    rawContent = fs.readFileSync(args.file, 'utf-8');
  } else if (args.content) {
    rawContent = args.content;
  } else {
    console.error('错误: 需要通过 --content 或 --file 提供文章内容');
    process.exit(1);
  }

  // 转换或直接使用
  let htmlContent;
  if (args.html) {
    htmlContent = rawContent;
    console.log('已跳过 Markdown 转换（--html 模式）');
  } else {
    console.log(`转换 Markdown（内置简易转换器，推荐使用 wechat-styler + --html 获得专业排版）...`);
    htmlContent = markdownToHtml(rawContent);
  }

  htmlContent = extractBodyContent(htmlContent);

  // 构建请求 payload
  const payload = {
    title: args.title,
    content: htmlContent,
    content_source_url: args.contentSourceUrl || '',
  };

  // 封面图处理
  if (args.coverPath) {
    if (!fs.existsSync(args.coverPath)) {
      console.error(`错误: 封面图文件不存在: ${args.coverPath}`);
      process.exit(1);
    }
    const imageBuffer = fs.readFileSync(args.coverPath);
    payload.cover_base64 = imageBuffer.toString('base64');
    payload.cover_filename = path.basename(args.coverPath);
    console.log(`封面图（本地文件）: ${args.coverPath}`);
  } else if (args.coverUrl) {
    payload.cover_url = args.coverUrl;
    console.log(`封面图（URL）: ${args.coverUrl}`);
  }

  console.log('正在通过代理服务器创建草稿...');

  try {
    const result = await createDraftViaProxy(args.server, args.apiKey, payload);

    if (result.success) {
      console.log('\n✅ 成功! 草稿已创建!');
      console.log(`media_id: ${result.media_id}`);
      if (result.failed_images && result.failed_images.length > 0) {
        console.log(`\n⚠️  ${result.failed_images.length} 张图片处理失败:`);
        for (const item of result.failed_images) {
          console.log(`  - ${item.url}: ${item.error}`);
        }
      }
      console.log('\n请到微信公众号后台 -> 内容与互动 -> 草稿箱 查看');
    } else {
      console.error(`\n❌ 创建失败: ${result.error || JSON.stringify(result)}`);
      process.exit(1);
    }
  } catch (err) {
    console.error(`\n❌ 请求失败: ${err.message}`);
    process.exit(1);
  }
}

// 入口
if (require.main === module) {
  main().catch((e) => {
    console.error('未捕获错误:', e);
    process.exit(1);
  });
}

module.exports = { markdownToHtml, extractBodyContent, createDraftViaProxy };
