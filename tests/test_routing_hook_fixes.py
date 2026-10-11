"""rag/05: place-attribute routing, Jev on in-loop knowledge searches, no ungrounded
knowledge citations next to place evidence. Fake embedder / model / Jev only, no network."""

import json
from pathlib import Path
from typing import Any

import pytest
from campuspilot.agent.plan import asks_place_attribute, make_plan
from campuspilot.agent.understand import Slots, Understanding
from campuspilot.llm.chat_model import Completion, ToolCall
from test_grounding_refusal import INDEX, MAIL, OFF_TOPIC, FakeLLM, say
from test_grounding_refusal import run as run_turn
from test_grounding_refusal import runner as grounding_runner
from test_jev_plugin import FakeJev
from test_jev_plugin import run as run_jev
from test_jev_plugin import runner as jev_runner

PLACE = say({"intent": "找地点", "identity": "unknown", "missing": [], "destination": "图书馆"})


@pytest.mark.parametrize(
    ("question", "knowledge"),
    [
        ("图书馆几点关门", True),
        ("东区图书馆几点开门", True),
        ("食堂几点开", True),
        ("体育馆周末开放吗", True),
        ("学校快递点在哪", False),
        ("东区图书馆在哪", False),
    ],
)
def test_place_attribute_questions_also_search_knowledge(question: str, knowledge: bool) -> None:
    for intent in ("找地点", "路线"):
        view = Understanding(intent=intent, slots=Slots(destination="图书馆"))
        tools = [s.tool for s in make_plan(view, question).steps]
        assert tools[0] == "search_place"
        assert ("search_knowledge" in tools) is knowledge
        assert asks_place_attribute(question) is knowledge


def in_loop_model(cited: str) -> FakeLLM:
    """Plan is place-only; the model itself calls search_knowledge, then answers."""
    return FakeLLM(
        PLACE,
        Completion(
            tool_calls=(
                ToolCall(
                    call_id="k1", name="search_knowledge", arguments='{"query":"学生邮箱激活"}'
                ),
            )
        ),
        say({"answer": "按指南登录激活。", "source_ids": [cited], "status": "success"}),
    )


def knowledge_payload(model: FakeLLM) -> list[dict[str, Any]]:
    tool_msgs = [m for m in model.calls[-1] if m.get("role") == "tool"]
    return [json.loads(str(m["content"])) for m in tool_msgs]


def test_on_mode_drops_rank_zero_chunks_from_in_loop_search(tmp_path: Path) -> None:
    model = in_loop_model(MAIL.source_id)
    fake = FakeJev(score={MAIL.chunk_id: 2.0})
    out = run_jev(
        jev_runner(INDEX.vectors[MAIL.chunk_id], model, fake, "on", tmp_path), "学生邮箱在哪"
    )
    (payload,) = knowledge_payload(model)
    assert [h["chunk_id"] for h in payload["hits"]] == [MAIL.chunk_id]
    assert out["jev"]["phase"] == "answer" and out["jev"]["applied"] == "rerank"
    assert len(fake.calls) == 1


def test_on_mode_withholds_insufficient_in_loop_search(tmp_path: Path) -> None:
    model = in_loop_model(MAIL.source_id)
    fake = FakeJev(sufficient=0.05)
    out = run_jev(jev_runner(OFF_TOPIC, model, fake, "on", tmp_path), "学生邮箱在哪")
    (payload,) = knowledge_payload(model)
    assert payload["hits"] == [] and payload["withheld"] is True
    # The model's citation is no longer in the allowed set, so it cannot be shown.
    assert MAIL.source_id not in [c["id"] for c in out["citations"]]
    assert out["jev"]["applied"] == "withhold"


@pytest.mark.parametrize(
    "fake", [FakeJev(status="unsure", sufficient=0.05), FakeJev(delay=1.0, timeout_seconds=0.01)]
)
def test_in_loop_jev_fails_open(fake: FakeJev, tmp_path: Path) -> None:
    model = in_loop_model(MAIL.source_id)
    run_jev(jev_runner(OFF_TOPIC, model, fake, "on", tmp_path), "学生邮箱在哪")
    (payload,) = knowledge_payload(model)
    assert payload["hits"]  # unchanged


def test_shadow_in_loop_records_only(tmp_path: Path) -> None:
    model = in_loop_model(MAIL.source_id)
    fake = FakeJev(sufficient=0.05)
    out = run_jev(jev_runner(OFF_TOPIC, model, fake, "shadow", tmp_path), "学生邮箱在哪")
    (payload,) = knowledge_payload(model)
    assert payload["hits"] and out["jev"]["mode"] == "shadow" and out["jev"]["phase"] == "answer"


def place_model() -> FakeLLM:
    return FakeLLM(
        PLACE, say({"answer": "资料里没有开闭馆时间。", "source_ids": [], "status": "success"})
    )


def test_flag_place_answer_shows_no_ungrounded_knowledge_citations() -> None:
    # Plan = place + knowledge; the knowledge hits are off-topic (not grounded).
    off = run_turn(grounding_runner(OFF_TOPIC, place_model(), "off"), "东区图书馆几点关门")
    flag = run_turn(grounding_runner(OFF_TOPIC, place_model(), "flag"), "东区图书馆几点关门")
    assert off["answer"] == flag["answer"]
    assert off["excerpts"] and flag["excerpts"] == []  # off mode: previous behaviour
    knowledge_ids = {e["source_id"] for e in off["excerpts"]}
    assert knowledge_ids & {c["id"] for c in off["citations"]}
    assert not knowledge_ids & {c["id"] for c in flag["citations"]}


def test_flag_keeps_grounded_knowledge_next_to_place_evidence() -> None:
    vector = INDEX.vectors[MAIL.chunk_id]
    out = run_turn(grounding_runner(vector, place_model(), "flag"), "学生邮箱几点能激活")
    assert MAIL.chunk_id in [e["chunk_id"] for e in out["excerpts"]]


def test_on_mode_withholds_in_loop_search_when_every_chunk_is_rank_zero(tmp_path: Path) -> None:
    model = in_loop_model(MAIL.source_id)
    fake = FakeJev(sufficient=0.5, mode="clarify")  # all scores default to 0
    out = run_jev(jev_runner(OFF_TOPIC, model, fake, "on", tmp_path), "学生邮箱在哪")
    (payload,) = knowledge_payload(model)
    assert payload["hits"] == [] and out["jev"]["applied"] == "withhold"
    assert out["excerpts"] == [] and MAIL.source_id not in [c["id"] for c in out["citations"]]


def test_withheld_knowledge_keeps_list_places_citations(tmp_path: Path) -> None:
    """Root cause of empty citations for 学校快递点在哪 (on mode): the model's list_places
    call returns its evidence under "sources", which was never registered as citations;
    withholding the knowledge search then left nothing to cite."""
    model = FakeLLM(
        PLACE,
        Completion(
            tool_calls=(
                ToolCall(call_id="p", name="list_places", arguments='{"query":"图书馆"}'),
                ToolCall(call_id="k", name="search_knowledge", arguments='{"query":"图书馆"}'),
            )
        ),
        say({"answer": "资料里有图书馆地点。", "source_ids": [], "status": "success"}),
    )
    fake = FakeJev(sufficient=0.03, mode="clarify")
    out = run_jev(jev_runner(OFF_TOPIC, model, fake, "on", tmp_path), "东区图书馆在哪")
    assert out["jev"]["applied"] == "withhold"
    assert out["result_status"] != "needs_clarification" and out["answer_mode"] != "agent_jev"
    assert out["citations"] and all(c["id"] != MAIL.source_id for c in out["citations"])
    assert out["excerpts"] == []


def test_list_places_sources_become_citations(tmp_path: Path) -> None:
    from campuspilot.agent.executor import Evidence

    agent = jev_runner(OFF_TOPIC, FakeLLM(), FakeJev(), "on", tmp_path)
    ev = Evidence()
    agent._absorb(
        "list_places",
        {"places": [], "sources": [{"evidence_id": "cdut:evidence:x", "source_reference": "图"}]},
        ev,
    )
    assert ev.citations["cdut:evidence:x"]["title"] == "图"
    assert "cdut:evidence:x" not in ev.knowledge_sources
