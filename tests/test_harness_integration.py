"""Profiles, route recipes and public experiment viewing across their real seams."""

import asyncio
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from campuspilot.agent.routing import RouteDecision, route_plan
from campuspilot.agent.understand import Slots, Understanding
from campuspilot.agent_lab import LabExperiment, LabRecords
from campuspilot.app.factory import create_web_app
from campuspilot.chat_runtime import ConversationContext
from campuspilot.evaluation_budget import OnlineBudget
from campuspilot.harness_profile import HarnessProfile
from campuspilot.jev_plugin import JevPlugin
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_agent_loop import DATA, FakeLLM, answer, run, runner, understood


def test_profile_identity_and_edit_surface() -> None:
    p = HarnessProfile.create("candidate-1", "先说明有依据的部分", "按任务使用工具")
    assert HarnessProfile.model_validate_json(p.model_dump_json()) == p
    with pytest.raises(ValidationError):
        p.version = "modified"
    with pytest.raises(ValueError, match="hash"):
        HarnessProfile.model_validate({**p.model_dump(), "answer_guidance": "changed"})
    with pytest.raises(ValueError, match="Only"):
        HarnessProfile.from_tree({"answer_guidance.md": "x", "guardrails.md": "x"}, "bad")


def test_profile_is_used_by_agent_and_does_not_leak_to_other_runner() -> None:
    profiled_model = FakeLLM(understood("政策问答"), answer("无法确认。", [], "empty"))
    agent = runner(profiled_model)
    agent.profile = HarnessProfile.create("experiment", "STRATEGY_SENTINEL")
    result = run(agent, "学生邮箱容量多少")
    assert result["harness_profile"] == agent.profile.identity()
    assert "STRATEGY_SENTINEL" in json.dumps(profiled_model.calls[-1]["messages"])
    other = FakeLLM(understood("政策问答"), answer("无法确认。", [], "empty"))
    plain = run(runner(other), "学生邮箱容量多少")
    assert "harness_profile" not in plain
    assert "STRATEGY_SENTINEL" not in json.dumps(other.calls)


def test_route_recipe_builds_valid_dependent_tools_without_model_arguments() -> None:
    view = Understanding(intent="政策问答", slots=Slots(service="补卡"))
    routed, plan = route_plan(view, "补卡怎么办", "service")
    assert routed.intent == "办事"
    assert [s.tool for s in plan.steps] == ["search_service", "make_checklist", "search_knowledge"]
    assert plan.steps[1].from_step == 1
    _, combined = route_plan(view, "图书馆服务", "place_knowledge")
    assert [s.tool for s in combined.steps] == ["search_place", "search_knowledge"]
    with pytest.raises(ValueError):
        route_plan(view, "q", "delete_everything")


class RouteClient:
    timeout_seconds = 0.01

    def __init__(self, result: RouteDecision | Exception) -> None:
        self.result, self.calls = result, 0

    async def evaluate_route(self, *_: Any, **__: Any) -> RouteDecision:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_route_cache_and_shared_turn_limit(tmp_path: Path) -> None:
    client = RouteClient(RouteDecision("ok", "knowledge", 0.98))
    plugin = JevPlugin(client, OnlineBudget(tmp_path, Decimal(1), 10), "on")  # type: ignore[arg-type]
    turn = plugin.turn()

    async def exercise() -> None:
        for _ in range(2):
            assert (await turn.route("q", "政策问答")).status == "ok"
        assert client.calls == 1
        assert (await turn.route("q2", "政策问答")).status == "unknown"
        await turn.assess("q3", ())
        await turn.assess("q4", ())
        assert (await turn.assess("q5", ())).reason == "turn_judge_limit"

    asyncio.run(exercise())
    assert client.calls == 1


def test_route_fault_preserves_answer_and_reports_fallback(tmp_path: Path) -> None:
    model = FakeLLM(understood("找地点", destination="香樟食堂"))
    agent = runner(model)
    agent.routing_jev = JevPlugin(
        RouteClient(TimeoutError()),  # type: ignore[arg-type]
        OnlineBudget(tmp_path, Decimal(1), 10),
        "on",
    )
    result = run(agent, "香樟食堂在哪")
    assert result["places"]
    assert result["decisions"][0]["action"] == "baseline"
    assert "raw" not in json.dumps(result["decisions"])


def test_exact_place_resolution_keeps_selected_knowledge_recipe(tmp_path: Path) -> None:
    agent = runner(FakeLLM(understood("找地点", destination="香樟食堂")))
    agent.routing_jev = JevPlugin(
        RouteClient(RouteDecision("ok", "place_knowledge", 0.99)),  # type: ignore[arg-type]
        OnlineBudget(tmp_path, Decimal(1), 10),
        "on",
    )
    events = []

    async def emit(event: str, payload: dict[str, Any]) -> None:
        if event == "tool_start":
            events.append(payload["tool"])

    asyncio.run(agent.run("香樟食堂服务说明", ConversationContext(), emit))
    assert "search_place" in events
    assert "search_knowledge" in events


def test_quoted_official_figure_text_does_not_require_an_upload() -> None:
    model = FakeLLM(understood("政策问答"))
    agent = runner(model)
    result = run(agent, "办理指南图上写着SYNTHETIC事项，我应按哪项业务提交？")
    assert model.calls
    assert "请上传" not in result["answer"]
    # A request to actually read an absent image must still ask for the image.
    missing_model = FakeLLM()
    missing = run(runner(missing_model), "帮我读这张图上的文字")
    assert "请上传" in missing["answer"]
    assert not missing_model.calls


def test_route_answer_keeps_unconfirmed_building_entrance_explicit() -> None:
    result = run(
        runner(FakeLLM(understood("路线", destination="香樟食堂"))),
        "带我去香樟食堂，入口不确定就说明",
    )
    assert result["places"]
    assert "参考" in result["answer"]
    assert "入口" in result["answer"] and "尚未确认" in result["answer"]


def experiment() -> dict[str, Any]:
    return {
        "id": "public-test",
        "title": "明确标记的测试实验",
        "kind": "campus_public_experiment",
        "status": "completed",
        "upstream_commit": "1cfe254e8d25b15f37048c3730134686abe60335",
        "code_identity": "test-identity",
        "knowledge_version": "test-version",
        "model": "fake",
        "question": "公开测试问题",
        "stages": ["base", "propose", "probe", "compose"],
        "limitation": "Synthetic test; no live model or university claim.",
    }


def test_lab_only_serves_valid_public_exports_and_no_start_api(tmp_path: Path) -> None:
    (tmp_path / "public-test.json").write_text(json.dumps(experiment()), encoding="utf-8")
    (tmp_path / "invalid.json").write_text('{"api_key":"secret"}', encoding="utf-8")
    assert len(LabRecords(tmp_path).list()) == 1
    app = create_web_app(data_dir=DATA, lab_records_dir=str(tmp_path), asset_version="labtest")
    with TestClient(app) as client:
        assert "/assets/v-labtest/v2/lab.mjs" in client.get("/lab").text
        assert len(client.get("/api/lab/experiments").json()["experiments"]) == 1
        assert client.get("/api/lab/experiments/public-test").json()["status"] == "completed"
        assert client.get("/api/lab/experiments/invalid").status_code == 404
        assert client.post("/api/lab/experiments").status_code == 405
        assert client.post("/api/lab/start").status_code == 404


def test_lab_rejects_private_exports_and_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        LabExperiment.model_validate({**experiment(), "question": "Bearer supersecretvalue"})
    with pytest.raises(FileNotFoundError):
        LabRecords(tmp_path).read("../secret")
    with pytest.raises(ValueError):
        LabExperiment.model_validate({**experiment(), "status": "running", "adopted": True})
