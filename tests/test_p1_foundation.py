"""P1 foundation: unified Settings, shared app assembly, rate guards and Tool registry."""

import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from campuspilot.app import main as app_main  # noqa: E402
from campuspilot.app.state import ChatBudget, SlidingWindow  # noqa: E402
from campuspilot.config import Settings  # noqa: E402
from campuspilot.directory.repository import DirectoryRepository  # noqa: E402
from campuspilot.knowledge import KnowledgeStore  # noqa: E402
from campuspilot.tools import ToolError, ToolRegistry, default_registry, tool_schema  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data" / "cdut"
HEADERS = {"Origin": "http://testserver", "X-CampusPilot-Request": "1"}


def test_settings_from_env_defaults_and_values() -> None:
    assert Settings.from_env({}) == Settings()
    settings = Settings.from_env(
        {
            "CAMPUSPILOT_RUNTIME_MODE": "phase2",
            "CAMPUSPILOT_DAILY_CHAT_LIMIT": "7",
            "PUBLIC_ORIGIN": "https://example.com",
            "DIFY_STRUCTURED_ANSWERS": "1",
            "DIFY_API_KEY": "synthetic-secret",
        }
    )
    assert settings.runtime_mode == "phase2" and settings.daily_chat_limit == 7
    assert settings.public_origin == "https://example.com"
    assert settings.dify_structured_answers
    assert "synthetic-secret" not in repr(settings)
    with pytest.raises(ValueError):
        Settings.from_env({"CAMPUSPILOT_RUNTIME_MODE": "other"})


def test_main_and_app_factory_share_build_app(monkeypatch: pytest.MonkeyPatch) -> None:
    """Behavior change: main() now honours PUBLIC_ORIGIN and CAMPUSPILOT_DAILY_CHAT_LIMIT."""
    seen: list[Settings] = []

    def fake_build(settings: Settings) -> object:
        seen.append(settings)
        return object()

    monkeypatch.setattr(app_main, "build_app", fake_build)

    class StopServe(Exception):
        pass

    def fake_config(*args: object, **kwargs: object) -> object:
        raise StopServe

    import uvicorn

    monkeypatch.setattr(uvicorn, "Config", fake_config)
    for key, value in {
        "PUBLIC_ORIGIN": "https://example.com",
        "CAMPUSPILOT_DAILY_CHAT_LIMIT": "5",
        "CAMPUSPILOT_DATA_DIR": str(DATA),
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(sys, "argv", ["campuspilot-web", "--data-dir", str(DATA)])
    with pytest.raises(StopServe):
        app_main.main()
    app_main.app_factory()
    cli, factory = seen
    assert cli == factory
    assert cli.public_origin == "https://example.com" and cli.daily_chat_limit == 5


def test_build_app_applies_daily_limit() -> None:
    app = app_main.build_app(Settings(data_dir=DATA, daily_chat_limit=1, dify_api_key=""))
    with TestClient(app) as client:
        assert client.post("/api/session", headers=HEADERS).status_code == 200
    with pytest.raises(ValueError):
        app_main.build_app(Settings(data_dir=DATA, daily_chat_limit=0))


def test_sliding_window_and_chat_budget() -> None:
    window = SlidingWindow(60, 2)
    window.record(0)
    window.record(1)
    assert window.full(30) and not window.full(60.5)
    budget = ChatBudget(daily_limit=3, max_active=2)
    assert budget.try_acquire() and budget.try_acquire()
    assert not budget.try_acquire()  # concurrency
    budget.release()
    assert budget.try_acquire()
    budget.release()
    budget.release()
    assert not budget.try_acquire()  # daily limit of 3 reached
    with pytest.raises(ValueError):
        ChatBudget(0)


def registry() -> tuple[DirectoryRepository, ToolRegistry]:
    repository = DirectoryRepository.load(DATA)
    return repository, default_registry(repository, KnowledgeStore.load(DATA / "knowledge.json"))


def test_registry_lists_validated_function_schemas() -> None:
    _, tools = registry()
    assert set(tools.names) == {
        "search_service",
        "find_office",
        "search_place",
        "search_teacher",
        "search_knowledge",
        "list_places",
    }
    for schema in tools.schemas():
        function = schema["function"]
        assert isinstance(function, dict) and function["description"]
        assert isinstance(function["parameters"], dict)
        assert function["parameters"]["type"] == "object"


def test_registry_rejects_unknown_tool_and_invalid_arguments() -> None:
    _, tools = registry()
    with pytest.raises(ToolError) as unknown:
        tools.call("delete_everything", {})
    assert unknown.value.code == "unknown_tool"
    with pytest.raises(ToolError) as invalid:
        tools.call("search_service", {"query": ""})
    assert invalid.value.code == "invalid_arguments"
    with pytest.raises(ToolError):
        tools.call("search_service", {"query": "x", "unexpected": 1})


def test_registry_wraps_existing_lookups() -> None:
    repository, tools = registry()
    service = repository.services()[0]
    found = tools.call("search_service", {"query": service.name})
    assert found["status"] == "success" and found["matches"]
    assert tools.call("search_service", {"query": "SYNTHETIC-不存在的事项"}) == {"status": "empty"}
    places = tools.call("list_places", {})
    assert isinstance(places["places"], list) and places["places"]
    knowledge = tools.call("search_knowledge", {"query": "学生邮箱怎么激活"})
    assert knowledge["result_status"] == "success" and knowledge["answer"]
    assert tool_schema is not None  # exported helper


def test_legacy_import_paths_still_work() -> None:
    from campuspilot import chat_model, web
    from campuspilot.llm import chat_model as moved
    from campuspilot.tools import ReadOnlyPermissionPolicy, ToolExecutor

    assert chat_model.ChatCompletionsModel is moved.ChatCompletionsModel
    assert callable(web.create_web_app) and callable(web.app_factory) and web.ASSETS.is_dir()
    assert isinstance(ReadOnlyPermissionPolicy, type) and isinstance(ToolExecutor, type)
