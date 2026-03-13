# Trace Schema (v1)

- trace_version: "v1"
- Step fields: name, output_preview, input_preview, severity, notes, duration_ms, prompt_tokens, completion_tokens, total_tokens
- Stage mapping used in summaries:
  - intent: step name startswith "intent"
  - plan: load_schema, generate_sql, generate_write_sql, selfcheck, repair_sql, repair_after
  - execute: execute_sql, execute_write, execute_write_probe
  - summarize: summarize*
  - other: everything else
- Aggregates:
  - stage_latency_ms: sum of duration_ms per stage
  - stage_tokens: sum of total_tokens per stage
  - tokens: sum of total_tokens all steps

request_id: UUID per sample. run_id: UUID per run. prompt_version: manual tag from config. config_hash: SHA1 of config overrides used for the run.
