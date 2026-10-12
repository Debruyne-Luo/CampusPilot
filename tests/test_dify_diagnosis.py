"""Diagnostic privacy and redirect boundaries, using only synthetic responses."""

import io
import json
import runpy
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

import httpx
import pytest

HELPER = Path(__file__).resolve().parents[1] / "deploy/diagnose_dify.py"


@pytest.mark.parametrize(
    "content_type,body,extra_headers,expected",
    [
        (
            "application/json",
            {"code": "forbidden", "message": "SYNTHETIC-PRIVATE-RESPONSE"},
            {},
            {"api_error_code": "forbidden", "gateway_challenge": False},
        ),
        (
            "application/json",
            {"code": "synthetic_private_credential", "message": "SYNTHETIC-PRIVATE-RESPONSE"},
            {},
            {"api_error_code": "unrecognized", "gateway_challenge": False},
        ),
        (
            "text/html",
            "<title>SYNTHETIC-PRIVATE-RESPONSE</title>cf-chl-test; Error code: 1020",
            {"cf-mitigated": "challenge"},
            {"gateway_error_code": "1020", "gateway_challenge": True},
        ),
    ],
)
def test_error_metadata_never_echoes_response_values(
    content_type: str, body: Any, extra_headers: dict[str, str], expected: dict[str, Any]
) -> None:
    helper = runpy.run_path(str(HELPER))
    raw = (json.dumps(body) if isinstance(body, dict) else body).encode()
    result = helper["summarize"](
        403, {"Content-Type": content_type, "Server": "cloudflare", **extra_headers}, raw
    )
    assert result["http_status"] == 403
    assert all(result[key] == value for key, value in expected.items())
    rendered = json.dumps(result)
    assert "SYNTHETIC-PRIVATE-RESPONSE" not in rendered
    assert "synthetic_private_credential" not in rendered


def test_urllib_does_not_forward_credentials_on_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    helper = runpy.run_path(str(HELPER))
    calls = 0

    class RedirectResponse:
        def open(self, request: Any, **kwargs: Any) -> None:
            nonlocal calls
            calls += 1
            assert request.full_url == helper["DIFY_URL"]
            headers = EmailMessage()
            headers["Content-Type"] = "text/html"
            headers["Location"] = "https://example.com/synthetic"
            raise HTTPError(
                request.full_url,
                307,
                "Synthetic redirect",
                headers,
                io.BytesIO(b"SYNTHETIC-PRIVATE-RESPONSE"),
            )

    def opener(handler: Any) -> RedirectResponse:
        assert handler.redirect_request(None, None, 307, "", {}, "https://example.com") is None
        return RedirectResponse()

    monkeypatch.setitem(helper["probe_urllib"].__globals__, "build_opener", opener)
    result = helper["probe_urllib"]({}, {"Authorization": "Bearer synthetic-credential"})
    assert calls == 1 and result["http_status"] == 307
    assert "SYNTHETIC-PRIVATE-RESPONSE" not in json.dumps(result)


def test_backend_client_uses_one_fixed_destination_without_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper = runpy.run_path(str(HELPER))
    original = httpx.Client
    destinations = []

    def handler(request: httpx.Request) -> httpx.Response:
        destinations.append(str(request.url))
        return httpx.Response(
            307,
            headers={"location": "https://example.com/synthetic", "content-type": "text/html"},
            text="SYNTHETIC-PRIVATE-RESPONSE",
        )

    def factory(**kwargs: Any) -> httpx.Client:
        assert kwargs["follow_redirects"] is False
        assert "verify" not in kwargs and "proxy" not in kwargs and "trust_env" not in kwargs
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "Client", factory)
    result = helper["probe_httpx"]({}, {"Authorization": "Bearer synthetic-credential"})
    assert destinations == [helper["DIFY_URL"]] and result["http_status"] == 307
    assert "SYNTHETIC-PRIVATE-RESPONSE" not in json.dumps(result)


def test_read_only_run_emits_only_safe_comparison_results(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    helper = runpy.run_path(str(HELPER))
    namespace = helper["run"].__globals__

    def probe(payload: Any, headers: Any) -> dict[str, Any]:
        assert payload["response_mode"] == "blocking"
        assert headers["Authorization"] == "Bearer app-" + "x" * 36
        return {"http_status": 403, "body_kind": "html", "gateway_challenge": True}

    def no_write(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Read-only diagnostic attempted a file write")

    monkeypatch.setitem(namespace, "probe_urllib", probe)
    monkeypatch.setitem(namespace, "probe_httpx", probe)
    monkeypatch.setattr(Path, "write_text", no_write)
    monkeypatch.setattr(Path, "write_bytes", no_write)
    helper["run"]({"dify_api_key": "app-" + "x" * 36})
    output = capsys.readouterr().out
    assert "deployment-urllib:" in output and "backend-httpx:" in output
    assert "app-" + "x" * 36 not in output
