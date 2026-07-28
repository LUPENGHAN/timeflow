# Timeflow API

后端使用 Python 3.11、uv、FastAPI、SQLAlchemy、Alembic 和 PostgreSQL。

## 本地启动

```bash
cp .env.example .env
uv sync --locked --all-groups
uv run alembic upgrade head
uv run uvicorn timeapp.main:app --reload
```

如果本机没有 PostgreSQL，使用仓库根目录的 Compose（容器启动时会自动执行迁移）：

```bash
docker compose up --build
```

健康检查：<http://127.0.0.1:8000/api/v1/health>
Swagger：<http://127.0.0.1:8000/docs>

## 语音服务

文本命令入口为 `POST /api/v1/voice/commands`，音频入口为
`POST /api/v1/voice/commands/audio`。外部服务均通过本地 `.env` 配置：

```bash
TIMEAPP_LLM_API_KEY=
TIMEAPP_LLM_BASE_URL=https://api.openai.com/v1
TIMEAPP_LLM_MODEL=gpt-4o-mini

TIMEAPP_ASR_API_KEY=
TIMEAPP_ASR_BASE_URL=https://api.openai.com/v1
TIMEAPP_ASR_MODEL=whisper-1
TIMEAPP_ASR_PROTOCOL=openai_transcription
```

`TIMEAPP_ASR_PROTOCOL` 支持标准 OpenAI multipart 转写接口的
`openai_transcription`，以及通过 Chat Completions 传入 Base64 音频的
`qwen_chat`。未配置 LLM 时自动使用本地关键词解析；未配置 ASR 时音频入口返回
`503 asr_not_configured`。

## 目录结构

```text
src/timeapp/
├── ai/                     # AI 层：ASR 客户端和命令解析器
│   ├── asr/
│   └── parser.py           # LLMCommandParser / MockCommandParser
├── api/                    # HTTP 路由聚合和基础设施探活
├── application/            # 编排：命令处理、确认门禁、事件产出
├── capabilities/           # 能力包：calendar/todo/reminder 等
├── context/                # Context & Policy：触发条件与投递策略
├── core/                   # 配置、数据库连接和基础设施
├── domain/                 # 稳定内核：Command/WriteRequest/DomainEvent 等
└── infrastructure/         # SQLAlchemy 模型
```

完整分层说明见 `docs/architecture.md`。

## 数据库迁移（Alembic）

连接串来自 `TIMEAPP_DATABASE_URL`（见 `.env.example`），不要写进 `alembic.ini`。

```bash
# 应用迁移到最新
uv run alembic upgrade head

# 模型变更后生成迁移（需先在 alembic/env.py 导入新 models 模块）
uv run alembic revision --autogenerate -m "describe change"

# 查看当前版本
uv run alembic current
```

迁移脚本位于 `alembic/versions/`。禁止手改已提交的历史迁移；禁止用 `Base.metadata.create_all` 走生产建表路径。
Docker 镜像通过 `docker-entrypoint.sh` 在启动 uvicorn 前自动执行 `alembic upgrade head`。

## 测试与检查

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

或在仓库根目录执行官方门禁：`bash scripts/check-all.sh backend`。
