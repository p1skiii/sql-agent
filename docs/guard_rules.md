# Guard Rules (current implementation)

- READ_ONLY:
  - Only SELECT allowed; multiple statements rejected; forbidden keywords (insert/update/delete/alter/drop/truncate/create).
- WRITE_GUARD:
  - Only INSERT/UPDATE/DELETE; forbid DDL keywords; forbid multiple statements.
  - UPDATE/DELETE require WHERE; reject tautology (1=1) and broad IS NOT NULL without operator.
- REQUIRE_WHERE: enabled by default; can be bypassed only with allow_force+--force.
- MULTI_ROW_WRITE: wide update/delete blocked if affected_rows>1 and not force.
- MAX_WRITE_ROWS: block if probe rows exceed limit.

Error codes commonly emitted: WRITE_GUARD, WRITE_WIDE, WRITE_DISABLED, FORCE_DISABLED, WRITE_REFUSED, WRITE_EXEC_ERROR. Guard hit is derived when error_code contains "GUARD" or WRITE_*.
