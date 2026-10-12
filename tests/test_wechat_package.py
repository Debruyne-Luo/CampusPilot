"""WeChat package (2026-10-11b): OCR chunks, placeholder removal, example-amount guard."""

import asyncio
import json
from pathlib import Path
from typing import Any

from campuspilot.agent.executor import OCR_NOTE, AgentRunner
from campuspilot.agent.verify import ocr_example_amount
from campuspilot.chat_runtime import ConversationContext
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.knowledge import KnowledgeStore
from campuspilot.knowledge_package import build, drop_unreadable
from campuspilot.knowledge_release import read_candidate
from campuspilot.rag import KnowledgeSnapshot, SnapshotStore
from campuspilot.tools import agent_registry
from test_agent_loop import FakeLLM, answer, understood

DATA = Path(__file__).resolve().parents[1] / "data" / "cdut"
PACKAGE = DATA / "rag" / "packages" / "approved-20261011b-wechat"
BUNDLE = DATA / "rag" / "approved-20261011b"
FEE = "cdut:source:wx:fresh2026fee"


def test_wechat_import_is_reproducible_and_ocr_is_clean() -> None:
    base = read_candidate(DATA / "rag" / "approved-20261011")
    snapshot, raw, report = build(
        PACKAGE, base, json.loads((PACKAGE / "APPROVAL.json").read_bytes())
    )
    committed = KnowledgeSnapshot.model_validate_json((BUNDLE / "snapshot.json").read_bytes())
    assert snapshot.version == committed.version
    assert (report["sources"], report["chunks"], report["ocr_chunks"]) == (8, 26, 4)
    assert "package/teachers_roster.json" not in raw
    new = [c for c in snapshot.chunks if c.approval_id == "CDUT-KB-APPROVAL-2026-10-11-02"]
    assert len(new) == 26 and {c.reviewer for c in new} == {"宇豪罗"}
    assert not any("无法识别" in c.text for c in snapshot.chunks)
    assert sum(c.ocr for c in snapshot.chunks) == 4
    club = [c for c in new if "clubfair2026" in c.chunk_id]
    assert club and all(c.stale for c in club)
    assert {c.chunk_id for c in base.chunks} <= {c.chunk_id for c in snapshot.chunks}


def test_unreadable_clauses_are_dropped() -> None:
    text = (
        "开户行：建行双建路支行；账号：[无法识别]；统一社会信用代码：[无法识别]。请按页面提示缴费。"
    )
    assert drop_unreadable(text) == "开户行：建行双建路支行；请按页面提示缴费。"


def test_ocr_example_amount_guard_unit() -> None:
    assert ocr_example_amount("学费4440元", "示例：学费 4440元", "按通知缴费")
    assert not ocr_example_amount("学费4440元", "示例 4440元", "学费 4,440.00 元")
    assert not ocr_example_amount("按页面金额缴费", "示例 4440元", "")


def runner(model: FakeLLM) -> AgentRunner:
    repo = DirectoryRepository.load(DATA)
    registry = agent_registry(
        repo,
        KnowledgeStore.load(DATA / "knowledge.json"),
        SnapshotStore(DATA / "rag", "lexical", bundled="approved-20261011b"),
    )
    return AgentRunner(registry, repo, model)


def ask(model: FakeLLM, question: str) -> Any:
    return asyncio.run(runner(model).run(question, ConversationContext()))


def test_agent_refuses_ocr_example_amount_as_current_fee() -> None:
    model = FakeLLM(understood("政策问答"), answer("新生学费为4440元，在迎新系统缴纳。", [FEE]))
    out = ask(model, "迎新系统怎么缴费")
    assert out["result_status"] != "success"
    assert out.get("degraded_reason") == "ocr_example_amount" or "ocr_example_amount" in json.dumps(
        out, ensure_ascii=False
    )


def test_agent_cites_ocr_with_note_when_no_amount() -> None:
    model = FakeLLM(understood("政策问答"), answer("在迎新系统按步骤点“去缴费”完成缴费。", [FEE]))
    out = ask(model, "迎新系统怎么缴费")
    assert out["result_status"] == "success", out
    cited = [c for c in out["citations"] if c["id"] == FEE]
    assert cited and cited[0].get("note") == OCR_NOTE
