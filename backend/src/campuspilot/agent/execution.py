"""Application-owned authorization and metadata audit for Agent capabilities.

The registry continues to own parameter validation. Registering a callable, or naming it
in model output, does not grant execution permission or declare its risk.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic import JsonValue

from campuspilot.contracts import ExecutionContext, ToolDescriptor
from campuspilot.observability import record_event
from campuspilot.tools.base import ToolError, ToolRegistry
from campuspilot.tools.executor import ReadOnlyPermissionPolicy

AuditSink = Callable[[str, dict[str, JsonValue]], None]
T = TypeVar("T")

# These declarations are trusted application configuration, never model-provided data.
AGENT_CAPABILITIES = tuple(
    ToolDescriptor(tool_id=name, risk="public_read")
    for name in (
        "search_service",
        "find_office",
        "search_place",
        "search_teacher",
        "search_knowledge",
        "list_places",
        "make_checklist",
        "find_teacher",
        "jev_assess",
        "search_web",
    )
)
DEFAULT_ALLOWED_CAPABILITIES = frozenset(d.tool_id for d in AGENT_CAPABILITIES)
SAFE_ERROR_CODES = frozenset({"unknown_tool", "invalid_arguments", "permission_denied"})


class ExecutionBoundary:
    def __init__(
        self,
        context: ExecutionContext | None = None,
        *,
        descriptors: tuple[ToolDescriptor, ...] = AGENT_CAPABILITIES,
        audit: AuditSink | None = None,
    ) -> None:
        declared = {d.tool_id: d for d in descriptors}
        if len(declared) != len(descriptors):
            raise ValueError("Duplicate capability declaration")
        self._descriptors = declared
        self._context = context or ExecutionContext(
            session_id="agent",
            task_id="agent",
            run_id="agent",
            allowed_tools=DEFAULT_ALLOWED_CAPABILITIES,
        )
        self._policy = ReadOnlyPermissionPolicy()
        self._audit: AuditSink = audit if audit is not None else self._default_audit

    @staticmethod
    def _default_audit(event: str, record: dict[str, JsonValue]) -> None:
        record_event(event, **record)

    def _record(
        self,
        capability: str,
        phase: str,
        outcome: str,
        **detail: JsonValue,
    ) -> None:
        # Undeclared names can originate in model output and are not safe audit metadata.
        name = capability if capability in self._descriptors else "undeclared"
        self._audit(
            "execution",
            {"capability": name, "phase": phase, "outcome": outcome, **detail},
        )

    def _deny(self, capability: str, reason: str, code: str = "permission_denied") -> None:
        self._record(capability, "permission", "denied", reason=reason)
        self._record(capability, "result", "denied", error_code=code)
        raise ToolError(code)

    def _authorize(self, capability: str) -> None:
        descriptor = self._descriptors.get(capability)
        if descriptor is None:
            self._deny(capability, "undeclared_capability")
            return
        decision = self._policy.decide(descriptor, self._context)
        if not decision.allowed:
            self._deny(capability, decision.reason)
        self._record(capability, "permission", "allowed", reason=decision.reason)

    def _failure(self, capability: str, exc: BaseException, outcome: str = "failed") -> None:
        detail: dict[str, JsonValue] = {"error_type": type(exc).__name__}
        if isinstance(exc, ToolError) and exc.code in SAFE_ERROR_CODES:
            detail["error_code"] = exc.code
        self._record(capability, "result", outcome, **detail)

    def invalid_arguments(self, capability: str) -> None:
        """Record a model argument decode failure without creating or authorizing a call."""
        self._failure(capability, ToolError("invalid_arguments"))

    def call_tool(
        self, registry: ToolRegistry, name: str, arguments: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        """Authorize before invoking registry validation or the tool implementation."""
        if not registry.has(name):
            self._deny(name, "unknown_tool", "unknown_tool")
        self._authorize(name)
        started = time.monotonic()
        try:
            result = registry.call(name, arguments)
        except asyncio.CancelledError as exc:
            self._failure(name, exc, "cancelled")
            raise
        except Exception as exc:
            self._failure(name, exc)
            raise
        self._record(name, "result", "success", elapsed_ms=(time.monotonic() - started) * 1000)
        return result

    async def run(self, capability: str, operation: Callable[[], Awaitable[T]]) -> T:
        """Authorize before creating the coroutine; keep provider budgets inside it."""
        self._authorize(capability)
        started = time.monotonic()
        try:
            result = await operation()
        except asyncio.CancelledError as exc:
            self._failure(capability, exc, "cancelled")
            raise
        except Exception as exc:
            self._failure(capability, exc)
            raise
        self._record(
            capability, "result", "success", elapsed_ms=(time.monotonic() - started) * 1000
        )
        return result
