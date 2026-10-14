"""Local no-grounding policy in each CAMPUSPILOT_GROUNDING mode.

block: refuse out-of-KB questions, never cite irrelevant chunks. flag (default): record the
decision only; answers, citations and summaries match off, except that an ``empty`` answer
shows no fallback citations. off: no grounding computed.

No network: query embeddings are served by an httpx MockTransport. "Off-topic" queries use a
seeded random vector (cosine to every chunk is far below the vector floor), "on-topic" ones
reuse a chunk's own indexed vector.
"""

import asyncio
import json
import random
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
from campuspilot.agent.executor import NO_BASIS_ANSWER, AgentRunner
from campuspilot.config import Settings
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.knowledge import KnowledgeStore
from campuspilot.llm.chat_model import Completion
from campuspilot.llm.embedding import CloudflareEmbedder
from campuspilot.rag import KnowledgeSnapshot, RetrievalFilters, RetrievalHit, SnapshotStore
from campuspilot.retrieval.grounding import (
    FLOOR_SIMILARITY,
    STRONG_SIMILARITY,
    GroundingMode,
    LocalGroundingPolicy,
    assess,
    is_grounded,
    parse_grounding_mode,
)
from campuspilot.retrieval.hybrid import ChannelResult
from campuspilot.retrieval.vector import INDEX_NAME, VectorIndex
from campuspilot.tools import agent_registry

DATA = Path(__file__).resolve().parents[1] / "data" / "cdut"
SNAPSHOT = KnowledgeSnapshot.model_validate_json((DATA / "rag/bootstrap.json").read_bytes())
INDEX = VectorIndex.load(DATA / "rag" / ("bootstrap." + INDEX_NAME), SNAPSHOT, "@cf/baai/bge-m3")
REPO = DirectoryRepository.load(DATA)
MAIL = next(c for c in SNAPSHOT.chunks if "邮箱" in c.title)
OFF_TOPIC = [random.Random(7).gauss(0, 1) for _ in range(INDEX.dimensions)]


def embedder(vector: list[float]) -> CloudflareEmbedder:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True, "result": {"data": [vector]}})

    return CloudflareEmbedder(
        "0123456789abcdef", "synthetic-token-never-real", transport=httpx.MockTransport(handler)
    )


class FakeLLM:
    def __init__(self, *script: Completion) -> None:
        self.script = list(script)
        self.calls: list[list[dict[str, object]]] = []

    async def complete(self, messages: Any, tools: Any = None, **_: Any) -> Completion:
        self.calls.append(messages)
        return self.script.pop(0)


def say(payload: dict[str, object]) -> Completion:
    return Completion(content=json.dumps(payload, ensure_ascii=False))


UNDERSTOOD = say({"intent": "政策问答", "identity": "unknown", "missing": []})


def runner(vector: list[float], model: Any, grounding: GroundingMode = "block") -> AgentRunner:
    emb = embedder(vector)
    snapshots = SnapshotStore(DATA / "rag", "hybrid", embedder=emb)
    registry = agent_registry(
        REPO, KnowledgeStore.load(DATA / "knowledge.json"), snapshots, emb, grounding=grounding
    )
    return AgentRunner(registry, REPO, model, grounding=grounding)


def run(agent: AgentRunner, question: str) -> Any:
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


def hit(chunk_id: str) -> RetrievalHit:
    chunk = next(c for c in SNAPSHOT.chunks if c.chunk_id == chunk_id)
    source = next(s for s in SNAPSHOT.sources if s.source_id == chunk.source_id)
    return RetrievalHit(knowledge_version=SNAPSHOT.version, chunk=chunk, source=source, score=1.0)


# --- policy -------------------------------------------------------------------------------


def test_threshold_rule() -> None:
    assert is_grounded(STRONG_SIMILARITY, None, None)
    assert is_grounded(FLOOR_SIMILARITY, 1, 3)
    assert not is_grounded(FLOOR_SIMILARITY, 1, 4)  # channels disagree
    assert not is_grounded(FLOOR_SIMILARITY - 0.01, 1, 1)  # below the floor
    assert not is_grounded(None, 1, 1)  # absent from the vector channel


def test_assess_uses_channel_rankings_and_degrades_to_unassessed() -> None:
    a, b = hit(MAIL.chunk_id), hit(SNAPSHOT.chunks[0].chunk_id)
    dense = (a.model_copy(update={"score": 0.55}), b.model_copy(update={"score": 0.50}))
    grounded = assess("学生邮箱怎么激活", ChannelResult((a, b), (a, b), dense))
    assert grounded.decision == "grounded" and grounded.grounded_ids == {a.chunk.chunk_id}
    off = assess("学生邮箱怎么激活", ChannelResult((b, a), (b,), dense[1:]))
    assert off.decision == "insufficient" and not off.grounded_ids
    lexical_only = assess("学生邮箱怎么激活", ChannelResult((a,), (a,), None))
    assert lexical_only.decision == "unassessed" and lexical_only.grounded_ids == {a.chunk.chunk_id}
    policy = LocalGroundingPolicy(ChannelResult((a,), (a,), dense))
    assert asyncio.run(policy.decide("学生邮箱怎么激活", (a,))) == "grounded"


def registry_for(vector: list[float], grounding: GroundingMode = "block") -> Any:
    return agent_registry(
        REPO,
        KnowledgeStore.load(DATA / "knowledge.json"),
        SnapshotStore(DATA / "rag", "hybrid", embedder=embedder(vector)),
        embedder(vector),
        grounding=grounding,
    )


def test_grounding_mode_config_defaults_to_flag() -> None:
    assert Settings.from_env({}).grounding == "flag"
    for mode in ("off", "flag", "block"):
        assert Settings.from_env({"CAMPUSPILOT_GROUNDING": mode}).grounding == mode
    with pytest.raises(ValueError):
        parse_grounding_mode("on")


def test_search_knowledge_tool_per_mode() -> None:
    query = {"query": "学生邮箱用户名能改吗"}
    off = registry_for(OFF_TOPIC, "off").call("search_knowledge", query)
    assert "grounding" not in off and all("grounded" not in h for h in off["hits"])
    flag = registry_for(OFF_TOPIC, "flag").call("search_knowledge", query)
    assert flag["grounding"] == {**flag["grounding"], "mode": "flag", "decision": "insufficient"}
    # flag keeps the pre-grounding answer text; only block blanks it.
    assert flag["answer"] == off["answer"] != ""


def test_search_knowledge_flags_grounding() -> None:
    registry = registry_for(INDEX.vectors[MAIL.chunk_id])
    on = registry.call("search_knowledge", {"query": "学生邮箱怎么激活"})
    assert on["grounding"]["decision"] == "grounded"
    assert on["hits"][0]["chunk_id"] == MAIL.chunk_id and on["hits"][0]["grounded"] is True
    registry = registry_for(OFF_TOPIC)
    off = registry.call("search_knowledge", {"query": "学生邮箱用户名能改吗"})
    # Lexical overlap still finds chunks, but no vector support: none is grounded.
    assert off["hits"] and off["grounding"]["decision"] == "insufficient"
    assert not any(h["grounded"] for h in off["hits"]) and off["answer"] == ""


# --- agent: out-of-KB refusal, no fallback citations ---------------------------------------


@pytest.mark.parametrize("question", ["学生邮箱用户名能改吗", "图书馆里有咖啡厅吗"])
def test_off_topic_without_model_is_honest_refusal(question: str) -> None:
    out = run(runner(OFF_TOPIC, None), question)
    assert out["answer"] == NO_BASIS_ANSWER and out["result_status"] == "empty"
    assert out["citations"] == [] and out["excerpts"] == [] and out["source_ids"] == []
    assert out["grounding"] == "insufficient"


def test_off_topic_chunks_never_reach_the_model_or_citations() -> None:
    cited = SNAPSHOT.sources[0].source_id
    model = FakeLLM(
        UNDERSTOOD,
        say({"answer": "可以改用户名。", "source_ids": [cited], "status": "success"}),
    )
    out = run(runner(OFF_TOPIC, model), "学生邮箱用户名能改吗")
    tool_payload = json.loads(str(model.calls[-1][-1]["content"]))["tool_results"]
    knowledge = [r["result"] for r in tool_payload if r["tool"] == "search_knowledge"]
    assert knowledge and all(r["hits"] == [] and r["withheld"] for r in knowledge)
    # The model's citation is not in the allowed set: verify fails, summary has no basis.
    assert out["answer"] == NO_BASIS_ANSWER and out["result_status"] == "empty"
    assert out["citations"] == [] and out["excerpts"] == []


def test_model_empty_status_shows_no_fallback_citations() -> None:
    model = FakeLLM(
        UNDERSTOOD, say({"answer": "资料里没有。", "source_ids": [], "status": "empty"})
    )
    # Even when retrieval was grounded, an "empty" answer lists no citations or excerpts.
    out = run(runner(INDEX.vectors[MAIL.chunk_id], model), "学生邮箱怎么激活")
    assert out["result_status"] == "empty" and out["answer"] == "资料里没有。"
    assert out["citations"] == [] and out["excerpts"] == []


# --- agent: answerable questions are not over-refused -------------------------------------


def test_answerable_question_keeps_grounded_summary_and_citations() -> None:
    out = run(runner(INDEX.vectors[MAIL.chunk_id], None), "学生邮箱怎么激活")
    assert out["result_status"] == "limited" and out["answer"] != NO_BASIS_ANSWER
    assert MAIL.title in out["answer"] and "grounding" not in out
    assert out["excerpts"][0]["chunk_id"] == MAIL.chunk_id
    assert MAIL.source_id in {c["id"] for c in out["citations"]}


def test_answerable_question_reaches_model_with_evidence() -> None:
    model = FakeLLM(
        UNDERSTOOD,
        say({"answer": "按指南登录激活。", "source_ids": [MAIL.source_id], "status": "success"}),
    )
    out = run(runner(INDEX.vectors[MAIL.chunk_id], model), "学生邮箱怎么激活")
    assert out["result_status"] == "success" and out["source_ids"] == [MAIL.source_id]
    assert [c["id"] for c in out["citations"]] == [MAIL.source_id]


def test_retrieval_filters_unchanged_by_channel_search() -> None:
    retriever = SnapshotStore(DATA / "rag", "lexical").acquire()
    assert retriever is not None
    filters = RetrievalFilters(today=date(2026, 10, 11))
    result = retriever.search_channels("学生邮箱激活", filters, 4)
    assert result.dense is None and result.hits == retriever.search("学生邮箱激活", filters, 4)


# --- flag / off modes: record only, answers unchanged ----------------------------------------


def comparable(out: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in out.items() if k != "grounding_check"}


@pytest.mark.parametrize("question", ["学生邮箱用户名能改吗", "图书馆里有咖啡厅吗"])
def test_flag_mode_does_not_dump_unrelated_text_after_model_failure(question: str) -> None:
    flagged = run(runner(OFF_TOPIC, None, "flag"), question)
    off = run(runner(OFF_TOPIC, None, "off"), question)
    assert comparable(flagged) == off and "grounding_check" not in off
    assert flagged["result_status"] == "empty" and flagged["answer"] == NO_BASIS_ANSWER
    assert not flagged["citations"] and not flagged["excerpts"] and "grounding" not in flagged
    check = flagged["grounding_check"]
    assert check["mode"] == "flag" and check["policy"] == "local-grounding-v1"
    assert check["would_refuse"] is True and set(check["decisions"]) == {"insufficient"}
    assert check["grounded_chunk_ids"] == []


def test_flag_mode_model_sees_pre_grounding_payload() -> None:
    cited = SNAPSHOT.sources[0].source_id

    def model() -> FakeLLM:
        return FakeLLM(
            UNDERSTOOD,
            say({"answer": "可以改用户名。", "source_ids": [cited], "status": "success"}),
        )

    flag_model, off_model = model(), model()
    flagged = run(runner(OFF_TOPIC, flag_model, "flag"), "学生邮箱用户名能改吗")
    off = run(runner(OFF_TOPIC, off_model, "off"), "学生邮箱用户名能改吗")
    assert flag_model.calls[-1] == off_model.calls[-1]
    payload = json.loads(str(flag_model.calls[-1][-1]["content"]))["tool_results"]
    knowledge = [r["result"] for r in payload if r["tool"] == "search_knowledge"]
    assert knowledge and all(r["hits"] and "grounding" not in r for r in knowledge)
    assert comparable(flagged) == off and flagged["grounding_check"]["would_refuse"]


@pytest.mark.parametrize("mode", ["off", "flag"])
def test_model_empty_status_hides_fallback_citations_in_every_mode(mode: GroundingMode) -> None:
    model = FakeLLM(
        UNDERSTOOD, say({"answer": "资料里没有。", "source_ids": [], "status": "empty"})
    )
    out = run(runner(OFF_TOPIC, model, mode), "学生邮箱用户名能改吗")
    assert out["result_status"] == "empty" and out["answer"] == "资料里没有。"
    assert out["citations"] == [] and out["excerpts"] == []


def test_grounded_fallback_shows_only_confirmed_source_titles() -> None:
    vector = INDEX.vectors[MAIL.chunk_id]
    flagged = run(runner(vector, None, "flag"), "学生邮箱怎么激活")
    assert flagged["result_status"] == "limited"
    assert MAIL.title in flagged["answer"] and MAIL.text not in flagged["answer"]
    off = run(runner(vector, None, "off"), "学生邮箱怎么激活")
    assert off["result_status"] == "empty"  # no relevance decision, no raw-text fallback
    check = flagged["grounding_check"]
    assert check["would_refuse"] is False and MAIL.chunk_id in check["grounded_chunk_ids"]


def test_block_mode_records_grounding_check() -> None:
    out = run(runner(OFF_TOPIC, None, "block"), "学生邮箱用户名能改吗")
    assert out["grounding_check"]["mode"] == "block" and out["grounding_check"]["would_refuse"]
