# Coach App Frontend

本目录是前端服务（React + Vite + Tailwind + Nginx）。

## 1. 部署模式

### 推荐模式（与后端同 compose）
- 直接使用项目根目录 `docker-compose.yml`
- 前端容器内 Nginx 已配置 `/api` 反向代理到 `http://backend:8000/api/`
- 浏览器只需要访问前端地址，例如 `http://<server-ip>:3000`；Docker 宿主机端口可在 `coach-app/.env` 中通过 `FRONTEND_PORT` 自定义

### 独立模式（前端单独部署）
- 可以单独构建前端镜像
- 但必须保证 `/api` 请求能转发到后端
- 做法二选一：
1. 复用当前 `nginx.conf` 并保证 upstream `backend` 可解析
2. 修改 `nginx.conf` 的 `proxy_pass` 指向后端实际地址后重建镜像

## 2. 端到端部署步骤（前端视角）

以下命令在 `/Users/frog_wch/playground/Career/interview/coach-app/frontend` 执行。

### Step 0: 本地开发
```bash
npm install
npm run dev
```
开发地址默认 `http://localhost:5173`。

### Step 1: 构建产物
```bash
npm run build
```
产物目录：`dist/`。

如果你不走 Nginx 的 `/api` 反代，而是让前端直连后端，请先配置：
```bash
cp .env.example .env
# 设置 VITE_API_BASE_URL，例如 http://<backend-ip>:8000
```

### Step 2: 容器化部署
```bash
docker build -t coach-frontend:latest .
docker run -d --name coach-frontend -p 3000:80 coach-frontend:latest
```

### Step 3: 访问验证
- 首页：`http://127.0.0.1:3000`
- 打开开发者工具 Network，确认 `/api/*` 请求返回 200/4xx（不是 502）

## 3. 手机端访问与响应式

- 当前页面已支持响应式，手机浏览器（Safari/Chrome）可直接访问。
- “面经挖掘”在手机端使用三段式 tab：
1. 上传
2. 批次
3. 高频题

## 4. 前端运行依赖与中间件

### 必需
- 一个可用的后端 API（FastAPI）
- 一个能把 `/api` 转发到后端的网关层（当前由前端容器内 Nginx承担）

### 非必需
- 前端本身不需要 Redis / MQ / Elasticsearch

## 5. 常见问题

### Q1: 页面能打开，但接口都失败
- 检查 `nginx.conf` 里的 `proxy_pass` 是否指向可达后端
- 检查后端健康：`curl http://<backend-host>:8000/health`

### Q2: Docker build 时 npm 拉包失败
- 这是服务器网络问题（npm registry 不可达）
- 可先在有网环境构建镜像后推到镜像仓库，再在服务器拉取运行

### Q3: 前端构建里的 TypeScript 检查范围
- 当前 `build` 脚本使用 `tsc -p tsconfig.app.json`，只检查应用代码
- 这样在离线环境下可避免 Node 类型依赖导致构建中断
