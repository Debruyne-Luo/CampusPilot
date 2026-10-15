"""SYNTHETIC fixed-evidence replay contracts; no real model or network calls."""

import asyncio
import copy
import json
from pathlib import Path
from typing import Any

import pytest
from campuspilot.agent.executor import AgentRunner
from campuspilot.jev_plugin import JevPlugin
from campuspilot.llm.chat_model import Completion, ToolCall
from campuspilot.rag import SnapshotStore, digest, make_snapshot
from campuspilot.retrieval.hybrid import HybridRetriever
from campuspilot.tools.base import ToolRegistry
from test_agent_loop import REPO, FakeLLM, answer
from test_jev_plugin import FakeJev
from test_snapshot_fallback import synthetic_snapshot
from test_web_evidence import MemoryBudget

# Repo root comes from `pythonpath` in pyproject.toml, which both `python -m pytest` and the
# `pytest` console script (CI) honour.
from scripts.evaluate_jev_replay import prepare_cases, replay_arm


def source_case() -> tuple[HybridRetriever, list[dict[str, Any]], list[dict[str, Any]]]:
    first = synthetic_snapshot()
    unrelated = first.chunks[0].model_copy(update={
        "chunk_id": "SYNTHETIC:unrelated", "text": "SYNTHETIC unrelated glossary",
        "text_sha256": digest(b"SYNTHETIC unrelated glossary"),
    })
    snapshot = make_snapshot(first.sources, (*first.chunks, unrelated), digest(b"SYNTHETIC"))
    rows = [{
        "source_id": chunk.source_id, "chunk_id": chunk.chunk_id, "text": chunk.text,
        "text_sha256": chunk.text_sha256, "title": chunk.title,
        "url": snapshot.sources[0].url, "source_title": snapshot.sources[0].title,
        "grounded": True, "score": 0.8,
    } for chunk in snapshot.chunks]
    labels = [{
        "id": "SYNTHETIC-case", "category": "partial", "question": "SYNTHETIC guideline?",
        "expected": "SYNTHETIC GOLD MUST NOT ENTER THE GENERATION PROMPT",
        "unknown": "SYNTHETIC unknown condition",
        "label_basis": "SYNTHETIC public scenario, no student transcript",
    }]
    observations = [{
        "id": labels[0]["id"], "question": labels[0]["question"], "arm": "off",
        "body": {"understanding": {"intent": "政策问答"}},
        "evidence": [{"tool": "search_knowledge", "result": {
            "knowledge_version": snapshot.version, "result_status": "success", "hits": rows,
            "answer": "\n".join(str(row["text"]) for row in rows),
            "grounding": {"policy": "SYNTHETIC", "decision": "grounded"},
        }}],
        "messages": ["SYNTHETIC CAPTURED MESSAGE MUST NOT PERSIST"],
        "credentials": "SYNTHETIC CREDENTIAL MUST NOT PERSIST",
    }]
    return HybridRetriever(snapshot, "lexical"), labels, observations


def test_preparation_copies_original_tools_without_history_credentials_or_gold_prompts() -> None:
    frozen, labels, observations = source_case()
    case = prepare_cases(labels, observations, frozen.snapshot)[0]
    exported = json.dumps(case.as_dict())
    assert "CAPTURED MESSAGE MUST NOT PERSIST" not in exported
    assert "CREDENTIAL MUST NOT PERSIST" not in exported
    original_hash = case.evidence_sha256
    observations[0]["evidence"][0]["result"]["hits"].clear()
    result = case.tools[0]["result"]
    assert isinstance(result, dict)
    hits = result["hits"]
    assert isinstance(hits, list) and len(hits) == 2
    assert case.evidence_sha256 == original_hash


def test_on_and_off_use_identical_fresh_evidence_and_no_understanding_or_tools(
    tmp_path: Path,
) -> None:
    frozen, labels, observations = source_case()
    case = prepare_cases(labels, observations, frozen.snapshot)[0]
    baseline = copy.deepcopy(case.as_dict())
    store = SnapshotStore(tmp_path / "SYNTHETIC-store")
    source_id = frozen.snapshot.sources[0].source_id
    first_id = frozen.snapshot.chunks[0].chunk_id
    judge = FakeJev(sufficient=0.1, mode="clarify", score={first_id: 2})
    on_model = FakeLLM(answer("SYNTHETIC graduate guideline one", [source_id]))
    off_model = FakeLLM(answer("SYNTHETIC graduate guideline one", [source_id]))
    on = AgentRunner(ToolRegistry(()), REPO, on_model, max_tool_rounds=0,
                     snapshots=store, jev=JevPlugin(judge, MemoryBudget(), "on", store))
    off = AgentRunner(ToolRegistry(()), REPO, off_model, max_tool_rounds=0, snapshots=store)

    async def compare() -> tuple[dict[str, Any], dict[str, Any]]:
        return (await replay_arm(on, case, frozen, "jev_on"),
                await replay_arm(off, case, frozen, "off"))

    on_result, off_result = asyncio.run(compare())
    assert on_result["evidence_sha256"] == off_result["evidence_sha256"]
    assert on_result["before_chunk_ids"] == off_result["before_chunk_ids"]
    assert on_result["after_chunk_ids"] == [first_id]
    assert off_result["after_chunk_ids"] == off_result["before_chunk_ids"]
    assert case.as_dict() == baseline
    assert on_result["body"]["result_status"] == off_result["body"]["result_status"] == "success"
    assert len(judge.calls) == 1
    assert on_result["quality_review"] == "pending_source_review"
    for model in (on_model, off_model):
        assert len(model.calls) == 1
        assert model.calls[0]["tools"] is None and model.calls[0]["json_mode"] is True
        prompt = json.dumps(model.calls[0]["messages"], ensure_ascii=False)
        assert "GOLD MUST NOT ENTER" not in prompt and "unknown condition" not in prompt


@pytest.mark.parametrize("fault", ["body", "url", "hash", "version", "web"])
def test_unmatched_or_web_evidence_is_rejected_before_any_model_call(fault: str) -> None:
    frozen, labels, observations = source_case()
    result = observations[0]["evidence"][0]["result"]
    if fault == "body":
        result["hits"][0]["text"] = "SYNTHETIC changed body"
    elif fault == "url":
        result["hits"][0]["url"] = "https://third.example/SYNTHETIC"
    elif fault == "hash":
        result["hits"][0]["text_sha256"] = digest(b"SYNTHETIC tampered")
    elif fault == "version":
        result["knowledge_version"] = "kb-0000000000000000"
    elif fault == "web":
        result["hits"][0]["web"] = True
    with pytest.raises(ValueError, match="^replay_"):
        prepare_cases(labels, observations, frozen.snapshot)


def test_private_question_and_duplicate_original_records_are_rejected() -> None:
    frozen, labels, observations = source_case()
    with pytest.raises(ValueError, match="^replay_duplicate_source_case$"):
        prepare_cases(labels, observations * 2, frozen.snapshot)
    labels[0]["question"] = observations[0]["question"] = "我的密码是SYNTHETIC123"
    with pytest.raises(ValueError, match="^replay_public_question_required$"):
        prepare_cases(labels, observations, frozen.snapshot)


def test_model_cannot_trigger_additional_retrieval_during_replay(tmp_path: Path) -> None:
    frozen, labels, observations = source_case()
    case = prepare_cases(labels, observations, frozen.snapshot)[0]
    model = FakeLLM(Completion(tool_calls=(ToolCall(
        call_id="SYNTHETIC-call", name="search_knowledge", arguments='{"query":"SYNTHETIC"}',
    ),)))
    agent = AgentRunner(ToolRegistry(()), REPO, model, max_tool_rounds=0,
                        snapshots=SnapshotStore(tmp_path / "SYNTHETIC-store"))
    result = asyncio.run(replay_arm(agent, case, frozen, "off"))
    assert len(model.calls) == 1
    assert result["body"]["degraded_reason"] == "tool_rounds_exceeded"
    assert result["after_chunk_ids"] == result["before_chunk_ids"]


def test_replay_rejects_normal_runner_with_tool_rounds_enabled(tmp_path: Path) -> None:
    frozen, labels, observations = source_case()
    case = prepare_cases(labels, observations, frozen.snapshot)[0]
    model = FakeLLM()
    agent = AgentRunner(ToolRegistry(()), REPO, model,
                        snapshots=SnapshotStore(tmp_path / "SYNTHETIC-store"))
    with pytest.raises(ValueError, match="^replay_requires_generation_only_runner$"):
        asyncio.run(replay_arm(agent, case, frozen, "off"))
    assert model.calls == []
