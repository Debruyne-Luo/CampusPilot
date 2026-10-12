"""Boundary tests use explicitly synthetic documents; real inventory checks are separate."""

import importlib.util
import json
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest
from campuspilot.knowledge import KnowledgeQuery, KnowledgeRecord, KnowledgeStore
from campuspilot.web import create_web_app
from fastapi.testclient import TestClient
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/cdut"
TODAY = date(2026, 10, 8)
HEADERS = {"Origin": "http://testserver", "X-CampusPilot-Request": "1"}


def record(ident: str = "one", **changes: object) -> KnowledgeRecord:
    body: dict[str, object] = {
        "record_id": "cdut:knowledge:" + ident,
        "title": "SYNTHETIC 测试讲座 " + ident,
        "category": "event",
        "publisher": "SYNTHETIC 校园资料测试",
        "source_url": "https://www.cdut.edu.cn/synthetic-test/" + ident,
        "published_on": "2026-09-01",
        "collected_on": "2026-10-08",
        "accessed_via": "provided_document",
        "summary": "SYNTHETIC 非真实校园活动",
        "details": ["SYNTHETIC 内容，仅用于测试。"],
        "keywords": ["测试讲座"],
        "audience_text": "SYNTHETIC 测试人群",
        "locator": "SYNTHETIC 段落",
        "valid_from": "2026-09-01",
        "valid_until": "2026-10-12",
        "registration_from": "2026-09-01",
        "registration_until": "2026-10-08",
        "event_from": "2026-10-10",
        "event_until": "2026-10-10",
    }
    body.update(changes)
    return KnowledgeRecord.model_validate_json(json.dumps(body))


def test_time_filters_use_business_dates_not_collection() -> None:
    old = record(
        "old",
        valid_until="2026-09-30",
        registration_until="2026-09-29",
        event_from="2026-09-30",
        event_until="2026-09-30",
    )
    unknown = record(
        "unknown",
        valid_from=None,
        valid_until=None,
        registration_from=None,
        registration_until=None,
        event_from=None,
        event_until=None,
    )
    future = record(
        "future",
        valid_from="2026-11-01",
        valid_until="2026-11-10",
        registration_from="2026-11-01",
        registration_until="2026-11-09",
        event_from="2026-11-10",
        event_until="2026-11-10",
    )
    current = record()
    store = KnowledgeStore((old, unknown, future, current))
    for period in ("registration", "week", "current"):
        query = KnowledgeQuery.model_validate_json(json.dumps({"period": period}))
        assert store.search(query, TODAY) == (current,)
    assert store.search(KnowledgeQuery(period="history"), TODAY) == (old,)
    assert not store.search(KnowledgeQuery(period="registration"), date(2026, 10, 9))
    assert unknown.status(TODAY) == "undated"


def test_combined_week_registration_and_audience_filters() -> None:
    current = record(audiences=["graduate"])
    later = record("later", event_from="2026-10-20", event_until="2026-10-20")
    store = KnowledgeStore((current, later))
    q = store.for_chat("本周还有哪些可以报名的活动？")
    assert q is not None and store.search(q, TODAY) == (current,)
    assert not store.search(KnowledgeQuery(period="week", audience="undergraduate"), TODAY)
    assert store.search(KnowledgeQuery(period="week", audience="graduate"), TODAY) == (current,)


def test_unrelated_topic_and_wrong_year_do_not_return_generic_results() -> None:
    store = KnowledgeStore((record(),))
    assert not store.search(KnowledgeQuery(query="咖啡烘焙培训"), TODAY)
    assert not store.search(KnowledgeQuery(query="2025年的测试讲座"), TODAY)
    assert store.for_chat("王洪辉老师办公室在哪里") is None
    assert store.for_chat("校园卡丢了怎么补办") is None
    assert store.for_chat("研究生在读证明申请") is None
    query = store.for_chat("本周有哪些活动？")
    assert query and store.search(query, TODAY)


@pytest.mark.parametrize(
    "url",
    [
        "https://cdut.edu.cn.evil.example/article",
        "https://127.0.0.1/private",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "https://u:p@www.cdut.edu.cn/",
        "https://www.cdut.edu.cn:8443/",
        "http://www.cdut.edu.cn/",
    ],
)
def test_untrusted_source_urls_rejected(url: str) -> None:
    with pytest.raises(ValidationError):
        record(source_url=url)


def test_wechat_requires_publisher_attribution_and_dates_are_validated() -> None:
    with pytest.raises(ValidationError):
        record(source_kind="official_wechat", source_url="https://mp.weixin.qq.com/s/synthetic")
    adopted = record(
        source_kind="official_wechat",
        source_url="https://mp.weixin.qq.com/s/synthetic",
        publisher_evidence_url="https://www.cdut.edu.cn/synthetic-attribution",
    )
    assert adopted.adoption == "official_document"
    with pytest.raises(ValidationError):
        record(valid_until="2026-01-01")
    with pytest.raises(ValidationError):
        record(published_on="2027-01-01")


def test_superseded_records_not_recommended_and_cycles_rejected() -> None:
    old = record("old")
    new = record("new", supersedes=[old.record_id])
    store = KnowledgeStore((old, new))
    assert store.search(KnowledgeQuery(), TODAY) == (new,)
    assert store.search(KnowledgeQuery(period="history"), TODAY) == (old,)
    cycle = record("old", supersedes=[new.record_id])
    with pytest.raises(ValueError, match="Cyclic"):
        KnowledgeStore((cycle, new))


def test_real_inventory_adopts_official_sources_without_human_review_queue() -> None:
    store = KnowledgeStore.load(DATA / "knowledge.json")
    assert len(store.records) >= 6
    assert all(r.adoption == "official_document" for r in store.records)
    art = store.search(KnowledgeQuery(query="校庆"), TODAY)
    assert len(art) == 1 and art[0].status(TODAY) == "ended"
    assert not store.search(KnowledgeQuery(period="registration"), TODAY)
    assert store.search(KnowledgeQuery(query="VPN怎么用"), TODAY)


def test_browser_boundary_local_answers_followups_and_no_dify_requirement() -> None:
    with TestClient(create_web_app(data_dir=DATA)) as client:
        assert client.post("/api/knowledge/search", json={}).status_code == 403
        client.post("/api/session", headers=HEADERS)
        result = client.post("/api/knowledge/search", json={"query": "校庆"}, headers=HEADERS)
        assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
        assert result.json()["knowledge"][0]["time_status"] == "ended"
        answer = client.post("/api/chat", json={"message": "校庆活动什么时候截止"}, headers=HEADERS)
        assert answer.status_code == 200
        assert "2026-08-30" in answer.json()["answer"]
        assert answer.json()["answer_mode"] == "official_retrieval"
        follow = client.post("/api/chat", json={"message": "这条活动在哪里"}, headers=HEADERS)
        assert "东区图书馆" in follow.json()["answer"]
        client.post("/api/session/reset", headers=HEADERS)
        empty = client.post("/api/chat", json={"message": "本周有哪些活动"}, headers=HEADERS)
        assert empty.status_code == 200 and empty.json()["result_status"] == "empty"
        assert "不代表学校没有" in empty.json()["answer"]
        bad = client.post("/api/knowledge/search", json={"period": "future"}, headers=HEADERS)
        assert bad.status_code == 422


def importer() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "import_knowledge", ROOT / "scripts/import_knowledge.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_import_atomic_validation_backup_and_existing_supersession(tmp_path: Path) -> None:
    mod = importer()
    target = tmp_path / "knowledge.json"
    source = tmp_path / "incoming.json"
    old = record("old")
    target.write_text(json.dumps([old.model_dump(mode="json")]), encoding="utf-8")
    before = target.read_bytes()
    new = record("new", supersedes=[old.record_id])
    source.write_text(json.dumps([new.model_dump(mode="json")]), encoding="utf-8")
    assert mod.merge_snapshot(source, target, DATA, check_only=True) == 1
    assert target.read_bytes() == before
    assert mod.merge_snapshot(source, target, DATA, check_only=False) == 1
    assert len(KnowledgeStore.load(target).records) == 2
    assert len(list((tmp_path / ".knowledge-history").glob("*.json"))) == 1
    before = target.read_bytes()
    source.write_text('[{"source_url":"http://127.0.0.1/"}]', encoding="utf-8")
    with pytest.raises(ValidationError):
        mod.merge_snapshot(source, target, DATA, check_only=False)
    assert target.read_bytes() == before
