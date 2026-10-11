"""Local no-grounding policy: refuse out-of-KB questions, never cite irrelevant chunks.

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
from campuspilot.chat_runtime import ConversationContext
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.knowledge import KnowledgeStore
from campuspilot.llm.chat_model import Completion
from campuspilot.llm.embedding import CloudflareEmbedder
from campuspilot.rag import KnowledgeSnapshot, RetrievalFilters, RetrievalHit, SnapshotStore
from campuspilot.retrieval.grounding import (
    FLOOR_SIMILARITY,
    STRONG_SIMILARITY,
    LocalGroundingPolicy,
    assess,
    is_grounded,
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


def runner(vector: list[float], model: FakeLLM | None) -> AgentRunner:
    emb = embedder(vector)
    snapshots = SnapshotStore(DATA / "rag", "hybrid", embedder=emb)
    registry = agent_registry(REPO, KnowledgeStore.load(DATA / "knowledge.json"), snapshots, emb)
    return AgentRunner(registry, REPO, model)


def run(agent: AgentRunner, question: str) -> Any:
    return asyncio.run(agent.run(question, ConversationContext()))


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


def test_search_knowledge_flags_grounding() -> None:
    registry = agent_registry(
        REPO,
        KnowledgeStore.load(DATA / "knowledge.json"),
        SnapshotStore(DATA / "rag", "hybrid", embedder=embedder(INDEX.vectors[MAIL.chunk_id])),
        embedder(INDEX.vectors[MAIL.chunk_id]),
    )
    on = registry.call("search_knowledge", {"query": "学生邮箱怎么激活"})
    assert on["grounding"]["decision"] == "grounded"
    assert on["hits"][0]["chunk_id"] == MAIL.chunk_id and on["hits"][0]["grounded"] is True
    registry = agent_registry(
        REPO,
        KnowledgeStore.load(DATA / "knowledge.json"),
        SnapshotStore(DATA / "rag", "hybrid", embedder=embedder(OFF_TOPIC)),
        embedder(OFF_TOPIC),
    )
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
