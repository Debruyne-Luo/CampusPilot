"""SYNTHETIC governance, scope and evidence contracts; no real university policy fixtures."""

import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from campuspilot.agent.evidence import (
    CONTEXT_BUDGET_REASON,
    Evidence,
    bounded_knowledge_evidence,
)
from campuspilot.agent.executor import AgentRunner
from campuspilot.chat_runtime import ChatRuntime, ConversationContext, filters_for
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.knowledge import KnowledgeStore
from campuspilot.llm.chat_model import Completion, GroundedAnswer, ModelReply, ToolCall
from campuspilot.rag import (
    KnowledgeSnapshot,
    RagChunk,
    RagSource,
    RetrievalFilters,
    SnapshotStore,
    digest,
    make_snapshot,
)
from campuspilot.retrieval.applicability import query_filters, scope_notes
from campuspilot.retrieval.bm25 import BM25Retriever, eligible
from campuspilot.retrieval.context import context_complete, section_context
from campuspilot.tools.base import ToolRegistry
from campuspilot.tools.knowledge import HybridKnowledgeTool, SnapshotQuery
from pydantic import JsonValue

DATA = Path(__file__).resolve().parents[1] / "data/cdut"
TODAY = date(2026, 10, 17)
FILTERS = RetrievalFilters(today=TODAY)


def source() -> RagSource:
    return RagSource(
        source_id="SYNTHETIC-source", title="SYNTHETIC policy",
        url="https://www.cdut.edu.cn/SYNTHETIC-governance-test", publisher="SYNTHETIC issuer",
        applicability="SYNTHETIC", verification_status="official_document",
        reviewer="SYNTHETIC validator", verified_at=date(2000, 1, 1),
    )


def chunk(ident: str = "anchor", **updates: Any) -> RagChunk:
    text = ("SYNTHETIC 申请条件：材料原件。" if ident == "anchor"
            else "SYNTHETIC 例外：测试对象免交。")
    values = {
        "chunk_id": ident, "source_id": source().source_id, "topic_id": "synthetic",
        "title": "SYNTHETIC 申请条件" if ident == "anchor" else "SYNTHETIC 例外",
        "text": text, "text_sha256": digest(text.encode()), "locator": "SYNTHETIC body:chars[0:20]",
        "verification_status": "official_document", "reviewer": "SYNTHETIC validator",
        "verified_at": TODAY, "approval_id": "SYNTHETIC approval", "document_id": "synthetic",
        "revision_id": "a" * 64, "section_id": "requirements", "campuses": ("chengdu",),
    }
    values.update(updates)
    return RagChunk.model_validate(values)


def snapshot(*chunks: RagChunk) -> KnowledgeSnapshot:
    return make_snapshot((source(),), chunks or (chunk(), chunk("exception")), "0" * 64)


def store(tmp_path: Path, snap: KnowledgeSnapshot | None = None) -> SnapshotStore:
    (tmp_path / "bootstrap.json").write_text(
        (snap or snapshot()).model_dump_json(), encoding="utf-8"
    )
    return SnapshotStore(tmp_path, "lexical")


@pytest.mark.parametrize("relative", ["bootstrap.json", "approved-20261011b/snapshot.json"])
def test_v1_snapshot_keeps_original_identity(relative: str) -> None:
    path = DATA / "rag" / relative
    before = path.read_bytes()
    raw = json.loads(before)
    old = KnowledgeSnapshot.model_validate_json(before)
    rebuilt = make_snapshot(old.sources, old.chunks, old.source_package_sha256)
    assert rebuilt.version == raw["version"] and rebuilt.schema_version == 1
    assert path.read_bytes() == before


def test_v2_hash_binds_revision_structure_and_scope() -> None:
    snap = snapshot()
    assert snap.schema_version == 2
    assert KnowledgeSnapshot.model_validate_json(snap.model_dump_json()) == snap
    raw = snap.model_dump(mode="json")
    raw["chunks"][0]["campuses"] = ["yibin"]
    with pytest.raises(ValueError, match="version does not match"):
        KnowledgeSnapshot.model_validate_json(json.dumps(raw))
    raw = snap.model_dump(mode="json")
    raw["schema_version"] = 1
    with pytest.raises(ValueError, match="schema v2"):
        KnowledgeSnapshot.model_validate_json(json.dumps(raw))


def test_shared_filters_do_not_enable_history_or_override_explicit_user_scope() -> None:
    query = "宜宾校区本科2026—2027学年历史申请条件"
    direct = filters_for(query, ConversationContext(audience="graduate"))
    tool = query_filters(query, direct.today, audience="graduate", campus="chengdu")
    assert direct == tool
    assert direct.campus == "yibin" and direct.audience == "undergraduate"
    assert direct.academic_year == "2026-2027" and not direct.historical


@pytest.mark.parametrize("name", ["成都理工大学", "成都理工"])
def test_university_name_does_not_override_explicit_yibin_campus(name: str) -> None:
    filters = query_filters(name + "宜宾校区研究生申请条件", TODAY)
    assert filters.campus == "yibin" and filters.audience == "graduate"


def test_explicit_expiry_and_scope_excluded_but_old_publication_is_not_expiry() -> None:
    current = chunk(audiences=("undergraduate",))
    filters = FILTERS.model_copy(update={"audience": "undergraduate"})
    assert eligible(current, source(), filters)
    assert not eligible(current.model_copy(update={"campuses": ("yibin",)}), source(), filters)
    assert not eligible(current.model_copy(update={"audiences": ("graduate",)}), source(), filters)
    assert not eligible(current.model_copy(update={"valid_until": date(2026, 10, 16)}),
                        source(), filters)
    assert not eligible(current, source().model_copy(update={"temporal_status": "superseded"}),
                        filters)
    assert eligible(current.model_copy(update={"valid_until": TODAY}), source(), filters)
    assert eligible(current.model_copy(update={"campuses": ("unknown",)}), source(), filters)
    assert "来源适用人群尚未确认" in scope_notes(
        current.model_copy(update={"audiences": ("unknown",)}), filters
    )


def test_context_retains_exceptions_without_crossing_revision_campus_audience_or_budget() -> None:
    anchor = chunk(audiences=("undergraduate",))
    siblings = [chunk("exception", exceptions=("SYNTHETIC 例外",),
                      audiences=("undergraduate",))]
    for name, update in (
        ("revision", {"revision_id": "b" * 64}), ("campus", {"campuses": ("yibin",)}),
        ("audience", {"audiences": ("graduate",)}), ("section", {"section_id": "other"}),
        ("expired", {"valid_until": date(2020, 1, 1)}),
    ):
        siblings.append(chunk(name, **update))
    snap = snapshot(anchor, *siblings)
    hits = BM25Retriever(snap).search("申请条件 材料原件", FILTERS, 1)
    assert hits[0].chunk.chunk_id == "anchor"
    expanded = section_context(snap, hits, FILTERS)
    assert [h.chunk.chunk_id for h in expanded] == ["exception"]
    assert expanded[0].chunk.locator == siblings[0].locator
    assert section_context(snap, hits, FILTERS, max_chars=1) == ()
    assert section_context(snap, hits, FILTERS, max_chunks=0) == ()


def test_universal_rule_expands_applicable_scoped_exception(tmp_path: Path) -> None:
    snap = snapshot(chunk(campuses=("all",)),
                    chunk("graduate-exception", audiences=("graduate",)),
                    chunk("undergraduate-exception", audiences=("undergraduate",)),
                    chunk("yibin-exception", campuses=("yibin",)))
    filters = FILTERS.model_copy(update={"audience": "graduate"})
    hits = BM25Retriever(snap).search("申请条件 材料原件", filters, 1)
    expanded = section_context(snap, hits, filters)
    assert [h.chunk.chunk_id for h in expanded] == ["graduate-exception"]


def test_tool_returns_ranked_hits_and_separate_citable_context(tmp_path: Path) -> None:
    tool = HybridKnowledgeTool(store(tmp_path), None, grounding="off")
    result = tool.run(SnapshotQuery(query="申请条件 材料原件", top_k=1))
    hits, context = result["hits"], result["context"]
    assert isinstance(hits, list) and isinstance(context, list)
    assert len(hits) == 1 and len(context) == 1
    assert isinstance(context[0], dict) and context[0]["context_of"] == ["anchor"]
    assert context[0]["revision_id"] == "a" * 64


def test_agent_receives_context_and_program_preserves_applicability(tmp_path: Path) -> None:
    snap = snapshot(chunk(audiences=("undergraduate",)),
                    chunk("exception", audiences=("undergraduate",)))
    snapshots = store(tmp_path, snap)
    tool = HybridKnowledgeTool(snapshots, None, grounding="off")

    class Model:
        calls = 0
        received = ""

        async def complete(
            self, messages: list[dict[str, object]], tools: list[dict[str, object]] | None = None,
            json_mode: bool = False, max_tokens: int | None = None,
        ) -> Completion:
            self.calls += 1
            if self.calls == 1:
                body = {"intent": "政策问答", "identity": "unknown", "missing": []}
            else:
                self.received = json.dumps(messages, ensure_ascii=False)
                body = {"answer": "SYNTHETIC 材料原件。测试对象免交。",
                        "source_ids": [source().source_id], "status": "success"}
            return Completion(content=json.dumps(body, ensure_ascii=False))

    model = Model()
    repo = DirectoryRepository.load(DATA)
    agent = AgentRunner(ToolRegistry((tool,)), repo, model, grounding="off")
    response = asyncio.run(agent.run("SYNTHETIC 申请条件材料原件是什么", ConversationContext()))
    assert "测试对象免交" in model.received and "revision_id" in model.received
    assert "仅适用于本科生" in str(response["answer"])
    assert response["result_status"] == "success"
    citations = response["citations"]
    assert isinstance(citations, list) and isinstance(citations[0], dict)
    refs = citations[0]["evidence_refs"]
    assert isinstance(refs, list) and len(refs) == 2


def test_direct_summary_includes_expanded_exception(tmp_path: Path) -> None:
    snapshots = store(tmp_path)
    runtime = ChatRuntime(DirectoryRepository.load(DATA),
                          KnowledgeStore.load(DATA / "knowledge.json"), snapshots, mode="phase2")
    prepared = runtime.prepare("SYNTHETIC 申请条件材料原件", ConversationContext(), "SYNTHETIC")
    assert "测试对象免交" in str(prepared.response)
    assert "revision_id" in prepared.evidence


def test_judge_rerank_keeps_context_only_while_anchor_survives(tmp_path: Path) -> None:
    snapshots = store(tmp_path)
    tool = HybridKnowledgeTool(snapshots, None, grounding="off")
    result = tool.run(SnapshotQuery(query="申请条件 材料原件", top_k=1))
    agent = AgentRunner(ToolRegistry((tool,)), DirectoryRepository.load(DATA), None)
    ev = Evidence(results=[{"tool": "search_knowledge", "result": result}])
    agent._absorb("search_knowledge", result, ev)
    agent._apply_rerank(ev, ("anchor", "exception"))
    assert [row["chunk_id"] for row in ev.hits] == ["anchor", "exception"]
    agent._apply_rerank(ev, ())
    assert not ev.hits and not ev.allowed and not ev.citations
    empty = ev.results[0]["result"]
    assert isinstance(empty, dict) and empty["context"] == []


def test_context_dependencies_cannot_cross_heading_or_audience(tmp_path: Path) -> None:
    snap = snapshot(
        chunk(audiences=("undergraduate",), heading_path=("SYNTHETIC 本科",)),
        chunk("graduate-anchor", audiences=("graduate",),
              heading_path=("SYNTHETIC 研究生",), title="SYNTHETIC 申请条件 材料原件"),
        chunk("exception", audiences=("undergraduate",),
              heading_path=("SYNTHETIC 本科",)),
    )
    result = HybridKnowledgeTool(store(tmp_path, snap), None, grounding="off").run(
        SnapshotQuery(query="申请条件 材料原件", top_k=2)
    )
    hits, contexts = result["hits"], result["context"]
    assert isinstance(hits, list) and isinstance(contexts, list)
    # Force the actual matched anchors to make this independent of lexical score ties.
    assert {h["chunk_id"] for h in hits if isinstance(h, dict)} == {"anchor", "graduate-anchor"}
    assert len(contexts) == 1 and isinstance(contexts[0], dict)
    assert contexts[0]["context_of"] == ["anchor"]
    agent = AgentRunner(ToolRegistry(()), DirectoryRepository.load(DATA), None)
    ev = Evidence(results=[{"tool": "search_knowledge", "result": result}])
    agent._absorb("search_knowledge", result, ev)
    agent._apply_rerank(ev, ("graduate-anchor",))
    assert [row["chunk_id"] for row in ev.hits] == ["graduate-anchor"]


def test_rerank_rebuilds_source_evidence_bindings_from_retained_chunks(tmp_path: Path) -> None:
    snap = snapshot(chunk(section_id="a"), chunk("discarded", section_id="b"))
    result = HybridKnowledgeTool(store(tmp_path, snap), None, grounding="off").run(
        SnapshotQuery(query="SYNTHETIC 申请条件 测试对象", top_k=2)
    )
    agent = AgentRunner(ToolRegistry(()), DirectoryRepository.load(DATA), None)
    ev = Evidence(results=[{"tool": "search_knowledge", "result": result}])
    agent._absorb("search_knowledge", result, ev)
    agent._apply_rerank(ev, ("anchor",))
    citation = ev.citations[source().source_id]
    refs = citation["evidence_refs"]
    assert isinstance(refs, list) and len(refs) == 1 and isinstance(refs[0], dict)
    assert refs[0]["chunk_id"] == "anchor"
    assert citation["locator"] == chunk().locator


def test_agent_followup_inherits_campus_year_and_explicit_override_wins(tmp_path: Path) -> None:
    snap = snapshot(
        chunk(campuses=("yibin",), audiences=("graduate",), academic_year="2026-2027"),
        chunk("other-year", campuses=("yibin",), audiences=("graduate",),
              academic_year="2027-2028", title="SYNTHETIC 申请条件"),
        chunk("other-campus", audiences=("graduate",), academic_year="2026-2027",
              title="SYNTHETIC 申请条件"),
    )

    class RecordingTool(HybridKnowledgeTool):
        results: list[dict[str, Any]] = []

        def run(self, params: Any) -> dict[str, Any]:
            result = super().run(params)
            self.results.append(result)
            return result

    tool = RecordingTool(store(tmp_path, snap), None, grounding="off")
    agent = AgentRunner(ToolRegistry((tool,)), DirectoryRepository.load(DATA), None)
    context = ConversationContext()
    asyncio.run(agent.run("宜宾校区研究生2026-2027学年SYNTHETIC申请条件", context))
    asyncio.run(agent.run("那SYNTHETIC申请条件呢", context))
    for result in tool.results:
        assert [row["chunk_id"] for row in result["hits"]] == ["anchor"]
    assert len(tool.results) == 2 and context.campus == "yibin"
    asyncio.run(agent.run("成都校区研究生2026-2027学年SYNTHETIC申请条件", context))
    assert [row["chunk_id"] for row in tool.results[-1]["hits"]] == ["other-campus"]


def test_model_search_rewrite_cannot_change_bound_user_scope(tmp_path: Path) -> None:
    snap = snapshot(chunk(campuses=("yibin",), audiences=("graduate",),
                          academic_year="2026-2027"))
    tool = HybridKnowledgeTool(store(tmp_path, snap), None, grounding="off")
    agent = AgentRunner(ToolRegistry((tool,)), DirectoryRepository.load(DATA), None)
    ev = Evidence(retrieval_scope=FILTERS.model_copy(update={
        "campus": "yibin", "audience": "graduate", "academic_year": "2026-2027",
    }))
    asyncio.run(agent._call("search_knowledge", {
        "query": "成都本科2027-2028学年申请条件", "campus": "chengdu",
        "audience": "undergraduate", "academic_year": "2027-2028",
    }, ev))
    assert [row["chunk_id"] for row in ev.hits] == ["anchor"]
    # The pin belongs to the turn only; independent callers keep their own scope.
    assert tool.run(SnapshotQuery(query="成都本科2027-2028学年申请条件"))["hits"] == []


def test_budget_preserves_complete_search_or_withholds_every_fact() -> None:
    small: dict[str, JsonValue] = {
        "hits": [{"chunk_id": "SYNTHETIC-a", "text": "SYNTHETIC condition"}],
        "context": [{"chunk_id": "SYNTHETIC-b", "text": "SYNTHETIC exception"}],
    }
    assert bounded_knowledge_evidence(small) == small
    large: dict[str, JsonValue] = {
        **small, "context": [{"chunk_id": "SYNTHETIC-b", "text": "X" * 12000}],
    }
    withheld = bounded_knowledge_evidence(large)
    assert withheld["hits"] == [] and withheld["context"] == []
    assert withheld["reason"] == CONTEXT_BUDGET_REASON
    assert "SYNTHETIC-a" not in json.dumps(withheld)


def test_model_extra_search_receives_valid_json_or_explicit_context_budget_failure(
    tmp_path: Path,
) -> None:
    anchor = "SYNTHETIC 申请条件：" + "甲" * 6000
    exception = "SYNTHETIC 例外：" + "乙" * 6000
    snap = snapshot(
        chunk(text=anchor, text_sha256=digest(anchor.encode())),
        chunk("exception", text=exception, text_sha256=digest(exception.encode())),
    )
    tool = HybridKnowledgeTool(store(tmp_path, snap), None, grounding="off")

    class Model:
        calls = 0

        async def complete(
            self, messages: list[dict[str, object]], tools: list[dict[str, object]] | None = None,
            json_mode: bool = False, max_tokens: int | None = None,
        ) -> Completion:
            self.calls += 1
            if self.calls == 1:
                return Completion(content='{"intent":"政策问答","identity":"unknown"}')
            if self.calls == 2:
                return Completion(tool_calls=(ToolCall(
                    call_id="SYNTHETIC-extra", name="search_knowledge",
                    arguments='{"query":"申请条件","top_k":1}',
                ),))
            message = next(m for m in messages if m["role"] == "tool")
            payload = json.loads(str(message["content"]))
            assert payload["reason"] == CONTEXT_BUDGET_REASON
            assert payload["hits"] == [] and payload["context"] == []
            return Completion(content=json.dumps({
                "answer": "资料不足，无法确认完整要求。", "source_ids": [], "status": "empty",
            }, ensure_ascii=False))

    model = Model()
    agent = AgentRunner(ToolRegistry((tool,)), DirectoryRepository.load(DATA), model)
    body = asyncio.run(agent.run("完全无关", ConversationContext()))
    assert model.calls == 3 and body["degraded_reason"] == CONTEXT_BUDGET_REASON
    assert "未能核验完整要求" in str(body["answer"])
    assert body["citations"] == [] and body["excerpts"] == []


def test_section_budget_withholds_anchor_in_direct_and_tool_paths(tmp_path: Path) -> None:
    snap = snapshot(chunk(), *(chunk(f"exception-{i}") for i in range(10)))
    hits = BM25Retriever(snap).search("申请条件 材料原件", FILTERS, 1)
    expanded = section_context(snap, hits, FILTERS)
    assert len(expanded) == 8 and not context_complete(snap, hits, expanded, FILTERS)
    snapshots = store(tmp_path, snap)
    tool = HybridKnowledgeTool(snapshots, None, grounding="off")
    result = tool.run(SnapshotQuery(query="申请条件 材料原件", top_k=1))
    assert result["reason"] == CONTEXT_BUDGET_REASON and result["hits"] == []
    assert result["context"] == [] and result["context_complete"] is False
    runtime = ChatRuntime(DirectoryRepository.load(DATA),
                          KnowledgeStore.load(DATA / "knowledge.json"), snapshots, mode="phase2")
    prepared = runtime.prepare("申请条件 材料原件", ConversationContext(), "SYNTHETIC")
    assert prepared.response and prepared.response["degraded_reason"] == CONTEXT_BUDGET_REASON
    assert prepared.response["excerpts"] == [] and not prepared.model_needed


def test_service_supplement_uses_shared_scope_revision_and_complete_section(tmp_path: Path) -> None:
    snap = snapshot(
        chunk(topic_id="card", title="SYNTHETIC 校园卡补办材料", audiences=("undergraduate",)),
        chunk("exception", topic_id="card", audiences=("undergraduate",)),
    )

    class Model:
        async def generate(
            self, question: str, evidence: str, history: tuple[Any, ...],
        ) -> ModelReply:
            payload = json.loads(evidence)
            rows = payload["same_topic_supplements"]
            assert {row["chunk_id"] for row in rows} == {"anchor", "exception"}
            assert all(row["revision_id"] == "a" * 64 and row["locator"] for row in rows)
            assert "仅适用于本科生" in rows[0]["scope_notes"]
            return ModelReply(result=GroundedAnswer(
                answer=payload["directory_answer"], source_ids=(source().source_id,),
                status="success",
            ), input_tokens=0, output_tokens=0)

    runtime = ChatRuntime(DirectoryRepository.load(DATA),
                          KnowledgeStore.load(DATA / "knowledge.json"), store(tmp_path, snap),
                          mode="phase2", model=Model())
    prepared = runtime.prepare("校园卡补办费用与材料有哪些", ConversationContext(), "SYNTHETIC")
    assert prepared.route == "service" and prepared.model_needed
    response = asyncio.run(runtime.generate(prepared, ()))
    assert str(response["answer"]).startswith("适用限制：")
    assert "仅适用于本科生" in str(response["answer"])


def test_incomplete_service_supplement_keeps_structured_guide_without_unsafe_policy(
    tmp_path: Path,
) -> None:
    snap = snapshot(
        chunk(topic_id="card", title="SYNTHETIC 校园卡补办材料"),
        *(chunk(f"exception-{i}", topic_id="card") for i in range(10)),
    )
    runtime = ChatRuntime(DirectoryRepository.load(DATA),
                          KnowledgeStore.load(DATA / "knowledge.json"), store(tmp_path, snap),
                          mode="phase2")
    prepared = runtime.prepare("校园卡补办费用与材料有哪些", ConversationContext(), "SYNTHETIC")
    assert prepared.route == "service" and prepared.response and prepared.response["services"]
    assert json.loads(prepared.evidence)["same_topic_supplements"] == []
    assert source().source_id not in prepared.allowed_sources
    assert prepared.response["degraded_reason"] == CONTEXT_BUDGET_REASON
