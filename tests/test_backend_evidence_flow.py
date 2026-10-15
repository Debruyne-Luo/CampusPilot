"""End-to-end regressions for explicit destinations and bounded evidence enrichment."""

import asyncio
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import httpx
import pytest
from campuspilot.agent.executor import AgentRunner
from campuspilot.agent.understand import reconcile, rules_understanding, understand
from campuspilot.agent.verify import verify_answer
from campuspilot.app.factory import create_web_app
from campuspilot.chat_runtime import ConversationContext
from campuspilot.dify import ChatUnavailable
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.evaluation_budget import OnlineBudget
from campuspilot.jev_plugin import JevPlugin
from campuspilot.jev_shadow import ShadowResult
from campuspilot.knowledge import KnowledgeStore
from campuspilot.llm.chat_model import Completion, ImageInput, ToolCall
from campuspilot.places_discovery import PlaceDiscovery
from campuspilot.rag import SnapshotStore
from campuspilot.tools import agent_registry
from campuspilot.web_evidence import WebPageEvidence, WebSearchResult
from fastapi.testclient import TestClient

DATA = Path(__file__).resolve().parents[1] / "data/cdut"
REPO = DirectoryRepository.load(DATA)


@pytest.mark.parametrize(
    ("daily_usd", "flows"),
    [("1.01", 100), ("1", 101), ("NaN", 100), ("0", 100), ("1", 0)],
)
def test_configuration_cannot_raise_approved_evidence_limits(
    tmp_path: Path, daily_usd: str, flows: int
) -> None:
    with pytest.raises(ValueError, match="Evidence limits"):
        create_web_app(
            data_dir=DATA,
            web_search=True,
            evidence_budget_dir=str(tmp_path),
            evidence_daily_usd=daily_usd,
            evidence_daily_flows=flows,
        )


def test_embedding_prefetch_cannot_start_two_writers_in_one_session() -> None:
    async def scenario() -> None:
        release = asyncio.Event()
        both_prefetches = asyncio.Event()

        class QueuedEmbedder:
            calls = 0

            async def prefetch(self, query: str) -> None:
                self.calls += 1
                if self.calls == 2:
                    both_prefetches.set()
                await both_prefetches.wait()

        class PausedModel(ScriptModel):
            async def complete(
                self,
                messages: list[dict[str, object]],
                tools: list[dict[str, object]] | None = None,
                json_mode: bool = False,
                max_tokens: int | None = None,
            ) -> Completion:
                await release.wait()
                return await super().complete(messages, tools, json_mode, max_tokens)

        model: Any = PausedModel({"intent": "找地点", "destination": "E2A403"})
        embedder: Any = QueuedEmbedder()
        app = create_web_app(
            data_dir=DATA, runtime_mode="phase2", agent_loop=True, model=model, embedder=embedder
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver",
            headers={"Origin": "http://testserver", "X-CampusPilot-Request": "1"},
        ) as client:
            assert (await client.post("/api/session")).status_code == 200
            tasks = [
                asyncio.create_task(client.post("/api/chat", json={"message": "我想去E2A403"}))
                for _ in range(2)
            ]
            try:
                finished, _ = await asyncio.wait(
                    tasks, timeout=2, return_when=asyncio.FIRST_COMPLETED
                )
                assert len(finished) == 1
                assert next(iter(finished)).result().status_code == 409
            finally:
                release.set()
                responses = await asyncio.gather(*tasks)
            assert sorted(response.status_code for response in responses) == [200, 409]
            assert len(model.calls) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("path", ["/api/chat", "/api/chat/stream"])
def test_rejected_private_queries_never_reach_embedding_or_model(path: str) -> None:
    class RecordingEmbedder:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def prefetch(self, query: str) -> None:
            self.calls.append(query)

    embedder: Any = RecordingEmbedder()
    model: Any = ScriptModel()
    app = create_web_app(
        data_dir=DATA, runtime_mode="phase2", agent_loop=True, model=model, embedder=embedder
    )
    headers = {"Origin": "http://testserver", "X-CampusPilot-Request": "1"}
    with TestClient(app, headers=headers) as client:
        assert client.post("/api/session").status_code == 200
        # Unmistakably synthetic coordinates; never an actual user's position.
        response = client.post(
            path, json={"message": "SYNTHETIC PRIVATE QUERY 104.123456,30.123456"}
        )
        assert response.status_code == 200 and "请移除" in response.text
        assert embedder.calls == model.calls == []


class ScriptModel:
    def __init__(self, *values: dict[str, Any] | Completion | ChatUnavailable) -> None:
        self.values = list(values)
        self.calls: list[list[dict[str, object]]] = []

    async def complete(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]] | None = None,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> Completion:
        self.calls.append(messages)
        if not self.values:
            raise AssertionError("Unexpected additional model call")
        value = self.values.pop(0)
        if isinstance(value, ChatUnavailable):
            raise value
        return (
            value
            if isinstance(value, Completion)
            else Completion(content=json.dumps(value, ensure_ascii=False))
        )


def agent(model: ScriptModel | None = None, **kwargs: Any) -> AgentRunner:
    discovery = kwargs.pop("discovery", PlaceDiscovery(REPO))
    registry = agent_registry(
        REPO,
        KnowledgeStore.load(DATA / "knowledge.json"),
        SnapshotStore(DATA / "rag"),
        discovery=discovery,
    )
    return AgentRunner(registry, REPO, model, **kwargs)


@pytest.mark.parametrize(
    "question",
    [
        "我的上课教室在东教E2A403",
        "我的教室在东教Ｅ２Ａ４０３",
        "我想去E2A-403",
        "东教 E2A 403 在哪里",
        "带我去东教E2A403",
    ],
)
def test_explicit_classroom_has_one_building_no_unrelated_material(question: str) -> None:
    output: Any = asyncio.run(agent().run(question, ConversationContext()))
    assert [p["place_id"] for p in output["places"]] == ["cdut:place:east-e2a"]
    assert "E2A403" in output["answer"] and "室内路线尚未确认" in output["answer"]
    assert "电话" not in output["answer"] and not output["excerpts"]


def test_explicit_destination_beats_model_broadening() -> None:
    bad = rules_understanding("东教在哪里")
    corrected = reconcile(bad, "我的教室在东教E2A403")
    assert corrected.slots.destination == "E2A403"
    assert corrected.intent == "找地点"


def test_attributed_classroom_does_not_whitelist_other_user_numbers() -> None:
    raw = "我的教室是E2A403，电话12345678，费用999元"
    assert (
        verify_answer("你提供的教室号E2A403。", ["p"], ["p"], "success", "E2A", user_context=raw)
        is None
    )
    assert (
        verify_answer("电话12345678，费用999元。", ["p"], ["p"], "success", "E2A", user_context=raw)
        == "invalid_response"
    )


def test_provider_candidate_and_followup_keep_transient_identity() -> None:
    def reply(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "1",
                "pois": [
                    {
                        "id": "TESTPOI00001",
                        "name": "合成测试学院",
                        "location": "104.147531,30.675012",
                        "address": "纯合成测试地址，非真实校务记录",
                    }
                ],
            },
        )

    discovery = PlaceDiscovery(
        REPO, key="synthetic-test", enabled=True, transport=httpx.MockTransport(reply)
    )
    context = ConversationContext()
    runner = agent(discovery=discovery)
    output: Any = asyncio.run(runner.run("我想去合成测试学院", context))
    assert output["result_status"] == "success"
    assert output["places"][0]["place_id"] == "amap:poi:TESTPOI00001"
    assert output["places"][0]["evidence_scope"] == "location_only"
    assert "高德地图" in output["answer"] and output["citations"]
    follow: Any = asyncio.run(runner.run("就去这个", context))
    assert follow["places"] == output["places"]


class Judge:
    timeout_seconds = 1.0

    def __init__(self) -> None:
        self.calls = 0

    async def evaluate(self, *args: Any, **kwargs: Any) -> ShadowResult:
        raise AssertionError("Structured evidence context required")

    async def evaluate_evidence(self, *args: Any, **kwargs: Any) -> ShadowResult:
        self.calls += 1
        after = kwargs["evidence_context"].search_completed
        return ShadowResult(
            status="ok",
            answer_mode="generate",
            search_needed=not after,
            sufficient_probability=0.95 if after else 0.1,
        )


class Search:
    def __init__(
        self, authority: Literal["official_university", "third_party"] = "official_university"
    ) -> None:
        self.calls = 0
        self.authority = authority

    async def search(self, question: str) -> WebSearchResult:
        self.calls += 1
        return WebSearchResult(
            "success",
            (
                WebPageEvidence(
                    "web:synthetic",
                    "纯合成测试文档",
                    "https://www.cdut.edu.cn/__synthetic_test__",
                    "纯合成测试事项的材料是合成测试表，非真实校务规则。",
                    self.authority,
                    "2026-10-14",
                ),
            ),
        )


def test_zero_hits_routes_search_then_judge_once_each(tmp_path: Path) -> None:
    model = ScriptModel(
        {"intent": "政策问答", "missing": []},
        {
            "answer": "合成测试材料是合成测试表。",
            "source_ids": ["web:synthetic"],
            "status": "success",
        },
    )
    judge, search = Judge(), Search()
    plugin = JevPlugin(judge, OnlineBudget(tmp_path, Decimal("1"), 100), mode="on")
    runner = agent(model, jev=plugin, web_service=search)
    output: Any = asyncio.run(runner.run("合成测试事项需要什么", ConversationContext()))
    assert output["result_status"] == "success"
    assert judge.calls == 2 and search.calls == 1
    assert output["citations"][0]["source_authority"] == "official_university"


def test_third_party_cannot_establish_campus_policy(tmp_path: Path) -> None:
    # A valid judge response cannot upgrade a third-party page to campus authority.
    model = ScriptModel({"intent": "政策问答", "missing": []})
    judge, search = Judge(), Search("third_party")
    plugin = JevPlugin(judge, OnlineBudget(tmp_path, Decimal("1"), 100), mode="on")
    output: Any = asyncio.run(
        agent(model, jev=plugin, web_service=search).run(
            "合成测试事项需要什么", ConversationContext()
        )
    )
    assert not output["citations"]
    assert len(model.calls) == 1 and output["web_sources"][0]["source_label"] == "第三方辅助信息"


def test_image_reaches_understanding_and_resolves_visible_room() -> None:
    model = ScriptModel(
        {
            "intent": "找地点",
            "destination": "E2A403",
            "missing": [],
            "image_observation": "合成测试课表写着E2A403。",
            "image_visible_text": "E2A403",
        }
    )
    image = ImageInput("synthetic-image", "image/png", b"synthetic-image-bytes")
    output: Any = asyncio.run(
        agent(model).run("这张课表的教室在哪里", ConversationContext(), images=(image,))
    )
    blocks = model.calls[0][-1]["content"]
    assert isinstance(blocks, list) and blocks[1]["type"] == "image_url"
    assert output["places"][0]["place_id"] == "cdut:place:east-e2a"


def test_no_model_never_dumps_keyword_hits() -> None:
    output: Any = asyncio.run(agent().run("楼寓商学院未收录问题合成测试", ConversationContext()))
    assert "84078849" not in output["answer"]
    assert len(output["answer"]) < 400


@pytest.mark.parametrize("code", ["E9Z403", "E2D403", "E1C403"])
def test_unknown_classroom_is_not_replaced_by_generic_east_building(code: str) -> None:
    output: Any = asyncio.run(agent().run("我想去东教" + code, ConversationContext()))
    assert output["result_status"] == "needs_clarification"
    assert output["places"] == [] and output["map_actions"] == []


def test_appearance_guess_does_not_create_a_navigation_target() -> None:
    model = ScriptModel(
        {
            "intent": "找地点",
            "destination": "E2A",
            "missing": [],
            "image_observation": "建筑外观像东教E2A，照片上没有文字。",
            "image_visible_text": "",
        }
    )
    image = ImageInput("synthetic-appearance", "image/png", b"synthetic")
    output: Any = asyncio.run(
        agent(model).run("照片中的地方在哪里", ConversationContext(), images=(image,))
    )
    assert output["places"] == [] and output["map_actions"] == []


def test_text_only_request_ignores_phantom_image_fields() -> None:
    proposal = {
        "intent": "找地点",
        "destination": "E2A",
        "missing": [],
        "image_observation": "模型虚构了合成图片 E2A。",
        "image_visible_text": "E2A",
    }
    view = asyncio.run(understand(ScriptModel(proposal), "商学院在哪里", ()))
    assert view.slots.destination is None
    assert view.image_visible_text == view.image_observation == ""
    output: Any = asyncio.run(
        agent(ScriptModel(proposal)).run("商学院在哪里", ConversationContext())
    )
    assert output["places"] == [] and output["map_actions"] == []


def test_image_reading_answer_does_not_require_or_invent_official_sources() -> None:
    model = ScriptModel(
        {
            "intent": "政策问答",
            "missing": [],
            "image_observation": "合成通知写着要交合成测试表。",
            "image_visible_text": "合成通知：提交合成测试表。",
        },
        {
            "answer": "图片里的合成通知要求提交合成测试表。",
            "source_ids": [],
            "status": "success",
        },
    )
    image = ImageInput("synthetic-notice", "image/png", b"synthetic")
    output: Any = asyncio.run(
        agent(model).run("帮我读这张通知，要求交什么", ConversationContext(), images=(image,))
    )
    assert output["result_status"] == "success" and output["answer_mode"] == "agent_image"
    assert "未经学校核验" in output["answer"] and "合成测试表" in output["answer"]
    assert not output["citations"] and not output["excerpts"] and not output["places"]


@pytest.mark.parametrize(
    ("failure", "reason", "status"),
    [
        (ChatUnavailable("upstream_timeout"), "upstream_timeout", "limited"),
        (ChatUnavailable("upstream_limit"), "upstream_limit", "limited"),
        (Completion(content="{broken"), "model_format", "limited"),
        (
            {"answer": "截止2026年10月15日。", "status": "success", "source_ids": []},
            "answer_validation",
            "needs_clarification",
        ),
    ],
)
def test_image_failures_distinguish_service_format_and_evidence(
    failure: dict[str, Any] | Completion | ChatUnavailable, reason: str, status: str
) -> None:
    model = ScriptModel(
        {
            "intent": "政策问答",
            "missing": [],
            "image_observation": "纯合成测试通知。",
            "image_visible_text": "截止2026-10-14。",
        },
        failure,
    )
    image = ImageInput("synthetic-failures", "image/png", b"synthetic")
    output: Any = asyncio.run(
        agent(model).run("读这张通知的截止时间", ConversationContext(), images=(image,))
    )
    assert output["degraded_reason"] == reason and output["result_status"] == status
    assert not output["citations"] and not output["excerpts"]
    if reason == "upstream_timeout":
        assert "超时" in output["answer"] and "清晰" not in output["answer"]


@pytest.mark.parametrize("claim", ["办公室在4楼。", "收费9元。", "从东门进入。"])
def test_small_unsupported_indoor_and_fee_claims_are_blocked(claim: str) -> None:
    assert (
        verify_answer(claim, ["p"], ["p"], "success", "合成测试学院位于校园。")
        == "invalid_response"
    )


def test_image_amount_cannot_be_promoted_to_current_official_fee() -> None:
    model = ScriptModel(
        {
            "intent": "办事",
            "service": "校园卡补办",
            "missing": [],
            "image_observation": "纯合成测试截图写999元，不是真实收费。",
            "image_visible_text": "合成测试：999元。",
        },
        {
            "answer": "自助补卡前卡内余额大于20元，现行收费999元。",
            "source_ids": ["cdut:service:campus-card-replacement"],
            "status": "success",
        },
    )
    image = ImageInput("synthetic-fee", "image/png", b"synthetic")
    output: Any = asyncio.run(
        agent(model).run(
            "我是本科生，核实图片里补卡的现行收费", ConversationContext(), images=(image,)
        )
    )
    assert output["degraded_reason"] == "answer_validation"
    assert "999元" not in output["answer"]


def test_single_fuzzy_provider_result_does_not_automatically_choose_route() -> None:
    discovery = PlaceDiscovery(
        REPO,
        key="synthetic-test",
        enabled=True,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "status": "1",
                    "pois": [
                        {
                            "id": "TESTPOI00001",
                            "name": "合成测试学院办公楼",
                            "location": "104.147531,30.675012",
                            "address": "纯合成测试，非真实地点",
                        }
                    ],
                },
            )
        ),
    )
    output: Any = asyncio.run(
        agent(discovery=discovery).run("我想去合成测试学院", ConversationContext())
    )
    assert output["result_status"] == "needs_clarification"
    assert all(action["type"] != "plan_route" for action in output["map_actions"])


def test_no_extra_evidence_can_bypass_completed_jev_routing(tmp_path: Path) -> None:
    class EnoughJudge(Judge):
        async def evaluate_evidence(self, *args: Any, **kwargs: Any) -> ShadowResult:
            self.calls += 1
            return ShadowResult(
                status="ok",
                answer_mode="generate",
                search_needed=False,
                sufficient_probability=0.95,
                chunk_scores=tuple((hit.chunk.chunk_id, 2.0) for hit in args[1]),
            )

    model = ScriptModel(
        {"intent": "政策问答", "missing": []},
        Completion(
            tool_calls=(
                ToolCall(
                    call_id="unreviewed", name="search_knowledge", arguments='{"query":"楼寓中心"}'
                ),
            )
        ),
    )
    judge, search = EnoughJudge(), Search()
    plugin = JevPlugin(
        judge,
        OnlineBudget(tmp_path, Decimal("1"), 100),
        mode="on",
        snapshots=SnapshotStore(DATA / "rag"),
    )
    output: Any = asyncio.run(
        agent(model, jev=plugin, web_service=search).run("学生邮箱怎么激活", ConversationContext())
    )
    assert judge.calls == 1 and search.calls == 0
    assert "楼寓" not in output["answer"] and "repair" not in str(output["citations"])
