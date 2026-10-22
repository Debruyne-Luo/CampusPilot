"""Synthetic HTTPS transport only: real Agent/tool/provider path, no external requests."""

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from campuspilot.knowledge import campus_today
from campuspilot.knowledge_answer_eval import (
    CollectionError,
    FixtureClockRetriever,
    RequestLedger,
    collect_answers,
    load_free_config,
    load_query_vectors,
)
from campuspilot.knowledge_evaluation import EvidenceAnchor, Observation, QualityCase, fingerprint
from campuspilot.knowledge_release import write_candidate
from campuspilot.rag import RagChunk, RagSource, RetrievalFilters, digest, make_snapshot
from campuspilot.retrieval.hybrid import HybridRetriever

SECRET = "synthetic-test-token-not-a-real-secret"


def setup_fixture(tmp_path: Path, *, requests: int = 40) -> dict[str, Any]:
    workspace, external = tmp_path / "workspace", tmp_path / "external"
    workspace.mkdir()
    external.mkdir()
    config_file = external / "free-model.json"
    config_file.write_text(
        json.dumps(
            {
                "base_url": "https://synthetic.invalid/v1",
                "model": "synthetic-test-model",
                "api_key": SECRET,
                "free_only": True,
                "max_requests": requests,
                "max_output_tokens": 1000,
            }
        )
    )
    config = load_free_config(config_file, workspace)
    directory = workspace / "directory"
    directory.mkdir()
    for name in ("services", "offices", "sources"):
        (directory / (name + ".json")).write_text("[]")
    source = RagSource(
        source_id="synthetic:source",
        title="SYNTHETIC 办事规则（测试数据）",
        url="https://www.cdut.edu.cn/synthetic-test-only",
        publisher="SYNTHETIC TEST ONLY",
        applicability="synthetic test only",
        temporal_status="current",
        verification_status="official_document",
        reviewer="synthetic-test-reviewer",
        verified_at=campus_today(),
    )
    text = "SYNTHETIC 测试业务需要先取得审批，不代表任何真实学校业务。"
    chunk = RagChunk(
        chunk_id="synthetic:chunk",
        source_id=source.source_id,
        topic_id="synthetic-topic",
        title=source.title,
        text=text,
        locator="SYNTHETIC section 1",
        text_sha256=digest(text.encode()),
        verification_status="official_document",
        reviewer="synthetic-test-reviewer",
        verified_at=campus_today(),
        approval_id="synthetic-test-only",
        audiences=("all",),
    )
    snapshot = make_snapshot((source,), (chunk,), "a" * 64)
    release = workspace / "release"
    write_candidate(release, snapshot)
    anchor = EvidenceAnchor(
        evidence_id="synthetic:e1",
        source_id=source.source_id,
        source_url=source.url,
        knowledge_version=snapshot.version,
        source_revision_sha256="b" * 64,
        revision_kind="snapshot_extract",
        locator=chunk.locator,
        quote=text,
        necessary_fact="SYNTHETIC test only, approval needed",
        chunk_ids=(chunk.chunk_id,),
    )
    cases = [
        QualityCase(
            case_id=f"synthetic:q{i}",
            question=f"SYNTHETIC 测试业务{i}是否需要审批？",
            category="common",
            split="development" if i < 3 else "holdout",
            issue_group="synthetic-test-only",
            expected_behavior="answer",
            today=campus_today(),
            evidence=(anchor,),
            expected_next_step="SYNTHETIC test next step",
            messages=("我是研究生。",) if i == 1 else (),
        )
        for i in range(4)
    ]
    return {
        "workspace": workspace,
        "config_file": config_file,
        "config": config,
        "directory": directory,
        "release": release,
        "cases": cases,
        "output": workspace / "output" / "answers.jsonl",
        "snapshot": snapshot,
    }


def synthetic_transport(payloads: list[dict[str, Any]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        payloads.append(payload)
        assert request.url.host == "synthetic.invalid"
        assert request.headers["Authorization"] == "Bearer " + SECRET
        assert payload["max_tokens"] <= 1000
        system = payload["messages"][0]["content"]
        if "意图识别器" in system:
            content: dict[str, Any] = {"intent": "政策问答", "identity": "unknown", "missing": []}
        else:
            content = {
                "answer": "SYNTHETIC 测试业务需先审批。",
                "source_ids": ["synthetic:source"],
                "status": "success",
            }
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(content, ensure_ascii=False),
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 12},
            },
        )

    return httpx.MockTransport(handler)


def collect(fixture: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    return asyncio.run(
        collect_answers(
            fixture["cases"],
            config=fixture["config"],
            release=fixture["release"],
            directory=fixture["directory"],
            output=fixture["output"],
            **kwargs,
        )
    )


def test_external_config_explicit_free_only_and_no_secret_diagnostics(tmp_path: Path) -> None:
    fixture = setup_fixture(tmp_path)
    assert SECRET not in repr(fixture["config"])
    raw = json.loads(fixture["config_file"].read_bytes())
    raw["free_only"] = False
    fixture["config_file"].write_text(json.dumps(raw))
    with pytest.raises(CollectionError) as error:
        load_free_config(fixture["config_file"], fixture["workspace"])
    assert SECRET not in str(error.value)
    raw["free_only"] = True
    inside = fixture["workspace"] / "forbidden-config.json"
    inside.write_text(json.dumps(raw))
    with pytest.raises(CollectionError, match="external_free_model_config_invalid"):
        load_free_config(inside, fixture["workspace"])


def test_external_key_file_supported_and_repository_key_file_rejected(tmp_path: Path) -> None:
    fixture = setup_fixture(tmp_path)
    raw = json.loads(fixture["config_file"].read_bytes())
    raw.pop("api_key")
    raw["api_key_file"] = "key.txt"
    key = fixture["config_file"].parent / "key.txt"
    key.write_text(SECRET)
    fixture["config_file"].write_text(json.dumps(raw))
    assert load_free_config(fixture["config_file"], fixture["workspace"]).api_key == SECRET
    bad_key = fixture["workspace"] / "secret.txt"
    bad_key.write_text(SECRET)
    raw["api_key_file"] = str(bad_key)
    fixture["config_file"].write_text(json.dumps(raw))
    with pytest.raises(CollectionError):
        load_free_config(fixture["config_file"], fixture["workspace"])


def test_ledger_reserves_before_dispatch_and_never_refunds_unknown(tmp_path: Path) -> None:
    fixture = setup_fixture(tmp_path, requests=1)
    ledger = RequestLedger(fixture["config"])
    ident = ledger.reserve("synthetic-case")
    ledger.settle(ident, "unknown")
    with pytest.raises(CollectionError, match="request_budget_exhausted"):
        RequestLedger(fixture["config"]).reserve("another-case")
    assert ledger.report() == {"max_requests": 1, "reserved_requests": 1, "unknown_requests": 1}
    assert SECRET not in ledger.path.read_text(encoding="utf-8")


def test_real_agent_smoke_multiturn_resume_and_observation_binding(tmp_path: Path) -> None:
    fixture = setup_fixture(tmp_path)
    requests: list[dict[str, Any]] = []
    transport = synthetic_transport(requests)
    with pytest.raises(CollectionError, match="initial_smoke_requires_limit_2"):
        collect(fixture, transport=transport)
    report = collect(fixture, limit=2, transport=transport)
    assert report["completed_cases"] == 2
    observations = [
        Observation.model_validate_json(line)
        for line in fixture["output"].read_text(encoding="utf-8").splitlines()
    ]
    assert all(
        o.answer and o.behavior is None and o.execution_mode.startswith("real_agent")
        for o in observations
    )
    assert observations[0].case_sha256 == fingerprint(fixture["cases"][0].model_dump(mode="json"))
    details = [
        json.loads(line)
        for line in fixture["output"]
        .with_suffix(".details.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert any(
        r["tool"] == "search_knowledge" and r.get("result", {}).get("hits")
        for r in details[0]["tool_records"]
    )
    assert len(details[1]["turns"]) == 2
    assert details[1]["turns"][0]["question"] == "我是研究生。"
    assert any(any(m.get("role") == "assistant" for m in p["messages"]) for p in requests)
    count = len(requests)
    report = collect(fixture, transport=transport)
    assert report["completed_cases"] == 3
    assert report["request_budget"]["reserved_requests"] == len(requests)
    assert len(requests) > count
    count = len(requests)
    collect(fixture, transport=transport)
    assert len(requests) == count
    all_rows = [
        json.loads(line) for line in fixture["output"].read_text(encoding="utf-8").splitlines()
    ]
    assert {row["case_id"] for row in all_rows} == {"synthetic:q0", "synthetic:q1", "synthetic:q2"}
    all_details = [
        json.loads(line)
        for line in fixture["output"]
        .with_suffix(".details.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert all_details[1]["final_context"]["audience"] == "graduate"
    assert all_details[2]["final_context"]["audience"] == "unknown"
    assert SECRET not in fixture["output"].with_suffix(".details.jsonl").read_text(encoding="utf-8")
    assert all(o.case_id != "synthetic:q3" for o in observations)
    assert not (fixture["workspace"] / "current.json").exists()


def test_timeout_not_retried_and_resume_stays_blocked(tmp_path: Path) -> None:
    fixture = setup_fixture(tmp_path)
    calls = []

    def timeout(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        ledger = RequestLedger(fixture["config"])
        assert json.loads(ledger.path.read_bytes())["requests"][0]["status"] == "reserved"
        raise httpx.ReadTimeout("SYNTHETIC timeout " + SECRET)

    transport = httpx.MockTransport(timeout)
    report = collect(fixture, limit=2, transport=transport)
    assert report["status"] == "blocked" and len(calls) == 1
    assert report["request_budget"]["unknown_requests"] == 1
    report = collect(fixture, transport=transport)
    assert report["status"] == "blocked" and len(calls) == 1
    assert SECRET not in fixture["output"].with_suffix(".run.json").read_text(encoding="utf-8")


def test_timeout_cannot_be_retried_by_changing_output(tmp_path: Path) -> None:
    fixture = setup_fixture(tmp_path)
    calls = []

    def timeout(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ReadTimeout("SYNTHETIC timeout")

    transport = httpx.MockTransport(timeout)
    report = collect(fixture, limit=2, transport=transport)
    assert report["status"] == "blocked" and len(calls) == 1
    fixture["output"] = fixture["output"].with_name("new-output.jsonl")
    report = collect(fixture, limit=2, transport=transport)
    assert report["status"] == "blocked" and len(calls) == 1
    assert report["request_budget"]["reserved_requests"] == 1


def test_ledger_completed_turns_continue_but_reserved_or_unknown_case_cannot_retry(
    tmp_path: Path,
) -> None:
    fixture = setup_fixture(tmp_path)
    ledger = RequestLedger(fixture["config"])
    first = ledger.reserve("SYNTHETIC-case")
    with pytest.raises(CollectionError, match="case_request_outcome_unknown_no_automatic_retry"):
        ledger.reserve("SYNTHETIC-case")
    ledger.settle(first, "completed")
    second = ledger.reserve("SYNTHETIC-case")
    ledger.settle(second, "unknown")
    with pytest.raises(CollectionError, match="case_request_outcome_unknown_no_automatic_retry"):
        ledger.reserve("SYNTHETIC-case")
    assert ledger.report()["reserved_requests"] == 2


def test_hard_call_cap_includes_multiple_agent_calls(tmp_path: Path) -> None:
    fixture = setup_fixture(tmp_path, requests=1)
    requests: list[dict[str, Any]] = []
    report = collect(fixture, limit=2, transport=synthetic_transport(requests))
    assert len(requests) == 1
    assert report["status"] == "blocked"
    assert report["request_budget"]["reserved_requests"] == 1


def test_interrupted_case_not_redispatched_and_binding_change_rejected(tmp_path: Path) -> None:
    fixture = setup_fixture(tmp_path)
    requests: list[dict[str, Any]] = []
    transport = synthetic_transport(requests)
    collect(fixture, limit=2, transport=transport)
    state_path = fixture["output"].with_suffix(".run.json")
    state = json.loads(state_path.read_bytes())
    state["cases"]["synthetic:q2"] = "running"
    state_path.write_text(json.dumps(state))
    count = len(requests)
    report = collect(fixture, transport=transport)
    assert report["status"] == "blocked" and len(requests) == count
    fixture["cases"][0] = fixture["cases"][0].model_copy(update={"question": "SYNTHETIC changed"})
    with pytest.raises(CollectionError, match="resume_binding_mismatch"):
        collect(fixture, transport=transport)


def test_frozen_day_reaches_agent_tools_after_runtime_date_changes(tmp_path: Path) -> None:
    from datetime import date

    fixture = setup_fixture(tmp_path)
    frozen = date(2001, 2, 3)
    fixture["cases"] = [case.model_copy(update={"today": frozen}) for case in fixture["cases"]]
    actual = campus_today()
    requests: list[dict[str, Any]] = []
    report = collect(fixture, limit=2, transport=synthetic_transport(requests))
    assert report["completed_cases"] == 2 and requests
    details = [
        json.loads(line)
        for line in fixture["output"].with_suffix(".details.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    records = [record for item in details for record in item["retrieval_records"]]
    assert records and all(record["filters"]["today"] == frozen.isoformat() for record in records)
    assert campus_today() == actual


def test_local_query_cache_and_clock_do_not_override_scope(tmp_path: Path) -> None:
    fixture = setup_fixture(tmp_path)
    cache = tmp_path / "cache.json"
    cache.write_text(
        json.dumps(
            {
                "model": "synthetic-embedding",
                "dimensions": 2,
                "queries": {"SYNTHETIC query": [1, 0]},
            }
        )
    )
    loaded = load_query_vectors(cache)
    assert loaded is not None and loaded.cached("SYNTHETIC query") == [1.0, 0.0]
    assert loaded.cached("uncached") is None
    retriever = FixtureClockRetriever(
        HybridRetriever(fixture["snapshot"], mode="lexical"), fixture["cases"][0]
    )
    retriever.search(
        "SYNTHETIC",
        RetrievalFilters(
            today=campus_today(), campus="yibin", audience="graduate", academic_year="2026-2027"
        ),
    )
    assert retriever.records[0]["filters"]["campus"] == "yibin"
    assert retriever.records[0]["filters"]["audience"] == "graduate"
    assert retriever.records[0]["filters"]["academic_year"] == "2026-2027"


def test_cache_without_matching_index_records_lexical_fallback(tmp_path: Path) -> None:
    fixture = setup_fixture(tmp_path)
    cache = tmp_path / "queries.json"
    cache.write_text(json.dumps({"model": "synthetic-embedding", "dimensions": 2, "queries": {}}))
    calls: list[dict[str, Any]] = []
    report = collect(fixture, limit=2, query_vectors=cache, transport=synthetic_transport(calls))
    assert report["completed_cases"] == 2
    details = [
        json.loads(line)
        for line in fixture["output"]
        .with_suffix(".details.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert all(row["index_status"] == "unavailable_lexical_fallback" for row in details)
    assert any(
        r["effective_mode"] == "lexical" for row in details for r in row["retrieval_records"]
    )


def test_changed_budget_cannot_increase_remaining_calls(tmp_path: Path) -> None:
    fixture = setup_fixture(tmp_path, requests=1)
    ledger = RequestLedger(fixture["config"])
    ledger.reserve("synthetic-reserved-before-interruption")
    raw = json.loads(fixture["config_file"].read_bytes())
    raw["max_requests"] = 99
    fixture["config_file"].write_text(json.dumps(raw))
    config = load_free_config(fixture["config_file"], fixture["workspace"])
    with pytest.raises(CollectionError, match="request_ledger_invalid_or_limit_changed"):
        RequestLedger(config).reserve("synthetic-second-call")


def test_resume_with_durable_completed_artifacts_does_not_redispatch(tmp_path: Path) -> None:
    fixture = setup_fixture(tmp_path)
    calls: list[dict[str, Any]] = []
    transport = synthetic_transport(calls)
    collect(fixture, limit=2, transport=transport)
    path = fixture["output"].with_suffix(".run.json")
    state = json.loads(path.read_bytes())
    state["cases"]["synthetic:q1"] = "running"
    path.write_text(json.dumps(state))
    count = len(calls)
    collect(fixture, transport=transport)
    assert len(calls) == count + 2  # only the pending final development case
