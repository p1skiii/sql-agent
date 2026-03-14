# Run Guide

这份文档只回答两件事：

1. 怎么启动并人工检查 PostgreSQL 业务演示线。
2. 怎么确认 CLI 的实验线确实绑定到了 SQLite。

## 0. 先理解双轨结构

### PostgreSQL
用途：业务演示数据库。

用于：
- 后端 API
- 前端页面
- 读查询演示
- 写操作 dry-run 演示
- 写操作 commit 演示
- 风险拦截演示

### SQLite
用途：实验数据库。

用于：
- CLI
- Spider
- benchmark
- 自动化测试
- 低成本复现问题

注意：
- SQLite 不进入 Web 演示端。
- PostgreSQL 不是拿来替代 SQLite 的。

## 1. 环境准备

### 1.1 安装依赖
```bash
uv sync
pnpm --dir frontend install
```

### 1.2 准备 `.env`
```bash
cp .env.example .env
```

至少确认下面这些值存在：

```bash
LLM_API_KEY=your-openai-compatible-key
LLM_BASE_URL=http://localhost:4141/v1

SQL_AGENT_DB_BACKEND=postgres
SQL_AGENT_DB_URL=postgresql+psycopg://sql_agent:sql_agent@127.0.0.1:15432/sql_agent_demo
SQL_AGENT_SCHEMA_PATH=./schema.postgres.sql
SQL_AGENT_SEED_PATH=./seed.postgres.sql
SQL_AGENT_OVERWRITE_DB=true
```

说明：
- 文档默认模型代理地址是 `http://localhost:4141/v1`。
- 如果模型代理没起，常见业务演示问题现在有本地 fallback，可继续做人工 review。
- 如果你完全不做 Web 业务演示，只跑 SQLite CLI，那么 `SQL_AGENT_DB_BACKEND` 和 `SQL_AGENT_DB_URL` 可以不生效。

## 2. PostgreSQL 业务演示线

这一段是你“打开后端，打开前端，然后检查业务逻辑层面演示”的标准流程。

### 2.1 启 PostgreSQL
```bash
docker compose -f docker-compose.postgres.yml up -d postgres
```

### 2.2 启后端
```bash
uv run sql-agent-api --host 127.0.0.1 --port 8000
```

这会启动当前 Flask API。当前后端可用路由包括：
- `POST /run`
- `POST /api/query`
- `GET /api/schema`
- `GET /api/examples`
- `GET /api/health`

### 2.3 启前端
```bash
SQL_AGENT_RUN_URL=http://127.0.0.1:8000/run pnpm --dir frontend dev --hostname 127.0.0.1 --port 3000
```

打开：

```text
http://127.0.0.1:3000
```

### 2.4 你应该人工检查的 4 组案例

#### 读查询案例
输入：

```text
Show the inventory for all laptop products.
```

你要确认：
- 返回的是电商业务数据，不是 `students` / `courses`
- 数据来自 `products + inventory + categories`
- 至少应能看到 `LAP-001` 和 `LAP-002`

#### 写操作 dry-run 案例
输入：

```text
Update the inventory quantity for product LAP-001 to 15.
```

前端要开启写入，但保持 dry-run。

你要确认：
- 返回内容明确是演练模式
- 能看到“将影响 1 行”或者等价效果
- 不是真正提交

#### 写操作 commit 案例
输入：

```text
Update the inventory quantity for product LAP-001 to 15.
```

这次切成 commit。

你要确认：
- 返回内容明确是已提交
- 再查一次时，数量已经变成 `15`

#### 风险拦截案例
输入：

```text
Update all inventory quantities to 0.
```

你要确认：
- 系统拒绝执行
- 理由是危险更新、无 `WHERE`、或者宽更新拦截

### 2.5 不经过前端的后端检查

如果你想绕开前端，先做最小健康检查：

```bash
curl -s http://127.0.0.1:8000/api/health
curl -s http://127.0.0.1:8000/api/schema
curl -s http://127.0.0.1:8000/api/examples
```

你要确认：
- `/api/health` 返回 `ok=true`
- `/api/schema` 返回业务表概览，例如 `products`、`inventory`、`orders`
- `/api/examples` 返回内置英文问题列表

如果你要直接验证查询执行，可以打 `/run`，也可以打 `/api/query`。两者当前行为等价。

`/run` 示例：

```bash
curl -s http://127.0.0.1:8000/run \
  -H 'Content-Type: application/json' \
  -d '{"question":"Show the inventory for all laptop products.","allow_write":false,"dry_run":true}'
```

`/api/query` 示例：

```bash
curl -s http://127.0.0.1:8000/api/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"Show the inventory for all laptop products.","allow_write":false,"dry_run":true}'
```

你要确认：
- `status=SUCCESS`
- 返回里有 `result.columns`
- 返回里有 `result.rows`
- 返回里有 `result.row_count`

## 3. SQLite 实验线

这一段是你“检查 CLI 是否真的更改了，并且绑定到 SQLite”的标准流程。

### 3.1 先看代码上的硬绑定点

看 [cli.py](/Users/wang/i/langchain-sql/src/sql_agent_demo/interfaces/cli.py#L264)。

当前逻辑是：
- `experiment-run-file`
- 如果你没有显式传 `--db-backend`
- 它会默认把 `db_backend` 设成 `sqlite`

也就是这条实验命令本身就有默认绑定，不依赖你全局 `.env` 里是不是 `postgres`。

### 3.2 看帮助文本
先跑：

```bash
uv run sql-agent --help
uv run sql-agent experiment-run-file --help
```

你要确认：
- 总说明里写清楚 `PostgreSQL` 是 business demo path
- `experiment-run-file` 写清楚是 SQLite experiment workflow

### 3.3 跑 SQLite smoke
```bash
uv run sql-agent experiment-run-file configs/queries/sqlite_smoke.yaml --db-path ./sandbox/sandbox.db
```

你要确认：
- 命令能跑通
- 它用的是 SQLite 文件库
- 返回的是 CLI 实验结果，不经过前端

### 3.4 做一个反证检查

即使你的 `.env` 默认还是：

```bash
SQL_AGENT_DB_BACKEND=postgres
```

你仍然执行：

```bash
uv run sql-agent experiment-run-file configs/queries/sqlite_smoke.yaml --db-path ./sandbox/sandbox.db
```

如果这条命令还能正常走 SQLite，说明：
- `experiment-run-file` 的默认绑定生效了
- 它不是跟着全局 PostgreSQL 默认值走的

### 3.5 跑 Spider / benchmark 风格实验
```bash
uv run python scripts/run_benchmark.py \
  --config configs/eval/sqlite_spider.yaml \
  --dataset datasets/spider/dev.jsonl \
  --tag sqlite_spider
```

这条命令属于实验线，不属于 Web 业务演示线。

## 4. 最短人工 Review 清单

如果你只想快速过一遍，按这个顺序执行。

### 4.1 验 PostgreSQL 业务演示
1. `docker compose -f docker-compose.postgres.yml up -d postgres`
2. `uv run sql-agent-api --host 127.0.0.1 --port 8000`
3. `SQL_AGENT_RUN_URL=http://127.0.0.1:8000/run pnpm --dir frontend dev --hostname 127.0.0.1 --port 3000`
4. 打开 `http://127.0.0.1:3000`
5. 依次测：
   - `Show the inventory for all laptop products.`
   - `Update the inventory quantity for product LAP-001 to 15.` dry-run
   - `Update the inventory quantity for product LAP-001 to 15.` commit
   - `Update all inventory quantities to 0.`

### 4.2 验 SQLite CLI
1. `uv run sql-agent --help`
2. `uv run sql-agent experiment-run-file --help`
3. `uv run sql-agent experiment-run-file configs/queries/sqlite_smoke.yaml --db-path ./sandbox/sandbox.db`

## 5. Troubleshooting

### `Connection refused`
如果你看到：

```text
<urlopen error [Errno 61] Connection refused>
```

含义通常是模型代理没起。

当前状态：
- 常见业务演示问题已经加了本地 SQL fallback
- 所以读库存、更新库存、订单状态变更这类基础演示，不应该再因为这个错误完全卡死

### PostgreSQL 连接失败
如果后端启动时报 PostgreSQL 初始化失败，重点检查：

```bash
SQL_AGENT_DB_URL=postgresql+psycopg://sql_agent:sql_agent@127.0.0.1:15432/sql_agent_demo
```

以及容器是否已启动：

```bash
docker compose -f docker-compose.postgres.yml up -d postgres
```

### 前端打不通后端
重点检查：

```bash
SQL_AGENT_RUN_URL=http://127.0.0.1:8000/run
```

以及后端是否真的在 `8000` 端口启动。

### `/api/health` 或 `/api/schema` 返回 404
这通常不是接口没实现，而是你当前访问的是旧的后端进程。

先停掉旧进程，再用当前源码重启：

```bash
uv run sql-agent-api --host 127.0.0.1 --port 8000
```

然后重新验证：

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/schema
```
