# Adapter Contract Samples

- `read_success`, `write_dry_run_success`, and `write_commit_success` are live `/api/chat` outputs captured through the real adapter route with the local proxy model at `LLM_BASE_URL=http://localhost:4141/v1`.
- `unsupported` and `error` are normalized from audit-stage real backend failure payloads so failure-shape examples stay stable.
- `bad_request` is the local adapter validation shape returned before any backend call.
