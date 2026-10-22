"""Assemble the same-origin web app from its route modules."""

import asyncio
import hashlib
import re
import secrets
import time
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import Response

from campuspilot.agent.executor import AgentRunner
from campuspilot.api import create_app
from campuspilot.app import amap, routes_attachments, routes_chat, routes_data
from campuspilot.app.state import (
    ASSETS,
    COOKIE,
    MAX_SESSIONS,
    NOTICE,
    BrowserSession,
    ChatBudget,
    SlidingWindow,
    WebState,
)
from campuspilot.chat_runtime import ChatRuntime, Mode
from campuspilot.config import parse_retrieval_mode
from campuspilot.dify import DifyClient
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.evaluation_budget import OnlineBudget
from campuspilot.harness_profile import HarnessProfile
from campuspilot.jev_plugin import JevMode, build_plugin
from campuspilot.knowledge import KnowledgeStore
from campuspilot.llm.chat_model import ProductionModel, ToolCallingModel
from campuspilot.llm.embedding import CloudflareEmbedder
from campuspilot.observability import configure_logging
from campuspilot.places_discovery import PlaceDiscovery
from campuspilot.rag import SnapshotStore
from campuspilot.retrieval.grounding import GroundingMode
from campuspilot.tools import agent_registry
from campuspilot.web_evidence import (
    DeepSeekToolsProvider,
    TavilySearchProvider,
    WebEvidenceService,
)


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


def asset_hash(root: Path = ASSETS) -> str:
    """Short content hash of every shipped front-end file (names + bytes)."""
    h = hashlib.sha256()
    # Path ordering follows the host's case rules. Sort explicit relative components to
    # preserve the Linux release fingerprint on Windows exports of identical bytes.
    paths = (p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    for path in sorted(paths, key=lambda p: p.relative_to(root).parts):
        h.update(path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes())
    return h.hexdigest()[:12]


def versioned_shell(shell: str, version: str) -> str:
    """Point the v2 shell at the versioned prefix; relative module imports follow it."""
    return shell.replace('"/assets/', f'"/assets/v-{version}/')


def create_web_app(
    *,
    data_dir: Path,
    dify: DifyClient | None = None,
    api_token: str | None = None,
    public_origin: str | None = None,
    amap_key: str = "",
    amap_security_code: str = "",
    amap_web_service_key: str = "",
    amap_discovery: bool = False,
    images_enabled: bool = False,
    web_search: bool = False,
    web_search_provider: str = "deepseek",
    evidence_budget_dir: str = "",
    evidence_daily_usd: str = "1",
    evidence_daily_flows: int = 100,
    search_input_price: str = "",
    search_output_price: str = "",
    tavily_api_key: str = "",
    tavily_free_plan_confirmed: bool = False,
    daily_chat_limit: int = 100,
    runtime_mode: Mode = "legacy",
    model: ProductionModel | None = None,
    reader: ProductionModel | None = None,
    approved_direct_rules: frozenset[str] = frozenset(),
    retrieval_mode: str = "hybrid",
    embedder: CloudflareEmbedder | None = None,
    embedding_model: str = "@cf/baai/bge-m3",
    agent_loop: bool = False,
    grounding: GroundingMode = "flag",
    jev: JevMode = "off",
    jev_routing: bool = False,
    harness_profile: str = "",
    lab_records_dir: str = "",
    jev_budget_dir: str = "",
    jev_daily_usd: str = "1",
    jev_daily_calls: int = 2000,
    knowledge_bundle: str = "",
    asset_version: str = "",
) -> FastAPI:
    configure_logging()
    # Directory tools keep their own service credential, never exposed to the browser.
    if runtime_mode not in {"legacy", "phase1", "phase2"}:
        raise ValueError("Invalid backend runtime mode")
    version = asset_hash() if asset_version == "auto" else asset_version
    if version and not re.fullmatch(r"[a-z0-9]{1,32}", version):
        raise ValueError("Invalid asset version")
    snapshots = SnapshotStore(
        data_dir / "rag",
        retrieval_mode=parse_retrieval_mode(retrieval_mode),
        embedder=embedder,
        embedding_model=embedding_model,
        bundled=knowledge_bundle,
    )
    data_dir = snapshots.bind_directory(data_dir)
    repository = DirectoryRepository.load(data_dir)
    knowledge = KnowledgeStore.load(data_dir / "knowledge.json")
    web_service = None
    shared_budget = None
    if web_search:
        if not evidence_budget_dir or web_search_provider not in {"deepseek", "tavily"}:
            raise ValueError(
                "Web search requires an evidence budget directory and a supported provider"
            )
        approved_limit = Decimal(evidence_daily_usd)
        if (
            not approved_limit.is_finite()
            or not 0 < approved_limit <= 1
            or not 1 <= evidence_daily_flows <= 100
        ):
            raise ValueError("Evidence limits must stay within USD 1 and 100 daily search flows")
        shared_budget = OnlineBudget(
            Path(evidence_budget_dir),
            approved_limit,
            2000,
            max_search_flows=evidence_daily_flows,
        )
        native = DeepSeekToolsProvider(
            api_key=str(getattr(model, "api_key", ""))
            if getattr(model, "base_url", "").rstrip("/")
            in {"https://api.deepseek.com", "https://api.deepseek.com/v1"}
            else "",
        )
        alternative = TavilySearchProvider(
            tavily_api_key, free_plan_confirmed=tavily_free_plan_confirmed
        )
        web_service = WebEvidenceService(
            shared_budget,
            native if web_search_provider == "deepseek" else alternative,
            alternative if web_search_provider == "deepseek" else None,
        )
    try:
        plugin = build_plugin(
            jev if jev != "off" else "on" if jev_routing else "off",
            evidence_budget_dir if web_search else jev_budget_dir,
            snapshots,
            jev_daily_usd,
            jev_daily_calls,
            budget=shared_budget,
        )
    except (OSError, ValueError):
        if not web_search:
            raise
        # Missing judge configuration is explicit at response time; local functions stay usable.
        plugin = None
    runtime = ChatRuntime(
        repository,
        knowledge,
        snapshots,
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
    app.title = "理小龙 CDUTdino 校园办事与地图"
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)
    map_window = SlidingWindow(60, 120)
    discovery = (
        PlaceDiscovery(
            repository, key=amap_web_service_key, enabled=True, acquire=map_window.try_record
        )
        if amap_discovery
        else None
    )
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
        embedder=embedder if retrieval_mode != "lexical" else None,
        place_discovery=discovery,
        map_window=map_window,
        agent=(
            AgentRunner(
                agent_registry(
                    repository,
                    knowledge,
                    snapshots,
                    embedder,
                    roster=data_dir / "teachers_roster.json",
                    grounding=grounding,
                    discovery=discovery,
                ),
                repository,
                model if isinstance(model, ToolCallingModel) else None,
                grounding=grounding,
                jev=plugin,
                concise=True,
                web_service=web_service,
                snapshots=snapshots,
                reader=reader if isinstance(reader, ToolCallingModel) else None,
                profile=HarnessProfile.load(Path(harness_profile)) if harness_profile else None,
                jev_routing=jev_routing,
                jev_evidence=jev != "off",
            )
            if agent_loop and runtime_mode == "phase2"
            else None
        ),
    )
    if images_enabled:
        from campuspilot.attachments import AttachmentStore

        state.attachments = AttachmentStore()

    previous_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application: FastAPI):  # type: ignore[no-untyped-def]
        async def cleanup() -> None:
            while True:
                await asyncio.sleep(60)
                now = time.monotonic()
                active = {s.user for s in state.sessions.values() if s.expires > now or s.busy}
                if state.attachments is not None:
                    state.attachments.prune(active)
                for token, session in tuple(state.sessions.items()):
                    if session.expires <= now and not session.busy:
                        state.sessions.pop(token, None)

        async with previous_lifespan(application):
            task = asyncio.create_task(cleanup())
            try:
                yield
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                if state.agent is not None:
                    await state.agent.drain()
                if state.attachments is not None:
                    state.attachments.close()

    app.router.lifespan_context = lifespan
    _register_shell(app, state, version)
    from campuspilot.app.routes_lab import register as register_lab

    register_lab(app, Path(lab_records_dir) if lab_records_dir else None, version)
    routes_chat.register(app, state)
    routes_data.register(app, state)
    routes_attachments.register(app, state)
    amap.register(app, state)
    return app


def _register_shell(app: FastAPI, state: WebState, version: str = "") -> None:
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
                limit = 10 * 1024 * 1024 if request.url.path == "/api/attachments" else 16_384
                if len(data) > limit:
                    return JSONResponse(
                        {
                            "message": "图片不能超过10MB。"
                            if limit > 16_384
                            else "请求过长，请缩短问题。"
                        },
                        status_code=413,
                    )
            request._body = bytes(data)
        response = await call_next(request)
        map_view = request.url.path == "/map-view"
        script_policy = (
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
            "https://webapi.amap.com https://jsapi-service.amap.com https://mapplugin.amap.com "
            # Map-frame POI (hotspot) clicks resolve through a JSONP call on vdata.amap.com.
            "https://vdata.amap.com; "
            if map_view
            else "script-src 'self'; "
        )
        # GLTFLoader fetches embedded image blobs for createImageBitmap.
        # Limit this permission to the frame that renders the 3D guide.
        connect_policy = (
            "connect-src 'self' "
            + ("blob: " if map_view else "")
            + "https://*.amap.com https://*.autonavi.com; "
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; " + script_policy + "frame-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob: https://*.amap.com https://*.autonavi.com; "
            + connect_policy
            + "worker-src 'self' blob:; "
            + ("frame-ancestors 'self'; " if map_view else "frame-ancestors 'none'; ")
            + "base-uri 'none'; form-action 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "geolocation=(self)"
        if request.url.path.startswith(("/api/", "/_AMapService/")):
            response.headers["Cache-Control"] = "no-store"
        elif version and request.url.path.startswith(f"/assets/v-{version}/"):
            # Content-addressed URL: a new release changes the prefix, so CDNs may keep it.
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif request.url.path in {"/", "/classic", "/map-view"} or request.url.path.startswith(
            "/assets/"
        ):
            # The front end ships unversioned filenames. Revalidate every time so a release
            # cannot leave a phone running the previous app.js; unchanged files still answer 304.
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/", include_in_schema=False, response_model=None)
    def index() -> FileResponse | HTMLResponse:
        if not version:
            return FileResponse(ASSETS / "v2" / "index.html")
        shell = (ASSETS / "v2" / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(versioned_shell(shell, version))

    @app.get("/classic", include_in_schema=False)
    def classic() -> FileResponse:
        """Previous UI, kept so the existing browser journeys keep running against it."""
        return FileResponse(ASSETS / "index.html")

    @app.get("/map-view", include_in_schema=False)
    def map_view_page() -> FileResponse:
        return FileResponse(ASSETS / "map-frame.html")

    if version:
        app.mount(f"/assets/v-{version}", StaticFiles(directory=ASSETS), name="assets-versioned")
    app.mount("/assets", StaticFiles(directory=ASSETS), name="assets")


    @app.post("/api/session")
    async def start(request: Request) -> JSONResponse:
        state.check_browser(request)
        now = time.monotonic()
        for key in list(state.sessions):
            if state.sessions[key].expires < now and not state.sessions[key].busy:
                if state.attachments is not None:
                    state.attachments.cleanup_session(state.sessions[key].user)
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
                "images_enabled": state.attachments is not None
                and state.agent is not None
                and state.agent.reader is not None,
                "place_discovery_enabled": state.place_discovery is not None,
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
        if session is not None and state.attachments is not None:
            state.attachments.cleanup_session(session.user)
        state.sessions.pop(token, None)
        return await start(request)
