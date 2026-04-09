# API Contract (AMP v1)

## Task endpoints

- `POST /api/tasks/plan`
- `POST /api/tasks/{task_id}/confirm`
- `GET /api/tasks/{task_id}`

All task responses contain:

- `task_id`
- `status`
- `risk_level`
- `thinking_summary`
- `workflow[] { step, agent, purpose }`
- `result | proposal | error`
- `trace[] { name, agent, preview, notes, duration_ms }`

## Risk and confirmation policy

- `R0`: auto execution (read)
- `R1`: confirmation required
- `R2`: strong confirmation / blocked by policy for DDL proposal flow

## Deprecated

- `POST /run` -> `410`
- `POST /api/query` -> `410`
