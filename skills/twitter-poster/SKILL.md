---
name: twitter-poster
description: |
  Post tweets to Twitter/X via Twitter API v2. Use this skill whenever the user wants to:
  - Publish a tweet, post, or thread to Twitter/X
  - Share content on Twitter/X
  - Reply to a tweet
  - Post with images or media
  - Automate or batch-post tweets

  Trigger on phrases like: "发推", "发推特", "发条推", "发布推文", "推特发帖", "post a tweet",
  "tweet this", "share on twitter", "send a tweet", "reply to tweet", "post to X", "发个推",
  "帮我发推", "自动发推", "tweet about". Even when the user doesn't say "Twitter" explicitly
  but clearly wants to post to Twitter/X, use this skill.
---

# Twitter Poster

This skill posts tweets via the Twitter API v2. Before executing, always ask the user which
tweet type they want. Then validate, run the script, and report the result.

## Step 1: Ask the user which tweet type they want

Every time the user asks to post, ask them to choose one of three modes. Use AskUserQuestion
with these options:

| Mode | When to use |
|---|---|
| **单条推文** | 一条普通推文，可选附 1-4 张图 |
| **多图推文** | 一条推文带 2-4 张图，适合图集展示 |
| **Thread（连续推文）** | 多条推文串成 thread，适合长内容/故事/教程，第一条可带图 |

If the user's message already makes the type clear (e.g. "发个 thread" or "带上这三张图"),
skip asking and proceed directly.

## Step 2: Collect what's missing

Based on the chosen mode, check if you have everything needed:

| Mode | Required info |
|---|---|
| 单条推文 | 推文内容（≤280字），可选图片路径 |
| 多图推文 | 推文内容，2-4 张图片路径 |
| Thread | 每条推文的内容（分别 ≤280字），可选第一条的图片 |

Ask the user for anything that's missing before running the script.

## Step 3: Check environment variables

Verify all four are set. If missing, tell the user which ones and show the setup guide below.

| Variable | Description |
|---|---|
| `TWITTER_API_KEY` | API Key (Consumer Key) |
| `TWITTER_API_SECRET` | API Secret (Consumer Secret) |
| `TWITTER_ACCESS_TOKEN` | Access Token |
| `TWITTER_ACCESS_TOKEN_SECRET` | Access Token Secret |

## Step 4: Run the script

Script path: `/home/byclaw/.claude/skills/twitter-poster/scripts/post_tweet.py`

### 单条推文（无图）
```bash
python /home/byclaw/.claude/skills/twitter-poster/scripts/post_tweet.py \
  --text "推文内容"
```

### 单条推文（带图，最多 4 张）
```bash
python /home/byclaw/.claude/skills/twitter-poster/scripts/post_tweet.py \
  --text "推文内容" \
  --image /path/to/image1.jpg \
  --image /path/to/image2.jpg
```

### Thread（多条连续推文）
```bash
python /home/byclaw/.claude/skills/twitter-poster/scripts/post_tweet.py \
  --text "第一条内容" \
  --text "第二条内容" \
  --text "第三条内容"
```

### Thread + 第一条带图
```bash
python /home/byclaw/.claude/skills/twitter-poster/scripts/post_tweet.py \
  --text "第一条内容" \
  --text "第二条内容" \
  --image /path/to/image.jpg
```

### 回复某条推文
```bash
python /home/byclaw/.claude/skills/twitter-poster/scripts/post_tweet.py \
  --text "回复内容" \
  --reply-to 1234567890123456789
```

**规则：**
- `--text` 可重复多次 → thread 模式（按顺序串成 thread）
- `--image` 可重复多次（最多 4 张）→ 附到单条推文或 thread 的第一条
- 每条推文独立限制 280 字符

## Step 5: Report results

- 单条推文：显示推文 URL：`https://twitter.com/i/web/status/{id}`
- Thread：显示所有条目的 URL 列表

## Error handling

| Error | Cause | Action |
|---|---|---|
| 401 Unauthorized | 凭证错误 | 请用户检查环境变量 |
| 403 Forbidden | 应用没有写权限 | 在开发者后台开启 Read and Write |
| 429 Too Many Requests | 触发频率限制 | 等 15 分钟后重试 |
| 400 Bad Request | 推文内容问题 | 显示错误信息并修正 |

## Setup Guide（首次配置）

1. 访问 https://developer.twitter.com/en/portal/dashboard
2. 创建 Project → 创建 App
3. App 设置 → User authentication settings → 开启 OAuth 1.0a，权限选 **Read and Write**
4. Keys and Tokens → 生成全部 4 个凭证（Access Token Secret 只显示一次，立即保存）
5. 设置环境变量：
   ```bash
   export TWITTER_API_KEY="..."
   export TWITTER_API_SECRET="..."
   export TWITTER_ACCESS_TOKEN="..."
   export TWITTER_ACCESS_TOKEN_SECRET="..."
   ```
   加入 `~/.bashrc` 或 `~/.zshrc` 可永久生效。
