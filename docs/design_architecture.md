# SQL Agent Demo – Architecture v3.2（简化伪代码版）

目标：

* 做一个 **只读 SQL Agent**，可以当作品集 & 论文骨架；
* **自然语言部分都用真实模型完成**（Intent / NL→SQL / 自检）；
* **SQL 安全用硬规则防线**；
* 留出 trace，未来前端可以展示“工作流”。

---

## 1. 目录结构

基于 `src/sql_agent_demo/`：

```text
src/sql_agent_demo/
  core/
    models.py       # 数据模型 + 异常
    intent.py       # 意图识别（LLM）
    safety.py       # SQL 只读安全检查（硬规则）
    summarizer.py   # 结果摘要（规则）
    sql_agent.py    # 总入口 + READ pipeline（内部包含：NL→SQL、自检、trace）

  infra/
    config.py       # 读取配置（默认 + env + CLI 覆盖）
    db.py           # SQLite sandbox 初始化 + 查询执行
    llm_provider.py # 创建模型实例（intent_model / sql_model）
    logging.py      # 日志初始化

  interfaces/
    cli.py          # 命令行入口
    api.py          # HTTP 入口占位（未来再做）

tests/
  ...               # pytest，之后再写
```

---

## 2. 数据模型（`core/models.py`）

### 2.1 枚举

* `IntentType`

  * `READ_SIMPLE`
  * `READ_ANALYTIC`
  * `WRITE`
  * `COMPLEX_ACTION`
  * `UNSUPPORTED`

* `TaskStatus`

  * `SUCCESS`
  * `ERROR`
  * `UNSUPPORTED`

* `SeverityLevel`

  * `INFO`
  * `WARNING`
  * `DANGER`

### 2.2 配置 & 上下文

* `AgentConfig`（配置）

  * `top_k`：给模型看的 schema 信息“数量提示”

  * `max_rows`：最多返回给用户的行数

  * `allow_trace`：是否记录 trace

  * `db_path`：SQLite 路径

  * `schema_path`：schema.sql 路径

  * `seed_path`：seed.sql 路径

  * `overwrite_db`：是否重建 DB

  * `intent_model_name`：意图识别用的模型名

  * `sql_model_name`：NL→SQL & 自检用的模型名

  * `selfcheck_enabled`：是否启用自检

  * `language`：问题语言（MVP1 固定 `"en"`）

* `AgentContext`（运行上下文）

  * `config`：AgentConfig
  * `db_handle`：数据库句柄（infra/db 提供）
  * `intent_model`：意图模型（统一抽象）
  * `sql_model`：SQL 模型（统一抽象）

### 2.3 结果 & Trace

* `StepTrace`

  * `name`：步骤名称（例如 `"intent_detection"`、`"generate_sql"`）
  * `input_preview`：输入概要（简短文本/字段）
  * `output_preview`：输出概要（如 intent、sql 片段、row_count）
  * `severity`：严重级别
  * `notes`：备注（字符串或 None）

* `QueryResult`

  * `sql`：最终执行的 SQL
  * `columns`：列名列表
  * `rows`：行数据列表（最多 `max_rows`）
  * `summary`：摘要字符串
  * `trace`：`StepTrace` 列表或 None

* `TaskResult`

  * `intent`：IntentType
  * `status`：TaskStatus
  * `query_result`：QueryResult 或 None
  * `error_message`：错误信息（如果有）
  * `raw_question`：原始用户问题

### 2.4 异常类型

* `SqlAgentError`：所有 Agent 相关错误的基类
* `LlmNotConfigured`：没有配置 API Key / 模型不能用
* `UnsupportedOperation`：不支持的操作类型（比如写入）
* `SqlGuardViolation`

  * 包含：`sql`、`reason`
* `DbExecutionError`

  * 包含：`sql`、`inner_message`

---

## 3. core 模块

### 3.1 `core/intent.py` – 意图识别

**对外函数**

* `detect_intent(question, model) -> IntentType`

**逻辑（伪代码）**

```text
function detect_intent(question, model):
  1. 构造提示词：
     - system：你是 DB 助手，只输出一个标签：
       READ_SIMPLE / READ_ANALYTIC / WRITE / COMPLEX_ACTION / UNSUPPORTED
     - user：包含用户问题文本

  2. 调用 model.generate(messages)，拿到字符串 label

  3. 统一大写，去空格

  4. 如果 label 是 "READ_SIMPLE" / "READ" → 返回 IntentType.READ_SIMPLE
     如果 label 是 "READ_ANALYTIC" → 返回 IntentType.READ_ANALYTIC
     如果 label 是 "WRITE" → 返回 IntentType.WRITE
     如果 label 是 "COMPLEX_ACTION" → 返回 IntentType.COMPLEX_ACTION
     其他 → 返回 IntentType.UNSUPPORTED
```

---

### 3.2 `core/safety.py` – SQL Guard（只读安全）

**对外函数**

* `validate_readonly_sql(sql) -> None`

**逻辑（伪代码）**

```text
function validate_readonly_sql(sql):
  1. 去掉首尾空白，转小写，得到 normalized

  2. 如果 normalized 为空 → 抛 SqlGuardViolation("Empty SQL")

  3. 如果不是以 "select" 开头 → 抛 SqlGuardViolation("Only SELECT allowed")

  4. 检查分号：
     - 如果在字符串中间出现 ;（不是最后一位）→ 抛 SqlGuardViolation("Multiple statements")

  5. 定义黑名单动词：
     ["insert", "update", "delete", "alter", "drop", "truncate", "create"]

     对每个动词：
       如果它在 normalized 里出现（以空格或换行分隔），
       → 抛 SqlGuardViolation("Forbidden keyword: xxx")

  6. （可选）以后再加 AST 级校验

  7. 如果没抛异常 → 认为 SQL 安全（只读）
```

---

### 3.3 `core/summarizer.py` – 结果摘要

**对外函数**

* `summarize(question, columns, rows) -> str`

**逻辑（伪代码）**

```text
function summarize(question, columns, rows):
  1. 如果 rows 为空：
       返回 "No results found for '{question}'."

  2. row_count = rows 的长度

  3. 选展示列 display_idx：
     - 优先包含 "name" 的列
     - 否则取与 question token 交集最高的列
     - 如果只有 1 列则直接使用；若多列且没有匹配则返回 None

  4. 从 question 提取 subject（list/show 之后的 1~3 个 token，剔除 all/the/please 等）
     label = subject 或 display 列名（做简单单复数处理）
     prefix = "{row_count} {label}"

  5. 如果 display_idx 存在：
       - 取前 10 个值，逗号拼接；超出加 "(+N more)"
       - 返回 "{prefix}: v1, v2, v3 ..."
     否则：
       - 用第一行构造 "col: value" 对
       - 返回 "{prefix}. Example -> col1: v1, col2: v2, ..."
```

---

### 3.4 `core/sql_agent.py` – 总入口 + READ pipeline（含 NL→SQL、自检、trace）

#### 3.4.1 顶层入口：`run_task`

**对外函数**

* `run_task(question, ctx) -> TaskResult`

**逻辑（伪代码）**

```text
function run_task(question, ctx):
  1. 创建 traces 空列表

  2. 调用 detect_intent(question, ctx.intent_model) → intent

  3. 在 traces 里追加 StepTrace：
     - name: "intent_detection"
     - input_preview: {question 的截断版}
     - output_preview: {intent 名字}
     - severity: INFO

  4. 如果 intent 是 READ_SIMPLE 或 READ_ANALYTIC：
       调用 run_read_query(question, ctx, intent, traces)
       返回这个 TaskResult

  5. 否则（WRITE / COMPLEX_ACTION / UNSUPPORTED）：
       构造一个 TaskResult：
         - intent: 当前 intent
         - status: UNSUPPORTED
         - query_result: None
         - error_message: 说明“只读 demo，不支持该类型操作”
         - raw_question: question
       返回它
```

---

#### 3.4.2 内部：生成 SQL（NL→SQL）`_generate_sql_with_llm`

**内部函数**

* `_generate_sql_with_llm(question, table_info, model, top_k) -> sql 或 None`

**逻辑（伪代码）**

````text
function _generate_sql_with_llm(question, table_info, model, top_k):
  1. 构造 system 提示：
     - 你是 SQL 专家
     - 只生成 1 条 SQL
     - 必须是 SELECT（只读）
     - 禁止各种写操作动词
     - 如果用户在要求修改/删除/多步骤操作 → 不生成 SQL，
       而是只输出 "ONLY_READ_ONLY_SUPPORTED"

  2. 构造 user 提示：
     - 包含简化的 table_info（带 top_k 提示）
     - 包含用户 question

  3. 调用 model.generate(messages) → 原始文本 text

  4. 如果 text 中包含 "ONLY_READ_ONLY_SUPPORTED"：
       返回 None（表示模型拒绝生成）

  5. 如果 text 被 ```sql ... ``` 包裹：
       去掉这些标记，保留中间内容

  6. 去掉前后空白，得到 sql 字符串

  7. 返回 sql
````

---

#### 3.4.3 内部：自检 `_selfcheck_sql`

**内部函数**

* `_selfcheck_sql(question, sql, model) -> SelfCheckResult`

（SelfCheckResult 可以在 models 里定义：`is_readonly` / `is_relevant` / `risk_level` / `notes`）

**逻辑（伪代码）**

```text
function _selfcheck_sql(question, sql, model):
  1. 构造 system 提示：
     - 你的任务：审查 SQL
     - 判断：
       a) 是否只读（SELECT-only）
       b) 是否回答了用户问题
       c) 风险等级：INFO / WARNING / DANGER
     - 要求返回 JSON（四个字段）

  2. 构造 user 提示：
     - 包含 question 和 sql

  3. 调用 model.generate(messages) → 文本

  4. 尝试从文本中解析 JSON，如果失败就给默认值：
     - is_readonly = False
     - is_relevant = True
     - risk_level = WARNING
     - notes = ""

  5. 构造 SelfCheckResult 对象返回
```

> MVP1 策略：
>
> * 自检的结果只用来写进 trace / 日志，不真正阻止执行；
> * 真正阻止执行的是 `validate_readonly_sql(sql)`。

---

#### 3.4.4 READ pipeline：`run_read_query`

**内部函数**

* `run_read_query(question, ctx, intent, traces) -> TaskResult`

**逻辑（伪代码）**

```text
function run_read_query(question, ctx, intent, traces):
  1. 从 ctx.db_handle 获取 table_info（简要的 schema 字符串）

     在 traces 追加 StepTrace:
       name: "load_schema"
       output_preview: {table_info 的截断版}

  2. 调用 _generate_sql_with_llm(question, table_info, ctx.sql_model, ctx.config.top_k)
     → sql 或 None

     如果返回 None：
       - 构造 TaskResult:
           status: UNSUPPORTED
           error_message: "模型认为这个请求不是只读查询"
       - 返回

     否则：
       在 traces 追加 StepTrace:
         name: "generate_sql"
         output_preview: {sql 的截断版}

  3. 如果 config.selfcheck_enabled 为 True：
       - 调用 _selfcheck_sql(question, sql, ctx.sql_model) → sc
       - 在 traces 追加 StepTrace:
           name: "selfcheck"
           output_preview: {is_readonly, is_relevant, risk_level}
           severity: sc.risk_level
       - （MVP1 不根据 sc 结果阻止执行，只记录）

  4. 调用 validate_readonly_sql(sql)：
       - 如果抛出 SqlGuardViolation → 交给外层处理（CLI 打印错误并退出）
       - 如果正常返回 → 说明 SQL 通过硬规则校验

  5. 调用 ctx.db_handle.execute_select(sql) → (columns, all_rows)
       - 如果底层抛异常 → 包装成 DbExecutionError 抛出

     截取前 max_rows 行作为 rows

     在 traces 追加 StepTrace:
       name: "execute_sql"
       output_preview: {row_count: all_rows 的长度}

  6. 调用 summarize(question, columns, rows) → summary

     在 traces 追加 StepTrace:
       name: "summarize"
       output_preview: {summary 的截断版}

  7. 构造 QueryResult：
       - sql
       - columns
       - rows
       - summary
       - trace: 如果 config.allow_trace 为 True → 使用 traces；
                否则 → None

  8. 构造 TaskResult：
       - intent: intent
       - status: SUCCESS
       - query_result: 上面的 QueryResult
       - error_message: None
       - raw_question: question

     返回这个 TaskResult
```

---

## 4. infra 模块（高层伪代码）

### 4.1 `infra/config.py` – 加载配置

**对外函数**

* `load_config(cli_overrides) -> AgentConfig`

**逻辑（伪代码）**

```text
function load_config(cli_overrides):
  1. 先设一套默认值：
     - top_k = 5
     - max_rows = 20
     - allow_trace = False
     - db_path = "./sandbox/sandbox.db"
     - schema_path = "./schema.sql"
     - seed_path = "./seed.sql"
     - overwrite_db = False
     - intent_model_name = "gpt-4o-mini"
     - sql_model_name = "gpt-4o-mini"
     - selfcheck_enabled = False
     - language = "en"

  2. 从环境变量读取并覆盖（如果存在）：
     - 如 SQL_AGENT_DB_PATH / SQL_AGENT_MAX_ROWS 等

  3. 再用 cli_overrides 覆盖同名字段

  4. 返回最终的 AgentConfig
```

---

### 4.2 `infra/db.py` – 初始化 DB + 查询执行

**对外内容**

* `init_sandbox_db(config) -> DatabaseHandle`
* `DatabaseHandle` 对象：

  * 方法 `get_table_info() -> str`
  * 方法 `execute_select(sql) -> (columns, rows)`

**`init_sandbox_db` 逻辑（伪代码）**

```text
function init_sandbox_db(config):
  1. 确保 db_path 的上级目录存在

  2. 如果 db 文件不存在 或者 overwrite_db 为 True：
       - 打开一个 sqlite 连接
       - 执行 schema.sql 文件
       - 执行 seed.sql 文件
       - 关闭连接

  3. 创建一个 DatabaseHandle（内部持有某种 DB 引擎/连接）

  4. 返回 DatabaseHandle
```

**`DatabaseHandle` 方法逻辑（伪代码）**

```text
class DatabaseHandle:
  function get_table_info():
    - 查询 sqlite_master 或 INFORMATION_SCHEMA
    - 把每个表名 + 列名 + 类型拼成一段简要文本
    - 返回这段文本

  function execute_select(sql):
    - 打开连接
    - 执行 sql
    - 获取所有行和列名
    - 返回 (columns_list, rows_list)
```

---

### 4.3 `infra/llm_provider.py` – 创建模型实例

**抽象**

* `LanguageModel`：一个有 `.generate(messages) -> str` 接口的对象

**对外函数**

* `build_models(config) -> (intent_model, sql_model)`

**逻辑（伪代码）**

```text
function build_models(config):
  1. 从环境变量读取 API key（LLM_API_KEY）
     - 如果不存在 → 抛 LlmNotConfigured

  2. 基于 config.intent_model_name 创建 intent_model
     - 例如：把它映射成 OpenAI 的某个 chat 模型

  3. 基于 config.sql_model_name 创建 sql_model

  4. 返回 (intent_model, sql_model)
```

> 真正怎么 new OpenAI / DeepSeek / Gemini，由 Codex 根据你的依赖去写具体代码。

---

### 4.4 `infra/logging.py` – 日志初始化

**对外函数**

* `setup_logging(level) -> None`

**逻辑（伪代码）**

```text
function setup_logging(level = "INFO"):
  - 用统一格式初始化 logging
  - 例如输出时间 / 级别 / logger 名称 / 消息
```

---

## 5. interfaces/cli.py – 命令行入口

**对外函数**

* `main() -> None`

**命令行行为**

* 基本用法：

  * `sql-agent-demo "List students majoring in Computer Science ordered by GPA."`

* 支持参数：

  * `--db-path`
  * `--overwrite-db`
  * `--max-rows`
  * `--top-k`
  * `--intent-model`
  * `--sql-model`
  * `--trace`
  * `--selfcheck`

**`main()` 逻辑（伪代码）**

```text
function main():
  1. 使用 argparse 解析：
     - question（必选位置参数）
     - 各种可选参数，写入 cli_overrides 字典

  2. 调用 setup_logging()

  3. 调用 load_config(cli_overrides) → config

  4. 调用 init_sandbox_db(config) → db_handle

  5. 调用 build_models(config) → (intent_model, sql_model)

  6. 构造 AgentContext(ctx):
       - config, db_handle, intent_model, sql_model

  7. 调用 run_task(question, ctx) → result
       - 捕获可能抛出的：
         - SqlGuardViolation
         - DbExecutionError
         - LlmNotConfigured
         - 其他异常（打印后退出）

  8. 根据 result.status 和 result.query_result：
       - 如果 SUCCESS：
           - 打印 Intent
           - 打印 SQL
           - 打印列名和每一行
           - 打印 Summary
           - 如果 config.allow_trace：
               - 打印 Trace 中每个 StepTrace 的简要信息
       - 如果 UNSUPPORTED：
           - 打印 “[UNSUPPORTED] ...错误消息...”
       - 如果 ERROR：
           - 打印 “[ERROR] ...错误消息...”
```
