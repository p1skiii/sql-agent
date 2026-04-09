# Trace Schema (AMP v1)

Each task response exposes `trace[]` entries with:

- `name`: logical step key
- `agent`: runtime agent class
- `preview`: short output summary
- `notes`: optional diagnostics
- `duration_ms`: step latency

Typical read flow:

`intent -> memory -> planner -> normalize -> schema -> plan_sql -> guard -> execute -> summarize`

Typical write flow:

`intent -> memory -> planner -> normalize -> schema -> plan_sql -> guard -> (pending confirmation) -> execute -> summarize`

DDL flow:

`intent -> memory -> planner -> normalize -> proposal`
