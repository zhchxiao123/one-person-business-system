/**
 * 微信 API 封装层 (Node.js 版)
 * - token 管理（文件缓存）
 * - 图片下载与上传（正文图、永久素材封面）
 * - 草稿创建
 * - HTML 正文图片外链 -> 微信 CDN 替换
 *
 * 零依赖，纯 Node.js (>=18)
 */

const https = require('https');
const http = require('http');
const fs = require('fs');
const { URL } = require('url');

const TOKEN_CACHE_FILE = '/tmp/wechat_token_cache.json';

let _tokenCache = null;

function loadCache() {
  if (_tokenCache) return _tokenCache;
  try {
    if (fs.existsSync(TOKEN_CACHE_FILE)) {
      const raw = fs.readFileSync(TOKEN_CACHE_FILE, 'utf8');
      _tokenCache = JSON.parse(raw);
      return _tokenCache;
    }
  } catch (e) {
    // ignore corrupt cache
  }
  _tokenCache = {};
  return _tokenCache;
}

function saveCache(cache) {
  try {
    fs.writeFileSync(TOKEN_CACHE_FILE, JSON.stringify(cache, null, 2), 'utf8');
  } catch (e) {
    // ignore fs errors (e.g. /tmp readonly in some containers)
  }
  _tokenCache = cache;
}

const MIME_MAP = {
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  png: 'image/png',
  gif: 'image/gif',
  webp: 'image/webp',
};

function guessMime(url, contentType = '') {
  const clean = url.split('?')[0].split('#')[0];
  const ext = clean.split('.').pop().toLowerCase();
  if (MIME_MAP[ext]) {
    return { mime: MIME_MAP[ext], ext };
  }
  for (const [e, m] of Object.entries(MIME_MAP)) {
    if (contentType && contentType.toLowerCase().includes(e)) {
      return { mime: m, ext: e };
    }
  }
  return { mime: 'image/png', ext: 'png' };
}

// 通用 HTTPS 请求封装
async function httpsRequest(method, urlStr, { body = null, headers = {} } = {}) {
  return new Promise((resolve, reject) => {
    const u = new URL(urlStr);
    const client = u.protocol === 'https:' ? https : http;

    const opts = {
      hostname: u.hostname,
      port: u.port || (u.protocol === 'https:' ? 443 : 80),
      path: u.pathname + u.search,
      method: method.toUpperCase(),
      headers: { ...headers },
    };

    if (body) {
      if (Buffer.isBuffer(body)) {
        opts.headers['Content-Length'] = body.length;
      } else if (typeof body === 'string' || body instanceof Uint8Array) {
        opts.headers['Content-Length'] = Buffer.byteLength(body);
      }
    }

    const req = client.request(opts, (res) => {
      const chunks = [];
      res.on('data', (c) => chunks.push(c));
      res.on('end', () => {
        const buf = Buffer.concat(chunks);
        const text = buf.toString('utf8');
        const ct = (res.headers['content-type'] || '').toLowerCase();

        let data;
        // 优先按 Content-Type 解析;微信 add_material?type=video 接口偶尔返回
        // Content-Type: text/plain 但 body 实际是 JSON,做兜底
        if (ct.includes('application/json')) {
          try {
            data = JSON.parse(text);
          } catch {
            data = { raw: text };
          }
        } else if (ct.includes('text/plain') || ct === '') {
          try {
            data = JSON.parse(text);
          } catch {
            data = { raw: text, contentType: ct };
          }
        } else {
          data = { raw: text, contentType: ct };
        }

        if (res.statusCode >= 400) {
          const err = new Error(`HTTP ${res.statusCode}: ${text.slice(0, 300)}`);
          err.status = res.statusCode;
          err.response = data;
          reject(err);
        } else {
          resolve(data);
        }
      });
    });

    req.on('error', reject);

    if (body) {
      req.write(body);
    }
    req.end();
  });
}

async function httpsGetJSON(urlStr) {
  return httpsRequest('GET', urlStr);
}

async function httpsPostJSON(urlStr, payload) {
  const jsonStr = JSON.stringify(payload);
  return httpsRequest('POST', urlStr, {
    body: jsonStr,
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
}

function buildMultipart(fieldName, filename, mimeType, buffer) {
  const boundary = '----NodeFormBoundary' + Date.now().toString(16) + Math.random().toString(16).slice(2);
  const header = Buffer.from(
    `--${boundary}\r\n` +
      `Content-Disposition: form-data; name="${fieldName}"; filename="${filename}"\r\n` +
      `Content-Type: ${mimeType}\r\n\r\n`
  );
  const footer = Buffer.from(`\r\n--${boundary}--\r\n`);
  const body = Buffer.concat([header, buffer, footer]);
  return { boundary, body };
}

// 构造多字段 multipart/form-data (用于上传到微信 add_material?type=video
// — 需要同时携带 media(文件) 和 description(JSON 字符串))
function buildMultipartFields(fields, fileBoundary) {
  const boundary = fileBoundary || ('----NodeFormBoundary' + Date.now().toString(16) + Math.random().toString(16).slice(2));
  const parts = [];
  for (const f of fields) {
    let header;
    if (f.filename) {
      header =
        `--${boundary}\r\n` +
        `Content-Disposition: form-data; name="${f.name}"; filename="${f.filename}"\r\n` +
        `Content-Type: ${f.contentType || 'application/octet-stream'}\r\n\r\n`;
    } else {
      header =
        `--${boundary}\r\n` +
        `Content-Disposition: form-data; name="${f.name}"\r\n\r\n`;
    }
    parts.push(Buffer.from(header));
    parts.push(Buffer.isBuffer(f.data) ? f.data : Buffer.from(String(f.data), 'utf8'));
    parts.push(Buffer.from('\r\n'));
  }
  parts.push(Buffer.from(`--${boundary}--\r\n`));
  return { boundary, body: Buffer.concat(parts) };
}

// 极简 multipart/form-data 解析器(用于本代理服务器接收客户端上传的视频文件)
// 仅支持 RFC 7578 常见形式(单文件 + 若干普通字段),不处理嵌套/多文件
function parseMultipart(buffer, contentType) {
  const m = /boundary=(?:"([^"]+)"|([^;]+))/i.exec(contentType || '');
  if (!m) throw new Error('multipart 请求缺少 boundary');
  const boundary = '--' + (m[1] || m[2]).trim();
  const text = buffer.toString('binary');
  const parts = [];
  const segments = text.split(boundary);
  // segments: ['', header1\r\n\r\nbody1\r\n, header2\r\n\r\nbody2\r\n, --]
  for (let i = 1; i < segments.length; i++) {
    const seg = segments[i];
    if (seg === '--' || seg === '--\r\n') break;
    const idx = seg.indexOf('\r\n\r\n');
    if (idx === -1) continue;
    const head = seg.slice(0, idx);
    let body = seg.slice(idx + 4);
    if (body.endsWith('\r\n')) body = body.slice(0, -2);

    const nameM = /name="([^"]+)"/i.exec(head);
    const fileM = /filename="([^"]*)"/i.exec(head);
    const ctM = /Content-Type:\s*([^\r\n]+)/i.exec(head);
    if (!nameM) continue;

    const name = nameM[1];
    if (fileM) {
      parts.push({
        name,
        filename: fileM[1],
        contentType: ctM ? ctM[1].trim() : 'application/octet-stream',
        data: Buffer.from(body, 'binary'),
      });
    } else {
      parts.push({ name, data: Buffer.from(body, 'binary').toString('utf8') });
    }
  }
  return parts;
}

async function httpsPostMultipart(urlStr, boundary, buffer) {
  return httpsRequest('POST', urlStr, {
    body: buffer,
    headers: {
      'Content-Type': `multipart/form-data; boundary=${boundary}`,
    },
  });
}

// ==================== 公开 API ====================

async function getAccessToken(appid, appsecret) {
  const cache = loadCache();
  const entry = cache[appid] || {};
  if (entry.token && entry.expires_at > Math.floor(Date.now() / 1000) + 300) {
    return entry.token;
  }

  const url = `https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid=${appid}&secret=${appsecret}`;
  const data = await httpsGetJSON(url);

  if (!data.access_token) {
    throw new Error(`获取 access_token 失败: ${data.errmsg || JSON.stringify(data)}`);
  }

  const token = data.access_token;
  const expires_in = data.expires_in || 7200;

  cache[appid] = {
    token,
    expires_at: Math.floor(Date.now() / 1000) + expires_in - 300,
  };
  saveCache(cache);
  return token;
}

async function downloadImage(url, timeoutMs = 30000) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const client = u.protocol === 'https:' ? https : http;

    const req = client.get(
      url,
      {
        headers: { 'User-Agent': 'Mozilla/5.0 (compatible; WeChatProxy/1.0)' },
        timeout: timeoutMs,
      },
      (res) => {
        if (res.statusCode !== 200) {
          reject(new Error(`下载失败: HTTP ${res.statusCode}`));
          res.resume();
          return;
        }
        const chunks = [];
        res.on('data', (c) => chunks.push(c));
        res.on('end', () => {
          resolve({
            buffer: Buffer.concat(chunks),
            contentType: res.headers['content-type'] || '',
          });
        });
      }
    );

    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('下载超时'));
    });
  });
}

async function uploadContentImage(token, imageData, filename, mime) {
  const { boundary, body } = buildMultipart('media', filename, mime, imageData);
  const url = `https://api.weixin.qq.com/cgi-bin/media/uploadimg?access_token=${token}`;
  const result = await httpsPostMultipart(url, boundary, body);
  if (!result.url) {
    throw new Error(`上传正文图片失败: ${JSON.stringify(result)}`);
  }
  let u = result.url;
  if (typeof u === 'string' && u.startsWith('http://')) {
    u = 'https://' + u.slice(7);
  }
  return u;
}

async function uploadPermanentImage(token, imageData, filename = 'cover.jpg') {
  const ext = (filename.split('.').pop() || 'jpg').toLowerCase().split('?')[0];
  const mime = MIME_MAP[ext] || 'image/jpeg';
  const { boundary, body } = buildMultipart('media', filename, mime, imageData);
  const url = `https://api.weixin.qq.com/cgi-bin/material/add_material?access_token=${token}&type=image`;
  const result = await httpsPostMultipart(url, boundary, body);
  if (!result.media_id) {
    throw new Error(`上传封面图失败: ${JSON.stringify(result)}`);
  }
  return result.media_id;
}

// 上传永久视频素材 (material/add_material?type=video)
// 返回 { media_id, url } —— url 是微信返回的视频源地址,可用于图文 content 中 <video src=...>
// 注意:
//   - description 字段是 JSON 字符串: {"title": "...", "introduction": "..."}
//   - 仅认证服务号可用; 单个公众号最多 1000 条非图文永久素材
async function uploadPermanentVideo(token, videoBuffer, filename = 'video.mp4', title = '', introduction = '') {
  if (!Buffer.isBuffer(videoBuffer) || videoBuffer.length === 0) {
    throw new Error('视频文件为空');
  }
  const ext = (filename.split('.').pop() || 'mp4').toLowerCase().split('?')[0];
  const mime = ext === 'mp4' ? 'video/mp4' : (ext === 'mov' ? 'video/quicktime' : 'video/mp4');
  const description = JSON.stringify({
    title: title || filename,
    introduction: introduction || '',
  });
  const { boundary, body } = buildMultipartFields([
    { name: 'media', filename, contentType: mime, data: videoBuffer },
    { name: 'description', data: description },
  ]);
  const url = `https://api.weixin.qq.com/cgi-bin/material/add_material?access_token=${token}&type=video`;
  const result = await httpsPostMultipart(url, boundary, body);
  if (!result.media_id) {
    throw new Error(`上传视频素材失败: ${JSON.stringify(result)}`);
  }
  return {
    media_id: result.media_id,
    url: result.url || '',
  };
}

async function getFallbackThumbMediaId(token) {
  const url = `https://api.weixin.qq.com/cgi-bin/material/batchget_material?access_token=${token}`;
  const res = await httpsPostJSON(url, { type: 'image', offset: 0, count: 1 });
  const items = (res && res.item) || [];
  return items.length ? items[0].media_id : '';
}

async function processContentImages(token, html) {
  // 提取所有 img src（去重，保持顺序）
  const urls = [];
  const seen = new Set();
  const imgRegex = /<img[^>]+src=["']([^"']+)["'][^>]*>/gi;
  let match;
  while ((match = imgRegex.exec(html)) !== null) {
    const u = match[1];
    if (!seen.has(u)) {
      seen.add(u);
      urls.push(u);
    }
  }

  if (urls.length === 0) {
    return { html, failures: [] };
  }

  const urlMap = {};
  const failures = [];

  for (let i = 0; i < urls.length; i++) {
    const origUrl = urls[i];
    try {
      const { buffer, contentType } = await downloadImage(origUrl);
      const { mime, ext } = guessMime(origUrl, contentType);
      const wxUrl = await uploadContentImage(token, buffer, `img_${i}.${ext}`, mime);
      urlMap[origUrl] = wxUrl;
    } catch (e) {
      failures.push({ url: origUrl, error: e.message || String(e) });
    }
  }

  // 替换 src 为 data-src（仅替换成功上传的）
  let processed = html;
  for (const [orig, wx] of Object.entries(urlMap)) {
    const safe = orig.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const re = new RegExp(`(<img[^>]*?)src=["']${safe}["']([^>]*>)`, 'gi');
    processed = processed.replace(re, `$1data-src="${wx}"$2`);
  }

  return { html: processed, failures };
}

async function createDraft({
  token,
  title,
  content,
  thumb_media_id = '',
  content_source_url = '',
  digest = '',
}) {
  const payload = {
    articles: [
      {
        title,
        content,
        thumb_media_id,
        content_source_url,
        digest,
        author: '',
        need_open_comment: 1,
        only_fans_can_comment: 0,
      },
    ],
  };
  const url = `https://api.weixin.qq.com/cgi-bin/draft/add?access_token=${token}`;
  return httpsPostJSON(url, payload);
}

module.exports = {
  getAccessToken,
  downloadImage,
  uploadContentImage,
  uploadPermanentImage,
  uploadPermanentVideo,
  getFallbackThumbMediaId,
  processContentImages,
  createDraft,
  parseMultipart,
  // 内部工具按需导出（测试用）
  _guessMime: guessMime,
  _buildMultipartFields: buildMultipartFields,
};
