"""Optional in-process Jev plugin (CAMPUSPILOT_JEV): fake Jev client only, no network."""

import asyncio
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from campuspilot.agent.executor import NO_BASIS_ANSWER, AgentRunner
from campuspilot.config import Settings
from campuspilot.evaluation_budget import (
    BudgetExhausted,
    EvaluationBudget,
    SpendBudget,
    TokenPrice,
)
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
from campuspilot.web_evidence import TurnEvidenceContext, WebPageEvidence
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
        budget: SpendBudget,
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
    """One turn; trace records (logs only, never in the response) merged in for asserts."""
    from campuspilot.chat_runtime import ConversationContext as Context

    records: dict[str, Any] = {}
    agent.trace = lambda kind, record: records.__setitem__(kind, record)

    async def turn() -> Any:
        body = await agent.run(question, Context())
        await agent.drain()
        return body

    body = asyncio.run(turn())
    assert "grounding_check" not in body and "jev" not in body  # never sent to the frontend
    return {**body, **records}


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


def test_on_clarify_without_user_gap_reports_missing_evidence(tmp_path: Path) -> None:
    fake = FakeJev(sufficient=0.5, mode="clarify")
    model = FakeLLM(UNDERSTOOD)
    out = run(runner(OFF_TOPIC, model, fake, "on", tmp_path))
    assert out["answer"] == NO_BASIS_ANSWER and out["result_status"] == "empty"
    assert "身份" not in out["answer"] and "补充" not in out["answer"]
    assert out["citations"] == [] and out["excerpts"] == [] and out["jev"]["applied"] == "refuse"
    assert len(model.calls) == 1


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


@pytest.mark.parametrize("retrieved_at,published_at", [
    ("2026-10-15T03:28:17.829643+00:00", None),
    ("2026-10-15T11:28:17.830147+08:00", "2026-10-14T03:20:21.030902Z"),
    ("2026-10-15T03:28:17Z", "2026-10-14"),
])
def test_web_source_timestamps_do_not_look_like_personal_coordinates(
    tmp_path: Path, retrieved_at: str, published_at: str | None,
) -> None:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=jev_reply(0, 0.1))

    page = WebPageEvidence(
        "web:SYNTHETIC", "SYNTHETIC paper", "https://fixture.cdut.edu.cn/SYNTHETIC",
        "SYNTHETIC public paper on library lighting; no loan-policy evidence.",
        "official_university", retrieved_at, published_at,
    )
    context = TurnEvidenceContext(task="SYNTHETIC loan policy", web_pages=(page,),
                                  search_completed=True)
    budget = EvaluationBudget(tmp_path, "phase2")
    client = JevShadowClient("SYNTHETIC-key", TokenPrice(Decimal("0.042"), Decimal("0")),
                             transport=httpx.MockTransport(handler))
    result = asyncio.run(client.evaluate_evidence(
        "SYNTHETIC loan policy", (), public_fixture=False, budget=budget,
        online=True, evidence_context=context,
    ))
    assert result.status == "ok" and result.sufficient_probability == 0.1
    assert len(sent) == 1 and budget.report()["calls"] == 1
    # Only the privacy-check representation may change. The evidence sent is exact.
    assert sent[0]["state"]["evidence_context"] == context.as_state()


@pytest.mark.parametrize("field,private", [
    ("retrieved_at", "104.123456,30.123456"),
    ("retrieved_at", "2026-10-15T03:28:17.829643Z 我的密码是SYNTHETIC123"),
    ("retrieved_at", "2026-99-99T03:28:17.829643+00:00"),
    ("published_at", "104.123456,30.123456"),
    ("published_at", "2026-10-14T03:28:17.829643Z 104.123456,30.123456"),
    ("text", "SYNTHETIC position 104.123456,30.123456"),
    ("text", "SYNTHETIC 2026-10-15T03:28:17Z position 104.123456,30.123456"),
    ("text", "我的密码是SYNTHETIC123"),
    ("title", "SYNTHETIC position 104.123456,30.123456"),
    ("url", "https://fixture.cdut.edu.cn/SYNTHETIC?position=104.123456,30.123456"),
    ("task", "SYNTHETIC position 104.123456,30.123456"),
    ("observation", "我的密码是SYNTHETIC123"),
    ("observation", "SYNTHETIC position 104.123456,30.123456"),
    ("directory", "SYNTHETIC position 104.123456,30.123456"),
])
def test_web_metadata_exception_cannot_bypass_private_context_checks(
    tmp_path: Path, field: str, private: str,
) -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json=jev_reply(0, 0.1))

    page = WebPageEvidence(
        "web:SYNTHETIC", "SYNTHETIC paper", "https://fixture.cdut.edu.cn/SYNTHETIC",
        "SYNTHETIC public document.", "official_university", "2026-10-15T03:28:17Z",
    )
    if field not in {"task", "observation", "directory"}:
        changes: dict[str, Any] = {field: private}
        page = replace(page, **changes)
    context = TurnEvidenceContext(
        task=private if field == "task" else "SYNTHETIC loan policy", web_pages=(page,),
        user_observations=(private,) if field == "observation" else (),
        directory_facts=({"description": private},) if field == "directory" else (),
        search_completed=True,
    )
    budget = EvaluationBudget(tmp_path, "phase2")
    client = JevShadowClient("SYNTHETIC-key", TokenPrice(Decimal("0.042"), Decimal("0")),
                             transport=httpx.MockTransport(handler))
    result = asyncio.run(client.evaluate_evidence(
        "SYNTHETIC loan policy", (), public_fixture=False, budget=budget,
        online=True, evidence_context=context,
    ))
    assert result.status == "unknown" and result.reason == "private_context"
    assert sent == [] and budget.report()["calls"] == 0


def test_shadow_runs_in_background_and_does_not_delay_the_answer(tmp_path: Path) -> None:
    fake = FakeJev(delay=0.5, sufficient=0.05)
    agent = runner(OFF_TOPIC, answering_model(), fake, "shadow", tmp_path)
    records: list[tuple[str, Any]] = []
    agent.trace = lambda kind, record: records.append((kind, record))

    async def turn() -> tuple[Any, float, list[Any]]:
        from campuspilot.chat_runtime import ConversationContext as Context

        started = asyncio.get_running_loop().time()
        body = await agent.run(QUESTION, Context())
        elapsed = asyncio.get_running_loop().time() - started
        before = [k for k, _ in records if k == "jev"]
        await agent.drain()
        return body, elapsed, before

    body, elapsed, before = asyncio.run(turn())
    assert elapsed < 0.4 and before == [] and "jev" not in body
    assert [r["mode"] for k, r in records if k == "jev"] == ["shadow"]


def test_online_budget_is_separate_and_enforces_caps(tmp_path: Path) -> None:
    from campuspilot.evaluation_budget import OnlineBudget

    budget = OnlineBudget(tmp_path, Decimal("0.01"), 2, today="20261011")
    first = budget.reserve(Decimal("0.004"), "jev")
    budget.settle(first, Decimal("0.001"))
    second = budget.reserve(Decimal("0.004"), "jev")
    budget.settle(second, None)  # unknown usage stays charged at the maximum
    assert budget.report()["charged_usd"] == "0.005" and budget.report()["calls"] == 2
    with pytest.raises(BudgetExhausted):
        budget.reserve(Decimal("0.001"), "jev")  # call cap
    with pytest.raises(BudgetExhausted):
        OnlineBudget(tmp_path, Decimal("0.005"), 10, today="20261011").reserve(
            Decimal("0.001"), "jev"
        )  # dollar cap
    assert not (tmp_path / "phase2").exists()  # the $5 eval ledger is untouched
    assert (tmp_path / "online" / "budget-20261011.json").exists()
    assert OnlineBudget(tmp_path, Decimal("1"), 2, today="20261012").report()["calls"] == 0


def test_settings_online_budget_defaults() -> None:
    s = Settings.from_env({"CAMPUSPILOT_JEV_DAILY_USD": "0.5"})
    assert s.jev_daily_usd == "0.5" and s.jev_daily_calls == 2000


def test_calibration_recomputes_unsure_from_raw_answers() -> None:
    from campuspilot.jev_plugin import Calibration

    raw = {
        "mode": "generate",
        "mode_probabilities": {"direct": 0.3, "generate": 0.6, "clarify": 0.1},
        "mode_confidence": 0.6,
        "search_needed": 0.5,
        "sufficient": 0.1,
        "ranks": [{"chunk_id": "a", "score": 0.1, "confidence": 0.65, "probabilities": {}}],
    }
    unsure = result(
        status="unsure",
        answer_mode="unknown",
        chunk_scores=(("a", 0.1),),
        sufficient_probability=0.1,
        raw=raw,
    )
    assert combine(unsure, "insufficient", ("a",)).status == "unsure"  # default rule
    loose = Calibration(mode_confidence=0.5, mode_margin=0.1, rank_confidence=0.6)
    a = combine(unsure, "insufficient", ("a",), loose)
    assert a.status == "ok" and a.decision == "insufficient" and a.answer_mode == "generate"
    recorded: Any = a.record("on")["raw"]
    assert recorded["mode_confidence"] == 0.6
