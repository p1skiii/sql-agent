# Frontend Evidence UI Notes

- Phase 2 input is frozen at adapter commit `1f4fac0` (`adapter/normalize-api-chat`).
- This Phase 3 worktree consumes that normalized `/api/chat` contract as stable input and does not redefine the adapter shape.
- READ result preview now comes from the backend `/run` payload. The adapter keeps the normalized contract stable and no longer does an adapter-local database reread for READ success.
