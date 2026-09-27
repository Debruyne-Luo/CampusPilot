"""In-memory state; single-process sequential use, no restart durability."""

from campuspilot.contracts import ExecutionContext, RunResult, Session, TraceEvent


class SessionConflict(RuntimeError):
    pass


class JournalError(RuntimeError):
    pass


class InMemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._active: dict[str, str] = {}
        self._attempts: dict[str, int] = {}

    def create(self, session_id: str) -> Session:
        if session_id in self._sessions:
            raise SessionConflict("Session already exists")
        session = Session(session_id=session_id)
        self._sessions[session_id] = session
        return session.model_copy(deep=True)

    def get(self, session_id: str) -> Session:
        return self._sessions[session_id].model_copy(deep=True)

    def begin(self, session_id: str) -> str:
        self.get(session_id)
        if session_id in self._active:
            raise SessionConflict("Session has an active run")
        number = self._attempts.get(session_id, 0) + 1
        self._attempts[session_id] = number
        # Bounded IDs even when the caller uses a maximum-length session identifier.
        run_id = f"run:{tuple(self._sessions).index(session_id) + 1}:{number}"
        self._active[session_id] = run_id
        return run_id

    def finish(self, result: RunResult) -> None:
        if self._active.get(result.session_id) != result.run_id:
            raise SessionConflict("Run does not own session")
        session = self.get(result.session_id)
        self._sessions[result.session_id] = Session(
            session_id=session.session_id,
            revision=session.revision + 1,
            runs=(*session.runs, result.model_copy(deep=True)),
        )
        self.release(result.session_id, result.run_id)

    def release(self, session_id: str, run_id: str) -> None:
        if self._active.get(session_id) == run_id:
            del self._active[session_id]


class InMemoryExecutionJournal:
    def __init__(self) -> None:
        self._events: list[TraceEvent] = []

    def append(
        self,
        context: ExecutionContext,
        kind: str,
        detail: str,
        call_id: str | None = None,
        tool_id: str | None = None,
        evidence_ids: tuple[str, ...] = (),
    ) -> TraceEvent:
        event = TraceEvent.model_validate(
            {
                "sequence": len(self._events) + 1,
                "session_id": context.session_id,
                "task_id": context.task_id,
                "run_id": context.run_id,
                "call_id": call_id,
                "tool_id": tool_id,
                "kind": kind,
                "detail": detail,
                "evidence_ids": evidence_ids,
            }
        )
        self._events.append(event)
        return event

    def events(self, session_id: str) -> tuple[TraceEvent, ...]:
        return tuple(event for event in self._events if event.session_id == session_id)
