# TEST_PLAN.md

SQL Agent Demo – 测试规划（以 pytest + 统一配置为核心）

## 1. 测试总体思路


---

## 2. tests 目录结构（建议）

```text
tests/
  conftest.py          # 全局配置与 fixture：模型模式、AgentContext 构造、DB 句柄
  test_db_init.py      # DB 初始化行为（init_sandbox_db）
  test_db_exec.py      # SELECT 执行行为（execute_select）
  test_safety.py       # SQL 只读安全 Guard
  test_summarizer.py   # 摘要策略（summarize）
  test_intent.py       # 意图识别（classify_intent）
  test_selfcheck.py    # 自检（selfcheck_sql）
  test_agent_integration.py  # 集成测试（单一“查询任务” pipeline）
  data/
    schema.sql         # 专门用于测试的 schema
    seed.sql           # 专门用于测试的 seed 数据

一、conftest 简化版：就干两件事
1.1 在 pytest 里加一个 --model 参数

目的：只给集成测试用，用来决定这次用 Fake，还是真 LLM。

伪代码：

# tests/conftest.py

def pytest_addoption(parser):
    parser.addoption(
        "--model",
        action="store",
        default="fake",
        help="Model name for integration tests, e.g. fake, deepseek-v3, gemini-2.5-flash",
    )

1.2 提供一个简单的 model_name fixture

供集成测试用（只这一处用就行）：

# tests/conftest.py

fixture model_name(request):
    """集成测试要用的模型名，来自 --model 参数。"""
    return request.config.getoption("--model")

1.3 DB fixture：就一个，别花里胡哨

所有测试（单元 + 集成）共用一个最简单的 DB fixture：

fixture db_handle(tmp_path):
    """
    - 在 tmp_path 下建一个 sandbox.db
    - 用 tests/data/schema.sql + seed.sql 初始化
    - 返回可执行 SELECT 的 db_handle
    """
    # 伪代码：
    # db_path = tmp_path / "sandbox.db"
    # cfg = AgentConfig(db_path=str(db_path), schema_path="tests/data/schema.sql", seed_path="tests/data/seed.sql", ...)
    # return init_sandbox_db(cfg)


这样你以后要换 DB，只用改这一处 fixture，单测 & 集测全部跟着走。

1.4 集成用的 agent_ctx fixture（只给 test_agent_integration 用）

这里就是你说的「我只想在集成测试里切换 Fake / deepseek / gemini」：

fixture agent_ctx(model_name, db_handle):
    """
    根据 model_name 创建 AgentContext：
      - fake: 注入 Fake 模型（intent/selfcheck/sql 都走假实现，只为验证 pipeline）
      - 其他字符串: 用真实 LLM 构建（deepseek、gemini 等），intent/selfcheck 先 None
    """
    if model_name == "fake":
        # 用一套“全 READ_QUERY”的假模型：
        #   - intent_model: 总是返回 READ_QUERY
        #   - sql_model: 总是生成可用的 SELECT（你可以用固定模板）
        #   - selfcheck_model: None 或总是 OK
        ctx = AgentContext(
            db_handle=db_handle,
            intent_model=AlwaysReadIntentModel(),
            sql_model=FakeSqlModel(),
            selfcheck_model=None,
            config=AgentConfig(...),
        )
    else:
        # 真 LLM 模式：intent/selfcheck 先留空，重点是 sql_model 是个真模型
        real_llm = build_llm_from_name(model_name)
        ctx = AgentContext(
            db_handle=db_handle,
            intent_model=None,          # 将来可以填 LLM intent
            sql_model=real_llm,         # NL → SQL 走真 LLM
            selfcheck_model=None,       # 将来再说
            config=AgentConfig(...),
        )
    return ctx


关键点：

--model 只被 conftest 这里用一次；

单元测试不用管 --model，保持纯粹；

集成测试只写一份，里面用 agent_ctx，不会出现你讨厌的“Fake 测试一套、Real 测试一套”。

二、单元测试文件，按你刚刚列的来

下面是你要求的几个文件 + 每个文件测什么（都是行为伪代码）。

2.1 tests/test_db_init.py

目的：确认 init_sandbox_db 不瞎搞 DB。

场景 1：新建 DB

用新的 temp db_path + tests/data/schema.sql + seed.sql

调用 init

断言：能 SELECT 到数据，不抛错。

场景 2：overwrite_db=False

第一次 init

手动插入一条“噪音数据”

改 config.overwrite_db = False，再 init

断言：噪音数据还在。

场景 3：overwrite_db=True

类似上面，但第二次 init 后，噪音数据应该消失，只剩 seed。

场景 4：schema/seed 路径错 → 抛 DbInitError/ExecutionError。

2.2 tests/test_db_exec.py

目的：确认 execute_select 这个包装自己行为稳定。

场景 1：正常 SELECT

sql = "SELECT id, name FROM students" → 返回列名 + 行。

场景 2：非 SELECT

"UPDATE students SET gpa = 4.0" → 抛 ExecutionError。

场景 3：语法错

"SELECT FROM students" → 抛 ExecutionError。

2.3 tests/test_safety.py

目的：锁 validate_readonly_sql 的规则。

允许：

"SELECT * FROM students"

" SELECT id FROM students; " → 不抛错。

拦截：

非 SELECT 开头：UPDATE, DELETE, INSERT…

多语句："SELECT 1; SELECT 2", "SELECT *; DROP TABLE students"

写操作关键字：DROP, ALTER, TRUNCATE, CREATE

空 / 只空白。

全部抛 SqlGuardViolation。

2.4 tests/test_summarizer.py

目的：锁 summarize(question, columns, rows) 的最小行为。

rows 为空：summary 里有 “No results” 语义。

单列多行：

columns = ["name"], rows = [("Alice",), ("Bob",)]
→ 有行数信息（2 row(s)）、有 "name: Alice" 或类似。

多列：

["id", "name"], [(1, "Alice")]
→ summary 里有 question 一点点关键词（list/students），有 "id: 1" 和 "name: Alice"。

2.5 tests/test_intent.py

这里按照你刚刚的诉求，我设计成一个纯“函数级”的测试，和 --model 毫无关系，只做两件事：

有模型（FakeIntentModel）时：

验证 classify_intent 能把模型输出的 label 映射成你的枚举，比如：

"READ_QUERY" → IntentType.READ_QUERY

"WRITE" → IntentType.WRITE。

没有模型（None）时：

fallback 只做一件极简事：

含 "update"/"delete"/"insert" 这种英文 → IntentType.WRITE

其他 → IntentType.READ_QUERY

2.6 tests/test_selfcheck.py

按你说的：现在简单一点。

当前阶段：

selfcheck_sql(question, sql, model) 只是一个占位：

如果 model is None：直接返回 decision=OK, reason="selfcheck disabled"

如果是 FakeSelfCheckModel：根据 fake 返回写 OK/WARN/BLOCK。

对应 test 可以很简单：

场景 1：model=None → 返回 OK + 字符串 reason。

场景 2：FakeSelfCheckModel 返回 BLOCK → selfcheck_sql 的 decision == BLOCK。

1. Intent 的优雅扩展：就用“策略对象 + 依赖注入”

设计保持这样：

# 统一接口
intent = classify_intent(question: str, intent_model: BaseIntentModel | None) -> IntentType


Fake 模式：

ctx.intent_model = AlwaysReadQueryIntentModel()  # predict() 永远返回 IntentType.READ_QUERY


Real 模式：

ctx.intent_model = LlmIntentModel(real_llm)  # predict(question) -> 某个 IntentType


classify_intent 内部逻辑保持稳定不变：

if intent_model is None:
    # fallback：极简规则（比如有 update/delete 就当 WRITE，否则 READ_QUERY）
else:
    label = intent_model.predict(question)
    return map_label_to_intent_type(label)


以后你要扩展多任务（READ_SIMPLE / READ_AGG / WRITE_UPDATE / DDL_…）：

只需要改：

IntentType 枚举；

LlmIntentModel 里 prompt/解析；

classify_intent / 测试结构 / pipeline 入口都不用大改。

这块我们是完全对齐的。

方案 B：把“不同任务类型”分成几个集成测试（比如之后有 READ / WRITE / UPDATE / DELETE 四类），READ 测 READ pipeline，WRITE 测 WRITE pipeline；真要测“大综合”，另写一层逻辑再说。

我建议你走一个稍微改造过的 方案 B’：

2.1 把“意图识别”和“后半段 pipeline”拆开测试

先约定代码层的结构：

# 顶层入口：真正对外的 Agent
run_task(question: str, ctx: AgentContext) -> TaskResult:
    intent = classify_intent(question, ctx.intent_model)
    match intent:
        case IntentType.READ_QUERY:
            return run_read_query(question, ctx)
        case IntentType.WRITE_UPDATE:
            return run_write_update(question, ctx)
        case IntentType.DELETE:
            return run_delete_task(question, ctx)
        # ... 以后扩展更多 IntentType

# 各条子 pipeline（不再管“这是不是当前 intent”）
run_read_query(...)
run_write_update(...)
run_delete_task(...)


然后测试这样分层：

单元测试：tests/test_intent.py

专门测 classify_intent + BaseIntentModel 派生类（FakeIntentModel / LlmIntentModel 包装）。

跟 DB / SQL / summarizer 完全解耦。

单元测试：tests/test_safety.py / tests/test_summarizer.py / tests/test_db_*.py

专门测 SQL Guard / 摘要 / DB 行为。

集成测试（一类任务一个 pipeline）：

tests/test_read_pipeline.py：只测 run_read_query 这一条链（意图假设已经是 READ）。

以后新增：

tests/test_write_pipeline.py：测 run_write_update；

tests/test_delete_pipeline.py：测 run_delete_task；

这些测试不需要 intent 逻辑参与，因为它们测试的是“后半段”：

SQL 生成

Guard

执行

自检（可选）

摘要

薄路由测试：tests/test_routing.py

就测 run_task 这一层：

用一个 FakeIntentModel，让它 predict 不同 IntentType；

断言 run_task 会调用对应的子 pipeline。

这个测试很轻但非常关键：让 intent 系统“有用”，而不是消失。

这样的好处：

每条 pipeline 的集成都干净（READ 测 READ，未来 WRITE 测 WRITE），不会乱；

Intent 仍然是第一公民（有单测 + 路由集成），不是摆设；

你以后要改 intent 细节，test_routing + test_intent 直接告诉你有没有把 dispatch 搞挂。
