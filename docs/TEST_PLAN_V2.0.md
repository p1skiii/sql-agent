You are working inside the langchain-sql-agent-demo repo.

We already have many tests under tests/. Do NOT rewrite tests that are already fine (DB init/exec, safety, summarizer, selfcheck, intent).

Only adjust the fixtures + read pipeline test to match the new design.

1. Update tests/conftest.py

Goal: make it clear this fixture is only for the READ pipeline, and keep fake/real model logic simple.

Please modify tests/conftest.py as follows:

Keep these fixtures unchanged in semantics:

data_dir

pytest_addoption("--model", default="fake")

model_name

db_config

db_handle

Rename agent_ctx fixture → read_agent_ctx and keep it focused on READ pipeline tests:

If model_name == "fake":

intent_model = AlwaysReadIntentModel() (predict → always IntentType.READ_SIMPLE)

sql_model = FakeSqlModel() (returns a fixed SELECT over students)

Else (real model):

intent_model = AlwaysReadIntentModel()（我们在 pipeline 测试里显式传入 intent，不测 intent 识别）

sql_model = build_llm_from_name(model_name)

If this raises LlmNotConfigured, call pytest.skip("NO_API_KEY").

Normalize config before returning AgentContext:

db_config.max_rows = db_config.max_rows or 10
db_config.allow_trace = True

return AgentContext(
    config=db_config,
    db_handle=db_handle,
    intent_model=intent_model,
    sql_model=sql_model,
)


不要在 conftest 里引入新的 TestSettings、全局配置对象之类的东西。
Fixtures 保持目前这种扁平、简单的风格就好。

2. 修正 READ pipeline 集成测试

We already have a test for the read pipeline (currently something like test_read_query_pipeline using agent_ctx).

Please:

确保它在单独的文件里，例如：tests/test_read_pipeline.py。如果现在在别的文件里（比如 test_agent_integration.py），直接重命名文件即可。

修改 test 函数签名，使用新的 fixture 名字：

from sql_agent_demo.core.models import IntentType
from sql_agent_demo.core.sql_agent import run_read_query

def test_read_query_pipeline(read_agent_ctx, model_name: str) -> None:
    question = "List all students"
    traces: list = []

    result = run_read_query(
        question=question,
        ctx=read_agent_ctx,
        intent=IntentType.READ_SIMPLE,  # 显式传 READ_SIMPLE
        traces=traces,
    )

    assert result.query_result is not None
    assert result.query_result.sql.lower().startswith("select")
    assert isinstance(result.query_result.summary, str)
    assert result.query_result.columns

    if model_name == "fake":
        # fake 模型应该返回稳定的行
        assert result.query_result.rows
    else:
        # 真模型只要求有结果，不强行断言内容
        assert result.query_result.rows is not None

    if read_agent_ctx.config.allow_trace:
        assert result.query_result.trace is not None


约束（重要）：

这个 READ pipeline 测试 不要 调用 detect_intent。

它只测试 NL→SQL→guard→DB→summary→trace 这条管线，在调用时显式传 IntentType.READ_SIMPLE。

3. 不需要改动的部分（请保持现状）

请 不要 大改或重写 以下测试文件，只做必要的 import/fixture 名称调整（如果 conftest 改名导致 import 需要修）：

tests/test_db_init.py

tests/test_db_exec.py

tests/test_intent.py

tests/test_safety.py

tests/test_selfcheck.py

tests/test_summarizer.py

这些测试目前的逻辑是 OK 的，只要在你修改 fixture 名称之后还能通过即可。

4. 约束总结

只改：

tests/conftest.py 里的 agent_ctx → read_agent_ctx 及其逻辑；

READ pipeline 的测试文件（重命名 + 使用 read_agent_ctx）。

不要添加复杂的测试配置结构体或全局状态。

不要随便改 src/ 下的生产代码，除非是为了让上面这些测试通过的非常小的调整。

After changes, uv run pytest --model fake should still pass, and the read pipeline test should go through run_read_query(..., intent=IntentType.READ_SIMPLE, ...) using the new read_agent_ctx fixture.
