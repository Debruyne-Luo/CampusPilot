"""One persistent, non-daily USD 20 campaign ledger and a metered API gateway."""

from __future__ import annotations

import hmac
import json
import secrets
import threading
from dataclasses import dataclass, field
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx

from campuspilot.evaluation_budget import BudgetExhausted, OnlineBudget, TokenPrice

CAMPAIGN = "harness-jev-20261020"


class CampaignBudget(OnlineBudget):
    """Changing dates/output directories cannot reset the configured campaign."""

    def __init__(self, directory: Path) -> None:
        super().__init__(directory, Decimal("20"), 3000, today=CAMPAIGN)


@dataclass(frozen=True)
class MeteredProvider:
    endpoint: str
    model: str
    key: str = field(repr=False)
    price: TokenPrice
    max_output: int = 4096

    def __post_init__(self) -> None:
        if (
            self.endpoint
            not in {
                "https://api.deepseek.com/chat/completions",
                "https://openrouter.ai/api/alpha/decisions",
            }
            or not self.key
            or not self.model
            or not 1 <= self.max_output <= 4096
        ):
            raise ValueError("Invalid metered provider")


class ExperimentGateway:
    """All editor/solver/judge HTTP requests cross this gateway before transmission.

    The upstream API keys remain here, never in the editor workspace. Streaming is
    converted to a single bounded response so usage is accounted before delivery.
    """

    def __init__(
        self,
        budget: CampaignBudget,
        providers: dict[str, MeteredProvider],
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.budget, self.providers, self.transport = budget, providers, transport
        self.token = secrets.token_urlsafe(32)
        self.failure: dict[str, Any] | None = None
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def dispatch(self, path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if self.failure is not None:
            return 503, {"error": {"message": "experiment_provider_stopped"}}
        provider = self.providers.get(path)
        if provider is None or payload.get("model") != provider.model:
            return 400, {"error": {"message": "unapproved_endpoint_or_model"}}
        if any(k in payload for k in ("web_search_options", "mcp_servers")):
            return 400, {"error": {"message": "unpriced_server_tools_denied"}}
        payload = dict(payload)
        if path.endswith("chat/completions"):
            tools = payload.get("tools", [])
            if not isinstance(tools, list) or any(
                not isinstance(t, dict) or t.get("type") != "function" for t in tools
            ):
                return 400, {"error": {"message": "unpriced_tools_denied"}}
            if payload.get("n", 1) != 1 or int(payload.get("max_tokens", 4096)) <= 0:
                return 400, {"error": {"message": "unbounded_generation_denied"}}
            payload["stream"] = False
            payload.pop("stream_options", None)
            payload.pop("max_completion_tokens", None)
            payload["max_tokens"] = min(int(payload.get("max_tokens", 4096)), provider.max_output)
            payload["thinking"] = {"type": "disabled"}
        raw_input = json.dumps(payload, ensure_ascii=False).encode()
        if len(raw_input) > 500_000:
            return 413, {"error": {"message": "request_too_large"}}
        maximum = provider.price.cost(len(raw_input) + 16384, provider.max_output)
        try:
            reservation = self.budget.reserve(maximum, "gateway:" + path)
        except BudgetExhausted:
            self.failure = {"path": path, "status": 402, "reason": "campaign_budget_exhausted"}
            return 402, {"error": {"message": "campaign_budget_exhausted"}}
        actual = None
        try:
            with httpx.Client(
                transport=self.transport, timeout=90, follow_redirects=False, trust_env=False
            ) as client:
                response = client.post(
                    provider.endpoint,
                    json=payload,
                    headers={
                        "Authorization": "Bearer " + provider.key,
                    },
                )
            if len(response.content) > 2_000_000:
                return 502, {"error": {"message": "response_too_large"}}
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Invalid provider response")
            usage = data.get("usage", {})
            inputs = usage.get("prompt_tokens", usage.get("input_tokens"))
            outputs = usage.get("completion_tokens", usage.get("output_tokens"))
            if all(type(v) is int and v >= 0 for v in (inputs, outputs)):
                assert isinstance(inputs, int) and isinstance(outputs, int)
                actual = provider.price.cost(inputs, outputs)
                if usage.get("cost") is not None:
                    reported = Decimal(str(usage["cost"]))
                    if not reported.is_finite() or reported < 0:
                        raise ValueError("Invalid usage")
                    actual = max(actual, reported)
            # A definite authentication/request rejection did not execute a model.
            if response.status_code in {400, 401, 403, 404, 422}:
                actual = Decimal(0)
            if response.status_code != 200:
                self.failure = {
                    "path": path,
                    "status": response.status_code,
                    "reason": "provider_unavailable",
                }
            return response.status_code, data
        except httpx.HTTPError, ValueError:
            actual = None
            self.failure = {"path": path, "status": 502, "reason": "provider_outcome_unknown"}
            return 502, {"error": {"message": "provider_outcome_unknown"}}
        finally:
            self.budget.settle(reservation, actual)

    def __enter__(self) -> ExperimentGateway:
        gateway = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: object) -> None:
                pass

            def do_POST(self) -> None:
                stream = False
                if not hmac.compare_digest(
                    self.headers.get("Authorization", ""), "Bearer " + gateway.token
                ):
                    self.send_error(401)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 500_000:
                        raise ValueError
                    payload = json.loads(self.rfile.read(length))
                    if not isinstance(payload, dict):
                        raise ValueError
                    stream = payload.get("stream") is True
                    status, body = gateway.dispatch(self.path, payload)
                except ValueError, TypeError:
                    status, body = 400, {"error": {"message": "invalid_gateway_request"}}
                except BudgetExhausted:
                    status, body = 402, {"error": {"message": "campaign_budget_exhausted"}}
                streaming = status == 200 and stream and self.path.endswith("chat/completions")
                encoded = openai_stream(body) if streaming else json.dumps(body).encode()
                self.send_response(status)
                self.send_header(
                    "Content-Type", "text/event-stream" if streaming else "application/json"
                )
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                try:
                    self.wfile.write(encoded)
                except BrokenPipeError, ConnectionResetError:
                    # The caller's two-second judge timeout may precede provider completion.
                    # dispatch already settled/retained its durable reservation above.
                    return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    @property
    def base_url(self) -> str:
        assert self._server is not None
        return f"http://127.0.0.1:{self._server.server_port}"

    def __exit__(self, *_: object) -> None:
        assert self._server is not None
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=3)


def openai_stream(body: dict[str, Any]) -> bytes:
    """Serve metered non-stream completions to OpenCode's streaming client."""
    common = {k: body.get(k) for k in ("id", "model", "created")}
    common["object"] = "chat.completion.chunk"
    chunks = []
    for choice in body.get("choices", []):
        delta = dict(choice.get("message", {}))
        if isinstance(delta.get("tool_calls"), list):
            delta["tool_calls"] = [
                {**call, "index": i} for i, call in enumerate(delta["tool_calls"])
            ]
        chunks.append(
            {
                **common,
                "choices": [
                    {"index": choice.get("index", 0), "delta": delta, "finish_reason": None}
                ],
            }
        )
        chunks.append(
            {
                **common,
                "choices": [
                    {
                        "index": choice.get("index", 0),
                        "delta": {},
                        "finish_reason": choice.get("finish_reason", "stop"),
                    }
                ],
                "usage": body.get("usage", {}),
            }
        )
    return (
        "".join("data: " + json.dumps(c, ensure_ascii=False) + "\n\n" for c in chunks)
        + "data: [DONE]\n\n"
    ).encode()


class GatewayTransport(httpx.AsyncBaseTransport):
    """Keep production HTTPS configuration; only experiment requests use local metering."""

    def __init__(self, base_url: str, token: str) -> None:
        from urllib.parse import urlsplit

        url = urlsplit(base_url)
        if url.scheme != "http" or url.hostname != "127.0.0.1" or not url.port:
            raise ValueError("Experiment gateway must be local")
        self.base_url, self.token = base_url, token

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        path = "/v1/decisions" if request.url.path.endswith("decisions") else "/v1/chat/completions"
        # Each model call creates/closes its own transport; the wrapper itself owns no socket.
        async with httpx.AsyncClient(timeout=90, trust_env=False) as client:
            response = await client.post(
                self.base_url + path,
                content=await request.aread(),
                headers={
                    "Authorization": "Bearer " + self.token,
                    "Content-Type": "application/json",
                },
            )
            return httpx.Response(
                response.status_code,
                content=response.content,
                headers={"Content-Type": "application/json"},
            )
