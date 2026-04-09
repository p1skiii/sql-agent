"""Task service coordinates orchestration, memory, and persistence."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from .i18n import detect_language, localize
from .memory import YamlMemoryStore, YamlTaskStore
from .models import ErrorInfo, RunState, TaskStatus
from .orchestrator import Orchestrator, RuntimeContext


@dataclass
class TaskService:
    ctx: RuntimeContext
    orchestrator: Orchestrator
    memory_store: YamlMemoryStore
    task_store: YamlTaskStore

    def bootstrap(self) -> None:
        self.memory_store.bootstrap()
        self.task_store.bootstrap()

    def plan_task(
        self,
        *,
        question: str,
        session_id: str,
        db_target: str,
        language: str = "auto",
    ) -> RunState:
        chosen_language = detect_language(question) if language == "auto" else language
        state = RunState(
            task_id=str(uuid4()),
            session_id=session_id,
            db_target=db_target,
            question=question,
            language=chosen_language,
        )
        state = self.orchestrator.plan(state, self.ctx)

        self.memory_store.append_session_history(
            session_id,
            {
                "task_id": state.task_id,
                "question": question,
                "status": state.status.value,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        self.task_store.save(state)
        return state

    def confirm_task(self, *, task_id: str, approve: bool, comment: str | None = None) -> RunState:
        state = self.task_store.load(task_id)
        if state is None:
            unknown = RunState(
                task_id=task_id,
                session_id="unknown",
                db_target=self.ctx.config.db_target,
                question="",
                language="en",
                status=TaskStatus.FAILED,
                error=ErrorInfo(
                    code="TASK_NOT_FOUND",
                    message=localize("TASK_NOT_FOUND", "en"),
                    recoverable=True,
                ),
            )
            return unknown

        state = self.orchestrator.confirm(state, self.ctx, approve=approve, comment=comment)
        self.task_store.save(state)
        return state

    def get_task(self, task_id: str) -> RunState | None:
        return self.task_store.load(task_id)


__all__ = ["TaskService"]
