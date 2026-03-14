# SQL Agent

这是一个双轨数据库演示项目，不是“PostgreSQL 替代 SQLite”。

- `PostgreSQL`：业务演示数据库，用于后端 API、前端页面、答辩截图、读写流程演示。
- `SQLite`：实验数据库，用于 CLI、Spider、benchmark、低成本复现和自动化验证。

## 你应该先理解的两条线
### 1. PostgreSQL 业务演示线
这一条线是给你打开后端、打开前端、演示真实业务流程用的。

你会看到的业务表包括：
- `users`
- `categories`
- `products`
- `inventory`
- `orders`
- `order_items`
- `payments`

推荐入口：
- 后端 API：`uv run sql-agent-api --host 127.0.0.1 --port 8000`
- 前端：`SQL_AGENT_RUN_URL=http://127.0.0.1:8000/run pnpm --dir frontend dev --hostname 127.0.0.1 --port 3000`

当前后端除了兼容前端的 `POST /run`，还提供几个轻接口：
- `POST /api/query`：和 `/run` 等价的正式查询入口
- `GET /api/schema`：返回当前数据库的表、字段和行数概览
- `GET /api/examples`：返回内置英文示例问题
- `GET /api/health`：返回服务和数据库健康状态

### 2. SQLite 实验线
这一条线是给 CLI、Spider、benchmark 用的，不进 Web 演示端。

推荐入口：
- `uv run sql-agent experiment-run-file configs/queries/sqlite_smoke.yaml --db-path ./sandbox/sandbox.db`

## 最短启动方式
1. 安装依赖：
```bash
uv sync
pnpm --dir frontend install
```

2. 复制环境变量模板：
```bash
cp .env.example .env
```

3. 如果你要演示 Web 业务流程，先启动 PostgreSQL：
```bash
docker compose -f docker-compose.postgres.yml up -d postgres
```

4. 启后端：
```bash
uv run sql-agent-api --host 127.0.0.1 --port 8000
```

5. 启前端：
```bash
SQL_AGENT_RUN_URL=http://127.0.0.1:8000/run pnpm --dir frontend dev --hostname 127.0.0.1 --port 3000
```

6. 打开：
```text
http://127.0.0.1:3000
```

7. 如果你要直接检查后端接口，可以先跑：
```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/schema
curl http://127.0.0.1:8000/api/examples
```

## 你现在最需要看的文档
- 运行和人工 review 步骤：[docs/run_guide.md](/Users/wang/i/langchain-sql/docs/run_guide.md)
- 测试与 smoke 命令：[docs/test_guide.md](/Users/wang/i/langchain-sql/docs/test_guide.md)
- 后端接口契约：[docs/api_contract.md](/Users/wang/i/langchain-sql/docs/api_contract.md)
- 前端适配契约：[frontend/adapter_contract.md](/Users/wang/i/langchain-sql/frontend/adapter_contract.md)

## 两个最关键的命令
### 看 CLI 帮助文本
```bash
uv run sql-agent --help
uv run sql-agent experiment-run-file --help
```

你要确认：
- 总说明里明确写了 `PostgreSQL` 是 business demo path
- `experiment-run-file` 明确写成 SQLite experiment workflow

### 跑 SQLite smoke
```bash
uv run sql-agent experiment-run-file configs/queries/sqlite_smoke.yaml --db-path ./sandbox/sandbox.db
```

## 运行说明
- 使用 [.env.example](/Users/wang/i/langchain-sql/.env.example) 作为起点。
- 文档默认的模型代理地址是 `http://localhost:4141/v1`。
- 前端当前仍通过 `SQL_AGENT_RUN_URL` 连接后端 `/run`。
- 如果你改了 Flask 路由或接口实现，需要重启 `sql-agent-api` 进程，开发服务器不会自动热更新到你已经在后台跑着的旧进程上。
- 现在即使本地模型代理不可达，常见业务演示问题也有本地 fallback，不会再因为 `Connection refused` 完全跑不通。
