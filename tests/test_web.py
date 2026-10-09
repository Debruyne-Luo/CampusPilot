"""Transport/session boundary tests use unmistakable synthetic upstream replies."""

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

pytest.importorskip("fastapi")

from campuspilot.dify import DifyClient  # noqa: E402
from campuspilot.web import create_web_app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data" / "cdut"
KEY = "synthetic-dify-key-not-for-deployment"
HEADERS = {"Origin": "http://testserver", "X-CampusPilot-Request": "1"}


def test_unconfigured_ui_catalogue_and_no_mock_answer() -> None:
    with TestClient(create_web_app(data_dir=DATA)) as client:
        assert "CampusPilot" in client.get("/").text
        script = client.get("/assets/app.js")
        assert script.status_code == 200 and "innerHTML" not in script.text
        assert "frame-ancestors 'none'" in script.headers["Content-Security-Policy"]
        catalogue = client.get("/api/catalog").json()
        assert len(catalogue["services"]) == 4
        assert all(x["verification_status"] == "needs_review" for x in catalogue["services"])
        assert all(x["source_url"].startswith("https://") for x in catalogue["sources"])
        start = client.post("/api/session", headers=HEADERS)
        assert not start.json()["configured"]
        assert "HttpOnly" in start.headers["set-cookie"]
        assert "SameSite=strict" in start.headers["set-cookie"]
        reply = client.post("/api/chat", json={"message": "synthetic question"}, headers=HEADERS)
        assert reply.status_code == 503 and reply.json()["error_code"] == "not_configured"
        assert "answer" not in reply.json()


def test_conversation_owned_by_server_and_isolated_reset() -> None:
    calls: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        assert str(request.url) == "https://api.dify.ai/v1/chat-messages"
        assert request.headers["Authorization"] == f"Bearer {KEY}"
        return httpx.Response(
            200,
            json={
                "answer": "Synthetic answer <script>alert(1)</script>",
                "conversation_id": body["conversation_id"] or str(uuid4()),
                "metadata": {
                    "retriever_resources": [
                        {"document_name": "Synthetic document", "content": "Synthetic evidence"}
                    ],
                    "private_debug": KEY,
                },
            },
        )

    dify = DifyClient(KEY, transport=httpx.MockTransport(handler))
    app = create_web_app(data_dir=DATA, dify=dify)
    with TestClient(app) as a, TestClient(app) as b:
        for client in (a, b):
            client.post("/api/session", headers=HEADERS)
        replies = []
        for client in (a, a, b):
            response = client.post(
                "/api/chat", json={"message": "Synthetic question"}, headers=HEADERS
            )
            assert response.status_code == 200
            assert KEY not in response.text and "conversation_id" not in response.json()
            assert "private_debug" not in response.text
            replies.append(response.json())
        assert calls[0]["user"] == calls[1]["user"] != calls[2]["user"]
        assert calls[0]["conversation_id"] == calls[2]["conversation_id"] == ""
        assert calls[1]["conversation_id"]
        assert replies[0]["excerpts"][0]["document"] == "Synthetic document"
        a.post("/api/session/reset", headers=HEADERS)
        a.post("/api/chat", json={"message": "Synthetic reset"}, headers=HEADERS)
        assert calls[-1]["user"] != calls[0]["user"] and not calls[-1]["conversation_id"]
        assert KEY not in repr(dify)


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "upstream_credentials"),
        (429, "upstream_limit"),
        (500, "upstream_unavailable"),
        (302, "upstream_unavailable"),
    ],
)
def test_remote_error_is_sanitized_and_not_retried(status: int, code: str) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status, text=KEY, headers={"Location": "https://example.com/"})

    app = create_web_app(
        data_dir=DATA, dify=DifyClient(KEY, transport=httpx.MockTransport(handler))
    )
    with TestClient(app) as client:
        client.post("/api/session", headers=HEADERS)
        response = client.post("/api/chat", json={"message": "Synthetic question"}, headers=HEADERS)
        assert response.status_code == 502 and response.json()["error_code"] == code
        assert KEY not in response.text
        again = client.post("/api/chat", json={"message": "Synthetic question"}, headers=HEADERS)
        assert again.status_code == 409 and calls == 1


@pytest.mark.parametrize("failure", ["timeout", "invalid_json", "missing_answer", "too_large"])
def test_invalid_or_uncertain_reply_never_becomes_success(failure: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "timeout":
            raise httpx.ReadTimeout(KEY)
        if failure == "invalid_json":
            return httpx.Response(200, text="not json " + KEY)
        if failure == "too_large":
            return httpx.Response(200, content=b"x" * 1_000_001)
        return httpx.Response(200, json={"conversation_id": str(uuid4())})

    app = create_web_app(
        data_dir=DATA, dify=DifyClient(KEY, transport=httpx.MockTransport(handler))
    )
    with TestClient(app) as client:
        client.post("/api/session", headers=HEADERS)
        response = client.post("/api/chat", json={"message": "Synthetic question"}, headers=HEADERS)
        assert response.status_code == 502 and "answer" not in response.json()
        assert KEY not in response.text


def test_cross_origin_identity_override_body_size_and_invalid_host() -> None:
    with TestClient(create_web_app(data_dir=DATA)) as client:
        assert client.post("/api/session").status_code == 403
        assert (
            client.post(
                "/api/session", headers={**HEADERS, "Origin": "https://example.com"}
            ).status_code
            == 403
        )
        assert client.get("/", headers={"Host": "evil.example"}).status_code == 400
        client.post("/api/session", headers=HEADERS)
        for extra in ("user", "conversation_id", "api_key", "allowed_tools"):
            response = client.post(
                "/api/chat",
                json={"message": "Synthetic question", extra: "private-value"},
                headers=HEADERS,
            )
            assert response.status_code == 422 and "private-value" not in response.text
        response = client.post("/api/chat", content=b"x" * 17_000, headers=HEADERS)
        assert response.status_code == 413


def test_release_assets_revalidate_while_api_responses_are_not_stored() -> None:
    with TestClient(create_web_app(data_dir=DATA)) as client:
        # Unversioned asset names must revalidate, or a release leaves a phone on the old script.
        for path in ("/", "/map-view", "/assets/app.js", "/assets/style.css"):
            assert client.get(path).headers["cache-control"] == "no-cache"
        client.post("/api/session", headers=HEADERS)
        for path in ("/api/catalog", "/api/places"):
            assert client.get(path).headers["cache-control"] == "no-store"
        shell = client.get("/").text
        assert "send-label" in shell and "mobile-new-chat" not in shell


def test_stale_browser_session_is_distinguishable_and_recoverable() -> None:
    with TestClient(create_web_app(data_dir=DATA)) as first:
        first.post("/api/session", headers=HEADERS)
        stale = first.cookies["campuspilot_session"]
        assert (
            first.post(
                "/api/knowledge/search", json={"query": "校园网"}, headers=HEADERS
            ).status_code
            == 200
        )
    # A restarted single worker keeps no in-memory session, so the browser must be able to tell
    # that apart from a real failure and re-establish its cookie without reloading the page.
    with TestClient(create_web_app(data_dir=DATA)) as second:
        # Cookies travel as explicit headers so the jar cannot merge a stale and a fresh token.
        second.cookies.clear()
        stale_header = {**HEADERS, "Cookie": f"campuspilot_session={stale}"}
        rejected = second.post(
            "/api/knowledge/search", json={"query": "校园网"}, headers=stale_header
        )
        assert rejected.status_code == 401 and rejected.json()["error_code"] == "session_expired"
        second.cookies.clear()
        refreshed = second.post("/api/session", headers=stale_header)
        replacement = refreshed.cookies["campuspilot_session"]
        assert replacement != stale
        second.cookies.clear()
        accepted = second.post(
            "/api/knowledge/search",
            json={"query": "校园网"},
            headers={**HEADERS, "Cookie": f"campuspilot_session={replacement}"},
        )
        assert accepted.status_code == 200


def test_concurrent_turn_rejected_before_second_upstream_call() -> None:
    async def scenario() -> None:
        entered, finish = asyncio.Event(), asyncio.Event()

        async def handler(request: httpx.Request) -> httpx.Response:
            entered.set()
            await finish.wait()
            return httpx.Response(
                200, json={"answer": "Synthetic answer", "conversation_id": str(uuid4())}
            )

        app = create_web_app(
            data_dir=DATA, dify=DifyClient(KEY, transport=httpx.MockTransport(handler))
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://testserver", headers=HEADERS
        ) as client:
            await client.post("/api/session")
            first = asyncio.create_task(
                client.post("/api/chat", json={"message": "Synthetic question"})
            )
            await asyncio.wait_for(entered.wait(), timeout=3)
            second = await client.post("/api/chat", json={"message": "Synthetic concurrent"})
            reset = await client.post("/api/session/reset")
            assert second.status_code == reset.status_code == 409
            finish.set()
            assert (await first).status_code == 200

    asyncio.run(scenario())
