"""Optional in-process Jev plugin (CAMPUSPILOT_JEV): fake Jev client only, no network."""

import asyncio
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from campuspilot.agent.executor import JEV_CLARIFY_ANSWER, NO_BASIS_ANSWER, AgentRunner
from campuspilot.config import Settings
from campuspilot.evaluation_budget import BudgetExhausted, EvaluationBudget, TokenPrice
from campuspilot.jev_plugin import (
    JevPlugin,
    JevReranker,
    JevSufficiencyPolicy,
    build_plugin,
    combine,
    parse_jev_mode,
)
from campuspilot.jev_shadow import JevShadowClient, ShadowResult
from campuspilot.knowledge import KnowledgeStore
from campuspilot.rag import RetrievalHit, SnapshotStore
from campuspilot.tools import agent_registry
from test_grounding_refusal import (
    DATA,
    INDEX,
    MAIL,
    OFF_TOPIC,
    REPO,
    SNAPSHOT,
    UNDERSTOOD,
    FakeLLM,
    embedder,
    hit,
    say,
)

ON_TOPIC = INDEX.vectors[MAIL.chunk_id]
QUESTION = "学生邮箱怎么激活"


class FakeJev:
    """Stands in for JevShadowClient. `score` maps chunk_id -> 0..2 (default 0)."""

    def __init__(
        self,
        *,
        status: str = "ok",
        sufficient: float | None = 0.9,
        mode: str = "generate",
        score: dict[str, float] | None = None,
        fault: BaseException | None = None,
        delay: float = 0.0,
        timeout_seconds: float = 3.0,
    ) -> None:
        self.status, self.sufficient, self.mode = status, sufficient, mode
        self.score = score or {}
        self.fault, self.delay = fault, delay
        self.timeout_seconds = timeout_seconds
        self.calls: list[dict[str, Any]] = []

    async def evaluate(
        self,
        question: str,
        candidates: tuple[RetrievalHit, ...],
        *,
        public_fixture: bool,
        budget: EvaluationBudget,
        rule_summary: str = "",
        online: bool = False,
    ) -> ShadowResult:
        self.calls.append({"question": question, "online": online, "fixture": public_fixture})
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fault is not None:
            raise self.fault
        ids = tuple(h.chunk.chunk_id for h in candidates)
        return ShadowResult(
            status=self.status,
            answer_mode=self.mode if self.status == "ok" else "unknown",
            selected_ids=ids[:4],
            chunk_scores=tuple((c, self.score.get(c, 0.0)) for c in ids),
            sufficient_probability=self.sufficient,
        )


def runner(
    vector: list[float], model: Any, jev: FakeJev | None, mode: str, tmp_path: Path
) -> AgentRunner:
    emb = embedder(vector)
    snapshots = SnapshotStore(DATA / "rag", "hybrid", embedder=emb)
    registry = agent_registry(REPO, KnowledgeStore.load(DATA / "knowledge.json"), snapshots, emb)
    plugin = (
        JevPlugin(jev, EvaluationBudget(tmp_path, "phase2"), mode, snapshots)  # type: ignore[arg-type]
        if jev is not None
        else None
    )
    return AgentRunner(registry, REPO, model, jev=plugin)


def run(agent: AgentRunner, question: str = QUESTION) -> Any:
    from campuspilot.chat_runtime import ConversationContext

    return asyncio.run(agent.run(question, ConversationContext()))


def without_jev(out: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in out.items() if k != "jev"}


def answering_model() -> FakeLLM:
    return FakeLLM(
        UNDERSTOOD,
        say({"answer": "按指南登录激活。", "source_ids": [MAIL.source_id], "status": "success"}),
    )


# --- config and decision logic --------------------------------------------------------------


def test_config_defaults_off_and_requires_budget_dir() -> None:
    assert Settings.from_env({}).jev == "off"
    assert Settings.from_env({"CAMPUSPILOT_JEV": "shadow"}).jev == "shadow"
    with pytest.raises(ValueError):
        parse_jev_mode("mcp")
    assert build_plugin("off", "", None) is None
    with pytest.raises(ValueError, match="BUDGET_DIR"):
        build_plugin("on", "", None)


def result(**kw: Any) -> ShadowResult:
    base: dict[str, Any] = {
        "status": "ok",
        "answer_mode": "generate",
        "chunk_scores": (("a", 0.2), ("b", 1.9), ("c", 1.1)),
        "sufficient_probability": 0.9,
    }
    return ShadowResult(**{**base, **kw})


def test_combine_drops_rank_zero_sorts_and_decides() -> None:
    a = combine(result(), "unassessed", ("a", "b", "c"))
    assert a.decision == "sufficient" and a.ranked_ids == ("b", "c") and a.dropped_ids == ("a",)
    low = result(sufficient_probability=0.1, chunk_scores=(("a", 0.1),))
    assert combine(low, "insufficient", ("a",)).decision == "insufficient"
    # Jev says insufficient but local similarity and Jev's own ranking find support: fail open.
    mixed = combine(result(sufficient_probability=0.1), "grounded", ("a", "b", "c"))
    assert mixed.decision == "unknown" and mixed.reason == "local_grounding_disagrees"
    assert combine(low, "grounded", ("a",)).decision == "insufficient"  # nothing Jev ranks
    clarify = result(sufficient_probability=0.5, answer_mode="clarify")
    assert combine(clarify, "grounded", ("a", "b")).decision == "clarify"
    assert combine(result(sufficient_probability=0.5), "x", ("a",)).decision == "unknown"
    assert combine(result(status="unsure"), "x", ("a",)).decision == "unknown"
    # Unscored (injection-filtered) candidates are never kept.
    assert combine(result(), "x", ("a", "b", "c", "z")).dropped_ids == ("a", "z")


def test_reranker_and_policy_share_one_request(tmp_path: Path) -> None:
    fake = FakeJev(score={"b": 2, "a": 1})
    plugin = JevPlugin(fake, EvaluationBudget(tmp_path, "phase2"), "on")
    turn = plugin.turn()
    a, b = hit(MAIL.chunk_id), hit(SNAPSHOT.chunks[0].chunk_id)
    hits = (a, b)
    fake.score = {b.chunk.chunk_id: 2, a.chunk.chunk_id: 1}
    ranked = asyncio.run(JevReranker(turn).rank(QUESTION, hits))
    decision = asyncio.run(JevSufficiencyPolicy(turn).decide(QUESTION, hits))
    assert ranked == (b.chunk.chunk_id, a.chunk.chunk_id) and decision == "sufficient"
    assert len(fake.calls) == 1 and fake.calls[0]["online"] and not fake.calls[0]["fixture"]


# --- agent: off / shadow / on ------------------------------------------------------------------


def test_shadow_records_but_never_changes_the_answer(tmp_path: Path) -> None:
    plain = run(runner(OFF_TOPIC, answering_model(), None, "off", tmp_path))
    fake = FakeJev(sufficient=0.05)  # would refuse
    shadow = run(runner(OFF_TOPIC, answering_model(), fake, "shadow", tmp_path))
    assert "jev" not in plain and without_jev(shadow) == plain
    record = shadow["jev"]
    assert record["mode"] == "shadow" and record["decision"] == "insufficient"
    assert record["applied"] == "none" and len(fake.calls) == 1


def test_on_reranks_and_drops_rank_zero_chunks(tmp_path: Path) -> None:
    model = answering_model()
    fake = FakeJev(score={MAIL.chunk_id: 2.0})
    out = run(runner(ON_TOPIC, model, fake, "on", tmp_path))
    assert out["jev"]["applied"] == "rerank" and out["jev"]["dropped_ids"]
    assert [e["chunk_id"] for e in out["excerpts"]] == [MAIL.chunk_id]
    payload = json.loads(str(model.calls[-1][-1]["content"]))["tool_results"]
    knowledge = [r["result"] for r in payload if r["tool"] == "search_knowledge"]
    assert [h["chunk_id"] for r in knowledge for h in r["hits"]] == [MAIL.chunk_id]
    assert out["result_status"] == "success" and out["source_ids"] == [MAIL.source_id]


def test_on_insufficient_refuses_without_citations_or_model_answer(tmp_path: Path) -> None:
    model = FakeLLM(UNDERSTOOD)  # no answer scripted: the answer step must not run
    fake = FakeJev(sufficient=0.05)
    out = run(runner(OFF_TOPIC, model, fake, "on", tmp_path), "学生邮箱用户名能改吗")
    assert out["answer"] == NO_BASIS_ANSWER and out["result_status"] == "empty"
    assert out["citations"] == [] and out["excerpts"] == [] and out["source_ids"] == []
    assert out["jev"]["applied"] == "refuse" and len(model.calls) == 1


def test_on_clarify_asks_without_citations(tmp_path: Path) -> None:
    fake = FakeJev(sufficient=0.5, mode="clarify")
    out = run(runner(OFF_TOPIC, FakeLLM(UNDERSTOOD), fake, "on", tmp_path))
    assert out["answer"] == JEV_CLARIFY_ANSWER and out["result_status"] == "needs_clarification"
    assert out["citations"] == [] and out["excerpts"] == [] and out["jev"]["applied"] == "clarify"


@pytest.mark.parametrize(
    "fake",
    [
        FakeJev(fault=httpx.ConnectError("SYNTHETIC")),
        FakeJev(fault=BudgetExhausted("stage_evaluation_budget_exhausted")),
        FakeJev(delay=1.0, timeout_seconds=0.01),
        FakeJev(status="unsure", sufficient=0.05),
        FakeJev(status="unknown", sufficient=None),
    ],
    ids=["error", "budget", "timeout", "unsure", "unknown"],
)
def test_on_fails_open_to_the_original_flow(fake: FakeJev, tmp_path: Path) -> None:
    plain = run(runner(OFF_TOPIC, answering_model(), None, "off", tmp_path))
    out = run(runner(OFF_TOPIC, answering_model(), fake, "on", tmp_path))
    assert without_jev(out) == plain and out["jev"]["decision"] == "unknown"
    assert out["jev"]["applied"] == "none"


def test_no_knowledge_hits_means_no_jev_call(tmp_path: Path) -> None:
    fake = FakeJev()
    out = run(runner(ON_TOPIC, None, fake, "on", tmp_path), "你好")
    assert not fake.calls and "jev" not in out


# --- JevShadowClient online path keeps its safeguards ------------------------------------------


def jev_reply(n: int, sufficient: float) -> dict[str, object]:
    answers: dict[str, object] = {
        "answer_mode": {
            "type": "choice",
            "choice": "generate",
            "confidence": 0.9,
            "probabilities": {"direct": 0.05, "generate": 0.9, "clarify": 0.05},
        },
        "search_needed": {"type": "noul", "noul": 0.1},
        "sufficient": {"type": "noul", "noul": sufficient},
    }
    for i in range(n):
        answers[f"rank_{i}"] = {
            "type": "score",
            "score": 2 if i == 0 else 0,
            "confidence": 1,
            "probabilities": {"0": 0, "1": 0, "2": 1} if i == 0 else {"0": 1, "1": 0, "2": 0},
        }
    return {
        "model": "typesafe/jev-1.13",
        "answers": answers,
        "usage": {"input_tokens": 9, "output_tokens": 3},
    }


def test_online_path_returns_scores_and_keeps_privacy_guard(tmp_path: Path) -> None:
    sent: list[dict[str, Any]] = []
    hits = (hit(MAIL.chunk_id), hit(SNAPSHOT.chunks[0].chunk_id))

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append(body)
        return httpx.Response(200, json=jev_reply(len(body["state"]["passages"]), 0.95))

    price = TokenPrice(Decimal("0.042"), Decimal("0"))
    client = JevShadowClient("SYNTHETIC-key", price, transport=httpx.MockTransport(handler))
    budget = EvaluationBudget(tmp_path, "phase2")
    out = asyncio.run(
        client.evaluate(
            "邮箱 a@b.cn 怎么激活", hits, public_fixture=False, budget=budget, online=True
        )
    )
    assert out.status == "ok" and out.sufficient_probability == 0.95
    assert dict(out.chunk_scores) == {MAIL.chunk_id: 2.0, SNAPSHOT.chunks[0].chunk_id: 0.0}
    assert "a@b.cn" not in json.dumps(sent, ensure_ascii=False)  # redacted
    # Private-looking input is still never sent, online or not.
    private = asyncio.run(
        client.evaluate(
            "104.123456,30.123456", hits, public_fixture=False, budget=budget, online=True
        )
    )
    assert private.status == "unknown" and len(sent) == 1
