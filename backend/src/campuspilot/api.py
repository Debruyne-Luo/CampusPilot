"""Optional local HTTP pilot; the domain and CLI remain independent of FastAPI."""

import argparse
import asyncio
import json
import os
import secrets
import sys
import time
from collections import deque
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import Field, JsonValue, ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from campuspilot.contracts import (
    Contract,
    DirectoryOfficeResult,
    ExecutionContext,
    OfficeInput,
    PlaceSearchResult,
    SearchInput,
    ServiceSearchResult,
    TeacherSearchResult,
    ToolCall,
    ToolResult,
    TraceEvent,
)
from campuspilot.directory.assist import AssistInput, AssistResponse, assist
from campuspilot.directory.lookup import LookupInput, LookupResponse, lookup
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.directory.tools import directory_tools
from campuspilot.state import InMemoryExecutionJournal
from campuspilot.tools import ReadOnlyPermissionPolicy, ToolExecutor


class DirectoryToolResult(ToolResult):
    data: (
        Annotated[
            ServiceSearchResult | DirectoryOfficeResult | PlaceSearchResult | TeacherSearchResult,
            Field(discriminator="kind"),
        ]
        | None
    ) = None


class DirectoryResponse(Contract):
    request_id: str
    result: DirectoryToolResult
    trace: tuple[TraceEvent, ...]
    notice: Literal["资料待人工核验，仅提供指引，未替你办理。"] = (
        "资料待人工核验，仅提供指引，未替你办理。"
    )


class ApiError(Contract):
    request_id: str
    error_code: str
    message: str
    retryable: bool = False


def create_app(
    *,
    data_dir: Path,
    api_token: str,
    tool_gateway: bool = False,
    repository: DirectoryRepository | None = None,
) -> FastAPI:
    """Load one validated snapshot; allocate execution context and journal per request."""
    if len(api_token) < 32 or not api_token.isascii() or any(c.isspace() for c in api_token):
        raise ValueError("Configure a non-whitespace ASCII API token of at least 32 characters")
    repository = repository or DirectoryRepository.load(data_dir)
    app = FastAPI(
        title="CampusPilot read-only directory pilot",
        version="0.1.0",
        description="Read-only services, places and teachers with explicit source limitations.",
        docs_url=None if tool_gateway else "/docs",
        redoc_url=None if tool_gateway else "/redoc",
        openapi_url=None if tool_gateway else "/openapi.json",
    )
    bearer = HTTPBearer(auto_error=False)
    recent_requests: deque[float] = deque()

    def error(request: Request, code: str, message: str, status: int) -> JSONResponse:
        payload = ApiError(request_id=request.state.request_id, error_code=code, message=message)
        headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
        return JSONResponse(payload.model_dump(), status_code=status, headers=headers)

    @app.middleware("http")
    async def request_boundary(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.request_id = str(uuid4())
        response: Response
        try:
            if tool_gateway and request.url.path.startswith("/v1/"):
                now = time.monotonic()
                while recent_requests and now - recent_requests[0] >= 60:
                    recent_requests.popleft()
                if len(recent_requests) >= 90:
                    response = error(request, "rate_limited", "Too many requests", 429)
                else:
                    recent_requests.append(now)
                    data = bytearray()
                    async with asyncio.timeout(10):
                        async for chunk in request.stream():
                            data.extend(chunk)
                            if len(data) > 16_384:
                                break
                    if len(data) > 16_384:
                        response = error(request, "payload_too_large", "Request too large", 413)
                    else:
                        request._body = bytes(data)
                        response = await call_next(request)
            else:
                response = await call_next(request)
        except Exception:
            # Do not reflect exceptions, request bodies or authentication headers.
            response = error(request, "unavailable", "Directory query unavailable", 503)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error(request, "invalid_input", "Invalid query parameters", 422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        messages = {
            401: ("unauthorized", "Valid application credential required"),
            404: ("not_found", "Unknown endpoint"),
            405: ("method_not_allowed", "Unsupported method"),
            422: ("invalid_input", "Invalid query parameters"),
        }
        code, message = messages.get(exc.status_code, ("request_rejected", "Request rejected"))
        if exc.status_code == 401 and request.url.path.startswith("/api/"):
            code = "session_expired"
            message = "会话已失效（可能由于服务重启），请点击“新对话”。"
        return error(request, code, message, exc.status_code)

    def authorize(
        request: Request,
        credential: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> None:
        if credential is None or not secrets.compare_digest(
            credential.credentials.encode("utf-8"), api_token.encode("ascii")
        ):
            raise HTTPException(status_code=401)
        # Both operations accept only their declared body/path, never authority in query strings.
        if request.query_params:
            raise HTTPException(status_code=422)

    def execute(request: Request, tool_id: str, arguments: dict[str, JsonValue]) -> JSONResponse:
        request_id: str = request.state.request_id
        journal = InMemoryExecutionJournal()
        executor = ToolExecutor(directory_tools(repository), ReadOnlyPermissionPolicy(), journal)
        context = ExecutionContext(
            session_id=f"http-session:{request_id}",
            task_id=f"http-task:{request_id}",
            run_id=f"http-run:{request_id}",
            allowed_tools=frozenset(
                {"search_service", "find_office", "search_place", "search_teacher"}
            ),
        )
        result = executor.execute(
            ToolCall(call_id=f"http-call:{request_id}", tool_id=tool_id, arguments=arguments),
            context,
        )
        output = DirectoryResponse(
            request_id=request_id,
            result=DirectoryToolResult.model_validate(result.model_dump()),
            trace=journal.events(context.session_id),
        )
        status = {"success": 200, "empty": 200, "invalid": 422, "denied": 403}.get(
            result.status, 503
        )
        return JSONResponse(output.model_dump(mode="json"), status_code=status)

    @app.get("/healthz", operation_id="health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ready"}

    @app.post(
        "/v1/directory/services/search",
        operation_id="search_service",
        response_model=DirectoryResponse,
        dependencies=[Depends(authorize)],
        responses={
            401: {"model": ApiError},
            403: {"model": DirectoryResponse},
            422: {"model": ApiError | DirectoryResponse},
            503: {"model": ApiError | DirectoryResponse},
        },
        description="Search a service name/alias, not a whole conversational question. Read only.",
    )
    def search(body: SearchInput, request: Request) -> JSONResponse:
        return execute(request, "search_service", body.model_dump(mode="json"))

    @app.get(
        "/v1/directory/offices/{office_id}",
        operation_id="find_office",
        response_model=DirectoryResponse,
        dependencies=[Depends(authorize)],
        responses={
            401: {"model": ApiError},
            403: {"model": DirectoryResponse},
            422: {"model": ApiError | DirectoryResponse},
            503: {"model": ApiError | DirectoryResponse},
        },
        description="Use office_id from a service result. Null location is unknown, not a map pin.",
    )
    def office(office_id: str, request: Request) -> JSONResponse:
        try:
            body = OfficeInput(office_id=office_id)
        except ValidationError:
            raise HTTPException(status_code=422) from None
        return execute(request, "find_office", body.model_dump(mode="json"))

    @app.post(
        "/v1/directory/lookup",
        operation_id="lookup_campus_matter",
        response_model=LookupResponse,
        dependencies=[Depends(authorize)],
        responses={
            401: {"model": ApiError},
            422: {"model": ApiError},
            503: {"model": LookupResponse},
        },
        description="Read-only service/office lookup with audience/year clarification; no LLM.",
    )
    def lookup_matter(body: LookupInput, request: Request) -> JSONResponse:
        result = lookup(repository, body, request.state.request_id)
        return JSONResponse(
            result.model_dump(mode="json"),
            status_code=503 if result.status == "unavailable" else 200,
        )

    @app.post(
        "/v1/directory/places/search",
        operation_id="search_place",
        response_model=DirectoryResponse,
        dependencies=[Depends(authorize)],
    )
    def places(body: SearchInput, request: Request) -> JSONResponse:
        return execute(request, "search_place", body.model_dump(mode="json"))

    @app.post(
        "/v1/directory/teachers/search",
        operation_id="search_teacher",
        response_model=DirectoryResponse,
        dependencies=[Depends(authorize)],
    )
    def teachers(body: SearchInput, request: Request) -> JSONResponse:
        return execute(request, "search_teacher", body.model_dump(mode="json"))

    @app.post(
        "/v1/directory/assist",
        operation_id="query_campus_directory",
        response_model=AssistResponse,
        dependencies=[Depends(authorize)],
    )
    def assist_query(body: AssistInput, request: Request) -> JSONResponse:
        output = assist(repository, body, request.state.request_id)
        return JSONResponse(
            output.model_dump(mode="json"),
            status_code=503 if output.status == "unavailable" else 200,
        )

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="CampusPilot local read-only API pilot")
    parser.add_argument("--data-dir", type=Path, default=Path("data/cdut"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--export-openapi", type=Path)
    parser.add_argument(
        "--tool-gateway", action="store_true", help="Disable API docs; limit size/rate"
    )
    args = parser.parse_args()
    token = (
        secrets.token_urlsafe(32)
        if args.export_openapi
        else os.environ.get("CAMPUSPILOT_API_TOKEN", "")
    )
    try:
        app = create_app(data_dir=args.data_dir, api_token=token, tool_gateway=args.tool_gateway)
    except OSError, ValueError:
        parser.exit(2, "API configuration or directory data invalid; no synthetic fallback.\n")
    if args.export_openapi:
        args.export_openapi.write_text(
            json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return
    import uvicorn

    # Cloud deployment is separate; this entry point never opens a public listener.
    if sys.platform == "win32":
        # Proactor accept fails with WinError 10014 on the development host.
        # This local HTTP server needs neither subprocess nor pipe transports.
        server = uvicorn.Server(
            uvicorn.Config(
                app, host="127.0.0.1", port=args.port, access_log=False, proxy_headers=False
            )
        )
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            runner.run(server.serve())
    else:
        uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, proxy_headers=False)


if __name__ == "__main__":
    main()
