"""Run a read-only SQLite query and return JSON rows for adapter enrichment."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from sql_agent_demo.core.models import SqlGuardViolation
from sql_agent_demo.core.safety import validate_readonly_sql


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute a read-only SQL query and return JSON.")
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--sql", required=True)
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        raise SystemExit(f"Database file does not exist: {db_path}")

    sql = args.sql.strip()
    try:
        validate_readonly_sql(sql)
    except SqlGuardViolation as exc:
        raise SystemExit(exc.reason) from exc

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(sql)
        columns = [col[0] for col in cursor.description or []]
        rows = [dict(row) for row in cursor.fetchall()]

    payload = {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
    }
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
