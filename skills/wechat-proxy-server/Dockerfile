# WeChat Proxy Server (Node.js 版)
# 纯 Node.js 实现，零运行时依赖，镜像更小更轻量
FROM node:20-slim

WORKDIR /app

# 仅复制必要文件（零依赖，无需 npm install）
COPY package.json server.js wechat_client.js ./

# 可选：保留 Python 版以便对比/回退（不影响运行）
COPY main.py wechat_client.py requirements.txt ./

EXPOSE 8000

# 使用 node 直接启动（推荐）
CMD ["node", "server.js"]
