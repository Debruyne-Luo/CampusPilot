"""Content-free operational logs and correlation use only synthetic offline turns."""

import asyncio
import io
import json
import logging
from collections.abc import AsyncGenerator, Iterator
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from campuspilot import observability
from campuspilot.agent.executor import AgentRunner
from campuspilot.app.state import BrowserSession, WebState
from campuspilot.observability import record_event, set_knowledge_version, turn_scope
from campuspilot.web import create_web_app
from fastapi import Request
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

DATA = Path(__file__).resolve().parents[1] / "data/cdut"
HEADERS = {"Origin": "http://testserver", "X-CampusPilot-Request": "1"}
VERSION_A = "kb-0123456789abcdef"
VERSION_B = "kb-fedcba9876543210"
PRIVATE = "synthetic-secret prompt answer https://example.invalid/private 30.1,104.2"


@pytest.fixture
def event_log(monkeypatch: pytest.MonkeyPatch) -> Iterator[io.StringIO]:
    stream = io.StringIO()
    handler = observability._OperationsHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger(observability.LOGGER_NAME)
    monkeypatch.setattr(logger, "handlers", [handler])
    monkeypatch.setattr(logger, "level", logging.INFO)
    monkeypatch.setattr(logger, "propagate", False)
    yield stream


def records(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_factory_logging_is_idempotent_and_leaves_root_untouched(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = logging.getLogger()
    original = (root.level, tuple(root.handlers))
    logger = logging.getLogger(observability.LOGGER_NAME)
    monkeypatch.setattr(logger, "handlers", [])
    monkeypatch.setattr(logger, "level", logging.NOTSET)
    monkeypatch.setattr(logger, "propagate", True)
    observability.configure_logging()
    observability.configure_logging()
    record_event("execution", capability="search_web", phase="permission", outcome="allowed")
    output = capsys.readouterr().err.splitlines()
    assert len(output) == 1
    assert json.loads(output[0])["capability"] == "search_web"
    assert (root.level, tuple(root.handlers)) == original
    assert not logger.propagate


def test_content_allowlist_and_server_context(event_log: io.StringIO) -> None:
    request_id = str(uuid4())
    with turn_scope(request_id) as turn:
        set_knowledge_version(VERSION_A)
        record_event(
            "jev", request_id=PRIVATE, knowledge_version=PRIVATE, status="ok",
            raw={"prompt": PRIVATE}, args=PRIVATE, answer=PRIVATE, query=PRIVATE,
            observation=PRIVATE, url=PRIVATE, coordinates=[30.1, 104.2], exception=PRIVATE,
            reason=PRIVATE, error_type=PRIVATE, input_tokens=23, latency_ms=12.5,
            output_tokens=True, decision="sufficient", phase="answer",
        )
        record_event(PRIVATE, status="ok")
        turn.result("success")
    result = records(event_log)
    assert [r["event"] for r in result] == ["turn_started", "jev", "turn_completed"]
    assert PRIVATE not in event_log.getvalue()
    assert result[1] == {
        "event": "jev", "request_id": request_id, "knowledge_version": VERSION_A,
        "status": "ok", "input_tokens": 23, "latency_ms": 12.5,
        "decision": "sufficient", "phase": "answer",
    }
    assert result[-1]["status"] == "success" and result[-1]["elapsed_ms"] >= 0
    record_event("knowledge_acquired")
    assert records(event_log)[-1] == {"event": "knowledge_acquired"}


def test_invalid_ids_versions_and_nonfinite_counts_are_not_logged(event_log: io.StringIO) -> None:
    with turn_scope(PRIVATE):
        set_knowledge_version(PRIVATE)
        record_event("jev", latency_ms=float("nan"), elapsed_ms=float("inf"), input_tokens=-1)
    assert records(event_log)[1] == {"event": "jev"}
    assert PRIVATE not in event_log.getvalue()


def test_concurrent_workers_threads_and_delayed_shadow_keep_their_turn(
    event_log: io.StringIO,
) -> None:
    ids = (str(uuid4()), str(uuid4()))

    async def run() -> None:
        release = asyncio.Event()
        shadows: list[asyncio.Task[None]] = []

        async def shadow() -> None:
            await release.wait()
            record_event("jev", mode="shadow", status="ok")

        async def worker(request_id: str, version: str) -> None:
            with turn_scope(request_id) as turn:
                set_knowledge_version(version)
                shadows.append(asyncio.create_task(shadow()))
                await asyncio.to_thread(record_event, "execution", capability="search_knowledge")
                await asyncio.sleep(0)
                turn.result("success")

        await asyncio.gather(worker(ids[0], VERSION_A), worker(ids[1], VERSION_B))
        release.set()
        await asyncio.gather(*shadows)

    asyncio.run(run())
    result = records(event_log)
    for request_id, version in zip(ids, (VERSION_A, VERSION_B), strict=True):
        selected = [r for r in result if r.get("request_id") == request_id]
        assert [r["event"] for r in selected] == [
            "turn_started", "execution", "turn_completed", "jev",
        ]
        assert all(r["knowledge_version"] == version for r in selected[1:])


def test_cancellation_and_exception_are_terminal_without_exception_text(
    event_log: io.StringIO,
) -> None:
    async def run() -> None:
        entered = asyncio.Event()

        async def cancelled() -> None:
            with turn_scope(str(uuid4())):
                entered.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(cancelled())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    with pytest.raises(RuntimeError):
        with turn_scope(str(uuid4())):
            raise RuntimeError(PRIVATE)
    assert [r["event"] for r in records(event_log)] == [
        "turn_started", "turn_cancelled", "turn_started", "turn_failed",
    ]
    assert PRIVATE not in event_log.getvalue()


@pytest.mark.parametrize("endpoint", ["/api/chat", "/api/chat/stream"])
@pytest.mark.parametrize("failure", ["none", "timeout", "error"])
def test_transport_correlates_actual_execution_and_safe_terminal_outcome(
    monkeypatch: pytest.MonkeyPatch, event_log: io.StringIO, endpoint: str, failure: str,
) -> None:
    async def synthetic_run(self: AgentRunner, *args: Any, **kwargs: Any) -> dict[str, Any]:
        set_knowledge_version(VERSION_A)
        record_event("execution", capability="search_knowledge", outcome="success")
        if failure == "timeout":
            raise TimeoutError(PRIVATE)
        if failure == "error":
            raise RuntimeError(PRIVATE)
        return {"answer": "Synthetic answer", "result_status": "success"}

    monkeypatch.setattr(AgentRunner, "run", synthetic_run)
    app = create_web_app(data_dir=DATA, runtime_mode="phase2", agent_loop=True)
    forged = str(uuid4())
    with TestClient(app, raise_server_exceptions=False) as client:
        client.post("/api/session", headers=HEADERS)
        response = client.post(
            endpoint, headers={**HEADERS, "X-Request-ID": forged}, json={"message": "Synthetic"}
        )
    result = records(event_log)
    if failure == "error" and endpoint == "/api/chat":
        # api.request_boundary preserves its existing sanitized 503 error contract.
        assert response.status_code == 503 and response.json()["error_code"] == "unavailable"
        request_id = response.json()["request_id"]
        assert "http_status" not in result[-1]
    elif endpoint.endswith("/stream"):
        assert response.status_code == 200
        final = next(line[6:] for line in response.text.splitlines() if line.startswith("data: {")
                     and '"notice"' in line)
        request_id = json.loads(final)["request_id"]
    else:
        assert response.status_code == 200
        request_id = response.json()["request_id"]
    assert str(UUID(request_id)) == request_id and request_id != forged
    assert [r["event"] for r in result] == [
        "turn_started", "execution", "turn_completed" if failure == "none" else "turn_failed",
    ]
    assert all(r["request_id"] == request_id for r in result)
    assert result[-1]["knowledge_version"] == VERSION_A
    if failure == "timeout":
        assert result[-1]["degraded_reason"] == "agent_timeout"
    if failure == "error":
        assert result[-1]["degraded_reason"] == "agent_error"
    assert PRIVATE not in event_log.getvalue()


@pytest.mark.parametrize("start_worker", [False, True])
def test_stream_disconnect_records_one_cancelled_turn_and_releases_claim(
    monkeypatch: pytest.MonkeyPatch, event_log: io.StringIO, start_worker: bool,
) -> None:
    from campuspilot.app.validation import ChatInput

    session = BrowserSession()
    monkeypatch.setattr(WebState, "session_for", lambda *args, **kwargs: session)

    async def run() -> None:
        entered = asyncio.Event()

        async def synthetic_run(self: AgentRunner, *args: Any, **kwargs: Any) -> dict[str, Any]:
            entered.set()
            await asyncio.Event().wait()
            return {}

        monkeypatch.setattr(AgentRunner, "run", synthetic_run)
        app = create_web_app(data_dir=DATA, runtime_mode="phase2", agent_loop=True)
        route = next(r for r in app.routes if getattr(r, "path", None) == "/api/chat/stream")
        request = Request({"type": "http"})
        request.state.request_id = str(uuid4())
        response = await route.endpoint(ChatInput(message="Synthetic"), request)  # type: ignore[attr-defined]
        assert isinstance(response, StreamingResponse)
        stream = cast(AsyncGenerator[str], response.body_iterator)
        await anext(stream)
        if start_worker:
            await entered.wait()
        await stream.aclose()
        assert not session.busy

    asyncio.run(run())
    assert [r["event"] for r in records(event_log)] == ["turn_started", "turn_cancelled"]


def test_audit_io_failure_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    class Unavailable(io.StringIO):
        def write(self, text: str) -> int:
            raise OSError("synthetic sink unavailable")

    logger = logging.getLogger(observability.LOGGER_NAME)
    monkeypatch.setattr(logger, "handlers", [observability._OperationsHandler(Unavailable())])
    monkeypatch.setattr(logger, "level", logging.INFO)
    with pytest.raises(OSError):
        record_event("execution", phase="permission", outcome="allowed")
