"""Official-link provenance and delivery; all constructed university fixtures are SYNTHETIC."""

import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from campuspilot.agent.executor import AgentRunner
from campuspilot.chat_runtime import ConversationContext
from campuspilot.knowledge import KnowledgeStore
from campuspilot.knowledge_release import write_candidate
from campuspilot.official_knowledge import build
from campuspilot.rag import RetrievalHit, SnapshotStore
from campuspilot.service_links import (
    ServiceLink,
    answer_service_links,
    hit_service_links,
    load_link_catalog,
    safe_service_url,
)
from campuspilot.tools import agent_registry
from campuspilot.tools.knowledge import HybridKnowledgeTool, SnapshotQuery
from test_agent_loop import DATA, HEADERS, REPO, FakeLLM, answer, understood
from test_official_knowledge import base_snapshot, capture, save

SYNTHETIC_ENTRY = "https://www.cdut.edu.cn/SYNTHETIC-application"


def prepared(tmp_path: Path) -> tuple[Path, Any, dict[str, Any]]:
    package, doc, clause = capture(tmp_path)
    doc["service_entrances"] = [{"title": "SYNTHETIC 测试条款", "url": SYNTHETIC_ENTRY}]
    save(package, [doc])
    snapshot, raw, report = build(package, base_snapshot())
    assert not report["failed"]
    candidate = tmp_path / "candidate"
    write_candidate(candidate, snapshot, raw)
    manifest = json.loads((candidate / "manifest.json").read_bytes())
    return candidate, snapshot, manifest


@pytest.mark.parametrize("url", [
    "http://www.cdut.edu.cn/", "https://cdut.edu.cn.evil.example/",
    "https://evil.example/?school=cdut.edu.cn", "javascript:alert(1)",
    "https://secret@www.cdut.edu.cn/", "https://www.cdut.edu.cn:444/",
    "https://www.cdut.edu.cn/?ticket=secret", "https://www.cdut.edu.cn/?TOKEN=secret",
    "https://www.cdut.edu.cn/a;jsessionid=secret", "https://www.cdut.edu.cn/%0aother",
    "https://www.cdut.edu.cn/?service=http%3A%2F%2Fwww.cdut.edu.cn%2Fapp",
    "https://www.cdut.edu.cn/?service=https%3A%2F%2Fevil.example%2Fapp",
    "https://www.cdut.edu.cn/?service", "https://www.cdut.edu.cn/*default/index.do",
    "https://www.cdut.edu.cn/{session}/", "https://www.cdut.edu.cn/a#secret",
    "https://www.cdut.edu.cn/?next=%2Fapply%3Ftoken%3Dsecret",
    "https://www.cdut.edu.cn/?student_id=SYNTHETIC-private",
    "https://www.cdut.edu.cn/?%2574oken=SYNTHETIC-private",
])
def test_unsafe_or_session_bound_destinations_are_rejected(url: str) -> None:
    with pytest.raises(ValueError):
        safe_service_url(url)


def test_fixed_public_ids_and_safe_school_login_return_are_allowed() -> None:
    url = "https://bsdt.cdut.edu.cn/queryResult.htm?queryCode=SYNTHETIC-catalog-id"
    assert safe_service_url(url) == url
    url = "https://cas.paas.cdut.edu.cn/cas/login?service=https%3A%2F%2Fwww.cdut.edu.cn%2F"
    assert safe_service_url(url) == url


def test_only_current_adopted_capture_supplies_links(tmp_path: Path) -> None:
    candidate, snapshot, manifest = prepared(tmp_path)
    catalog = load_link_catalog(candidate, snapshot, manifest)
    source = next(s for s in snapshot.sources if s.verification_status == "official_document")
    assert [link.kind for link in catalog[source.source_id]] == ["online", "guide"]
    assert catalog[source.source_id][0].url == SYNTHETIC_ENTRY
    assert catalog[source.source_id][0].availability == "not_checked"
    assert catalog[source.source_id][0].checked_at == date(2026, 10, 14)
    # An old destination cannot be selected from another, noncurrent capture manifest.
    names = [n for n in manifest["files_sha256"] if "/captures/" in n]
    (candidate / names[0]).write_text("{}")
    assert load_link_catalog(candidate, snapshot, manifest) == {}


def test_unadopted_documents_cannot_supply_links(tmp_path: Path) -> None:
    candidate, _, manifest = prepared(tmp_path)
    assert load_link_catalog(candidate, base_snapshot(), manifest) == {}


def test_changed_capture_does_not_restore_previous_application_url(tmp_path: Path) -> None:
    package, doc, _ = capture(tmp_path)
    doc["service_entrances"] = [{"title": "SYNTHETIC 测试条款", "url": SYNTHETIC_ENTRY}]
    save(package, [doc])
    first, raw, report = build(package, base_snapshot())
    assert not report["failed"]
    doc["service_entrances"] = [{"title": "SYNTHETIC 测试条款", "url": SYNTHETIC_ENTRY + "-new"}]
    save(package, [doc])
    second, raw, report = build(package, first, prior_raw=raw)
    assert not report["failed"]
    candidate = tmp_path / "candidate"
    write_candidate(candidate, second, raw)
    manifest = json.loads((candidate / "manifest.json").read_bytes())
    catalog = load_link_catalog(candidate, second, manifest)
    links = [link.url for values in catalog.values() for link in values]
    assert SYNTHETIC_ENTRY + "-new" in links and SYNTHETIC_ENTRY not in links


def test_legacy_source_alias_keeps_request_source_binding(tmp_path: Path) -> None:
    candidate, snapshot, manifest = prepared(tmp_path)
    source = next(s for s in snapshot.sources if s.verification_status == "official_document")
    legacy = source.model_copy(update={"source_id": "cdut:source:SYNTHETIC-legacy-alias"})
    expanded = snapshot.model_copy(update={"sources": (*snapshot.sources, legacy)})
    catalog = load_link_catalog(candidate, expanded, manifest)
    assert catalog[source.source_id][0].source_id == source.source_id
    assert catalog[legacy.source_id][0].source_id == legacy.source_id
    assert catalog[source.source_id][0].id != catalog[legacy.source_id][0].id


def test_stale_historical_and_index_hits_never_offer_current_service(tmp_path: Path) -> None:
    candidate, snapshot, manifest = prepared(tmp_path)
    catalog = load_link_catalog(candidate, snapshot, manifest)
    chunk = next(c for c in snapshot.chunks if c.verification_status == "official_document")
    source = next(s for s in snapshot.sources if s.source_id == chunk.source_id)
    hit = RetrievalHit(knowledge_version=snapshot.version, chunk=chunk, source=source, score=1)
    assert hit_service_links(hit, catalog)
    for change in ({"stale": True}, {"kind": "index_only"}, {"kind": "historical"}):
        assert not hit_service_links(hit.model_copy(update={
            "chunk": chunk.model_copy(update=change),
        }), catalog)
    assert not hit_service_links(hit.model_copy(update={
        "source": source.model_copy(update={"temporal_status": "superseded"}),
    }), catalog)


def row() -> dict[str, Any]:
    link = ServiceLink(
        id="SYNTHETIC-link", title="SYNTHETIC 网上办理", url=SYNTHETIC_ENTRY,
        kind="online", source_id="SYNTHETIC-source", source_title="SYNTHETIC 原文",
        source_url="https://www.cdut.edu.cn/SYNTHETIC-guide",
        checked_at=date(2026, 10, 14),
    )
    return {"chunk_id": "SYNTHETIC-chunk", "source_id": link.source_id,
            "url": link.source_url, "verification_status": "official_document",
            "service_links": [link.model_dump(mode="json")]}


def test_only_actual_citations_contribute_links_and_duplicates_are_removed() -> None:
    hit = row()
    assert answer_service_links([hit, hit], ("SYNTHETIC-source",), "success") == (
        hit["service_links"]
    )
    assert answer_service_links([hit], ("SYNTHETIC-chunk",), "success")
    assert not answer_service_links([hit], ("another-source",), "success")
    assert not answer_service_links([hit], (), "limited")


@pytest.mark.parametrize("change", [
    {"grounded": False}, {"web": True}, {"stale": True},
    {"verification_status": "pending"}, {"url": "https://www.cdut.edu.cn/other"},
    {"service_links": {"url": SYNTHETIC_ENTRY}},
])
def test_rejected_or_unrelated_evidence_does_not_leak_links(change: dict[str, Any]) -> None:
    assert not answer_service_links([{**row(), **change}], ("SYNTHETIC-source",), "success")


@pytest.mark.parametrize("status", ["empty", "needs_clarification", "out_of_scope", "unavailable"])
def test_refusals_and_unresolved_identity_do_not_offer_actions(status: str) -> None:
    assert not answer_service_links([row()], ("SYNTHETIC-source",), status)


def test_model_url_is_still_rejected() -> None:
    model = FakeLLM(understood(service="校园卡补办"), answer(
        "请访问https://www.cdut.edu.cn/SYNTHETIC-invented", ["SYNTHETIC-source"]
    ))
    agent = AgentRunner(agent_registry(REPO, KnowledgeStore(())), REPO, model)
    result = asyncio.run(agent.run("校园卡补办怎么办", ConversationContext()))
    assert not result["service_links"]
    assert "https://" not in str(result["answer"])


def test_literal_platform_url_stops_at_adjacent_chinese_in_an_adopted_clause() -> None:
    from campuspilot.rag import digest

    snapshot = base_snapshot()
    text = "SYNTHETIC 请登录https://www.cdut.edu.cn/SYNTHETIC-payment→学生网上缴费。"
    chunk = snapshot.chunks[0].model_copy(update={
        "text": text, "text_sha256": digest(text.encode()),
    })
    hit = RetrievalHit(knowledge_version=snapshot.version, chunk=chunk,
                       source=snapshot.sources[0], score=1)
    links = hit_service_links(hit, {})
    assert links and isinstance(links[0], dict)
    assert links[0]["url"] == "https://www.cdut.edu.cn/SYNTHETIC-payment"
    assert links[0]["requires_login"] is True


def test_actual_new_knowledge_offers_guides_without_changing_version() -> None:
    store = SnapshotStore(DATA / "rag", "lexical")
    retriever = store.acquire()
    assert retriever is not None
    version = retriever.snapshot.version
    tool = HybridKnowledgeTool(store, None, grounding="off")
    result = tool.run(SnapshotQuery(query="网络故障报修怎么办"))
    hits = result["hits"]
    assert isinstance(hits, list)
    matching = [h for h in hits if isinstance(h, dict) and "网络故障报修" in str(h["title"])]
    assert matching and matching[0]["service_links"]
    assert result["knowledge_version"] == version
    loan = tool.run(SnapshotQuery(query="生源地贷款怎么办"))
    assert "*default" not in json.dumps(loan.get("hits"), ensure_ascii=False)


@pytest.mark.parametrize("stream", [False, True])
def test_normal_and_stream_chat_deliver_same_real_guide_links(stream: bool) -> None:
    from campuspilot.web import create_web_app
    from fastapi.testclient import TestClient

    sid = "cdut:source:official:portal-1053"
    model = FakeLLM(understood("政策问答"), answer("请先登录平台，按指南提交报修申请。", [sid]))
    with TestClient(create_web_app(
        data_dir=DATA, runtime_mode="phase2", model=model, agent_loop=True,
    )) as client:
        client.post("/api/session", headers=HEADERS)
        endpoint = "/api/chat/stream" if stream else "/api/chat"
        response = client.post(endpoint, json={"message": "网络故障报修怎么办"}, headers=HEADERS)
        assert response.status_code == 200
        if stream:
            final = next(block for block in response.text.split("\n\n")
                         if block.startswith("event: final\n"))
            payload = json.loads(final.split("data: ", 1)[1])
        else:
            payload = response.json()
        assert payload["result_status"] == "success"
        assert payload["service_links"]
        assert all(link["source_id"] == sid for link in payload["service_links"])
        assert payload["service_links"][0]["kind"] == "guide"
        assert payload["service_links"][0]["availability"] == "not_checked"
