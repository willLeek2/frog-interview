# Coach App Backend

本目录是后端服务（FastAPI + SQLModel）。

## 1. 当前存储与中间件（你问的重点）

### 业务数据数据库（非向量）
- 当前使用：`SQLite`
- 默认文件：`/app/data/coach_app.db`（容器内）
- 用途：会话、消息、面经批次、任务状态、题目、题簇元数据等事务数据

### 向量数据库
- 当前使用：`Qdrant`
- 用途：知识库检索向量、面经问题聚类向量

### 现在必须的中间件
- 必需：`Qdrant`
- 非必需：`Redis / MQ / Elasticsearch`（当前版本不需要）

### 现在可选的中间件（生产建议）
- 可选：外层反向代理（Nginx/Caddy/Traefik）做 TLS 和域名入口
- 可选：监控（Prometheus + Grafana / Sentry）

## 2. 部署拓扑（当前实现）

- `frontend`：Nginx 静态站点容器
- `backend`：FastAPI 容器
- `qdrant`：向量数据库容器
- `sqlite`：作为文件保存在 `backend/data/coach_app.db`

当前异步处理队列是“后端进程内队列 + worker 线程”，不是独立 MQ。  
因此建议生产先保持 **1 个 backend 实例**，避免多实例下队列分散。

## 3. 端到端部署步骤（Docker Compose）

以下命令在 `/Users/frog_wch/playground/Career/interview/coach-app` 执行。

### Step 0: 准备环境
1. 安装 Docker + Docker Compose（plugin）。
2. 服务器放通端口：默认 `3000`（前端）、`8000`（后端，可选内网）、`6333`（Qdrant）；可在 `coach-app/.env` 中通过 `FRONTEND_PORT`、`BACKEND_PORT`、`QDRANT_PORT` 自定义。

### Step 1: 准备配置文件
1. 复制配置：
```bash
cp backend/.env.example backend/.env
cp .env.example .env   # 可选：自定义端口
```
2. 编辑 `backend/.env`，至少填写：
```env
OPENROUTER_API_KEY=你的key
```
如需给不同用途模型分别指定 OpenRouter provider 顺序，可选填写：
```env
OPENROUTER_CHAT_PROVIDER_ORDER=openai,anthropic
OPENROUTER_EMBEDDING_PROVIDER_ORDER=openai
OPENROUTER_AUDIO_PROVIDER_ORDER=openai
OPENROUTER_VISION_PROVIDER_ORDER=openai,google
# 兜底顺序（当上述某项为空时生效）
OPENROUTER_PROVIDER_ORDER=
```
3. 如需 Explain 联网检索，额外填写：
```env
PERPLEXITY_API_KEY=你的key
JINA_API_KEY=你的key
```

### Step 2: 启动服务
```bash
docker compose up -d --build
# 若需 Qdrant 内存限制生效：docker compose --compatibility up -d --build
```

### Step 3: 健康检查
```bash
curl http://127.0.0.1:8000/health   # 若自定义了 BACKEND_PORT，请替换端口
```
预期返回 `{"status":"ok"}`。

### Step 4: 首次索引（必做一次）
```bash
curl -X POST http://127.0.0.1:8000/api/v1/index/rebuild
```

### Step 5: 面经挖掘链路验收（异步）
1. 上传批次：
```bash
curl -X POST http://127.0.0.1:8000/api/v1/experience/batches \
  -F "files=@./1.png" \
  -F "files=@./2.png" \
  -F "company=字节跳动" \
  -F "business_line=电商"
```
2. 触发异步处理：
```bash
curl -X POST http://127.0.0.1:8000/api/v1/experience/batches/<batch_id>/process
```
返回中会有 `task_id`。
3. 轮询任务状态：
```bash
curl http://127.0.0.1:8000/api/v1/experience/tasks/<task_id>
```
`status` 从 `queued/running` 到 `completed/failed`。
4. 查看高频题：
```bash
curl "http://127.0.0.1:8000/api/v1/experience/hot-questions?days=180&limit=20"
```
5. 查看题簇详情：
```bash
curl "http://127.0.0.1:8000/api/v1/experience/clusters/<cluster_id>"
```

## 4. Qdrant 配置说明

- **版本**：当前固定 `v1.15.3`，与 qdrant-client 兼容；如需升级可查 [Qdrant 发布页](https://github.com/qdrant/qdrant/releases)
- **持久化**：`./qdrant_storage` 挂载到容器 `/qdrant/storage`，数据落盘宿主机
- **内存限制**：`.env` 中 `QDRANT_MEMORY_LIMIT`（默认 1G）；非 Swarm 模式下需 `docker compose --compatibility up` 才能生效
- **低资源**：已启用 `ON_DISK_PAYLOAD=true`，payload 落盘以减内存

## 5. 端口配置

- 宿主机端口在 `coach-app/.env` 中配置：`FRONTEND_PORT`、`BACKEND_PORT`、`QDRANT_PORT`
- 复制 `coach-app/.env.example` 为 `coach-app/.env` 后修改
- 后端监听端口 `APP_PORT` 在 `backend/.env` 中，仅影响本地 `uvicorn`；Docker 容器内固定 8000

## 6. 数据持久化与备份

### 需要备份的内容
- `backend/data/coach_app.db`（SQLite）
- `backend/data/experience_uploads/`（上传原图）
- `qdrant_storage/`（Qdrant 向量数据）

### 简单备份示例
```bash
tar -czf coach-backup-$(date +%F).tar.gz \
  backend/data \
  qdrant_storage
```

## 7. 资源建议与限制

- 建议起步：2 vCPU / 4GB RAM / 20GB 磁盘
- 当前版本建议：单 backend 实例（1 worker）
- 若后续要多实例/高并发：
1. 把 SQLite 升级到 PostgreSQL
2. 把进程内队列升级为 Redis + Celery/RQ/Arq
3. 再做 backend 水平扩容

## 8. 常见问题

### Q1: 处理任务长时间 `queued`
- 先看后端日志：`docker logs coach-backend --tail 200`
- 确认 API key 有效、外网可访问模型服务

### Q2: `failed` 且报模型调用超时
- 调大 `OPENROUTER_TIMEOUT_SECONDS`
- 临时切更快模型，降低单张图片复杂度

### Q3: 手机能访问但接口 502/超时
- 检查 frontend 到 backend 的网络（容器名 `backend`）
- 检查 `coach-backend` 是否健康
