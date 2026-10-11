"""Characterization tests pinning current /api/chat status codes and messages.

These tests document existing behavior before refactoring web.py; they are not a spec.
All upstream replies are synthetic and offline.
"""

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import httpx
import pytest

pytest.importorskip("fastapi")

from campuspilot.chat_model import ChatCompletionsModel  # noqa: E402
from campuspilot.chat_runtime import Mode  # noqa: E402
from campuspilot.dify import DifyClient  # noqa: E402
from campuspilot.web import create_web_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data" / "cdut"
KEY = "synthetic-key-for-offline-characterization-only"
HEADERS = {"Origin": "http://testserver", "X-CampusPilot-Request": "1"}

BUSY = "上一条问题正在处理，请等待回答。"
RESET_BUSY = "上一条问题正在处理。"
SESSION_LIMIT_LOCAL = "本次提问较多，请开启新对话。"
SESSION_LIMIT_DIFY = "已达到本次开发会话的提问上限。"
GLOBAL_LIMIT = "当前提问额度或并发已满，请稍后再试。"
NOT_CONFIGURED = "AI 对话尚未连接，请先配置应用凭据。"
RESET_REQUIRED = "上次请求未能确认完成，请开启新对话。"

# Routing probes (questions chosen from current data/cdut content).
KNOWLEDGE_Q = "学生邮箱怎么激活"  # legacy local knowledge hit
DIFY_Q = "synthetic question"  # no local answer in legacy/phase1
PHASE2_LOCAL_Q = "synthetic question"  # phase2 local "empty" answer, no model needed


def dify_ok(request: httpx.Request) -> httpx.Response:
    # Continue the server-owned conversation id when one is sent.
    conversation = json.loads(request.content).get("conversation_id") or str(uuid4())
    return httpx.Response(200, json={"answer": "SYNTHETIC answer", "conversation_id": conversation})


def dify_client(handler: Callable[[httpx.Request], Any] = dify_ok) -> DifyClient:
    return DifyClient(KEY, transport=httpx.MockTransport(handler))


def model_ok(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    evidence = json.loads(json.loads(body["messages"][-1]["content"])["evidence"])
    sources = evidence["sources"] if isinstance(evidence, dict) else evidence
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": json.dumps(
                            {
                                "answer": "SYNTHETIC grounded answer",
                                "source_ids": [sources[0]["source_id"]],
                                "status": "success",
                            }
                        )
                    },
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
    )


def model_client(handler: Callable[[httpx.Request], Any] = model_ok) -> ChatCompletionsModel:
    return ChatCompletionsModel(
        "https://example.com/v1", "synthetic-model", KEY, transport=httpx.MockTransport(handler)
    )


def ask(client: TestClient, message: str) -> httpx.Response:
    response: httpx.Response = client.post("/api/chat", json={"message": message}, headers=HEADERS)
    return response


def assert_problem(response: httpx.Response, status: int, code: str, message: str) -> None:
    assert response.status_code == status
    body = response.json()
    assert body["error_code"] == code
    assert body["message"] == message
    assert body["request_id"]
    assert "answer" not in body


# --- Request boundary ------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["legacy", "phase1", "phase2"])
def test_boundary_status_codes(mode: str) -> None:
    with TestClient(create_web_app(data_dir=DATA, runtime_mode=cast(Mode, mode))) as client:
        assert ask(client, KNOWLEDGE_Q).status_code == 401  # no session cookie
        client.post("/api/session", headers=HEADERS)
        no_header = client.post(
            "/api/chat", json={"message": "x"}, headers={"Origin": "http://testserver"}
        )
        assert no_header.status_code == 403
        wrong_origin = client.post(
            "/api/chat",
            json={"message": "x"},
            headers={**HEADERS, "Origin": "https://example.com"},
        )
        assert wrong_origin.status_code == 403
        assert ask(client, "   ").status_code == 422
        assert (
            client.post("/api/chat", json={"message": "x" * 2001}, headers=HEADERS).status_code
            == 422
        )
        query = client.post("/api/chat?x=1", json={"message": "x"}, headers=HEADERS)
        assert query.status_code == 422


# --- Mode x route matrix without upstreams ---------------------------------------------


@pytest.mark.parametrize(
    "mode,message,status,error_code,result_status,answer_mode",
    [
        ("legacy", KNOWLEDGE_Q, 200, None, "success", "official_retrieval"),
        ("legacy", DIFY_Q, 503, "not_configured", None, None),
        ("legacy", "我的密码是123456", 503, "not_configured", None, None),
        ("phase1", KNOWLEDGE_Q, 200, None, "success", "official_retrieval"),
        ("phase1", DIFY_Q, 503, "not_configured", None, None),
        ("phase1", "教务处综合科负责什么", 503, "not_configured", None, None),
        ("phase1", "我的密码是123456", 200, None, "needs_clarification", "backend_local"),
        ("phase1", "校园卡补办费用是多少", 200, None, "limited", "backend_directory"),
        ("phase2", KNOWLEDGE_Q, 200, None, "limited", "backend_rag"),
        ("phase2", "教务处综合科负责什么", 200, None, "limited", "backend_rag"),
        ("phase2", PHASE2_LOCAL_Q, 200, None, "empty", "backend_local"),
        ("phase2", "我的密码是123456", 200, None, "needs_clarification", "backend_local"),
        ("phase2", "校园卡补办费用是多少", 200, None, "limited", "backend_directory"),
    ],
)
def test_mode_route_matrix_without_upstreams(
    mode: str,
    message: str,
    status: int,
    error_code: str | None,
    result_status: str | None,
    answer_mode: str | None,
) -> None:
    with TestClient(create_web_app(data_dir=DATA, runtime_mode=cast(Mode, mode))) as client:
        client.post("/api/session", headers=HEADERS)
        response = ask(client, message)
        body = response.json()
        assert response.status_code == status
        assert body["request_id"]
        if error_code:
            assert_problem(response, status, error_code, NOT_CONFIGURED)
            return
        assert body["result_status"] == result_status
        assert body["answer_mode"] == answer_mode
        if result_status == "limited":
            assert body["degraded_reason"] == "model_not_configured"
            assert body["answer"].startswith("暂时只能提供已收录的资料摘要：\n")
        if result_status == "needs_clarification" and "密码" in message:
            assert body["answer"] == "请移除个人位置、账号或密码，再询问公开资料。"


# --- session_limit (40 counted turns per session) --------------------------------------


@pytest.mark.parametrize("mode", ["legacy", "phase1"])
def test_session_limit_on_local_knowledge_path(mode: str) -> None:
    with TestClient(create_web_app(data_dir=DATA, runtime_mode=cast(Mode, mode))) as client:
        client.post("/api/session", headers=HEADERS)
        for _ in range(40):
            assert ask(client, KNOWLEDGE_Q).status_code == 200
        assert_problem(ask(client, KNOWLEDGE_Q), 429, "session_limit", SESSION_LIMIT_LOCAL)
        client.post("/api/session/reset", headers=HEADERS)
        assert ask(client, KNOWLEDGE_Q).status_code == 200


def test_session_limit_on_phase2_runtime_path_counts_local_answers() -> None:
    with TestClient(create_web_app(data_dir=DATA, runtime_mode="phase2")) as client:
        client.post("/api/session", headers=HEADERS)
        for _ in range(40):
            assert ask(client, PHASE2_LOCAL_Q).status_code == 200
        assert_problem(ask(client, PHASE2_LOCAL_Q), 429, "session_limit", SESSION_LIMIT_LOCAL)


@pytest.mark.parametrize("mode", ["legacy", "phase1"])
def test_session_limit_on_dify_path_uses_distinct_message(mode: str) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return dify_ok(request)

    app = create_web_app(
        data_dir=DATA,
        runtime_mode=cast(Mode, mode),
        dify=dify_client(handler),
        daily_chat_limit=1000,
    )
    with TestClient(app) as client:
        client.post("/api/session", headers=HEADERS)
        for _ in range(40):
            assert ask(client, DIFY_Q).status_code == 200
        assert_problem(ask(client, DIFY_Q), 429, "session_limit", SESSION_LIMIT_DIFY)
        # The local knowledge path shares the same counter but its own wording.
        assert_problem(ask(client, KNOWLEDGE_Q), 429, "session_limit", SESSION_LIMIT_LOCAL)
    assert calls == 40


# --- global_limit (daily budget / concurrency) -----------------------------------------


@pytest.mark.parametrize("mode", ["legacy", "phase1"])
def test_global_limit_on_dify_path_is_shared_across_sessions(mode: str) -> None:
    app = create_web_app(
        data_dir=DATA, runtime_mode=cast(Mode, mode), dify=dify_client(), daily_chat_limit=1
    )
    with TestClient(app) as a, TestClient(app) as b:
        a.post("/api/session", headers=HEADERS)
        b.post("/api/session", headers=HEADERS)
        assert ask(a, DIFY_Q).status_code == 200
        assert_problem(ask(b, DIFY_Q), 429, "global_limit", GLOBAL_LIMIT)
        assert_problem(ask(a, DIFY_Q), 429, "global_limit", GLOBAL_LIMIT)
        # Local knowledge answers do not consume the shared budget.
        assert ask(b, KNOWLEDGE_Q).status_code == 200


def test_global_limit_on_phase2_model_path_spares_local_routes() -> None:
    app = create_web_app(
        data_dir=DATA, runtime_mode="phase2", model=model_client(), daily_chat_limit=1
    )
    with TestClient(app) as a, TestClient(app) as b:
        a.post("/api/session", headers=HEADERS)
        b.post("/api/session", headers=HEADERS)
        first = ask(a, KNOWLEDGE_Q)
        assert first.status_code == 200 and first.json()["answer_mode"] == "backend_rag"
        assert_problem(ask(b, KNOWLEDGE_Q), 429, "global_limit", GLOBAL_LIMIT)
        assert ask(b, PHASE2_LOCAL_Q).status_code == 200
        assert ask(b, "我的密码是123456").status_code == 200


def test_daily_chat_limit_must_be_positive() -> None:
    with pytest.raises(ValueError):
        create_web_app(data_dir=DATA, daily_chat_limit=0)


# --- uncertain / upstream failures on the Dify path ------------------------------------


@pytest.mark.parametrize(
    "failure,code,message",
    [
        (500, "upstream_unavailable", "AI 服务暂不可用，请开启新对话后重试。"),
        (401, "upstream_credentials", "AI 服务凭据不可用，请检查 Dify 应用配置。"),
        (429, "upstream_limit", "AI 服务当前额度不足或请求受限，请稍后再试。"),
        (
            "timeout",
            "upstream_timeout",
            "AI 回答超时，远端可能仍在处理；请开启新对话，不自动重试。",
        ),
    ],
)
@pytest.mark.parametrize("mode", ["legacy", "phase1"])
def test_upstream_failure_marks_session_uncertain(
    mode: str, failure: int | str, code: str, message: str
) -> None:
    fail = True

    def handler(request: httpx.Request) -> httpx.Response:
        if not fail:
            return dify_ok(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("synthetic")
        return httpx.Response(int(failure))

    app = create_web_app(data_dir=DATA, runtime_mode=cast(Mode, mode), dify=dify_client(handler))
    with TestClient(app) as client:
        client.post("/api/session", headers=HEADERS)
        assert_problem(ask(client, DIFY_Q), 502, code, message)
        fail = False
        assert_problem(ask(client, DIFY_Q), 409, "reset_required", RESET_REQUIRED)
        # Local knowledge still answers while the session is uncertain.
        assert ask(client, KNOWLEDGE_Q).status_code == 200
        client.post("/api/session/reset", headers=HEADERS)
        assert ask(client, DIFY_Q).status_code == 200


def test_invalid_dify_reply_is_502_without_answer() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"conversation_id": str(uuid4())})

    with TestClient(create_web_app(data_dir=DATA, dify=dify_client(handler))) as client:
        client.post("/api/session", headers=HEADERS)
        response = ask(client, DIFY_Q)
        assert response.status_code == 502 and "answer" not in response.json()
        assert_problem(ask(client, DIFY_Q), 409, "reset_required", RESET_REQUIRED)


def test_phase2_model_failure_degrades_to_limited_200() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    app = create_web_app(data_dir=DATA, runtime_mode="phase2", model=model_client(handler))
    with TestClient(app) as client:
        client.post("/api/session", headers=HEADERS)
        response = ask(client, KNOWLEDGE_Q)
        assert response.status_code == 200
        assert response.json()["result_status"] == "limited"
        # No uncertain state in phase2: the next turn is accepted.
        assert ask(client, KNOWLEDGE_Q).status_code == 200


# --- busy (concurrent turn in one session) ---------------------------------------------


def _busy_scenario(
    app_kwargs: dict[str, Any], message: str, gate: dict[str, asyncio.Event]
) -> None:
    async def scenario() -> None:
        app = create_web_app(data_dir=DATA, **app_kwargs)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://testserver", headers=HEADERS
        ) as client:
            await client.post("/api/session")
            first = asyncio.create_task(client.post("/api/chat", json={"message": message}))
            await asyncio.wait_for(gate["entered"].wait(), timeout=3)
            second = await client.post("/api/chat", json={"message": KNOWLEDGE_Q})
            reset = await client.post("/api/session/reset")
            assert_problem(second, 409, "busy", BUSY)
            assert_problem(reset, 409, "busy", RESET_BUSY)
            gate["finish"].set()
            assert (await first).status_code == 200

    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["legacy", "phase1"])
def test_busy_on_dify_path(mode: str) -> None:
    gate = {"entered": asyncio.Event(), "finish": asyncio.Event()}

    async def handler(request: httpx.Request) -> httpx.Response:
        gate["entered"].set()
        await gate["finish"].wait()
        return dify_ok(request)

    _busy_scenario({"runtime_mode": mode, "dify": dify_client(handler)}, DIFY_Q, gate)


def test_busy_on_phase2_model_path() -> None:
    gate = {"entered": asyncio.Event(), "finish": asyncio.Event()}

    async def handler(request: httpx.Request) -> httpx.Response:
        gate["entered"].set()
        await gate["finish"].wait()
        return model_ok(request)

    _busy_scenario({"runtime_mode": "phase2", "model": model_client(handler)}, KNOWLEDGE_Q, gate)
