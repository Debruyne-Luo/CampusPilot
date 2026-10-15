"""Session-level image gating follows the reader model, not the generation model."""

from fastapi.testclient import TestClient
from test_backend_evidence_flow import DATA, ScriptModel

HEADERS = {"Origin": "http://testserver", "X-CampusPilot-Request": "1"}


def test_session_advertises_images_with_reader_only_model() -> None:
    from campuspilot.app.factory import create_web_app

    reader: object = ScriptModel({"intent": "办事"})
    app = create_web_app(
        data_dir=DATA, runtime_mode="phase2", agent_loop=True, images_enabled=True, reader=reader  # type: ignore[arg-type]
    )
    with TestClient(app, headers=HEADERS) as client:
        assert client.post("/api/session").status_code == 200
        body = client.post("/api/session").json()
        assert body["images_enabled"] is True
        # No generation model, so text answers stay honestly unavailable.
        assert body["model_configured"] is False


def test_session_hides_images_without_any_model() -> None:
    from campuspilot.app.factory import create_web_app

    app = create_web_app(
        data_dir=DATA, runtime_mode="phase2", agent_loop=True, images_enabled=True
    )
    with TestClient(app, headers=HEADERS) as client:
        body = client.post("/api/session").json()
        assert body["images_enabled"] is False
