# Frontend Evidence UI Notes

- Phase 2 input is frozen at adapter commit `1f4fac0` (`adapter/normalize-api-chat`).
- This Phase 3 worktree consumes that normalized `/api/chat` contract as stable input and does not redefine the adapter shape.
- Known limitation: READ result preview currently comes from the adapter-enriched SQLite helper path. It is the stable evidence source for this UI phase, but it should not be treated as the final database-layer design.
