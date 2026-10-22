"""Content-free operational events; stdout/stderr retention belongs to the service host.

Only server-owned identifiers, closed vocabularies and bounded counters cross this boundary.
Raw prompts, answers, tool arguments, provider payloads and exception messages never do.
"""

import asyncio
import json
import logging
import math
import re
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID

LOGGER_NAME = "campuspilot.operations"
_logger = logging.getLogger(LOGGER_NAME)
_configuration_lock = threading.Lock()
_request_id: ContextVar[str | None] = ContextVar("operations_request_id", default=None)
_knowledge_version: ContextVar[str | None] = ContextVar(
    "operations_knowledge_version", default=None
)
_VERSION = re.compile(r"kb-[0-9a-f]{16,64}\Z")
_ERROR_TYPE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
_EVENTS = frozenset({
    "turn_started", "turn_completed", "turn_cancelled", "turn_failed", "tool_start", "tool_end",
    "execution", "knowledge_acquired", "grounding_check", "jev", "answer_decision",
    "answer_recovery",
})
_CAPABILITIES = frozenset({
    "search_service", "find_office", "search_place", "search_teacher", "find_teacher",
    "search_knowledge", "make_checklist", "list_places", "place_cards", "search_web", "jev_assess",
    "undeclared",
})
_DECISIONS = frozenset({
    "grounded", "insufficient", "unassessed", "sufficient", "clarify", "unknown",
})
_STATUSES = frozenset({
    "success", "limited", "empty", "needs_clarification", "ok", "unsure", "unknown",
    "budget", "timeout", "error", "unavailable", "skipped", "cancelled", "failed",
    "denied", "allowed", "not_found", "invalid_arguments", "invalid_result", "tool_error",
})
_CODES = frozenset({
    "agent_timeout", "agent_error", "upstream_timeout", "upstream_unavailable",
    "upstream_credentials", "upstream_limit", "directory_unavailable", "model_format",
    "answer_validation", "invalid_response", "unverified", "tool_rounds_exceeded",
    "ocr_example_amount", "missing_premise", "budget", "timeout", "error", "unknown",
    "busy", "images_unavailable", "session_limit", "global_limit", "stream_unavailable",
    "not_configured", "reset_required", "invalid_arguments", "invalid_result", "unknown_tool",
    "permission_denied", "tool_error", "audit_unavailable", "snapshot_unavailable",
    "public_read", "unregistered_capability", "unsupported_risk", "not_allowed",
    "undeclared_capability", "tool_not_allowed", "risk_not_allowed", "public_read_allowed",
    "turn_judge_limit", "jev_unavailable_or_invalid", "private_context",
    "evidence_insufficient", "non_public_input", "missing_conditions", "supported",
    "model_not_configured", "output_truncated", "required_premise_missing",
    "local_grounding_disagrees", "sufficiency_uncertain", "no_sufficiency",
})
_ENUMS: dict[str, frozenset[str]] = {
    "tool": _CAPABILITIES,
    "capability": _CAPABILITIES,
    "mode": frozenset({"off", "on", "shadow", "flag", "block"}),
    "decision": _DECISIONS,
    "local": _DECISIONS,
    "local_grounding": _DECISIONS,
    "status": _STATUSES,
    "degraded_reason": _CODES,
    "reason": _CODES,
    "error_code": _CODES,
    "phase": frozenset({"permission", "result", "answer", "plan"}),
    "stage": frozenset({"before_search", "after_search"}),
    "outcome": frozenset({"allowed", "denied", "success", "error", "failed", "cancelled"}),
    "applied": frozenset({
        "none", "answer", "clarify", "refuse", "rerank", "filtered", "withhold", "drop_all",
    }),
    "answer_mode": frozenset({"answer", "clarify", "refuse", "unknown"}),
}
_COUNTS = frozenset({
    "count", "grounded_count", "dropped_count", "input_tokens", "output_tokens", "http_status",
})
_TIMINGS = frozenset({"elapsed_ms", "latency_ms"})
_BOOLEANS = frozenset({"would_refuse", "degraded", "search_needed", "other_evidence"})


class _OperationsHandler(logging.StreamHandler):  # type: ignore[type-arg]
    """A distinct handler type makes repeated application factories idempotent."""

    def emit(self, record: logging.LogRecord) -> None:
        # The execution boundary treats an unavailable audit sink as a failed operation.
        # Standard StreamHandler.handleError would silently discard an I/O failure.
        self.stream.write(self.format(record) + self.terminator)
        self.flush()


def configure_logging() -> None:
    """Configure only our content-free logger; preserve Uvicorn/root/access-log policy."""
    with _configuration_lock:
        if not any(isinstance(handler, _OperationsHandler) for handler in _logger.handlers):
            handler = _OperationsHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            _logger.addHandler(handler)
        _logger.setLevel(logging.INFO)
        _logger.propagate = False


def record_event(event: str, **fields: object) -> None:
    """Emit one JSON record after dropping all fields outside the metadata contract."""
    if event not in _EVENTS:
        return
    record: dict[str, str | int | float | bool] = {"event": event}
    if (request_id := _request_id.get()) is not None:
        record["request_id"] = request_id
    if (version := _knowledge_version.get()) is not None:
        record["knowledge_version"] = version
    for name, value in fields.items():
        if name in _ENUMS and isinstance(value, str) and value in _ENUMS[name]:
            record[name] = value
        elif name in _COUNTS and type(value) is int and 0 <= value <= 1_000_000_000:
            record[name] = value
        elif name in _TIMINGS and type(value) in (int, float):
            if (
                isinstance(value, (int, float)) and math.isfinite(value)
                and 0 <= value <= 86_400_000
            ):
                record[name] = round(value, 3)
        elif name in _BOOLEANS and isinstance(value, bool):
            record[name] = value
        elif name == "error_type" and isinstance(value, str) and _ERROR_TYPE.fullmatch(value):
            record[name] = value
    _logger.info(json.dumps(record, ensure_ascii=True, separators=(",", ":"), sort_keys=True))


def set_knowledge_version(version: str | None) -> None:
    """Associate only a validated content version with the current execution context."""
    _knowledge_version.set(version if version is not None and _VERSION.fullmatch(version) else None)


@dataclass
class TurnObservation:
    status: object = "unknown"
    degraded_reason: object = None
    http_status: int | None = None

    def result(
        self, status: object = None, degraded_reason: object = None, *, http_status: int = 200
    ) -> None:
        self.status = status if isinstance(status, str) and status in _STATUSES else "unknown"
        self.degraded_reason = degraded_reason
        self.http_status = http_status


@contextmanager
def turn_scope(request_id: str) -> Iterator[TurnObservation]:
    """Scope a real JSON/stream worker; child tasks inherit its immutable context values."""
    # IDs are generated by api.request_boundary, never accepted from a request header.
    try:
        safe_id = str(UUID(request_id))
    except (ValueError, TypeError, AttributeError):
        safe_id = None
    request_token = _request_id.set(safe_id)
    version_token = _knowledge_version.set(None)
    started = time.monotonic()
    outcome = TurnObservation()
    event = "turn_completed"
    try:
        record_event("turn_started")
        yield outcome
    except asyncio.CancelledError:
        event = "turn_cancelled"
        outcome.status = "cancelled"
        raise
    except BaseException:
        event = "turn_failed"
        outcome.status = "failed"
        outcome.degraded_reason = "agent_error"
        raise
    finally:
        try:
            if outcome.status == "cancelled":
                event = "turn_cancelled"
            if (outcome.http_status is not None and outcome.http_status >= 500) or (
                isinstance(outcome.degraded_reason, str) and outcome.degraded_reason in {
                    "agent_timeout", "agent_error", "upstream_timeout", "upstream_unavailable",
                }
            ):
                event = "turn_failed"
            record_event(
                event,
                status=outcome.status,
                degraded_reason=outcome.degraded_reason,
                http_status=outcome.http_status,
                elapsed_ms=(time.monotonic() - started) * 1000,
            )
        finally:
            _knowledge_version.reset(version_token)
            _request_id.reset(request_token)
