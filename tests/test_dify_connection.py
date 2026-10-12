"""Connection transport failures must stay controlled and precede server changes."""

import runpy
import stat
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

HELPER = Path(__file__).resolve().parents[1] / "deploy/configure_dify.py"


@pytest.mark.parametrize(
    "status,body,error",
    [
        (403, b"SYNTHETIC-PRIVATE-RESPONSE", "http_403"),
        (307, b"SYNTHETIC-PRIVATE-RESPONSE", "http_307"),
        (200, b"invalid SYNTHETIC-PRIVATE-RESPONSE", "network_or_response_error"),
        (200, b"x" * 1_000_001, "oversized_response"),
    ],
    ids=["forbidden", "redirect", "invalid-json", "oversized"],
)
def test_transport_failures_do_not_leak_body_or_follow_redirect(
    status: int, body: bytes, error: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    helper = runpy.run_path(str(HELPER))
    original = httpx.Client
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(
            status,
            content=body,
            headers={"location": "https://example.com/synthetic"},
        )

    def factory(**kwargs: Any) -> httpx.Client:
        assert kwargs["follow_redirects"] is False
        assert "verify" not in kwargs and "proxy" not in kwargs
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "Client", factory)
    with pytest.raises(helper["ConnectionFailure"]) as caught:
        helper["request_json"](helper["DIFY_URL"], {}, {"Authorization": "Bearer synthetic"})
    assert str(caught.value) == error and calls == [helper["DIFY_URL"]]


def test_success_keeps_session_headers_and_json(monkeypatch: pytest.MonkeyPatch) -> None:
    helper = runpy.run_path(str(HELPER))
    original = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        return httpx.Response(
            200, json={"configured": True}, headers={"Set-Cookie": "synthetic-session=one"}
        )

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    body, headers = helper["request_json"](helper["LOOPBACK"] + "/api/session", {})
    assert body == {"configured": True} and headers["Set-Cookie"] == "synthetic-session=one"


def test_failed_published_precheck_never_changes_server(monkeypatch: pytest.MonkeyPatch) -> None:
    helper = runpy.run_path(str(HELPER))
    namespace = helper["main"].__globals__
    origin = str(helper["ORIGIN"])

    class PrivateEnvironment:
        def is_symlink(self) -> bool:
            return False

        def is_file(self) -> bool:
            return True

        def stat(self) -> SimpleNamespace:
            return SimpleNamespace(st_uid=0, st_mode=stat.S_IFREG | 0o600, st_size=200)

        def read_text(self, **kwargs: Any) -> str:
            return "PUBLIC_ORIGIN=" + origin + "\nCAMPUSPILOT_API_TOKEN=" + "x" * 36 + "\n"

        def with_name(self, name: str) -> Any:
            return SimpleNamespace(exists=lambda: False, is_symlink=lambda: False)

    def precheck_failed(*args: Any, **kwargs: Any) -> None:
        raise helper["ConnectionFailure"]("http_403")

    def no_changes(*args: Any, **kwargs: Any) -> None:
        pytest.fail("A failed precheck attempted server configuration or a restart")

    monkeypatch.setitem(namespace, "ENV_PATH", PrivateEnvironment())
    monkeypatch.setitem(namespace, "expected_ids", lambda *args: {})
    monkeypatch.setitem(namespace, "request_json", precheck_failed)
    monkeypatch.setattr(namespace["os"], "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(namespace["shutil"], "copy2", no_changes)
    monkeypatch.setattr(namespace["tempfile"], "NamedTemporaryFile", no_changes)
    monkeypatch.setattr(namespace["subprocess"], "run", no_changes)
    with pytest.raises(helper["ConnectionFailure"], match="^http_403$"):
        helper["main"]({"dify_api_key": "app-" + "x" * 36})
