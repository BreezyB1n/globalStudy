# GlobalStudy AI

GlobalStudy AI 是一个本地运行的毕业设计 Demo，目标是面向 QS 前 50 代表性院校的硕士项目，提供可溯源的项目咨询问答能力。

当前分支提供子任务 1 的基础骨架：

- FastAPI 单体入口
- 环境变量配置管理
- 日志与统一异常处理
- 健康检查接口
- 静态首页托管
- 基础自动化测试

后续的数据采集、结构化抽取、向量知识库和问答链路会在后续功能分支中继续补充。

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

5. 运行测试：

   ```bash
   uv run pytest
   ```

## Project Layout

```text
app/        FastAPI 应用代码
frontend/   静态页面与前端资源
tests/      自动化测试
doc/        设计文档与任务拆分文档
```
