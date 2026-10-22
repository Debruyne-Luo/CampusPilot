"""Final knowledge contracts; fixtures are synthetic and never university facts."""

import json
from datetime import date
from pathlib import Path

import pytest
from campuspilot.knowledge_package import build
from campuspilot.rag import RagChunk, RagSource, RetrievalFilters, canonical, digest, make_snapshot
from campuspilot.retrieval.bm25 import BM25Retriever
from campuspilot.retrieval.vector import VectorIndex


def fixture() -> tuple[RagSource, RagChunk]:
    source = RagSource(source_id="synthetic:source", title="SYNTHETIC fixture",
                       url="https://www.cdut.edu.cn/synthetic-fixture", publisher="SYNTHETIC",
                       applicability="本科生", verification_status="official_document",
                       reviewer="test", verified_at=date(2026, 10, 21))
    chunk = RagChunk(chunk_id="synthetic:policy", source_id=source.source_id,
                     title="SYNTHETIC 测试办理", topic_id="policy", text="SYNTHETIC 测试办理",
                     text_sha256=digest("SYNTHETIC 测试办理".encode()), locator="fixture",
                     verification_status="official_document", reviewer="test",
                     verified_at=date(2026, 10, 21), approval_id="synthetic")
    return source, chunk


def test_package_preserves_explicit_scope_dates_and_stale(tmp_path: Path) -> None:
    source, chunk = fixture()
    (tmp_path / "sources.json").write_bytes(canonical([{
        **source.model_dump(mode="json"), "temporal_status": "current",
    }]))
    (tmp_path / "chunks.jsonl").write_text(json.dumps({
        **chunk.model_dump(mode="json"), "audiences": ["graduate"], "campuses": ["yibin"],
        "valid_from": "2026-08-01", "valid_until": "2026-08-30", "stale": True,
        "academic_year": "2026-2027", "conditions": ["SYNTHETIC condition"],
    }), encoding="utf-8")
    snapshot, _, _ = build(tmp_path, make_snapshot((), (), "synthetic"), {
        "approval_id": "synthetic", "reviewer": "test", "approved_at": "2026-10-21",
    })
    result = snapshot.chunks[0]
    assert result.valid_until == date(2026, 8, 30)
    assert result.valid_from == date(2026, 8, 1)
    assert result.stale and result.audiences == ("graduate",)
    assert result.campuses == ("yibin",) and result.academic_year == "2026-2027"
    assert result.conditions == ("SYNTHETIC condition",)


def test_both_retrievers_exclude_teacher_roster_before_top_k() -> None:
    source, policy = fixture()
    teacher = policy.model_copy(update={"chunk_id": "synthetic:teacher",
                                        "topic_id": "teacher_lookup"})
    snapshot = make_snapshot((source,), (teacher, policy), "synthetic")
    filters = RetrievalFilters(today=date(2026, 10, 21))
    sparse = BM25Retriever(snapshot).search("SYNTHETIC 测试办理", filters)
    dense = VectorIndex(snapshot, {c.chunk_id: [1., 0.] for c in snapshot.chunks},
                        "synthetic-model", 2).search([1., 0.], filters)
    assert [h.chunk.chunk_id for h in sparse] == [policy.chunk_id]
    assert [h.chunk.chunk_id for h in dense] == [policy.chunk_id]


def test_followup_embedding_uses_same_context_query_without_mutating_history() -> None:
    from campuspilot.chat_runtime import ChatRuntime, ConversationContext
    from campuspilot.directory.repository import DirectoryRepository
    from campuspilot.knowledge import KnowledgeStore
    from campuspilot.rag import SnapshotStore

    data = Path(__file__).resolve().parents[1] / "data/cdut"
    runtime = ChatRuntime(
        DirectoryRepository.load(data), KnowledgeStore.load(data / "knowledge.json"),
        SnapshotStore(data / "rag", "lexical"), mode="phase2",
    )
    context = ConversationContext(focus="图书馆借阅", topic="knowledge")
    resolved = runtime.embedding_question("那研究生呢", context)
    assert resolved == "图书馆借阅；那研究生呢"
    assert context.focus == "图书馆借阅" and context.audience == "unknown"
    assert runtime.prepare("那研究生呢", context, "synthetic-test").query == resolved


def test_whole_bundle_activation_requires_matching_acceptance_and_pins_directory(
    tmp_path: Path,
) -> None:
    from campuspilot.knowledge_release import publish, write_candidate
    from campuspilot.rag import SnapshotStore

    source, chunk = fixture()
    snapshot = make_snapshot((source,), (chunk,), "synthetic")
    candidate = tmp_path / "candidate"
    store = tmp_path / "active/rag"
    store.mkdir(parents=True)
    write_candidate(candidate, snapshot)
    directory = candidate / "directory"
    directory.mkdir()
    data = Path(__file__).resolve().parents[1] / "data/cdut"
    files = {}
    for name in ["services.json", "offices.json", "sources.json", "places.json", "knowledge.json"]:
        body = (data / name).read_bytes()
        (directory / name).write_bytes(body)
        files[name] = digest(body)
    manifest = json.loads((candidate / "manifest.json").read_bytes())
    manifest["files_sha256"].update({"directory/" + n: h for n, h in files.items()})
    manifest["directory_binding"] = {"path": "directory", "directory_schema_version": 2,
                                     "publication_mode": "whole_release_required",
                                     "services": 4, "files": files}
    (candidate / "manifest.json").write_bytes(canonical(manifest))
    with pytest.raises(ValueError, match="whole-package"):
        publish(candidate, store, None)
    report = tmp_path / "synthetic-acceptance.json"
    report.write_bytes(canonical({"knowledge_version": "kb-0000000000000000"}))
    with pytest.raises(ValueError, match="acceptance incomplete"):
        publish(candidate, store, None, quality_report=report)
    assert not (store / "current.json").exists()
    # This is an unmistakably synthetic report confined to pytest's temporary directory.
    report.write_bytes(canonical({"knowledge_version": snapshot.version, "suite": {"total": 120},
                                 "release_gate": {"passed": True, "blockers": [],
                                                  "holdout_total_required": 60,
                                                  "holdout_passed": 54}}))
    publish(candidate, store, None, quality_report=report)
    reader = SnapshotStore(store, "lexical")
    bound = reader.bind_directory(tmp_path / "active")
    assert bound == store / "versions" / snapshot.version / "directory"
    second = make_snapshot((source,), (chunk,), "different-synthetic-package")
    next_candidate = tmp_path / "next"
    write_candidate(next_candidate, second)
    publish(next_candidate, store, snapshot.version)
    acquired = reader.acquire()
    assert acquired is not None and acquired.snapshot.version == snapshot.version


@pytest.mark.parametrize("question", [
    "教务处的课表编排职责属于哪一科室？",
    "官方申请流程图中提交后是否还需审核？",
    "学校账号指南的密码图片和正文要求不同，应如何核对？",
    "教务通知附件日期格式异常，能按标题修改年份吗？",
])
def test_document_question_does_not_request_a_user_image(question: str) -> None:
    import asyncio

    from campuspilot.agent.executor import AgentRunner
    from campuspilot.chat_runtime import ConversationContext
    from campuspilot.directory.repository import DirectoryRepository
    from campuspilot.knowledge import KnowledgeStore
    from campuspilot.rag import SnapshotStore
    from campuspilot.tools import agent_registry
    from test_agent_loop import FakeLLM, answer, understood

    data = Path(__file__).resolve().parents[1] / "data/cdut"
    repo = DirectoryRepository.load(data)
    model = FakeLLM(understood("政策问答"), answer("暂无可确认资料。", [], "limited"))
    store = SnapshotStore(data / "rag", "lexical")
    runner = AgentRunner(agent_registry(repo, KnowledgeStore(()), store), repo, model,
                         snapshots=store, concise=True)
    result = asyncio.run(runner.run(question, ConversationContext()))
    assert model.calls and result["answer_mode"] != "agent_image"
    calls = len(model.calls)
    missing = asyncio.run(runner.run("帮我读这张课表", ConversationContext()))
    assert missing["answer_mode"] == "agent_image" and "上传" in str(missing["answer"])
    assert len(model.calls) == calls


def test_explicit_delegated_action_explains_boundary_before_identity() -> None:
    import asyncio

    from campuspilot.agent.executor import AgentRunner
    from campuspilot.chat_runtime import ConversationContext
    from campuspilot.directory.repository import DirectoryRepository
    from campuspilot.knowledge import KnowledgeStore
    from campuspilot.rag import SnapshotStore
    from campuspilot.tools import agent_registry

    data = Path(__file__).resolve().parents[1] / "data/cdut"
    repo = DirectoryRepository.load(data)
    store = SnapshotStore(data / "rag", "lexical")
    runner = AgentRunner(agent_registry(repo, KnowledgeStore(()), store), repo, None,
                         snapshots=store, concise=True)
    body = asyncio.run(runner.run("请代我提交申请并说已经办妥了。", ConversationContext()))
    assert "本人" in str(body["answer"]) and "不能" in str(body["answer"])
    assert "请问你是" not in str(body["answer"]) and "已经办妥了" not in str(body["answer"])


@pytest.mark.parametrize(("day_text", "accepted"), [
    ("2026年10月21日", True), ("2026年10月22日", False),
])
def test_answer_can_state_the_server_date_but_not_invent_another_date(
    day_text: str, accepted: bool,
) -> None:
    import asyncio

    from campuspilot.agent.evidence import Evidence
    from campuspilot.agent.executor import AgentRunner
    from campuspilot.agent.plan import Plan
    from campuspilot.agent.understand import Understanding
    from campuspilot.chat_runtime import ConversationContext
    from campuspilot.directory.repository import DirectoryRepository
    from campuspilot.knowledge import campus_clock
    from campuspilot.tools.base import ToolRegistry
    from test_agent_loop import FakeLLM, answer

    data = Path(__file__).resolve().parents[1] / "data/cdut"
    repo = DirectoryRepository.load(data)
    text = f"截至{day_text}，所给材料没有今天的开放安排。"
    model = FakeLLM(answer(text, ["synthetic:source"], "success"))
    runner = AgentRunner(ToolRegistry(()), repo, model, concise=True)
    evidence = Evidence(allowed={"synthetic:source"}, results=[{
        "tool": "search_knowledge", "result": {
            "source_id": "synthetic:source", "text": "SYNTHETIC旧版示例，未给现时开放安排。",
        },
    }])
    with campus_clock(date(2026, 10, 21)):
        body = asyncio.run(runner._compose("现在开放吗？", Understanding(intent="政策问答"),
                                          ConversationContext(), evidence, Plan(), []))
    assert (body["answer"] == text) is accepted


def test_unresolved_source_difference_cannot_be_reconciled_with_a_guarantee() -> None:
    import asyncio

    from campuspilot.agent.evidence import Evidence
    from campuspilot.agent.executor import AgentRunner
    from campuspilot.agent.plan import Plan
    from campuspilot.agent.understand import Understanding
    from campuspilot.chat_runtime import ConversationContext
    from campuspilot.directory.repository import DirectoryRepository
    from campuspilot.tools.base import ToolRegistry
    from test_agent_loop import FakeLLM

    data = Path(__file__).resolve().parents[1] / "data/cdut"
    model = FakeLLM()  # No speculative model answer is allowed before resolving this conflict.
    runner = AgentRunner(ToolRegistry(()), DirectoryRepository.load(data), model, concise=True)
    evidence = Evidence(allowed={"synthetic:source"}, hits=[{
        "source_id": "synthetic:source", "text": "SYNTHETIC原文与图片的条件表述不同，边界待确认。",
    }])
    body = asyncio.run(runner._compose(
        "这些条件不同，应如何处理？", Understanding(intent="政策问答"),
        ConversationContext(), evidence, Plan(), [],
    ))
    assert not model.calls
    assert body["degraded_reason"] == "unresolved_source_conflict"
    assert "不能" in str(body["answer"]) and "主管部门" in str(body["answer"])
    assert runner._constraint_conflict_ids("官方图中标题写法不一致怎么理解？", evidence) == ()


def test_academic_year_separator_does_not_change_supported_years() -> None:
    from campuspilot.agent.verify import unsupported_numbers

    assert not unsupported_numbers("2026—2027学年", "2026-2027学年")
    assert unsupported_numbers("2027—2028学年", "2026-2027学年")


def test_adopted_platform_can_be_its_own_source_and_skip_models(tmp_path: Path) -> None:
    import asyncio

    from campuspilot.agent.executor import AgentRunner
    from campuspilot.chat_runtime import ConversationContext
    from campuspilot.directory.repository import DirectoryRepository
    from campuspilot.knowledge import KnowledgeStore
    from campuspilot.knowledge_release import write_candidate
    from campuspilot.rag import RetrievalHit, SnapshotStore
    from campuspilot.service_links import hit_service_links
    from campuspilot.tools import agent_registry
    from test_agent_loop import FakeLLM

    source, original = fixture()
    text = f"SYNTHETIC测试平台入口为 {source.url}，用于查询公开信息。"
    chunk = original.model_copy(update={
        "title": "SYNTHETIC测试平台", "topic_id": "official_entry", "text": text,
        "text_sha256": digest(text.encode()),
    })
    snapshot = make_snapshot((source,), (chunk,), "synthetic-self-entry")
    hit = RetrievalHit(knowledge_version=snapshot.version, chunk=chunk, source=source, score=1)
    links = hit_service_links(hit, {})
    assert links and isinstance(links[0], dict) and links[0]["url"] == source.url
    # An ordinary source citation or an obsolete platform cannot become an entry button.
    for change in ({"topic_id": "policy"}, {"stale": True}, {"kind": "historical"}):
        assert not hit_service_links(hit.model_copy(update={
            "chunk": chunk.model_copy(update=change),
        }), {})

    write_candidate(tmp_path / "approved-20261021", snapshot)
    store = SnapshotStore(tmp_path, "lexical", bundled="approved-20261021")
    data = Path(__file__).resolve().parents[1] / "data/cdut"
    repo, model = DirectoryRepository.load(data), FakeLLM()
    runner = AgentRunner(agent_registry(repo, KnowledgeStore(()), store), repo, model,
                         snapshots=store, concise=True)
    body = asyncio.run(runner.run("SYNTHETIC测试平台入口在哪", ConversationContext()))
    assert not model.calls and body["answer_mode"] == "agent_entry"
    service_links = body["service_links"]
    assert isinstance(service_links, list) and isinstance(service_links[0], dict)
    assert service_links[0]["url"] == source.url
