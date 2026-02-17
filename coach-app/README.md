# Coach App

面向 Java 后端面试复习的 Web 服务，基于本仓库 `resources` 构建，支持：
- 随机抽题
- 解释知识点（本地资料 + 联网检索）
- 出题训练
- 面经挖掘（多图上传 -> 题目抽取 -> 高频统计）

## 技术栈
- 前端：React + Vite + Tailwind
- 后端：FastAPI + SQLModel + SQLite
- 向量检索：Qdrant
- 模型调用：OpenRouter
- Explain 联网检索：Perplexity + Jina Reader，失败回退 OpenRouter Web Plugin

## 快速启动（Docker）

1. 配置环境变量：

```bash
cp backend/.env.example backend/.env
cp .env.example .env   # 可选：自定义端口，默认 3000/8000/6333
# 编辑 backend/.env，至少填 OPENROUTER_API_KEY
# 如果启用混合联网检索，填 PERPLEXITY_API_KEY 和 JINA_API_KEY
# 自定义端口时编辑 .env 中的 FRONTEND_PORT、BACKEND_PORT、QDRANT_PORT
```

2. 启动服务：

```bash
docker compose up -d --build
# 若需 Qdrant 内存限制生效，使用：docker compose --compatibility up -d --build
```

3. 访问（默认端口，自定义见 `.env`）：
- 前端：[http://localhost:3000](http://localhost:3000)
- 后端健康检查：[http://localhost:8000/health](http://localhost:8000/health)

## 首次索引

有两种方式：
- 前端右上角点击“重建索引”
- 或直接调用：

```bash
curl -X POST http://localhost:8000/api/v1/index/rebuild
```

## 面经挖掘（API）

```bash
# 1) 上传一次面试的多张截图
curl -X POST http://localhost:8000/api/v1/experience/batches \
  -F "files=@./1.png" \
  -F "files=@./2.png" \
  -F "company=字节跳动" \
  -F "business_line=剪辑产品"

# 2) 触发处理（视觉抽取 + 聚类）
curl -X POST http://localhost:8000/api/v1/experience/batches/<batch_id>/process

# 3) 查询近半年高频题
curl "http://localhost:8000/api/v1/experience/hot-questions?days=180&limit=20"
```

## 模型与检索策略

- 聊天、嵌入、音频转写全部通过 OpenRouter 调用。
- OpenRouter provider 路由可通过 `.env` 配置：`OPENROUTER_PROVIDER_ORDER`、`OPENROUTER_ALLOW_FALLBACKS`、`OPENROUTER_PROVIDER_SORT`。
- Explain 模式默认流程：
  1. 本地向量检索（Qdrant）
  2. Perplexity 搜索（限定英文、最近一个月）
  3. Jina Reader 抓取前若干结果正文
  4. 汇总后交给 OpenRouter 生成答案
- 若 Perplexity/Jina 出错，自动回退到 OpenRouter web plugin。

## 开发启动（本地）

### 后端

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

## 注意事项

- `resources` 以只读方式挂载进后端容器：`/app/resources`。
- `xiaolin-java` 当前可先索引已有 markdown 文本（例如 `out.md`），后续可补全 PDF 转 markdown 后再重建索引。

## 低内存建议

- 建议最小配置：2 vCPU / 4GB RAM / 20GB 磁盘。
- 当资源紧张时，先降低并发与检索规模：
  - `RETRIEVAL_TOP_K=4`
  - `CHUNK_SIZE=900`
  - `CHUNK_OVERLAP=120`
- 索引任务建议在业务低峰执行。

## 已知风险与后续优化

- Perplexity 与 Jina 都可能出现偶发超时，系统已做重试并可回退到 OpenRouter web plugin。
- 前端语音识别受浏览器兼容性限制，当前实现为 Web Speech 优先、上传转写兜底。
- 大规模资料重建索引会产生较高 embedding 成本，建议按目录分批索引（后续可补增量索引）。
