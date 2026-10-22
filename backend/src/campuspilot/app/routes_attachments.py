"""Same-origin, session-protected image upload/read/delete endpoints."""

import asyncio
import time
from urllib.parse import unquote

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from campuspilot.app.state import COOKIE, WebState
from campuspilot.attachments import MAX_UPLOAD_BYTES, AttachmentError


def register(app: FastAPI, state: WebState) -> None:
    @app.post("/api/attachments")
    async def upload(request: Request) -> JSONResponse:
        session = state.session_for(request)
        store = state.attachments
        if store is None:
            return state.problem(request, "images_disabled", "图片功能尚未启用。", 503)
        if session.busy:
            return state.problem(request, "busy", "上一条问题正在处理，请等待回答。", 409)
        if request.headers.get("content-encoding", "identity") != "identity":
            return state.problem(request, "attachment_format", "请直接上传图片文件。", 415)
        try:
            length = int(request.headers.get("content-length", "0"))
            if not 0 <= length <= MAX_UPLOAD_BYTES:
                raise AttachmentError("attachment_size", "每张图片需在 10MB 以内。", 413)
            buffer = bytearray()
            async for part in request.stream():
                if len(buffer) + len(part) > MAX_UPLOAD_BYTES:
                    raise AttachmentError("attachment_size", "每张图片需在 10MB 以内。", 413)
                buffer.extend(part)
            mime_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
            raw_name = request.headers.get("x-attachment-name", "图片")
            if len(raw_name) > 2048:
                raise AttachmentError("attachment_name", "图片文件名过长。", 422)
            name = unquote(raw_name, errors="strict")
            item = await asyncio.to_thread(
                store.add, session.user, session.expires, bytes(buffer), mime_type, name
            )
            # Reset/expiry may have happened while decoding off the event loop.
            if (
                session.expires <= time.monotonic()
                or state.sessions.get(request.cookies.get(COOKIE, "")) is not session
            ):
                store.cleanup_session(session.user)
                raise AttachmentError("attachment_expired", "本次会话已过期，请开启新对话。", 401)
            return JSONResponse(
                item.public(), status_code=201, headers={"Cache-Control": "no-store"}
            )
        except AttachmentError as exc:
            return state.problem(request, exc.code, exc.message, exc.status)
        except (UnicodeDecodeError, ValueError):
            return state.problem(request, "attachment_invalid", "图片请求格式不正确。", 422)

    @app.get("/api/attachments/{identifier}")
    async def read(identifier: str, request: Request) -> Response:
        # Same-origin browser GET fetches omit Origin; keep the custom header, Fetch
        # Metadata and session ownership checks instead of making the image public.
        session = state.session_for(request, allow_originless_get=True)
        store = state.attachments
        if store is None:
            return state.problem(request, "images_disabled", "图片功能尚未启用。", 503)
        try:
            image = store.read(session.user, identifier)
            return Response(
                image.data,
                media_type=image.mime_type,
                headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
            )
        except AttachmentError as exc:
            return state.problem(request, exc.code, exc.message, exc.status)

    @app.delete("/api/attachments/{identifier}")
    async def delete(identifier: str, request: Request) -> Response:
        session = state.session_for(request)
        store = state.attachments
        if store is None:
            return state.problem(request, "images_disabled", "图片功能尚未启用。", 503)
        if session.busy:
            return state.problem(request, "busy", "上一条问题正在处理，请等待回答。", 409)
        try:
            store.delete(session.user, identifier)
            session.current_image_ids = tuple(
                i for i in session.current_image_ids if i != identifier
            )
            return Response(status_code=204, headers={"Cache-Control": "no-store"})
        except AttachmentError as exc:
            return state.problem(request, exc.code, exc.message, exc.status)
