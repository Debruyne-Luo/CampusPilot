"""Shared per-app state: browser sessions, rate limits and browser boundary helpers."""

import secrets
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from campuspilot.agent.executor import AgentRunner
from campuspilot.chat_runtime import ChatRuntime, ConversationContext, Mode
from campuspilot.dify import DifyClient
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.knowledge import KnowledgeStore
from campuspilot.llm.chat_model import ProductionModel
from campuspilot.llm.embedding import CloudflareEmbedder

ASSETS = Path(__file__).resolve().parent.parent / "web_assets"
COOKIE = "campuspilot_session"
NOTICE = "资料待人工核验，仅提供指引，未替你办理。"
SESSION_TURN_LIMIT = 40
MAX_SESSIONS = 256
MAX_ACTIVE_CHATS = 2


@dataclass
class BrowserSession:
    user: str = field(default_factory=lambda: "cp-" + secrets.token_urlsafe(24))
    conversation: str = ""
    expires: float = field(default_factory=lambda: time.monotonic() + 3600)
    busy: bool = False
    uncertain: bool = False
    attempts: int = 0
    knowledge_titles: tuple[str, ...] = ()
    context: ConversationContext = field(default_factory=ConversationContext)

    @property
    def turns_exhausted(self) -> bool:
        return self.attempts >= SESSION_TURN_LIMIT


class SlidingWindow:
    """Count events inside a trailing window (monotonic seconds)."""

    def __init__(self, window: float, limit: int) -> None:
        self.window = window
        self.limit = limit
        self.events: deque[float] = deque()

    def _prune(self, now: float) -> None:
        while self.events and now - self.events[0] >= self.window:
            self.events.popleft()

    def full(self, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        self._prune(now)
        return len(self.events) >= self.limit

    def record(self, now: float | None = None) -> None:
        self.events.append(time.monotonic() if now is None else now)


class ChatBudget:
    """Unified guard for upstream model/Dify calls: daily budget plus concurrency."""

    def __init__(self, daily_limit: int, max_active: int = MAX_ACTIVE_CHATS) -> None:
        if daily_limit < 1:
            raise ValueError("Chat budget must be positive")
        self.daily = SlidingWindow(86400, daily_limit)
        self.max_active = max_active
        self.active = 0

    def try_acquire(self) -> bool:
        now = time.monotonic()
        if self.daily.full(now) or self.active >= self.max_active:
            return False
        self.daily.record(now)
        self.active += 1
        return True

    def release(self) -> None:
        self.active -= 1


@dataclass
class WebState:
    repository: DirectoryRepository
    knowledge: KnowledgeStore
    runtime: ChatRuntime
    runtime_mode: Mode
    dify: DifyClient | None
    model: ProductionModel | None
    public_origin: str | None
    amap_key: str
    amap_security_code: str
    budget: ChatBudget
    embedder: CloudflareEmbedder | None = None
    agent: AgentRunner | None = None
    map_window: SlidingWindow = field(default_factory=lambda: SlidingWindow(60, 120))
    sessions: dict[str, BrowserSession] = field(default_factory=dict)

    def check_browser(self, request: Request) -> None:
        # No CORS. Custom header blocks cross-site simple forms; origin is checked as well.
        expected = self.public_origin or str(request.base_url).rstrip("/")
        if (
            request.headers.get("X-CampusPilot-Request") != "1"
            or request.headers.get("Origin") != expected
            or request.headers.get("Sec-Fetch-Site") == "cross-site"
        ):
            raise HTTPException(403)
        if request.query_params:
            raise HTTPException(422)

    @staticmethod
    def problem(request: Request, code: str, message: str, status: int) -> JSONResponse:
        return JSONResponse(
            {"error_code": code, "message": message, "request_id": request.state.request_id},
            status_code=status,
        )

    def session_for(self, request: Request) -> BrowserSession:
        self.check_browser(request)
        token = request.cookies.get(COOKIE, "")
        session = self.sessions.get(token)
        if session is None or session.expires < time.monotonic():
            raise HTTPException(401)
        return session
