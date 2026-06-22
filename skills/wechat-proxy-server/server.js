#!/usr/bin/env node
/**
 * WeChat Proxy Server (Node.js)
 *
 * 固定 IP 的微信 API 代理服务器，解决客户端 IP 不固定导致无法加入微信白名单的问题。
 * 纯 Node.js 实现（零运行时依赖），与 Python 版功能完全等价。
 *
 * 环境变量:
 *   WECHAT_APPID      微信公众号 AppID
 *   WECHAT_APPSECRET  微信公众号 AppSecret
 *   PROXY_API_KEY     客户端调用此代理时使用的鉴权密钥
 *   PORT              监听端口（默认 8000）
 *
 * 启动:
 *   node server.js
 */

const http = require('http');
const url = require('url');
const wx = require('./wechat_client');

// ── 配置校验 ────────────────────────────────────────────────────────────────
const WECHAT_APPID = process.env.WECHAT_APPID;
const WECHAT_APPSECRET = process.env.WECHAT_APPSECRET;
const API_KEY = process.env.PROXY_API_KEY;
const PORT = parseInt(process.env.PORT || '8000', 10);

if (!WECHAT_APPID || !WECHAT_APPSECRET || !API_KEY) {
  console.error('❌ 缺少必要环境变量：WECHAT_APPID、WECHAT_APPSECRET、PROXY_API_KEY');
  console.error('   请在 .env 文件或 docker-compose env_file 中配置后重试。');
  process.exit(1);
}

// ── 工具函数 ────────────────────────────────────────────────────────────────
function sendJSON(res, statusCode, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(statusCode, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(body),
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, X-API-Key',
  });
  res.end(body);
}

function sendText(res, statusCode, text) {
  res.writeHead(statusCode, {
    'Content-Type': 'text/plain; charset=utf-8',
    'Access-Control-Allow-Origin': '*',
  });
  res.end(text);
}

async function readRequestBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on('data', (chunk) => chunks.push(chunk));
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    req.on('error', reject);
  });
}

async function readRequestBuffer(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on('data', (chunk) => chunks.push(chunk));
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}

// ── HTTP 服务器 ─────────────────────────────────────────────────────────────
const server = http.createServer(async (req, res) => {
  const parsed = url.parse(req.url, true);
  const pathname = parsed.pathname || '/';

  // CORS 预检
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, X-API-Key',
      'Access-Control-Max-Age': '86400',
    });
    return res.end();
  }

  // 健康检查
  if (pathname === '/health' && req.method === 'GET') {
    return sendJSON(res, 200, { status: 'ok' });
  }

  // 创建草稿（核心接口）
  if (pathname === '/api/draft' && req.method === 'POST') {
    // 鉴权
    const headerKey =
      req.headers['x-api-key'] ||
      req.headers['X-API-Key'] ||
      req.headers['x-api-key'.toLowerCase()];

    if (!headerKey || headerKey !== API_KEY) {
      return sendJSON(res, 401, { success: false, error: 'Invalid API key' });
    }

    let rawBody = '';
    try {
      rawBody = await readRequestBody(req);
      const reqBody = JSON.parse(rawBody || '{}');

      if (!reqBody.title || typeof reqBody.content !== 'string') {
        return sendJSON(res, 400, {
          success: false,
          error: 'title 和 content 字段必填',
        });
      }

      console.log(`[wechat-proxy] 创建草稿: ${reqBody.title}`);

      // 1. 获取 access_token（带缓存）
      const token = await wx.getAccessToken(WECHAT_APPID, WECHAT_APPSECRET);
      console.log('[wechat-proxy] access_token 获取成功');

      // 2. 正文图片处理（外链 → 微信 HTTPS URL）
      const { html, failures } = await wx.processContentImages(token, reqBody.content);
      if (failures && failures.length > 0) {
        console.warn(`[wechat-proxy] ${failures.length} 张图片处理失败`);
      }

      // 3. 封面图上传
      let thumbMediaId = '';
      if (reqBody.cover_base64) {
        const imgBuffer = Buffer.from(reqBody.cover_base64, 'base64');
        const fname = reqBody.cover_filename || 'cover.jpg';
        thumbMediaId = await wx.uploadPermanentImage(token, imgBuffer, fname);
        console.log(`[wechat-proxy] 封面图(base64)上传成功`);
      } else if (reqBody.cover_url) {
        const { buffer } = await wx.downloadImage(reqBody.cover_url);
        thumbMediaId = await wx.uploadPermanentImage(token, buffer, 'cover.jpg');
        console.log(`[wechat-proxy] 封面图(URL)上传成功`);
      } else {
        thumbMediaId = await wx.getFallbackThumbMediaId(token);
        console.log(`[wechat-proxy] 使用素材库默认封面`);
      }

      // 4. 生成 digest（前 120 字纯文本）
      const plainText = (html || '')
        .replace(/<[^>]+>/g, '')
        .replace(/\s+/g, ' ')
        .trim();
      const digest = plainText.slice(0, 120);

      // 5. 调用微信创建草稿
      const result = await wx.createDraft({
        token,
        title: reqBody.title,
        content: html,
        thumb_media_id: thumbMediaId,
        content_source_url: reqBody.content_source_url || '',
        digest,
      });

      if (result && result.media_id) {
        console.log(`[wechat-proxy] 草稿创建成功: ${result.media_id}`);
        return sendJSON(res, 200, {
          success: true,
          media_id: result.media_id,
          failed_images: failures || [],
        });
      } else {
        console.error('[wechat-proxy] 微信返回失败:', result);
        return sendJSON(res, 200, {
          success: false,
          error: result ? JSON.stringify(result) : '未知错误',
          failed_images: failures || [],
        });
      }
    } catch (err) {
      console.error('[wechat-proxy] 处理异常:', err && err.stack ? err.stack : err);
      const msg = (err && err.message) || String(err);
      return sendJSON(res, 500, { success: false, error: msg });
    }
  }

  // 上传视频到永久素材库
  if (pathname === '/api/video/upload-permanent' && req.method === 'POST') {
    const headerKey =
      req.headers['x-api-key'] ||
      req.headers['X-API-Key'] ||
      req.headers['x-api-key'.toLowerCase()];

    if (!headerKey || headerKey !== API_KEY) {
      return sendJSON(res, 401, { success: false, error: 'Invalid API key' });
    }

    const contentType = req.headers['content-type'] || '';
    if (!contentType.toLowerCase().includes('multipart/form-data')) {
      return sendJSON(res, 400, {
        success: false,
        error: '此接口仅接受 multipart/form-data,字段: video(文件)、title、introduction',
      });
    }

    try {
      const rawBuf = await readRequestBuffer(req);
      const parts = wx.parseMultipart(rawBuf, contentType);

      const videoPart = parts.find((p) => p.name === 'video' && p.filename);
      if (!videoPart) {
        return sendJSON(res, 400, {
          success: false,
          error: '未找到 video 文件字段',
        });
      }

      const title = (parts.find((p) => p.name === 'title') || {}).data || videoPart.filename;
      const introduction = (parts.find((p) => p.name === 'introduction') || {}).data || '';

      const sizeMB = (videoPart.data.length / 1024 / 1024).toFixed(2);
      console.log(`[wechat-proxy] 上传视频: ${videoPart.filename} (${sizeMB}MB)`);

      const token = await wx.getAccessToken(WECHAT_APPID, WECHAT_APPSECRET);
      const result = await wx.uploadPermanentVideo(
        token,
        videoPart.data,
        videoPart.filename,
        String(title),
        String(introduction)
      );

      console.log(`[wechat-proxy] 视频素材上传成功: media_id=${result.media_id}`);
      return sendJSON(res, 200, {
        success: true,
        media_id: result.media_id,
        url: result.url,
        size: videoPart.data.length,
        filename: videoPart.filename,
      });
    } catch (err) {
      console.error('[wechat-proxy] 视频上传异常:', err && err.stack ? err.stack : err);
      const msg = (err && err.message) || String(err);
      return sendJSON(res, 500, { success: false, error: msg });
    }
  }

  // 转换永久素材 → 群发素材
  if (pathname === '/api/video/convert-to-mass' && req.method === 'POST') {
    const headerKey = req.headers['x-api-key'] || req.headers['X-API-Key'] || req.headers['x-api-key'.toLowerCase()];
    if (!headerKey || headerKey !== API_KEY) {
      return sendJSON(res, 401, { success: false, error: 'Invalid API key' });
    }
    try {
      const raw = await readRequestBody(req);
      const body = JSON.parse(raw || '{}');
      if (!body.media_id) {
        return sendJSON(res, 400, { success: false, error: 'media_id 必填' });
      }
      const token = await wx.getAccessToken(WECHAT_APPID, WECHAT_APPSECRET);
      const result = await wx.convertVideoToMass(token, body.media_id, body.title || '', body.description || '');
      console.log(`[wechat-proxy] 视频转群发素材成功: ${result.media_id}`);
      return sendJSON(res, 200, { success: true, ...result });
    } catch (err) {
      console.error('[wechat-proxy] convert 异常:', err && err.stack ? err.stack : err);
      return sendJSON(res, 500, { success: false, error: (err && err.message) || String(err) });
    }
  }

  // 创建 mpvideo 群发任务
  if (pathname === '/api/video/mass-send' && req.method === 'POST') {
    const headerKey = req.headers['x-api-key'] || req.headers['X-API-Key'] || req.headers['x-api-key'.toLowerCase()];
    if (!headerKey || headerKey !== API_KEY) {
      return sendJSON(res, 401, { success: false, error: 'Invalid API key' });
    }
    try {
      const raw = await readRequestBody(req);
      const body = JSON.parse(raw || '{}');
      if (!body.media_id) {
        return sendJSON(res, 400, { success: false, error: '群发素材 media_id 必填(调 /api/video/convert-to-mass 获得)' });
      }
      const token = await wx.getAccessToken(WECHAT_APPID, WECHAT_APPSECRET);
      const result = await wx.createMassVideoTask(
        token,
        body.media_id,
        body.title || '',
        body.description || '',
        { is_to_all: body.is_to_all !== false, tag_id: body.tag_id || 0 },
      );
      console.log(`[wechat-proxy] mpvideo 群发任务创建成功: msg_id=${result.msg_id}`);
      return sendJSON(res, 200, {
        success: true,
        ...result,
        note: '任务已创建,需在公众号后台「群发消息」中预览并点击"群发"才会真正推送(48h 预览期)。',
      });
    } catch (err) {
      console.error('[wechat-proxy] mass-send 异常:', err && err.stack ? err.stack : err);
      return sendJSON(res, 500, { success: false, error: (err && err.message) || String(err) });
    }
  }

  // 404
  sendJSON(res, 404, { success: false, error: 'Not Found' });
});

// ── 启动 ────────────────────────────────────────────────────────────────────
server.listen(PORT, '0.0.0.0', () => {
  console.log(`WeChat Proxy Server (Node.js) 已启动`);
  console.log(`监听地址: http://0.0.0.0:${PORT}`);
  console.log(`健康检查: http://localhost:${PORT}/health`);
  console.log(`草稿接口: POST /api/draft  (需 X-API-Key 头)`);
  console.log(`视频上传: POST /api/video/upload-permanent  (multipart/form-data, 需 X-API-Key 头)`);
  console.log(`视频转群发: POST /api/video/convert-to-mass  (JSON, 需 X-API-Key 头)`);
  console.log(`视频群发: POST /api/video/mass-send  (JSON, 需 X-API-Key 头,需先 convert)`);
});

// 优雅退出
process.on('SIGTERM', () => {
  console.log('收到 SIGTERM，优雅关闭...');
  server.close(() => process.exit(0));
});
process.on('SIGINT', () => {
  console.log('收到 SIGINT，优雅关闭...');
  server.close(() => process.exit(0));
});
