"""Backend migration boundaries; all upstream replies are synthetic and offline."""

import asyncio
import json
from datetime import date
from pathlib import Path

import httpx
import pytest
from campuspilot.chat_model import ChatCompletionsModel, GroundedAnswer
from campuspilot.chat_runtime import ChatRuntime, ConversationContext
from campuspilot.dify import DifyClient
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.knowledge import KnowledgeStore
from campuspilot.knowledge_release import publish, write_candidate
from campuspilot.rag import (
    KnowledgeSnapshot,
    LexicalRetriever,
    RetrievalFilters,
    SnapshotStore,
    canonical,
    make_snapshot,
)
from campuspilot.web import app_factory, create_web_app
from fastapi.testclient import TestClient

DATA = Path(__file__).resolve().parents[1] / "data/cdut"
HEADERS = {"Origin": "http://testserver", "X-CampusPilot-Request": "1"}
KEY = "synthetic-generation-key-for-offline-test-only"


def runtime(model: ChatCompletionsModel | None = None) -> ChatRuntime:
    return ChatRuntime(
        DirectoryRepository.load(DATA),
        KnowledgeStore.load(DATA / "knowledge.json"),
        SnapshotStore(DATA / "rag"),
        mode="phase2",
        model=model,
    )


def model_reply(content: dict[str, object]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content)}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
        },
    )


def test_phase2_chat_is_available_when_all_dify_requests_are_blocked() -> None:
    calls: list[str] = []

    def block_dify(request: httpx.Request) -> httpx.Response:
        pytest.fail("Phase two must not make a Dify request")

    def generate(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        body = json.loads(request.content)
        evidence = json.loads(json.loads(body["messages"][-1]["content"])["evidence"])
        return model_reply(
            {
                "answer": "SYNTHETIC grounded transport result",
                "source_ids": [evidence[0]["source_id"]],
                "status": "success",
            }
        )

    model = ChatCompletionsModel(
        "https://example.com/v1", "synthetic-model", KEY, transport=httpx.MockTransport(generate)
    )
    app = create_web_app(
        data_dir=DATA,
        runtime_mode="phase2",
        model=model,
        dify=DifyClient(KEY, transport=httpx.MockTransport(block_dify)),
    )
    with TestClient(app) as client:
        start = client.post("/api/session", headers=HEADERS)
        assert start.json()["configured"] and start.json()["runtime_mode"] == "phase2"
        direct = client.post("/api/chat", json={"message": "香樟食堂在哪"}, headers=HEADERS)
        assert direct.status_code == 200 and direct.json()["places"]
        response = client.post("/api/chat", json={"message": "学生邮箱怎么激活"}, headers=HEADERS)
        body = response.json()
        assert response.status_code == 200 and body["result_status"] == "success"
        assert body["knowledge_version"].startswith("kb-") and body["source_ids"]
        assert body["request_id"] and body["services"] == [] and body["places"] == []
    assert calls == ["https://example.com/v1/chat/completions"]


def test_phase2_factory_does_not_construct_legacy_dify(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAMPUSPILOT_RUNTIME_MODE", "phase2")
    monkeypatch.setenv("DIFY_API_KEY", KEY)
    monkeypatch.setenv("DIFY_API_BASE_URL", "http://invalid-legacy.example")
    monkeypatch.setenv("CAMPUSPILOT_DATA_DIR", str(DATA))
    for name in (
        "CAMPUSPILOT_MODEL_BASE_URL",
        "CAMPUSPILOT_MODEL",
        "CAMPUSPILOT_MODEL_KEY_FILE",
        "CAMPUSPILOT_MODEL_API_KEY",
        "CAMPUSPILOT_DIRECT_RULES_REPORT",
    ):
        monkeypatch.delenv(name, raising=False)
    with TestClient(app_factory()) as client:
        assert client.post("/api/session", headers=HEADERS).json()["configured"]


@pytest.mark.parametrize(
    "fault",
    [
        "unknown_reference",
        "no_reference",
        "coordinate",
        "short_coordinate",
        "named_coordinate",
        "url",
        "timeout",
    ],
)
def test_model_fault_keeps_local_evidence_and_never_displays_unknown_citation(fault: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if fault == "timeout":
            raise httpx.ReadTimeout(KEY)
        payload = json.loads(request.content)
        evidence = json.loads(json.loads(payload["messages"][-1]["content"])["evidence"])
        ids = [] if fault == "no_reference" else [evidence[0]["source_id"]]
        if fault == "unknown_reference":
            ids = ["SYNTHETIC_unknown_reference"]
        answer = {
            "coordinate": "SYNTHETIC 104.123456",
            "short_coordinate": "SYNTHETIC 30.1,90.2",
            "named_coordinate": "SYNTHETIC 坐标 30",
            "url": "https://example.com",
        }.get(fault, "SYNTHETIC invalid citation fixture")
        return model_reply({"answer": answer, "source_ids": ids, "status": "success"})

    model = ChatCompletionsModel(
        "https://example.com/v1", "synthetic", KEY, transport=httpx.MockTransport(handler)
    )
    with TestClient(create_web_app(data_dir=DATA, runtime_mode="phase2", model=model)) as client:
        client.post("/api/session", headers=HEADERS)
        response = client.post("/api/chat", json={"message": "学生邮箱怎么激活"}, headers=HEADERS)
        assert response.status_code == 200 and response.json()["result_status"] == "limited"
        assert response.json()["excerpts"] and "degraded_reason" in response.json()
        assert "SYNTHETIC" not in response.text and KEY not in response.text


def test_phase1_knowledge_only_uses_dify_and_local_directory_avoids_callback() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(
            200,
            json={
                "answer": "SYNTHETIC legacy phase-one result",
                "conversation_id": "00000000-0000-4000-8000-000000000001",
            },
        )

    app = create_web_app(
        data_dir=DATA,
        runtime_mode="phase1",
        dify=DifyClient(KEY, transport=httpx.MockTransport(handler)),
    )
    with TestClient(app) as client:
        client.post("/api/session", headers=HEADERS)
        teacher = DirectoryRepository.load(DATA).search_teacher()[0]
        local = client.post(
            "/api/chat", json={"message": teacher.name + "老师办公室在哪"}, headers=HEADERS
        )
        assert local.json()["teachers"] and not calls
        reply = client.post("/api/chat", json={"message": "教务处综合科负责什么"}, headers=HEADERS)
        assert reply.status_code == 200
    assert calls == ["https://api.dify.ai/v1/chat-messages"]


def test_phase1_dify_has_no_upstream_history_and_backend_context_is_bounded() -> None:
    calls: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "answer": "SYNTHETIC previous public reply",
                "conversation_id": "d37b7758-8df4-4c75-b8ac-38cfde0c4faa",
            },
        )

    with TestClient(
        create_web_app(
            data_dir=DATA,
            runtime_mode="phase1",
            dify=DifyClient(KEY, transport=httpx.MockTransport(handler)),
        )
    ) as client:
        client.post("/api/session", headers=HEADERS)
        for i in range(12):
            message = "SYNTHETIC topic" if i == 0 else f"那SYNTHETIC follow-up {i}"
            assert (
                client.post("/api/chat", json={"message": message}, headers=HEADERS).status_code
                == 200
            )
    assert len(calls) == 12 and all(c["conversation_id"] == "" for c in calls)
    assert len(json.loads(str(calls[-1]["query"]).split("\n", 1)[1])["recent_turns"]) == 16


def test_generated_replacement_answer_cannot_drop_balance_prerequisite() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        evidence = json.loads(json.loads(payload["messages"][-1]["content"])["evidence"])
        return model_reply(
            {
                "answer": "SYNTHETIC 带身份证办理。",
                "source_ids": [evidence["sources"][0]["source_id"]],
                "status": "success",
            }
        )

    model = ChatCompletionsModel(
        "https://example.com/v1", "SYNTHETIC model", KEY, transport=httpx.MockTransport(handler)
    )
    with TestClient(
        create_web_app(
            data_dir=DATA,
            runtime_mode="phase2",
            model=model,
        )
    ) as client:
        client.post("/api/session", headers=HEADERS)
        body = client.post(
            "/api/chat", json={"message": "校园卡补办费用是多少"}, headers=HEADERS
        ).json()
    assert body["result_status"] == "limited"
    assert body["degraded_reason"] == "required_premise_missing"
    assert "大于20" in body["answer"]


def test_missing_conditions_are_clarified_and_do_not_pollute_new_task() -> None:
    backend, context = runtime(), ConversationContext()
    first = backend.prepare("在读证明怎么办", context, "test-1")
    assert first.response and first.response["result_status"] == "needs_clarification"
    second = backend.prepare("我是研究生", context, "test-2")
    assert second.response and second.response["services"]
    third = backend.prepare("我是本科", context, "test-3")
    assert third.route == "rag" and third.response and not third.response["services"]
    assert all("undergraduate" in h.chunk.audiences or "all" in h.chunk.audiences
               for h in third.hits)
    backend.prepare("图书馆在哪里", context, "test-4")
    assert context.audience == "unknown" and context.history == ()


def test_context_eight_turns_and_sessions_are_isolated() -> None:
    a, b = ConversationContext(), ConversationContext()
    for i in range(12):
        a.remember(f"SYNTHETIC question {i}", f"SYNTHETIC answer {i}")
    assert len(a.history) == 16 and a.history[0].content.endswith("4") and b.history == ()
    with TestClient(create_web_app(data_dir=DATA, runtime_mode="phase2")) as client:
        client.post("/api/session", headers=HEADERS)
        client.post("/api/chat", json={"message": "研究生在读证明怎么办"}, headers=HEADERS)
        client.post("/api/session/reset", headers=HEADERS)
        response = client.post("/api/chat", json={"message": "那要准备什么"}, headers=HEADERS)
        assert not response.json()["services"]


def test_same_task_conditions_survive_rephrasing_and_explicit_year_replaces_previous() -> None:
    backend, context = runtime(), ConversationContext()
    backend.prepare("研究生2026-2027学年学杂费电子票据怎么办", context, "SYNTHETIC-1")
    context.remember("SYNTHETIC previous question", "SYNTHETIC previous answer")
    backend.prepare("票据要准备什么", context, "SYNTHETIC-2")
    assert context.audience == "graduate" and context.academic_year == "2026-2027"
    assert context.history
    changed = backend.prepare("那2025-2026学年呢", context, "SYNTHETIC-3")
    assert context.academic_year == "2025-2026" and "2026-2027" not in changed.query
    backend.prepare("学生邮箱如何激活", context, "SYNTHETIC-4")
    assert context.audience == "unknown" and context.academic_year is None
    assert context.history == ()


def test_switching_teacher_or_using_partial_name_never_borrows_previous_person() -> None:
    backend, context = runtime(), ConversationContext()
    backend.prepare("王洪辉老师办公室在哪", context, "SYNTHETIC-1")
    other = next(t.name for t in backend.repository.search_teacher() if t.name != "王洪辉")
    named = backend.prepare(f"那{other}老师办公室在哪", context, "SYNTHETIC-2")
    assert named.response
    teachers = named.response["teachers"]
    assert isinstance(teachers, list) and len(teachers) == 1
    assert isinstance(teachers[0], dict) and teachers[0]["name"] == other
    unknown = backend.prepare("那王老师呢", context, "SYNTHETIC-3")
    assert unknown.route == "unknown_teacher" and unknown.response
    assert unknown.response["teachers"] == [] and not unknown.model_needed
    completed = backend.prepare("全名王洪辉", context, "SYNTHETIC-completed")
    assert completed.route == "teacher" and completed.response
    assert completed.response["teachers"]
    backend.prepare("王洪辉老师办公室在哪", context, "SYNTHETIC-4")
    pronoun = backend.prepare("这位老师电话呢", context, "SYNTHETIC-5")
    assert pronoun.route == "teacher" and "王洪辉" in pronoun.query


def test_bank_card_followup_does_not_reuse_campus_card_procedure() -> None:
    backend, context = runtime(), ConversationContext()
    backend.prepare("校园卡补办在哪", context, "SYNTHETIC-1")
    bank = backend.prepare("那银行卡补办呢", context, "SYNTHETIC-2")
    assert bank.route == "outside_campus_card" and bank.response
    assert bank.response["services"] == [] and bank.response["places"] == []


def test_knowledge_change_invalidates_direct_rule_certificate(tmp_path: Path) -> None:
    original = KnowledgeSnapshot.model_validate_json((DATA / "rag/bootstrap.json").read_bytes())
    candidate, store = tmp_path / "a", tmp_path / "store"
    write_candidate(candidate, original)
    publish(candidate, store, None)
    backend = ChatRuntime(
        DirectoryRepository.load(DATA),
        KnowledgeStore.load(DATA / "knowledge.json"),
        SnapshotStore(store),
        mode="phase2",
        approved_direct_rules=frozenset({"service"}),
    )
    assert not backend.prepare(
        "研究生在读证明需要什么材料", ConversationContext(), "SYNTHETIC-1"
    ).model_needed
    changed = make_snapshot(original.sources, original.chunks[:-1], original.source_package_sha256)
    next_candidate = tmp_path / "b"
    write_candidate(next_candidate, changed)
    publish(next_candidate, store, original.version)
    assert backend.prepare(
        "研究生在读证明需要什么材料", ConversationContext(), "SYNTHETIC-2"
    ).model_needed


@pytest.mark.parametrize(
    "private", ["我的学号 202612345678", "密码是synthetic-secret", "我的位置104.123456,30.123456"]
)
def test_private_input_never_reaches_model_or_context(private: str) -> None:
    context = ConversationContext()
    prepared = runtime().prepare(private, context, "test-private")
    assert prepared.route == "private_input" and not prepared.model_needed
    assert context.history == () and not prepared.evidence


@pytest.mark.parametrize(
    "url",
    ["http://example.com/v1", "https://user:pass@example.com", "https://example.com?key=secret"],
)
def test_production_adapter_requires_exact_https_base(url: str) -> None:
    with pytest.raises(ValueError):
        ChatCompletionsModel(url, "synthetic", KEY)


def test_production_adapter_missing_usage_is_not_zero_cost() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": GroundedAnswer(
                                answer="SYNTHETIC", source_ids=(), status="empty"
                            ).model_dump_json(),
                        },
                    }
                ]
            },
        )

    model = ChatCompletionsModel(
        "https://example.com/v1", "synthetic", KEY, transport=httpx.MockTransport(handler)
    )
    reply = asyncio.run(model.generate("SYNTHETIC", "SYNTHETIC", ()))
    assert not reply.usage_known and KEY not in repr(model)


def test_lexical_filter_excludes_old_and_retired_current_rules() -> None:
    snapshot = KnowledgeSnapshot.model_validate_json((DATA / "rag/bootstrap.json").read_bytes())
    retriever = LexicalRetriever(snapshot)
    current = RetrievalFilters(today=date(2026, 10, 10))
    hits = retriever.search("Hillstone VPN 资源", current)
    assert all(h.source.temporal_status not in {"historical", "superseded"} for h in hits)
    history = retriever.search(
        "历史 Hillstone VPN", current.model_copy(update={"historical": True})
    )
    assert history and any(h.chunk.kind == "deprecated" for h in history)
    assert (
        retriever.search("Hillstone VPN", current.model_copy(update={"current_only": True})) == ()
    )


def test_undergraduate_filter_and_snapshot_source_integrity() -> None:
    data = json.loads((DATA / "rag/bootstrap.json").read_bytes())
    snapshot = KnowledgeSnapshot.model_validate_json(canonical(data))
    retriever = LexicalRetriever(snapshot)
    hits = retriever.search(
        "本科在读证明", RetrievalFilters(today=date(2026, 10, 10), audience="graduate")
    )
    assert all("undergraduate" not in h.chunk.audiences for h in hits)
    data["chunks"][0]["text"] += "SYNTHETIC unreviewed change"
    with pytest.raises(ValueError):
        KnowledgeSnapshot.model_validate_json(canonical(data))
