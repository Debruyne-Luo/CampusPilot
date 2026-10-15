"""Synthetic images verify the session and multimodal boundaries; no real student data."""

import asyncio
import base64
import io
import json
import random
import time
from collections.abc import Callable
from pathlib import Path
from typing import cast

import httpx
import pytest
from campuspilot.agent.executor import AgentRunner
from campuspilot.app import routes_attachments, routes_chat
from campuspilot.app.state import COOKIE, BrowserSession, ChatBudget, WebState
from campuspilot.app.validation import ChatInput
from campuspilot.attachments import (
    MAX_UPLOAD_BYTES,
    AttachmentError,
    AttachmentStore,
    normalize_image,
)
from campuspilot.chat_runtime import ChatRuntime, ConversationContext
from campuspilot.dify import ChatUnavailable
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.knowledge import KnowledgeStore
from campuspilot.llm.chat_model import ChatCompletionsModel, ImageInput, user_content
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from PIL import Image, PngImagePlugin
from pydantic import ValidationError
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

HEADERS = {"Origin": "http://testserver", "X-CampusPilot-Request": "1"}


def image_bytes(format: str = "PNG", size: tuple[int, int] = (64, 32)) -> bytes:
    buffer = io.BytesIO()
    image = Image.new("RGB", size, "navy")
    if format == "PNG":
        meta = PngImagePlugin.PngInfo()
        meta.add_text("Synthetic private note", "MUST BE REMOVED")
        image.save(buffer, format=format, pnginfo=meta)
    else:
        image.save(buffer, format=format)
    return buffer.getvalue()


class ImageAgent:
    model = object()
    # Image availability follows the reader model, so the stub mirrors that attribute too.
    reader = object()

    def __init__(self) -> None:
        self.seen: list[tuple[str, tuple[ImageInput, ...]]] = []

    async def run(
        self,
        question: str,
        context: ConversationContext,
        emit: Callable[..., object] | None = None,
        *,
        images: tuple[ImageInput, ...] = (),
    ) -> dict[str, object]:
        self.seen.append((question, images))
        return {"answer": "SYNTHETIC IMAGE ANSWER", "places": [], "result_status": "success"}


def attachment_app(tmp_path: Path) -> tuple[FastAPI, WebState, ImageAgent]:
    app = FastAPI()
    agent = ImageAgent()
    state = WebState(
        repository=cast(DirectoryRepository, None),
        knowledge=cast(KnowledgeStore, None),
        runtime=cast(ChatRuntime, None),
        runtime_mode="phase2",
        dify=None,
        model=None,
        public_origin=None,
        amap_key="",
        amap_security_code="",
        budget=ChatBudget(100),
        agent=cast(AgentRunner, agent),
        attachments=AttachmentStore(directory=tmp_path),
    )
    state.sessions["first"] = BrowserSession(user="SYNTHETIC FIRST")
    state.sessions["second"] = BrowserSession(user="SYNTHETIC SECOND")

    @app.middleware("http")
    async def request_id(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.request_id = "SYNTHETIC REQUEST"
        return await call_next(request)

    routes_attachments.register(app, state)
    routes_chat.register(app, state)
    return app, state, agent


def upload(client: TestClient, content: bytes | None = None) -> httpx.Response:
    return cast(
        httpx.Response,
        client.post(
            "/api/attachments",
            content=image_bytes() if content is None else content,
            headers={**HEADERS, "Content-Type": "image/png", "X-Attachment-Name": "SYNTHETIC.png"},
        ),
    )


def test_upload_normalizes_metadata_and_session_boundaries(tmp_path: Path) -> None:
    app, state, _ = attachment_app(tmp_path)
    assert state.attachments is not None
    try:
        with TestClient(app) as client:
            assert upload(client).status_code == 401
            client.cookies.set(COOKIE, "first")
            response = upload(client)
            assert response.status_code == 201
            item = response.json()
            assert set(item) == {"attachment_id", "name", "mime_type", "size"}
            found = client.get("/api/attachments/" + item["attachment_id"], headers=HEADERS)
            assert found.status_code == 200 and found.headers["cache-control"] == "no-store"
            decoded = Image.open(io.BytesIO(found.content))
            assert decoded.info == {} and decoded.size == (64, 32)
            assert item["size"] == len(found.content)
            assert client.get("/api/attachments/" + item["attachment_id"]).status_code == 403
            browser_headers = {"X-CampusPilot-Request": "1", "Sec-Fetch-Site": "same-origin"}
            assert (
                client.get(
                    "/api/attachments/" + item["attachment_id"], headers=browser_headers
                ).status_code
                == 200
            )
            assert (
                client.get(
                    "/api/attachments/" + item["attachment_id"],
                    headers={
                        **browser_headers,
                        "Sec-Fetch-Site": "cross-site",
                    },
                ).status_code
                == 403
            )
            client.cookies.set(COOKIE, "second")
            for method in (client.get, client.delete):
                assert (
                    method("/api/attachments/" + item["attachment_id"], headers=HEADERS).status_code
                    == 404
                )
            refused = client.post(
                "/api/chat", json={"attachment_ids": [item["attachment_id"]]}, headers=HEADERS
            )
            assert refused.status_code == 404
            assert state.sessions["second"].attempts == 0
            client.cookies.set(COOKIE, "first")
            deleted = client.delete("/api/attachments/" + item["attachment_id"], headers=HEADERS)
            assert deleted.status_code == 204
            assert not list(state.attachments.directory.iterdir())
    finally:
        state.attachments.close()


def test_chat_images_followup_replace_stream_and_delete(tmp_path: Path) -> None:
    app, state, agent = attachment_app(tmp_path)
    assert state.attachments is not None
    try:
        with TestClient(app) as client:
            client.cookies.set(COOKIE, "first")
            first = upload(client).json()["attachment_id"]
            second = upload(client).json()["attachment_id"]
            response = client.post("/api/chat", json={"attachment_ids": [first]}, headers=HEADERS)
            assert response.status_code == 200
            assert agent.seen[-1][0] == ""
            assert [i.attachment_id for i in agent.seen[-1][1]] == [first]
            assert state.sessions["first"].context.history[0].content == "[用户上传校园图片]"
            followup = client.post("/api/chat", json={"message": "读一下图片"}, headers=HEADERS)
            assert followup.status_code == 200
            assert [i.attachment_id for i in agent.seen[-1][1]] == [first]
            streamed = client.post(
                "/api/chat/stream",
                json={"message": "看看另一张", "attachment_ids": [second]},
                headers=HEADERS,
            )
            assert streamed.status_code == 200 and "event: final" in streamed.text
            assert [i.attachment_id for i in agent.seen[-1][1]] == [second]
            assert state.sessions["first"].current_image_ids == (second,)
            assert client.delete("/api/attachments/" + second, headers=HEADERS).status_code == 204
            assert len(state.sessions["first"].current_image_ids) == 0
            text_only = client.post("/api/chat", json={"message": "无图片问题"}, headers=HEADERS)
            assert text_only.status_code == 200
            assert agent.seen[-1][1] == ()
    finally:
        state.attachments.close()


def test_upload_rejects_oversize_invalid_format_and_busy(tmp_path: Path) -> None:
    app, state, _ = attachment_app(tmp_path)
    assert state.attachments is not None
    try:
        with TestClient(app) as client:
            client.cookies.set(COOKIE, "first")
            assert upload(client, b"not an image").status_code == 422
            assert upload(client, b"x" * (MAX_UPLOAD_BYTES + 1)).status_code == 413
            mismatch = client.post(
                "/api/attachments",
                content=image_bytes("JPEG"),
                headers={**HEADERS, "Content-Type": "image/png"},
            )
            assert mismatch.status_code == 422
            unsupported = client.post(
                "/api/attachments",
                content=image_bytes("GIF"),
                headers={**HEADERS, "Content-Type": "image/gif"},
            )
            assert unsupported.status_code == 415
            assert upload(client, image_bytes(size=(10001, 1))).status_code == 422
            state.sessions["first"].busy = True
            assert upload(client).status_code == 409
            assert list(state.attachments.directory.iterdir()) == []
    finally:
        state.attachments.close()


def test_orientation_limits_capacity_expiry_and_reset(tmp_path: Path) -> None:
    store = AttachmentStore(directory=tmp_path, max_session_images=1)
    try:
        buffer = io.BytesIO()
        original = Image.new("RGB", (120, 60), "navy")
        exif = Image.Exif()
        exif[274] = 6
        original.save(buffer, "JPEG", exif=exif)
        item = store.add(
            "SYNTHETIC", time.monotonic() + 60, buffer.getvalue(), "image/jpeg", "../s.jpg"
        )
        decoded = Image.open(io.BytesIO(store.read("SYNTHETIC", item.attachment_id).data))
        assert decoded.size == (60, 120) and not decoded.getexif()
        assert item.name == "s.jpg"
        with pytest.raises(AttachmentError) as capacity:
            store.add("SYNTHETIC", time.monotonic() + 60, image_bytes(), "image/png", "second")
        assert capacity.value.code == "attachment_capacity"
        store.cleanup_session("SYNTHETIC")
        assert not list(store.directory.iterdir())
        new = store.add("SYNTHETIC", time.monotonic() + 0.01, image_bytes(), "image/png", "new")
        time.sleep(0.02)
        with pytest.raises(AttachmentError):
            store.read("SYNTHETIC", new.attachment_id)
        assert not list(store.directory.iterdir())
        other = AttachmentStore(directory=tmp_path)
        try:
            with pytest.raises(AttachmentError):
                other.read("SYNTHETIC", item.attachment_id)
        finally:
            other.close()
    finally:
        store.close()
    assert not store.directory.exists()


def test_global_capacity_and_prune_inactive_sessions(tmp_path: Path) -> None:
    sample = image_bytes()
    normalized, _ = normalize_image(sample, "image/png")
    store = AttachmentStore(directory=tmp_path, total_capacity_bytes=len(normalized))
    try:
        first = store.add("SYNTHETIC ONE", time.monotonic() + 60, sample, "image/png", "one")
        with pytest.raises(AttachmentError) as exc:
            store.add("SYNTHETIC TWO", time.monotonic() + 60, sample, "image/png", "two")
        assert exc.value.code == "attachment_capacity"
        store.prune({"SYNTHETIC TWO"})
        with pytest.raises(AttachmentError):
            store.get("SYNTHETIC ONE", first.attachment_id)
        assert not list(store.directory.iterdir())
        store.add("SYNTHETIC TWO", time.monotonic() + 60, sample, "image/png", "two")
        assert len(list(store.directory.iterdir())) == 1
    finally:
        store.close()


def test_resizing_and_multiframe_rejection() -> None:
    data, mime = normalize_image(image_bytes(size=(3000, 30)), "image/png")
    assert mime == "image/png"
    assert Image.open(io.BytesIO(data)).size == (2048, 20)
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "navy").save(
        buffer, "PNG", save_all=True, append_images=[Image.new("RGB", (4, 4), "red")]
    )
    with pytest.raises(AttachmentError) as exc:
        normalize_image(buffer.getvalue(), "image/png")
    assert exc.value.code == "attachment_invalid"


def test_session_expiry_cleans_files_on_access(tmp_path: Path) -> None:
    app, state, _ = attachment_app(tmp_path)
    assert state.attachments is not None
    try:
        with TestClient(app) as client:
            client.cookies.set(COOKIE, "first")
            assert upload(client).status_code == 201
            state.sessions["first"].expires = time.monotonic() - 1
            assert upload(client).status_code == 401
            assert not list(state.attachments.directory.iterdir())
    finally:
        state.attachments.close()


def test_rejected_turn_does_not_replace_current_images(tmp_path: Path) -> None:
    app, state, _ = attachment_app(tmp_path)
    assert state.attachments is not None
    try:
        with TestClient(app) as client:
            client.cookies.set(COOKIE, "first")
            first = upload(client).json()["attachment_id"]
            second = upload(client).json()["attachment_id"]
            state.sessions["first"].current_image_ids = (first,)
            state.budget = ChatBudget(1)
            assert state.budget.try_acquire()
            state.budget.release()
            for path in ("/api/chat", "/api/chat/stream"):
                response = client.post(path, json={"attachment_ids": [second]}, headers=HEADERS)
                assert response.status_code == 429
                assert state.sessions["first"].current_image_ids == (first,)
    finally:
        state.attachments.close()


@pytest.mark.parametrize("task_started", [False, True])
def test_stream_disconnect_releases_busy_and_budget(tmp_path: Path, task_started: bool) -> None:
    from starlette.routing import Route

    app, state, _ = attachment_app(tmp_path)
    assert state.attachments is not None

    class BlockingAgent:
        model = object()

        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.cancelled = False

        async def run(self, *args: object, **kwargs: object) -> dict[str, object]:
            self.started.set()
            try:
                await asyncio.sleep(60)
                return {}
            except asyncio.CancelledError:
                self.cancelled = True
                raise

    async def scenario() -> None:
        agent = BlockingAgent()
        state.agent = cast(AgentRunner, agent)
        endpoint = next(
            route.endpoint
            for route in app.routes
            if isinstance(route, Route) and route.path == "/api/chat/stream"
        )
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "scheme": "http",
                "path": "/api/chat/stream",
                "server": ("testserver", 80),
                "query_string": b"",
                "headers": [
                    (b"host", b"testserver"),
                    (b"origin", b"http://testserver"),
                    (b"x-campuspilot-request", b"1"),
                    (b"cookie", b"campuspilot_session=first"),
                ],
            }
        )
        request.state.request_id = "SYNTHETIC STREAM"
        response = await endpoint(ChatInput(message="SYNTHETIC"), request)
        generator = response.body_iterator
        await anext(generator)
        if task_started:
            await agent.started.wait()
        assert state.sessions["first"].busy and state.budget.active == 1
        await generator.aclose()
        assert not state.sessions["first"].busy and state.budget.active == 0
        assert agent.cancelled is task_started

    try:
        asyncio.run(scenario())
    finally:
        state.attachments.close()


def test_factory_reset_cleans_attachments_and_keeps_text_limit(tmp_path: Path) -> None:
    from campuspilot.web import create_web_app

    data_dir = Path(__file__).resolve().parents[1] / "data/cdut"
    with TestClient(
        create_web_app(data_dir=data_dir, runtime_mode="phase2", images_enabled=True)
    ) as client:
        client.post("/api/session", headers=HEADERS)
        # A noisy file larger than the ordinary JSON limit exercises the upload exception.
        buffer = io.BytesIO()
        image = Image.frombytes("RGB", (128, 128), random.Random(7).randbytes(128 * 128 * 3))
        image.save(buffer, "PNG")
        item = upload(client, buffer.getvalue()).json()
        assert "attachment_id" in item
        reset = client.post("/api/session/reset", headers=HEADERS)
        assert reset.status_code == 200
        previous = client.get("/api/attachments/" + item["attachment_id"], headers=HEADERS)
        assert previous.status_code == 404
        oversized = client.post("/api/chat", content=b"x" * 17_000, headers=HEADERS)
        assert oversized.status_code == 413


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"message": " "},
        {"attachment_ids": ["bad"]},
        {"attachment_ids": ["x" * 24] * 2},
        {"attachment_ids": [str(i) * 24 for i in range(4)]},
    ],
)
def test_image_input_validation(body: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ChatInput.model_validate(body)


def test_vision_transport_preserves_images_and_separate_budget() -> None:
    buffer = io.BytesIO()
    image = Image.frombytes("RGB", (256, 256), random.Random(7).randbytes(256 * 256 * 3))
    image.save(buffer, "PNG")
    data = buffer.getvalue()
    assert len(data) > 60_000
    normalized = ImageInput("SYNTHETIC ID", "image/png", data)
    calls: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload)
        content = payload["messages"][-1]["content"]
        assert content[0] == {"type": "text", "text": "SYNTHETIC question"}
        image_url = content[1]["image_url"]["url"]
        assert base64.b64decode(image_url.split(",", 1)[1]) == data
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "SYNTHETIC"}, "finish_reason": "stop"}]},
        )

    model = ChatCompletionsModel(
        "https://example.com", "synthetic", "synthetic-key", transport=httpx.MockTransport(handler)
    )
    result = asyncio.run(
        model.complete(
            [{"role": "user", "content": user_content("SYNTHETIC question", (normalized,))}]
        )
    )
    assert result.content == "SYNTHETIC" and len(calls) == 1
    assert "data=" not in repr(normalized)
    for content in (
        "x" * 60_001,
        [{"type": "image_url", "image_url": {"url": "https://example.com/private.png"}}],
        [{"type": "image_url", "image_url": {"url": "data:image/png;base64,%%%"}}],
        user_content("SYNTHETIC", (normalized,) * 3) * 2,
    ):
        with pytest.raises(ChatUnavailable):
            asyncio.run(model.complete([{"role": "user", "content": content}]))
    assert len(calls) == 1
