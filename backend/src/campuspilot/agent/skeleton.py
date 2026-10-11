"""Scripted test doubles only; this is not a production Agent runtime."""

from threading import Event

from campuspilot.contracts import (
    ExecutionContext,
    ModelRequest,
    ModelResponse,
    OfficeResult,
    RouteResult,
    RunResult,
    ServiceResult,
    TaskRequest,
    ToolCall,
    ToolResult,
)
from campuspilot.interfaces import ExecutionJournal, ModelProvider, SessionStore
from campuspilot.skills import StaticSkillRegistry
from campuspilot.tools import ToolExecutor


class FakeModelProvider:
    def respond(self, request: ModelRequest) -> ModelResponse:
        if not request.previous_results:
            response = ModelResponse(
                tool_id="search_service",
                arguments={"query": request.objective},
            )
        else:
            data = request.previous_results[-1].data
            if isinstance(data, ServiceResult):
                response = ModelResponse(
                    tool_id="find_office",
                    arguments={"office_id": data.office_id},
                )
            elif isinstance(data, OfficeResult):
                response = ModelResponse(
                    tool_id="route_plan",
                    arguments={"origin": "synthetic:origin", "destination": data.place_id},
                )
            else:
                raise ValueError("Unsupported synthetic model state")
        if response.tool_id not in request.allowed_tools:
            raise ValueError("Unsupported synthetic capability")
        return response


class FakeAgentHarness:
    def __init__(
        self,
        model: ModelProvider,
        sessions: SessionStore,
        skills: StaticSkillRegistry,
        executor: ToolExecutor,
        journal: ExecutionJournal,
    ) -> None:
        self.model = model
        self.sessions = sessions
        self.skills = skills
        self.executor = executor
        self.journal = journal

    def run(self, request: TaskRequest, cancel: Event | None = None) -> RunResult:
        run_id = self.sessions.begin(request.session_id)
        context = ExecutionContext(
            session_id=request.session_id,
            task_id=request.task_id,
            run_id=run_id,
            allowed_tools=frozenset(),
        )
        results: list[ToolResult] = []

        def finish(
            status: str,
            error_code: str | None = None,
        ) -> RunResult:
            result = RunResult.model_validate(
                {
                    "session_id": request.session_id,
                    "task_id": request.task_id,
                    "run_id": run_id,
                    "status": status,
                    "task_outcome": "synthetic_guidance" if status == "completed" else "unresolved",
                    "results": tuple(results),
                    "error_code": error_code,
                }
            )
            self.journal.append(context, "run_finished", error_code or status)
            self.sessions.finish(result)
            return result

        try:
            self.journal.append(context, "run_started", "fake_harness:v1")
            try:
                skill = self.skills.get(request.skill_id)
            except KeyError:
                return finish("failed", "unknown_skill")
            self.journal.append(context, "skill_selected", f"{skill.skill_id}@{skill.version}")
            context = ExecutionContext(
                session_id=request.session_id,
                task_id=request.task_id,
                run_id=run_id,
                allowed_tools=frozenset(skill.required_tools),
            )
            if skill.risk != "public_read":
                return finish("failed", "skill_risk_denied")
            for index in range(request.max_steps):
                if cancel is not None and cancel.is_set():
                    return finish("cancelled", "cancelled")
                try:
                    response = self.model.respond(
                        ModelRequest(
                            objective=request.objective,
                            allowed_tools=skill.required_tools,
                            previous_results=tuple(results),
                        )
                    )
                    # Revalidate even test doubles; never trust provider-created objects.
                    response = ModelResponse.model_validate(response.model_dump())
                except Exception:
                    return finish("failed", "model_error")
                if cancel is not None and cancel.is_set():
                    return finish("cancelled", "cancelled")
                result = self.executor.execute(
                    ToolCall(
                        call_id=f"call:{index + 1}",
                        tool_id=response.tool_id,
                        arguments=response.arguments,
                    ),
                    context,
                )
                results.append(result)
                if result.status == "empty":
                    return finish("needs_input", "missing_evidence")
                if result.status != "success":
                    return finish("failed", result.error_code)
                if isinstance(result.data, RouteResult):
                    if tuple(r.data.kind for r in results if r.data) != (
                        "service",
                        "office",
                        "route",
                    ):
                        return finish("failed", "invalid_demo_sequence")
                    return finish("completed")
            return finish("failed", "step_limit")
        finally:
            # Journal failure propagates; do not report or save a successful run.
            self.sessions.release(request.session_id, run_id)
