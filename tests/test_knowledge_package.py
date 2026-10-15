"""Approved 2026-10-11 knowledge package: import rules, stale handling, teacher roster."""

import asyncio
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from campuspilot.agent.executor import STALE_NOTE_MARK, AgentRunner
from campuspilot.chat_runtime import ConversationContext
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.knowledge import KnowledgeStore
from campuspilot.knowledge_package import PHONE, _read, build
from campuspilot.rag import (
    KnowledgeSnapshot,
    RagSource,
    RetrievalFilters,
    SnapshotStore,
    make_snapshot,
)
from campuspilot.retrieval.hybrid import STALE_WEIGHT, downweight_stale
from campuspilot.tools import agent_registry
from campuspilot.tools.teachers import FindTeacherTool
from test_agent_loop import FakeLLM, answer, understood

DATA = Path(__file__).resolve().parents[1] / "data" / "cdut"
PACKAGE = DATA / "rag" / "packages" / "approved-20261011"
BUNDLE = DATA / "rag" / "approved-20261011"


def built() -> tuple[KnowledgeSnapshot, dict[str, bytes], dict[str, Any]]:
    base = KnowledgeSnapshot.model_validate_json((DATA / "rag" / "bootstrap.json").read_bytes())
    return build(PACKAGE, base, json.loads((PACKAGE / "APPROVAL.json").read_bytes()))


def test_import_is_reproducible_and_matches_committed_bundle() -> None:
    snapshot, raw, report = built()
    committed = KnowledgeSnapshot.model_validate_json((BUNDLE / "snapshot.json").read_bytes())
    assert snapshot.version == committed.version == report["version"]
    assert (report["sources"], report["chunks"], report["teachers"]) == (129, 205, 102)
    assert len(report["excluded"]) == 4 and report["conflicts"] == 35
    excluded = {e["chunk_id"] for e in report["excluded"]}
    assert not excluded & {c.chunk_id for c in snapshot.chunks}
    assert not snapshot.pending
    new = [c for c in snapshot.chunks if c.approval_id == "CDUT-KB-APPROVAL-2026-10-11-01"]
    assert len(new) == 205 and {c.reviewer for c in new} == {"宇豪罗"}
    assert json.loads(raw["APPROVAL_RECORD.json"])["reviewer"] == "宇豪罗"
    # base snapshot is carried over unchanged
    base = KnowledgeSnapshot.model_validate_json((DATA / "rag" / "bootstrap.json").read_bytes())
    assert {c.chunk_id for c in base.chunks} <= {c.chunk_id for c in snapshot.chunks}


def test_teachers_keep_public_emails_and_never_phones() -> None:
    snapshot, raw, _ = built()
    roster = json.loads(raw["package/teachers_roster.json"])
    assert roster == json.loads((DATA / "teachers_roster.json").read_bytes())
    assert "phone" not in json.dumps(roster) and all("phone" not in t for t in roster)
    personal = {t["name"]: t for t in roster if t["email"].endswith("@163.com")}
    assert "多滨" in personal and personal["多滨"]["email_source_page"].startswith("https://")
    teachers = [c for c in snapshot.chunks if c.topic_id == "teacher_lookup"]
    assert len(teachers) == 102
    for chunk in teachers:
        assert not PHONE.search(re.sub(r"https?://\S+", "", chunk.text)), chunk.chunk_id
        assert "电话" not in chunk.text


def test_package_reader_never_opens_browser_raw(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Only package"):
        _read(PACKAGE, "browser-raw/index.html")
    with pytest.raises(ValueError, match="Only package"):
        _read(PACKAGE, "README.md")


def test_stale_chunks_are_flagged_and_downweighted() -> None:
    snapshot = KnowledgeSnapshot.model_validate_json((BUNDLE / "snapshot.json").read_bytes())
    stale = {c.chunk_id for c in snapshot.chunks if c.stale}
    assert len(stale) == 63 and "cdut:chunk:cet2026h1:bs01" in stale
    store = SnapshotStore(DATA / "rag", "lexical", bundled="approved-20261011")
    retriever = store.acquire()
    assert retriever is not None
    hits = retriever.search("四六级考试报名", RetrievalFilters(today=date(2026, 10, 11)), 12)
    raw = retriever._search("四六级考试报名", RetrievalFilters(today=date(2026, 10, 11)), 12)
    by_id = {h.chunk.chunk_id: h.score for h in raw}
    for hit in hits:
        expected = by_id[hit.chunk.chunk_id] * (STALE_WEIGHT if hit.chunk.stale else 1)
        assert hit.score == pytest.approx(expected)
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)
    assert downweight_stale(()) == ()


def test_bundle_flag_validates_name_and_default_runtime_is_unchanged(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="bundled"):
        SnapshotStore(DATA / "rag", "lexical", bundled="../etc")
    # A locally published release must not affect the bootstrap fallback fixture.
    (tmp_path / "bootstrap.json").write_bytes((DATA / "rag/bootstrap.json").read_bytes())
    default = SnapshotStore(tmp_path, "lexical").acquire()
    assert default is not None and default.snapshot.version == "kb-db2f7f77dc388555"


def test_pending_sources_cannot_carry_review_and_are_never_served(tmp_path: Path) -> None:
    fields: dict[str, Any] = {
        "source_id": "cdut:source:x",
        "title": "t",
        "url": "https://www.cdut.edu.cn/x",
        "publisher": "p",
        "applicability": "a",
        "temporal_status": "current",
        "content_scope": "unknown",
    }
    with pytest.raises(ValueError, match="Pending"):
        RagSource(
            **fields, verification_status="pending", reviewer="r", verified_at=date(2026, 10, 11)
        )
    pending = RagSource(**fields, verification_status="pending", reviewer="", verified_at=None)
    snap = KnowledgeSnapshot.model_validate_json((BUNDLE / "snapshot.json").read_bytes())
    data = make_snapshot((*snap.sources, pending), snap.chunks, "0" * 64)
    assert data.pending
    (tmp_path / "bootstrap.json").write_text(data.model_dump_json())
    with pytest.raises(ValueError, match="Pending"):
        SnapshotStore(tmp_path, "lexical").acquire()


def test_find_teacher_tool_by_name_and_research_area() -> None:
    tool = FindTeacherTool.load(DATA / "teachers_roster.json")
    assert tool is not None
    hit: Any = tool.run(tool.params_model.model_validate({"query": "多滨老师邮箱"}))
    assert hit["status"] == "success" and hit["matches"][0]["email"] == "duo_bin@163.com"
    assert hit["evidence_ids"] == ["cdut:source:faculty-duobin"]
    assert tool.run(tool.params_model.model_validate({"query": "无人系统"}))["status"] == "success"
    assert tool.run(tool.params_model.model_validate({"query": "不存在的人"}))["status"] == "empty"


def bundle_runner(model: FakeLLM) -> AgentRunner:
    repo = DirectoryRepository.load(DATA)
    registry = agent_registry(
        repo,
        KnowledgeStore.load(DATA / "knowledge.json"),
        SnapshotStore(DATA / "rag", "lexical", bundled="approved-20261011"),
        roster=DATA / "teachers_roster.json",
    )
    return AgentRunner(registry, repo, model)


def test_agent_appends_stale_note_when_citing_stale_source() -> None:
    model = FakeLLM(
        understood("政策问答"),
        answer("四六级报名按学校通知在线完成。", ["cdut:source:cet2026h1"]),
    )
    out: Any = asyncio.run(bundle_runner(model).run("四六级考试怎么报名", ConversationContext()))
    assert out["result_status"] == "success", out
    assert STALE_NOTE_MARK in out["answer"]
    assert any(c.get("stale") for c in out["citations"])


def test_agent_finds_roster_teacher_with_citation() -> None:
    model = FakeLLM(
        understood("找人", destination="多滨"),
        answer("多滨老师公开邮箱见其主页。", ["cdut:source:faculty-duobin"]),
    )
    out: Any = asyncio.run(bundle_runner(model).run("多滨老师邮箱多少", ConversationContext()))
    assert [s["tool"] for s in out["plan"]] == ["search_teacher", "find_teacher"]
    assert out["result_status"] == "success", out
    assert STALE_NOTE_MARK not in out["answer"]
