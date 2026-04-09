# GlobalStudy AI

GlobalStudy AI 是一个本地运行的毕业设计 Demo，目标是面向 QS 前 50 代表性院校的硕士项目，提供可溯源的项目咨询问答能力。

当前分支提供子任务 1 的基础骨架：

- FastAPI 单体入口
- 环境变量配置管理
- 日志与统一异常处理
- 健康检查接口
- 静态首页托管
- 基础自动化测试

当前已接入子任务 2 的官网采集链路：

- `data/processed/source_catalog.json` 维护学校项目入口清单
- `scripts/crawl_sources.py` 支持按学校、项目、页面类型或全量触发抓取
- 抓取结果写入 `data/raw/<school>/<program>/`
- 失败记录追加到 `logs/crawl_failures.jsonl`

当前已接入子任务 3 的结构化抽取链路：

- `scripts/extract_projects.py` 支持按学校、项目或全量触发结构化抽取
- 抽取结果写入 `data/sqlite/app.db`
- 调试快照写入 `data/processed/projects.json`
- 失败记录追加到 `logs/extract_failures.jsonl`

当前已接入子任务 4 的向量知识库构建链路：

- `scripts/build_vector_store.py` 支持按学校、项目或全量构建 ChromaDB
- 原始 Markdown 会先清洗、分块，再调用百炼 `text-embedding-v3`
- 向量集合持久化到 `data/chroma/`
- 失败记录追加到 `logs/vector_build_failures.jsonl`

当前已接入子任务 5 的问答服务主链路：

- `POST /api/chat` 支持字段型、解释型和基础比较型问题
- 最近几轮消息由前端回传，后端会做实体补全和问题路由
- 字段型问题优先查 `SQLite`，解释型问题优先查 `ChromaDB`
- 返回值统一包含 `answer`、`citations` 和 `resolved_context`

## Quick Start

1. 复制配置模板并填写 Key：

   ```bash
   cp .env.example .env
   ```

2. 安装依赖：

   ```bash
   uv sync --dev
   ```

3. 启动开发服务：

   ```bash
   uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

4. 访问页面与接口：

   - 首页：`http://127.0.0.1:8000/`
   - 健康检查：`http://127.0.0.1:8000/api/health`
   - 问答接口：`http://127.0.0.1:8000/api/chat`

5. 运行测试：

   ```bash
   uv run pytest
   ```

6. 维护入口清单并执行抓取：

   ```bash
   uv run python scripts/crawl_sources.py --school imperial --force
   ```

7. 对已抓取原始页面执行结构化抽取：

   ```bash
   uv run python scripts/extract_projects.py --school imperial --force
   ```

8. 对已抓取原始页面构建向量知识库：

   ```bash
   uv run python scripts/build_vector_store.py --school imperial --force
   ```

9. 调用问答接口：

   ```bash
   curl -X POST http://127.0.0.1:8000/api/chat \
     -H 'Content-Type: application/json' \
     -d '{
       "messages": [
         {"role": "user", "content": "介绍一下帝国理工的 AI 硕士项目"},
         {"role": "assistant", "content": "这是 Imperial College London 的 MSc Artificial Intelligence 项目。"},
         {"role": "user", "content": "那它的雅思要求呢"}
       ]
     }'
   ```

## Project Layout

```text
app/        FastAPI 应用代码
frontend/   静态页面与前端资源
tests/      自动化测试
doc/        设计文档与任务拆分文档
data/       采集原始数据与处理中间文件
scripts/    离线采集脚本
```
