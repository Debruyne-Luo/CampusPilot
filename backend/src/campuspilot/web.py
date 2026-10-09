"""Local web pilot: same-origin UI + session-owned Dify calls + public catalogue."""

import argparse
import asyncio
import getpass
import math
import os
import re
import secrets
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field, JsonValue
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import Response

from campuspilot.api import create_app
from campuspilot.contracts import Contract
from campuspilot.dify import ChatUnavailable, DifyClient
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.knowledge import KnowledgeQuery, KnowledgeStore, campus_today
from campuspilot.presentation import place_card, resolve_cards

ASSETS = Path(__file__).parent / "web_assets"
COOKIE = "campuspilot_session"
NOTICE = "资料待人工核验，仅提供指引，未替你办理。"


def validate_route_params(path: str, params: dict[str, str]) -> None:
    """Bound the SDK's two added capabilities without reflecting private origins."""
    fields = {
        "v3/direction/walking": {"origin", "destination", "multipath"},
        "v3/assistant/coordinate/convert": {"locations", "coordsys"},
    }
    if path not in fields:
        return
    metadata = {
        "platform",
        "s",
        "logversion",
        "key",
        "sdkversion",
        "appname",
        "csid",
        "jscode",
        "callback",
        "jsonp",
        "cb",
    }
    if set(params) - metadata - fields[path]:
        raise HTTPException(422)
    names = ("origin", "destination") if path.endswith("walking") else ("locations",)
    for name in names:
        try:
            lng, lat = (float(part) for part in params.get(name, "").split(","))
            if not (
                math.isfinite(lng) and math.isfinite(lat) and abs(lng) <= 180 and abs(lat) <= 90
            ):
                raise ValueError
        except ValueError:
            raise HTTPException(422) from None
    if path.endswith("convert") and params.get("coordsys") != "gps":
        raise HTTPException(422)
    if path.endswith("walking") and params.get("multipath", "0") not in {"0", "1"}:
        raise HTTPException(422)


def validate_place_params(path: str, params: dict[str, str]) -> None:
    """Allow only the two observed PlaceSearch operations, near the pilot campus."""
    if path not in {"v3/place/around", "v3/place/detail"}:
        return
    metadata = {
        "platform",
        "s",
        "logversion",
        "key",
        "sdkversion",
        "appname",
        "csid",
        "jscode",
        "callback",
        "jsonp",
        "cb",
        "antiCrab",
        "language",
        "extensions",
    }
    fields = (
        {"id", "children", "type_"}
        if path.endswith("detail")
        else {
            "city",
            "page",
            "offset",
            "location",
            "radius",
            "children",
            "type_",
            "keywords",
            "citylimit",
            "sortrule",
        }
    )
    if set(params) - metadata - fields or params.get("extensions", "base") != "base":
        raise HTTPException(422)
    if path.endswith("detail"):
        if not re.fullmatch(r"[A-Za-z0-9]{8,32}", params.get("id", "")):
            raise HTTPException(422)
        return
    try:
        lng, lat = (float(part) for part in params.get("location", "").split(","))
        valid = (
            abs(lng - 104.147531) < 0.000001
            and abs(lat - 30.675012) < 0.000001
            and 1 <= int(params.get("radius", "0")) <= 2000
            and 1 <= int(params.get("offset", "10")) <= 10
            and 1 <= int(params.get("page", "1")) <= 5
        )
    except ValueError:
        valid = False
    keyword = params.get("keywords", "")
    if not valid or not keyword.strip() or len(keyword) > 120 or any(ord(c) < 32 for c in keyword):
        raise HTTPException(422)


class ChatInput(Contract):
    message: Annotated[str, Field(min_length=1, max_length=2000, pattern=r"\S")]


@dataclass
class BrowserSession:
    user: str = field(default_factory=lambda: "cp-" + secrets.token_urlsafe(24))
    conversation: str = ""
    expires: float = field(default_factory=lambda: time.monotonic() + 3600)
    busy: bool = False
    uncertain: bool = False
    attempts: int = 0
    knowledge_titles: tuple[str, ...] = ()


def create_web_app(
    *,
    data_dir: Path,
    dify: DifyClient | None = None,
    api_token: str | None = None,
    public_origin: str | None = None,
    amap_key: str = "",
    amap_security_code: str = "",
    daily_chat_limit: int = 100,
) -> FastAPI:
    # Directory tools keep their own service credential, never exposed to the browser.
    repository = DirectoryRepository.load(data_dir)
    knowledge = KnowledgeStore.load(data_dir / "knowledge.json")
    for record in knowledge.records:
        if any(repository.find_place(ident) is None for ident in record.place_ids):
            raise ValueError("Knowledge record references an unknown place")
    if daily_chat_limit < 1:
        raise ValueError("Chat budget must be positive")
    hosts = ["127.0.0.1", "localhost", "testserver"]
    if public_origin:
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
        hosts = [origin.hostname]
    app = create_app(
        data_dir=data_dir,
        api_token=api_token or secrets.token_urlsafe(40),
        tool_gateway=bool(public_origin),
        repository=repository,
    )
    app.title = "CampusPilot 校园办事与地图"
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)
    sessions: dict[str, BrowserSession] = {}
    chat_attempts: deque[float] = deque()
    active_chats = 0
    map_attempts: deque[float] = deque()

    def check_browser(request: Request) -> None:
        # No CORS. Custom header blocks cross-site simple forms; origin is checked as well.
        expected = public_origin or str(request.base_url).rstrip("/")
        if (
            request.headers.get("X-CampusPilot-Request") != "1"
            or request.headers.get("Origin") != expected
            or request.headers.get("Sec-Fetch-Site") == "cross-site"
        ):
            raise HTTPException(403)
        if request.query_params:
            raise HTTPException(422)

    def problem(request: Request, code: str, message: str, status: int) -> JSONResponse:
        return JSONResponse(
            {"error_code": code, "message": message, "request_id": request.state.request_id},
            status_code=status,
        )

    def session_for(request: Request) -> BrowserSession:
        check_browser(request)
        token = request.cookies.get(COOKIE, "")
        session = sessions.get(token)
        if session is None or session.expires < time.monotonic():
            raise HTTPException(401)
        return session

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
        check_browser(request)
        now = time.monotonic()
        for key in list(sessions):
            if sessions[key].expires < now and not sessions[key].busy:
                del sessions[key]
        token = request.cookies.get(COOKIE, "")
        if token not in sessions:
            if len(sessions) >= 256:
                return problem(request, "session_limit", "当前会话已满，请稍后再试。", 429)
            token = secrets.token_urlsafe(32)
            sessions[token] = BrowserSession()
        response = JSONResponse(
            {
                "configured": dify is not None,
                "knowledge_available": bool(knowledge.records),
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
        check_browser(request)
        token = request.cookies.get(COOKIE, "")
        session = sessions.get(token)
        if session and session.busy:
            return problem(request, "busy", "上一条问题正在处理。", 409)
        sessions.pop(token, None)
        return await start(request)

    @app.post("/api/chat")
    async def chat(body: ChatInput, request: Request) -> JSONResponse:
        nonlocal active_chats
        session = session_for(request)
        if session.busy:
            return problem(request, "busy", "上一条问题正在处理，请等待回答。", 409)
        query = knowledge.for_chat(body.message)
        # Follow-ups are explicit and local; unrelated business queries clear this context.
        if session.knowledge_titles and any(
            x in body.message for x in ("这条", "上一条", "第一条")
        ):
            if len(session.knowledge_titles) == 1 or "第一条" in body.message:
                query = KnowledgeQuery(query=session.knowledge_titles[0])
        if query is not None:
            if session.attempts >= 40:
                return problem(request, "session_limit", "本次提问较多，请开启新对话。", 429)
            session.attempts += 1
            response = knowledge.response(query, campus_today())
            knowledge.focus_answer(response, body.message)
            session.knowledge_titles = tuple(
                r.title for r in knowledge.search(query, campus_today())
            )
            return JSONResponse({**response, "request_id": request.state.request_id})
        session.knowledge_titles = ()
        if dify is None:
            return problem(request, "not_configured", "AI 对话尚未连接，请先配置应用凭据。", 503)
        if session.busy:
            return problem(request, "busy", "上一条问题正在处理，请等待回答。", 409)
        if session.uncertain:
            return problem(request, "reset_required", "上次请求未能确认完成，请开启新对话。", 409)
        if session.attempts >= 40:
            return problem(request, "session_limit", "已达到本次开发会话的提问上限。", 429)
        now = time.monotonic()
        while chat_attempts and now - chat_attempts[0] >= 86400:
            chat_attempts.popleft()
        if len(chat_attempts) >= daily_chat_limit or active_chats >= 2:
            return problem(request, "global_limit", "当前提问额度或并发已满，请稍后再试。", 429)
        chat_attempts.append(now)
        active_chats += 1
        session.busy = True
        session.attempts += 1
        session.uncertain = True
        try:
            reply, conversation = await dify.send(
                body.message.strip(), user=session.user, conversation_id=session.conversation
            )
            cards = (
                resolve_cards(repository, reply.references)
                if reply.references
                else {
                    "services": [],
                    "teachers": [],
                    "places": [],
                }
            )
            session.conversation = conversation
            session.uncertain = False
            return JSONResponse(
                {
                    **reply.model_dump(mode="json", exclude={"references"}),
                    **cards,
                    "result_status": reply.references.status if reply.references else None,
                    "notice": NOTICE,
                    "request_id": request.state.request_id,
                }
            )
        except ChatUnavailable as exc:
            session.uncertain = True
            messages = {
                "directory_unavailable": "业务工具查询失败，本次没有取得可用结果，请开启新对话。",
                "upstream_credentials": "AI 服务凭据不可用，请检查 Dify 应用配置。",
                "upstream_limit": "AI 服务当前额度不足或请求受限，请稍后再试。",
                "upstream_timeout": "AI 回答超时，远端可能仍在处理；请开启新对话，不自动重试。",
            }
            return problem(
                request,
                exc.code,
                messages.get(exc.code, "AI 服务暂不可用，请开启新对话后重试。"),
                502,
            )
        except ValueError:
            return problem(
                request, "invalid_response", "回答关联的资料未能校验，请开启新对话。", 502
            )
        finally:
            session.busy = False
            active_chats -= 1

    @app.get("/api/catalog")
    def catalog() -> dict[str, JsonValue]:
        # Explicit public catalogue. No model-selected operations or invented facts.
        records = repository.services()
        return {
            "services": [r.model_dump(mode="json") for r in records],
            "sources": [s.model_dump(mode="json") for s in repository.evidence_for(records)],
            "notice": NOTICE,
        }

    @app.post("/api/knowledge/search")
    def search_knowledge(body: KnowledgeQuery, request: Request) -> JSONResponse:
        session_for(request)
        return JSONResponse(
            {**knowledge.response(body, campus_today()), "request_id": request.state.request_id}
        )

    @app.get("/api/places")
    def places(
        q: Annotated[str, Field(max_length=120)] = "", category: str | None = None
    ) -> dict[str, JsonValue]:
        records = repository.search_place(q, category)
        return {
            "places": [place_card(p) for p in records],
            "sources": [s.model_dump(mode="json") for s in repository.evidence_for(records)],
            "notice": NOTICE,
        }

    @app.get("/api/teachers")
    def teachers(q: Annotated[str, Field(max_length=120)] = "") -> dict[str, JsonValue]:
        records = repository.search_teacher(q)
        return {
            "teachers": [t.model_dump(mode="json") for t in records],
            "sources": [s.model_dump(mode="json") for s in repository.evidence_for(records)],
            "notice": NOTICE,
        }

    @app.get("/api/map-config")
    def map_config() -> dict[str, JsonValue]:
        return {
            "configured": bool(amap_key and amap_security_code),
            "key": amap_key if amap_security_code else "",
            "service_host": "/_AMapService",
            "provider": "amap",
            "notice": "仅定位已有依据的地点；导航由高德提供。",
        }

    @app.get("/_AMapService/{path:path}", include_in_schema=False)
    async def amap_proxy(path: str, request: Request) -> Response:
        # SDK proxy only: no arbitrary URL, provider key, jscode or path from a caller.
        allowed = {
            "v3/log/init",  # JS SDK startup authentication; observed in the real map load.
            "v4/map/styles",
            "v4/map/tiles",
            "v3/config/district",
            "v4/map/district",
            "v3/direction/walking",
            "v3/assistant/coordinate/convert",
            "v3/place/around",  # Observed JS PlaceSearch.searchNearBy request.
            "v3/place/detail",  # PlaceSearch.getDetails for clicked base-map hotspots.
        }
        if not amap_key or not amap_security_code or path not in allowed:
            raise HTTPException(404)
        now = time.monotonic()
        while map_attempts and now - map_attempts[0] >= 60:
            map_attempts.popleft()
        if len(map_attempts) >= 120 or len(request.url.query) > 4096:
            raise HTTPException(429)
        map_attempts.append(now)
        params = dict(request.query_params)
        validate_route_params(path, params)
        validate_place_params(path, params)
        for key in ("callback", "jsonp", "cb"):
            if key in params and not re.fullmatch(
                r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*", params[key]
            ):
                raise HTTPException(422)
        params["key"] = amap_key
        params["jscode"] = amap_security_code
        base = (
            "https://webapi.amap.com/" if path == "v4/map/styles" else "https://restapi.amap.com/"
        )
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                async with client.stream("GET", base + path, params=params) as upstream:
                    if upstream.status_code != 200:
                        raise HTTPException(502)
                    content = bytearray()
                    async for chunk in upstream.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > 1_000_000:
                            raise HTTPException(502)
                    if amap_security_code.encode() in content:
                        raise HTTPException(502)
                    # SDK startup uses JSONP. Amap returns it as octet-stream;
                    # our nosniff boundary needs an explicit script MIME type.
                    media_type = (
                        "application/javascript"
                        if any(key in params for key in ("callback", "jsonp", "cb"))
                        else upstream.headers.get("content-type", "application/json")
                    )
                    return Response(
                        bytes(content),
                        media_type=media_type,
                    )
        except httpx.HTTPError:
            raise HTTPException(502) from None

    return app


def app_factory() -> FastAPI:
    """Single-worker VPS entry point; credentials remain in the environment."""
    key = os.environ.get("DIFY_API_KEY", "")
    dify = (
        DifyClient(
            key,
            os.environ.get("DIFY_API_BASE_URL", "https://api.dify.ai/v1"),
            structured_answers=os.environ.get("DIFY_STRUCTURED_ANSWERS") == "1",
        )
        if key
        else None
    )
    return create_web_app(
        data_dir=Path(os.environ.get("CAMPUSPILOT_DATA_DIR", "data/cdut")),
        dify=dify,
        api_token=os.environ.get("CAMPUSPILOT_API_TOKEN"),
        public_origin=os.environ.get("PUBLIC_ORIGIN"),
        amap_key=os.environ.get("AMAP_JS_KEY", ""),
        amap_security_code=os.environ.get("AMAP_SECURITY_JS_CODE", ""),
        daily_chat_limit=int(os.environ.get("CAMPUSPILOT_DAILY_CHAT_LIMIT", "100")),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="CampusPilot local web + Dify pilot")
    parser.add_argument("--data-dir", type=Path, default=Path("data/cdut"))
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--prompt-key", action="store_true")
    args = parser.parse_args()
    key = (
        getpass.getpass("Dify application API key (hidden): ")
        if args.prompt_key
        else os.environ.get("DIFY_API_KEY", "")
    )
    try:
        dify = (
            DifyClient(
                key,
                os.environ.get("DIFY_API_BASE_URL", "https://api.dify.ai/v1"),
                structured_answers=os.environ.get("DIFY_STRUCTURED_ANSWERS") == "1",
            )
            if key
            else None
        )
        app = create_web_app(
            data_dir=args.data_dir,
            dify=dify,
            api_token=os.environ.get("CAMPUSPILOT_API_TOKEN"),
            amap_key=os.environ.get("AMAP_JS_KEY", ""),
            amap_security_code=os.environ.get("AMAP_SECURITY_JS_CODE", ""),
        )
    except (OSError, ValueError):
        parser.exit(2, "Web configuration or directory data invalid.\n")
    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=args.port, access_log=False)
    if sys.platform == "win32":
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            runner.run(uvicorn.Server(config).serve())
    else:
        uvicorn.Server(config).run()


if __name__ == "__main__":
    main()
