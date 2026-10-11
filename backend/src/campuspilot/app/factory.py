"""Assemble the same-origin web app from its route modules."""

import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import Response

from campuspilot.api import create_app
from campuspilot.app import amap, routes_chat, routes_data
from campuspilot.app.state import (
    ASSETS,
    COOKIE,
    MAX_SESSIONS,
    NOTICE,
    BrowserSession,
    ChatBudget,
    WebState,
)
from campuspilot.chat_runtime import ChatRuntime, Mode
from campuspilot.dify import DifyClient
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.knowledge import KnowledgeStore
from campuspilot.llm.chat_model import ProductionModel
from campuspilot.rag import SnapshotStore


def _allowed_hosts(public_origin: str | None, api_token: str | None) -> list[str]:
    if not public_origin:
        return ["127.0.0.1", "localhost", "testserver"]
    origin = urlsplit(public_origin)
    if (
        origin.scheme != "https"
        or not origin.hostname
        or origin.path
        or origin.query
        or origin.fragment
        or origin.username
        or origin.password
    ):
        raise ValueError("Public origin must be an exact HTTPS origin")
    if not api_token:
        raise ValueError("Public deployment requires a stable tool credential")
    return [origin.hostname]


def create_web_app(
    *,
    data_dir: Path,
    dify: DifyClient | None = None,
    api_token: str | None = None,
    public_origin: str | None = None,
    amap_key: str = "",
    amap_security_code: str = "",
    daily_chat_limit: int = 100,
    runtime_mode: Mode = "legacy",
    model: ProductionModel | None = None,
    approved_direct_rules: frozenset[str] = frozenset(),
) -> FastAPI:
    # Directory tools keep their own service credential, never exposed to the browser.
    repository = DirectoryRepository.load(data_dir)
    knowledge = KnowledgeStore.load(data_dir / "knowledge.json")
    if runtime_mode not in {"legacy", "phase1", "phase2"}:
        raise ValueError("Invalid backend runtime mode")
    runtime = ChatRuntime(
        repository,
        knowledge,
        SnapshotStore(data_dir / "rag"),
        mode=runtime_mode,
        model=model,
        approved_direct_rules=approved_direct_rules,
    )
    for record in knowledge.records:
        if any(repository.find_place(ident) is None for ident in record.place_ids):
            raise ValueError("Knowledge record references an unknown place")
    budget = ChatBudget(daily_chat_limit)
    hosts = _allowed_hosts(public_origin, api_token)
    app = create_app(
        data_dir=data_dir,
        api_token=api_token or secrets.token_urlsafe(40),
        tool_gateway=bool(public_origin),
        repository=repository,
    )
    app.title = "CampusPilot 校园办事与地图"
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)
    state = WebState(
        repository=repository,
        knowledge=knowledge,
        runtime=runtime,
        runtime_mode=runtime_mode,
        dify=dify,
        model=model,
        public_origin=public_origin,
        amap_key=amap_key,
        amap_security_code=amap_security_code,
        budget=budget,
    )
    _register_shell(app, state)
    routes_chat.register(app, state)
    routes_data.register(app, state)
    amap.register(app, state)
    return app


def _register_shell(app: FastAPI, state: WebState) -> None:
    runtime_mode, dify, model, knowledge = (
        state.runtime_mode,
        state.dify,
        state.model,
        state.knowledge,
    )
    public_origin = state.public_origin

    @app.middleware("http")
    async def web_boundary(request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Bound body allocation before FastAPI parses JSON (including chunked requests).
        if request.url.path.startswith("/api/") and request.method == "POST":
            data = bytearray()
            async for chunk in request.stream():
                data.extend(chunk)
                if len(data) > 16_384:
                    return JSONResponse({"message": "请求过长，请缩短问题。"}, status_code=413)
            request._body = bytes(data)
        response = await call_next(request)
        map_view = request.url.path == "/map-view"
        script_policy = (
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
            "https://webapi.amap.com https://jsapi-service.amap.com https://mapplugin.amap.com; "
            if map_view
            else "script-src 'self'; "
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; " + script_policy + "frame-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob: https://*.amap.com https://*.autonavi.com; "
            "connect-src 'self' https://*.amap.com https://*.autonavi.com; "
            "worker-src 'self' blob:; "
            + ("frame-ancestors 'self'; " if map_view else "frame-ancestors 'none'; ")
            + "base-uri 'none'; form-action 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "geolocation=(self)"
        if request.url.path.startswith(("/api/", "/_AMapService/")):
            response.headers["Cache-Control"] = "no-store"
        elif request.url.path in {"/", "/map-view"} or request.url.path.startswith("/assets/"):
            # The front end ships unversioned filenames. Revalidate every time so a release
            # cannot leave a phone running the previous app.js; unchanged files still answer 304.
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(ASSETS / "index.html")

    @app.get("/map-view", include_in_schema=False)
    def map_view_page() -> FileResponse:
        return FileResponse(ASSETS / "map-frame.html")

    app.mount("/assets", StaticFiles(directory=ASSETS), name="assets")

    @app.post("/api/session")
    async def start(request: Request) -> JSONResponse:
        state.check_browser(request)
        now = time.monotonic()
        for key in list(state.sessions):
            if state.sessions[key].expires < now and not state.sessions[key].busy:
                del state.sessions[key]
        token = request.cookies.get(COOKIE, "")
        if token not in state.sessions:
            if len(state.sessions) >= MAX_SESSIONS:
                return state.problem(request, "session_limit", "当前会话已满，请稍后再试。", 429)
            token = secrets.token_urlsafe(32)
            state.sessions[token] = BrowserSession()
        response = JSONResponse(
            {
                "configured": runtime_mode != "legacy" or dify is not None,
                "knowledge_available": bool(knowledge.records),
                "runtime_mode": runtime_mode,
                "model_configured": (
                    model is not None if runtime_mode != "legacy" else dify is not None
                ),
                "context_notice": "后端会话仅保留本次最近8轮，服务更新后请开启新对话。"
                if runtime_mode != "legacy"
                else "",
                "notice": NOTICE,
            }
        )
        response.set_cookie(
            COOKIE,
            token,
            httponly=True,
            samesite="strict",
            max_age=3600,
            secure=bool(public_origin),
        )
        return response

    @app.post("/api/session/reset")
    async def reset(request: Request) -> JSONResponse:
        state.check_browser(request)
        token = request.cookies.get(COOKIE, "")
        session = state.sessions.get(token)
        if session and session.busy:
            return state.problem(request, "busy", "上一条问题正在处理。", 409)
        state.sessions.pop(token, None)
        return await start(request)
