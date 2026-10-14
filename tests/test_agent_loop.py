"""P3 agent loop with a scripted fake LLM (no network): understand, plan, tools, verify."""

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from campuspilot.agent.executor import ANSWER_MAX_TOKENS, MAX_TOOL_ROUNDS, AgentRunner
from campuspilot.agent.plan import make_plan
from campuspilot.agent.understand import Slots, Understanding, understand
from campuspilot.agent.verify import verify_answer
from campuspilot.chat_runtime import ConversationContext
from campuspilot.config import Settings
from campuspilot.dify import ChatUnavailable
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.knowledge import KnowledgeStore
from campuspilot.llm.chat_model import ChatCompletionsModel, Completion, ModelReply, ToolCall
from campuspilot.rag import SnapshotStore
from campuspilot.tools import ToolError, agent_registry

DATA = Path(__file__).resolve().parents[1] / "data" / "cdut"
REPO = DirectoryRepository.load(DATA)
CARD_ID = "cdut:service:campus-card-replacement"
CARD = REPO.find_service(CARD_ID)
assert CARD is not None
CARD_EVIDENCE = sorted({i for f in CARD.field_evidence for i in f.evidence_ids})
HEADERS = {"Origin": "http://testserver", "X-CampusPilot-Request": "1"}

Step = Completion | Exception | Callable[[list[dict[str, object]]], Completion]


class FakeLLM:
    """Scripted ToolCallingModel; records every request."""

    def __init__(self, *script: Step) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]] | None = None,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> Completion:
        self.calls.append(
            {"messages": messages, "tools": tools, "json_mode": json_mode, "max_tokens": max_tokens}
        )
        if not self.script:
            raise ChatUnavailable("upstream_unavailable")
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        if callable(step):
            return step(messages)
        return step

    async def generate(self, question: str, evidence: str, history: tuple[Any, ...]) -> ModelReply:
        raise AssertionError("agent path must not use the rule generator")


def say(payload: dict[str, object]) -> Completion:
    return Completion(content=json.dumps(payload, ensure_ascii=False))


def understood(intent: str = "办事", **extra: object) -> Completion:
    return say({"intent": intent, "identity": "unknown", "missing": [], **extra})


def answer(text: str, ids: list[str], status: str = "success") -> Completion:
    return say({"answer": text, "source_ids": ids, "status": status})


def runner(model: FakeLLM | None) -> AgentRunner:
    registry = agent_registry(
        REPO, KnowledgeStore.load(DATA / "knowledge.json"), SnapshotStore(DATA / "rag", "hybrid")
    )
    return AgentRunner(registry, REPO, model)


def run(agent: AgentRunner, question: str, context: ConversationContext | None = None) -> Any:
    return asyncio.run(agent.run(question, context or ConversationContext()))


GOOD_CARD = "自助补卡前确认卡内余额大于20元，带好本人身份证，到珙桐或香樟食堂自助服务区办理。"


# --- understand ---------------------------------------------------------------------------


def test_understand_uses_model_json_and_rules_validate_slots() -> None:
    model = FakeLLM(
        say(
            {
                "intent": "办事",
                "identity": "graduate",
                "academic_year": "2030-2031",
                "service": "在读证明",
                "missing": ["identity"],
                "clarify_question": "你是什么身份？",
            }
        )
    )
    view = asyncio.run(understand(model, "我是本科生，在读证明怎么开", ()))
    assert view.source == "model" and view.intent == "办事"
    assert view.slots.identity == "undergraduate"  # explicit text beats the model
    assert view.slots.academic_year is None  # year absent from text is discarded
    assert view.missing == () and view.clarify_question is None
    assert model.calls[0]["json_mode"] is True


@pytest.mark.parametrize(
    "reply",
    [
        Completion(content="not json"),
        say({"intent": "购物"}),
        say({"intent": "办事", "academic_year": "26-27"}),
        ChatUnavailable("upstream_timeout"),
    ],
)
def test_understand_falls_back_to_rules(reply: Step) -> None:
    view = asyncio.run(understand(FakeLLM(reply), "2026-2027学年研究生学杂费票据怎么办", ()))
    assert view.source == "rules" and view.intent == "办事"
    assert view.slots.identity == "graduate" and view.slots.academic_year == "2026-2027"
    rules = asyncio.run(understand(None, "香樟食堂怎么去", ()))
    assert rules.intent == "路线"


# --- plan -----------------------------------------------------------------------------------


def test_plans_are_bounded_and_intent_specific() -> None:
    service = make_plan(
        Understanding(intent="办事", slots=Slots(identity="graduate", service="在读证明")), "q"
    )
    assert [s.tool for s in service.steps] == [
        "search_service",
        "make_checklist",
        "search_knowledge",
    ]
    assert service.steps[1].from_step == 1 and service.steps[2].arguments["audience"] == "graduate"
    route = make_plan(Understanding(intent="路线", slots=Slots(destination="香樟食堂")), "q")
    assert route.map_action == "plan_route" and route.steps[0].arguments == {"query": "香樟食堂"}
    assert make_plan(Understanding(intent="闲聊"), "你好").steps == ()
    for intent in ("办事", "找人", "找地点", "路线", "政策问答", "闲聊"):
        assert len(make_plan(Understanding(intent=intent), "问题").steps) <= 4


# --- execution ------------------------------------------------------------------------------


def test_service_turn_runs_plan_checklist_and_verified_answer() -> None:
    model = FakeLLM(understood(service="校园卡补办"), answer(GOOD_CARD, [CARD_EVIDENCE[0]]))
    out = run(runner(model), "校园卡补办需要什么")
    assert out["result_status"] == "success" and out["answer_mode"] == "agent"
    assert [(s["tool"], s["status"]) for s in out["plan"]][:2] == [
        ("search_service", "success"),
        ("make_checklist", "success"),
    ]
    checklist = out["checklist"]
    assert checklist["service_id"] == CARD_ID
    assert any(i["kind"] == "limit" and "大于20" in i["text"] for i in checklist["items"])
    assert out["services"][0]["service_id"] == CARD_ID and out["places"]
    assert out["source_ids"] == [CARD_EVIDENCE[0]] and out["citations"]
    assert all(a["type"] == "show_place" for a in out["map_actions"])
    assert out["understanding"]["intent"] == "办事"
    assert len(model.calls) == 2


def test_function_calling_round_is_whitelisted_and_validated() -> None:
    def final(messages: list[dict[str, object]]) -> Completion:
        tool_messages = [m for m in messages if m["role"] == "tool"]
        assert len(tool_messages) == 3
        assert "unknown_tool" in str(tool_messages[1]["content"])
        assert "invalid_arguments" in str(tool_messages[2]["content"])
        return answer("香樟餐厅可以在地图上查看。", ["cdut:place:camphor-dining"])

    model = FakeLLM(
        understood("政策问答"),
        Completion(
            tool_calls=(
                ToolCall(call_id="c1", name="search_place", arguments='{"query":"香樟"}'),
                ToolCall(call_id="c2", name="delete_records", arguments="{}"),
                ToolCall(call_id="c3", name="search_place", arguments='{"query":""}'),
            )
        ),
        final,
    )
    out = run(runner(model), "香樟那边有什么")
    assert out["result_status"] == "success"
    assert any(p["place_id"] == "cdut:place:camphor-dining" for p in out["places"])
    assert model.calls[1]["tools"] and {t["function"]["name"] for t in model.calls[1]["tools"]} >= {
        "make_checklist",
        "search_knowledge",
    }


def test_tool_rounds_are_capped_then_degrade_to_summary() -> None:
    loop = Completion(
        tool_calls=(ToolCall(call_id="x", name="search_place", arguments='{"query":"香樟"}'),)
    )
    model = FakeLLM(understood("政策问答"), *[loop] * 10)
    out = run(runner(model), "香樟那边有什么")
    assert out["result_status"] == "limited" and out["degraded_reason"] == "tool_rounds_exceeded"
    assert out["answer"].startswith("已找到地点")
    assert len(model.calls) == 1 + MAX_TOOL_ROUNDS + 1
    assert model.calls[-1]["tools"] is None  # last round forces an answer


@pytest.mark.parametrize(
    "reply,reason",
    [
        (answer(GOOD_CARD, ["cdut:evidence:invented"]), "answer_validation"),
        (answer(GOOD_CARD, []), "answer_validation"),
        (answer(GOOD_CARD + "详见 https://example.com", ["E"]), "answer_validation"),
        (answer("余额大于20元，费用99999元。", ["E"]), "answer_validation"),
        (answer("带好本人身份证到食堂自助服务区办理。", ["E"]), "required_premise_missing"),
        (Completion(content="{bad"), "model_format"),
        (ChatUnavailable("upstream_limit"), "upstream_limit"),
    ],
)
def test_verification_failures_degrade(reply: Step, reason: str) -> None:
    if isinstance(reply, Completion) and reply.content and '"E"' in reply.content:
        reply = Completion(content=reply.content.replace('"E"', json.dumps(CARD_EVIDENCE[0])))
    model = FakeLLM(understood(service="校园卡补办"), reply)
    out = run(runner(model), "校园卡补办需要什么")
    assert out["result_status"] == "limited" and out["degraded_reason"] == reason
    assert "https://example.com" not in out["answer"] and "99999" not in out["answer"]
    assert out["checklist"] is not None  # tool results stay usable after degradation


def test_verify_answer_unit() -> None:
    assert verify_answer("余额大于20元", ["a"], {"a"}, "success", "x", "余额大于20元") is None
    assert verify_answer("ok", ["a"], {"b"}, "success", "") == "invalid_response"
    assert verify_answer("ok", [], set(), "needs_clarification", "") is None
    assert verify_answer("坐标 30.1", ["a"], {"a"}, "success", "") == "invalid_response"


# --- clarify, sensitive input, no model ------------------------------------------------------


def test_missing_identity_asks_and_context_answers_next_turn() -> None:
    context = ConversationContext()
    model = FakeLLM(
        understood(missing=["identity"], clarify_question="你是本科生还是研究生？"),
    )
    first = run(runner(model), "在读证明怎么开", context)
    assert (
        first["result_status"] == "needs_clarification" and first["answer_mode"] == "agent_clarify"
    )
    assert first["answer"] == "你是本科生还是研究生？" and first["plan"] == []
    assert len(model.calls) == 1
    # Identity given in text is authoritative, remembered in context, and removes the gap.
    second_model = FakeLLM(understood(missing=["identity"]), answer("请走研究生流程。", []))
    second = run(runner(second_model), "我是研究生，在读证明怎么开", context)
    assert second["understanding"]["slots"]["identity"] == "graduate"
    assert context.audience == "graduate"
    third_model = FakeLLM(understood(missing=["identity"]))
    third = run(runner(third_model), "在读证明要多久", context)
    assert third["understanding"]["slots"]["identity"] == "graduate"
    assert third["result_status"] != "needs_clarification"


def test_sensitive_input_is_blocked_before_any_model_call() -> None:
    model = FakeLLM(understood())
    out = run(runner(model), "我的密码是123456，帮我补办校园卡")
    assert out["result_status"] == "needs_clarification" and "密码" in out["answer"]
    assert model.calls == []


def test_chitchat_and_no_model_rules_path() -> None:
    assert run(runner(FakeLLM(understood("闲聊"))), "你好")["answer_mode"] == "agent_local"
    out = run(runner(None), "校园卡补办需要什么材料")
    assert out["result_status"] == "limited" and out["degraded_reason"] == "model_not_configured"
    assert out["checklist"]["service_id"] == CARD_ID


# --- tools and model transport -----------------------------------------------------------------


def test_checklist_tool_validation() -> None:
    registry = agent_registry(REPO, KnowledgeStore.load(DATA / "knowledge.json"))
    assert registry.call("make_checklist", {"service_id": "cdut:service:missing"}) == {
        "status": "empty"
    }
    with pytest.raises(ToolError):
        registry.call("make_checklist", {"service_id": "../etc"})
    result = registry.call("make_checklist", {"service_id": CARD_ID})
    items = result["items"]
    assert isinstance(items, list) and all(
        isinstance(i, dict) and i["done"] is False for i in items
    )


def test_chat_completions_complete_parses_tool_calls() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "search_place", "arguments": "{}"},
                                }
                            ],
                        },
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2},
            },
        )

    model = ChatCompletionsModel(
        "https://example.com/v1",
        "synthetic",
        "synthetic-key",
        transport=httpx.MockTransport(handler),
    )
    tools: list[dict[str, object]] = [{"type": "function", "function": {"name": "search_place"}}]
    result = asyncio.run(model.complete([{"role": "user", "content": "x"}], tools, json_mode=True))
    assert result.tool_calls[0].name == "search_place" and result.input_tokens == 5
    assert seen[0]["tools"] == tools and seen[0]["response_format"] == {"type": "json_object"}


# --- web wiring --------------------------------------------------------------------------------


def test_settings_agent_loop_flag() -> None:
    assert Settings.from_env({}).agent_loop is False
    assert Settings.from_env({"CAMPUSPILOT_AGENT_LOOP": "on"}).agent_loop is True


def web_client(model: FakeLLM, agent_loop: bool = True, daily: int = 100) -> Any:
    from campuspilot.web import create_web_app
    from fastapi.testclient import TestClient

    return TestClient(
        create_web_app(
            data_dir=DATA,
            runtime_mode="phase2",
            model=model,
            agent_loop=agent_loop,
            daily_chat_limit=daily,
        )
    )


def test_web_agent_turn_contract_and_budget() -> None:
    model = FakeLLM(understood(service="校园卡补办"), answer(GOOD_CARD, [CARD_EVIDENCE[0]]))
    with web_client(model, daily=1) as a, web_client(FakeLLM(), daily=1) as _:
        a.post("/api/session", headers=HEADERS)
        body = a.post("/api/chat", json={"message": "校园卡补办需要什么"}, headers=HEADERS).json()
        for key in ("answer", "result_status", "services", "places", "teachers", "request_id"):
            assert key in body
        assert body["notice"] and body["plan"] and body["checklist"] and body["citations"]
        limited = a.post("/api/chat", json={"message": "图书馆几点开"}, headers=HEADERS)
        assert limited.status_code == 429 and limited.json()["error_code"] == "global_limit"


def test_web_agent_blocks_sensitive_input_and_flag_off_keeps_rule_path() -> None:
    model = FakeLLM()
    with web_client(model) as client:
        client.post("/api/session", headers=HEADERS)
        out = client.post("/api/chat", json={"message": "我的密码是123456"}, headers=HEADERS)
        assert out.status_code == 200 and out.json()["result_status"] == "needs_clarification"
    assert model.calls == []
    with web_client(FakeLLM(), agent_loop=False) as client:
        client.post("/api/session", headers=HEADERS)
        body = client.post(
            "/api/chat", json={"message": "学生邮箱怎么激活"}, headers=HEADERS
        ).json()
        assert "plan" not in body and "checklist" not in body
        assert body.get("answer_mode") != "agent"


# --- real-model compatibility (DeepSeek smoke 2026-10-11) -------------------------------------


def test_truncated_output_degrades_with_reason_and_answer_budget_is_raised() -> None:
    cut = Completion(content='{"answer":"校园卡补办', finish_reason="length")
    model = FakeLLM(understood(service="校园卡补办"), cut)
    out = run(runner(model), "校园卡补办需要什么")
    assert out["degraded_reason"] == "output_truncated"
    assert model.calls[1]["max_tokens"] == ANSWER_MAX_TOKENS > 700


def test_checklist_item_keys_are_not_counted_as_citations() -> None:
    model = FakeLLM(
        understood(service="校园卡补办"), answer(GOOD_CARD, [CARD_EVIDENCE[0], "limit-3", "step-4"])
    )
    out = run(runner(model), "校园卡补办需要什么")
    assert out["result_status"] == "success" and out["source_ids"] == [CARD_EVIDENCE[0]]
    only_local = FakeLLM(understood(service="校园卡补办"), answer(GOOD_CARD, ["limit-3"]))
    assert run(runner(only_local), "校园卡补办需要什么")["degraded_reason"] == "answer_validation"


def test_identity_clarification_only_when_data_has_variants() -> None:
    agent = runner(FakeLLM(understood(missing=["identity"]), answer(GOOD_CARD, [CARD_EVIDENCE[0]])))
    out = run(agent, "校园卡补办需要什么")
    assert out["result_status"] == "success"  # one card service: asking identity is noise
    assert agent.matching_services("在读证明怎么开") == ["cdut:service:graduate-enrollment-proof"]
    vague = runner(FakeLLM(understood(missing=["需要办理的具体事项"])))
    assert run(vague, "这个怎么弄")["answer_mode"] == "agent_clarify"


def test_teacher_name_overrides_place_intent() -> None:
    model = FakeLLM(understood("找地点", destination="王洪辉老师办公室"), answer("见卡片。", []))
    out = run(runner(model), "王洪辉老师办公室在哪")
    assert out["understanding"]["intent"] == "找人"
    assert out["plan"][0] == {
        "step": 1,
        "tool": "search_teacher",
        "label": "查找老师",
        "status": "success",
    }
    assert out["teachers"] and out["teachers"][0]["name"] == "王洪辉"


def test_complete_sends_max_tokens_and_reads_finish_reason() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": "{", "reasoning_content": "思考过程"},
                    }
                ]
            },
        )

    model = ChatCompletionsModel(
        "https://example.com", "synthetic", "synthetic-key", transport=httpx.MockTransport(handler)
    )
    result = asyncio.run(model.complete([{"role": "user", "content": "x"}], max_tokens=1500))
    assert seen[0]["max_tokens"] == 1500 and result.finish_reason == "length"
    assert result.content == "{"  # reasoning_content is ignored, never surfaced


def test_business_ids_inside_id_lists_are_citable() -> None:
    # Service steps list place_ids; citing the service-area place is a valid citation.
    model = FakeLLM(
        understood(service="校园卡补办"),
        answer(GOOD_CARD, ["cdut:place:gongtong-dining", "cdut:place:finance"]),
    )
    out = run(runner(model), "校园卡补办需要什么")
    assert out["result_status"] == "success"


# --- P4: bare domains, colloquial aliases, SSE ---------------------------------------------


@pytest.mark.parametrize(
    "text", ["登录 mail.stu.cdut.edu.cn 激活", "见 www.cdut.edu.cn", "访问 Example.COM 即可"]
)
def test_bare_domains_are_blocked_like_urls(text: str) -> None:
    from campuspilot.agent.verify import unsafe_text

    assert unsafe_text(text)


def test_ordinary_text_with_dots_is_not_a_domain() -> None:
    from campuspilot.agent.verify import unsafe_text

    assert not unsafe_text("余额须大于20元。下一步：去珙桐食堂。版本2.0说明")
    assert not unsafe_text("请发邮件到 学校邮箱，或拨打028-84078750")


def test_colloquial_aliases_find_card_services() -> None:
    agent = runner(None)
    assert "cdut:service:campus-card-loss" in agent.matching_services("卡丢了咱整")
    assert agent.service_hint("丢卡补办怎么弄") == "校园卡补办"


def sse(text: str) -> list[tuple[str, Any]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_sse_streams_plan_tools_and_verified_answer() -> None:
    model = FakeLLM(understood(service="校园卡补办"), answer(GOOD_CARD, [CARD_EVIDENCE[0]]))
    with web_client(model) as client:
        client.post("/api/session", headers=HEADERS)
        r = client.post("/api/chat/stream", json={"message": "校园卡补办需要什么"}, headers=HEADERS)
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        events = sse(r.text)
    names = [e for e, _ in events]
    assert names[0] == "start" and names[1] == "understanding" and names[2] == "plan"
    assert names.index("tool_start") < names.index("tool_end") < names.index("composing")
    assert names[-1] == "final" and "answer_delta" in names
    final = events[-1][1]
    assert final["result_status"] == "success" and final["checklist"] and final["request_id"]
    assert "".join(d["text"] for e, d in events if e == "answer_delta") == final["answer"]


def test_sse_guards_match_chat() -> None:
    from campuspilot.web import create_web_app
    from fastapi.testclient import TestClient

    with TestClient(create_web_app(data_dir=DATA, runtime_mode="phase2")) as client:
        client.post("/api/session", headers=HEADERS)
        r = client.post("/api/chat/stream", json={"message": "你好"}, headers=HEADERS)
        assert r.status_code == 404 and r.json()["error_code"] == "stream_unavailable"
    spent = FakeLLM(understood("闲聊"))
    with web_client(spent, daily=1) as client:
        assert client.post("/api/chat/stream", json={"message": "x"}).status_code in {401, 403}
        client.post("/api/session", headers=HEADERS)
        client.post("/api/chat/stream", json={"message": "你好"}, headers=HEADERS)
        r = client.post("/api/chat/stream", json={"message": "图书馆"}, headers=HEADERS)
        assert r.status_code == 429 and r.json()["error_code"] == "global_limit"
    model = FakeLLM()
    with web_client(model) as client:
        client.post("/api/session", headers=HEADERS)
        r = client.post("/api/chat/stream", json={"message": "我的密码是123456"}, headers=HEADERS)
        final = sse(r.text)[-1][1]
        assert final["result_status"] == "needs_clarification" and model.calls == []


def test_v2_shell_classic_ui_and_module_assets() -> None:
    from campuspilot.web import create_web_app
    from fastapi.testclient import TestClient

    with TestClient(create_web_app(data_dir=DATA)) as client:
        shell = client.get("/").text
        assert 'type="module" src="/assets/v2/main.mjs"' in shell and 'id="map-frame"' in shell
        assert "script-src 'self';" in client.get("/").headers["content-security-policy"]
        classic = client.get("/classic")
        assert classic.status_code == 200 and "/assets/app.js" in classic.text
        assert classic.headers["cache-control"] == "no-cache"
        for name in ("main.mjs", "sse.mjs", "render.mjs", "vendor/motion-mini.mjs"):
            asset = client.get("/assets/v2/" + name)
            assert asset.status_code == 200 and "javascript" in asset.headers["content-type"]
            assert "innerHTML" not in asset.text and "eval(" not in asset.text
        assert "MIT License" in client.get("/assets/v2/vendor/MOTION-LICENSE.md").text
