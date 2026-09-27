from pydantic import ValidationError

from campuspilot.contracts import (
    Contract,
    ExecutionContext,
    PermissionDecision,
    Status,
    ToolCall,
    ToolDescriptor,
    ToolResult,
)
from campuspilot.interfaces import ExecutionJournal, PermissionPolicy, Tool
from campuspilot.state import JournalError


class ReadOnlyPermissionPolicy:
    def decide(
        self,
        descriptor: ToolDescriptor,
        context: ExecutionContext,
    ) -> PermissionDecision:
        if descriptor.tool_id not in context.allowed_tools:
            return PermissionDecision(allowed=False, reason="tool_not_allowed")
        if descriptor.risk != "public_read":
            return PermissionDecision(allowed=False, reason="risk_not_allowed")
        return PermissionDecision(allowed=True, reason="public_read_allowed")


class ToolExecutor:
    def __init__(
        self,
        tools: tuple[Tool, ...],
        policy: PermissionPolicy,
        journal: ExecutionJournal,
    ) -> None:
        self._tools: dict[str, Tool] = {}
        self._descriptors: dict[str, ToolDescriptor] = {}
        for tool in tools:
            descriptor = ToolDescriptor.model_validate(tool.descriptor.model_dump())
            if descriptor.tool_id in self._tools:
                raise ValueError("Duplicate Tool")
            self._tools[descriptor.tool_id] = tool
            self._descriptors[descriptor.tool_id] = descriptor
        self.policy = policy
        self.journal = journal

    @property
    def tool_ids(self) -> frozenset[str]:
        return frozenset(self._tools)

    def execute(self, call: ToolCall, context: ExecutionContext) -> ToolResult:
        def record(kind: str, detail: str, evidence_ids: tuple[str, ...] = ()) -> None:
            try:
                self.journal.append(
                    context,
                    kind,
                    detail,
                    call.call_id,
                    call.tool_id,
                    evidence_ids,
                )
            except Exception as exc:
                raise JournalError("Execution journal unavailable") from exc

        def reject(status: Status, code: str) -> ToolResult:
            result = ToolResult(call_id=call.call_id, status=status, error_code=code)
            record("tool_result", code)
            return result

        record("tool_requested", "request_received")
        tool = self._tools.get(call.tool_id)
        if tool is None:
            record("permission", "unknown_tool_denied")
            return reject("denied", "unknown_tool")
        try:
            validated: Contract = tool.input_model.model_validate(call.arguments)
        except ValidationError:
            return reject("invalid", "invalid_input")
        decision = self.policy.decide(self._descriptors[call.tool_id], context)
        record("permission", decision.reason)
        if not decision.allowed:
            return reject("denied", decision.reason)
        try:
            # Only schema-approved fields reach the Tool; raw model arguments are not reused.
            payload = tool.execute(validated.model_dump(mode="json"))
        except Exception:
            return reject("failed", "tool_error")
        if payload is None:
            result = ToolResult(call_id=call.call_id, status="empty")
        else:
            try:
                checked = tool.output_model.model_validate(payload.model_dump())
                result = ToolResult.model_validate(
                    {
                        "call_id": call.call_id,
                        "status": "success",
                        "data": checked.model_dump(),
                    }
                )
            except ValidationError, AttributeError:
                return reject("failed", "invalid_output")
        evidence_ids = tuple(e.evidence_id for e in result.data.evidence) if result.data else ()
        record("tool_result", result.status, evidence_ids)
        return result
