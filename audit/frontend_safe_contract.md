# Frontend Safe Contract

Source of truth for this document:
- `audit/report.md`
- `audit/samples/read_success/`
- `audit/samples/write_dry_run_success/`
- `audit/samples/write_commit_success/`
- `audit/samples/unsupported/`
- `audit/samples/error/`
- `audit/samples/bad_request_validation/`

This contract is for the current `/api/chat` response shape, not `/run` directly.

## Always Safe Fields

No top-level JSON body field is always present across every `/api/chat` response.

What is always safe today:
- HTTP status code
- `Content-Type: application/json`

What is not always safe at the body level:
- `summary`
- `raw`
- `error`

Frontend implication:
- treat `/api/chat` as a split contract: success body and failure body are different shapes

## Conditionally Safe Fields

Success-only safe fields:
- `summary: string`
- `raw: object`
- `raw.ok: boolean`
- `raw.status: string`
- `raw.mode: string`
- `raw.sql: string`
- `raw.raw_sql: string | null`
- `raw.repaired_sql: string | null`
- `raw.summary: string`
- `raw.trace: array`
- `raw.dry_run: boolean | null`

Failure-only safe fields:
- `error: string`

Important condition on `error`:
- local `/api/chat` validation failure returns a plain message string, for example `question is required`
- backend-proxied failure returns a serialized backend JSON string, not a parsed object
- display `error` as text only unless frontend adds an explicit guarded parser later

Write-success-only safe fields:
- `raw.mode === "WRITE"`
- `raw.dry_run` to distinguish dry-run vs commit
- `raw.summary` for a user-facing write result string

Read-success-only safe fields:
- `raw.mode === "READ"`
- `raw.summary`
- `raw.sql`
- `raw.trace`

## Unsafe / Do Not Depend On Yet

Do not depend on these yet:
- `raw.affected_rows`
- `raw.diagnosis`
- `raw.reason`
- `raw.error_code` as a unified frontend status source
- `raw.repaired_sql` always existing
- `raw` existing on failure
- `summary` existing on failure
- `error` being machine-parseable JSON
- one single top-level JSON shape covering both success and failure

Why these are unsafe:
- `raw.affected_rows` is observed as `null` even for successful writes
- `raw.diagnosis` is only available inside stringified backend errors, and not for local `/api/chat` validation failures
- `raw.reason` and `raw.error_code` are not exposed at the `/api/chat` top level on failure
- `raw.repaired_sql` is optional and absent in sampled write success responses

## Practical UI Mapping

Safe now:
- result message: `summary` on success, `error` on failure
- SQL panel: `raw.sql`, `raw.raw_sql`, `raw.repaired_sql` when `raw` exists
- trace panel: `raw.trace` when `raw` exists
- write badge: `raw.mode` plus `raw.dry_run` when `raw` exists

Not safe now:
- exact affected-row badge from `raw.affected_rows`
- UI logic that assumes `error` can always be parsed back into structured JSON
- UI logic that assumes `raw.status` exists on failure
