"""Offline request-scoped snapshot consistency without weakening reload validation."""

import asyncio
from datetime import date
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest
from campuspilot.evaluation_budget import SpendBudget
from campuspilot.jev_plugin import JevDecider, JevPlugin
from campuspilot.knowledge_release import current_version, publish, write_candidate
from campuspilot.rag import KnowledgeSnapshot, SnapshotStore
from campuspilot.retrieval.hybrid import HybridRetriever
from campuspilot.tools.knowledge import HybridKnowledgeTool, SnapshotQuery
from pydantic import JsonValue
from test_snapshot_fallback import synthetic_snapshot


def release(root: Path, snapshot: KnowledgeSnapshot) -> None:
    candidate = root.parent / ("candidate-" + snapshot.version)
    write_candidate(candidate, snapshot, {"SYNTHETIC.txt": b"SYNTHETIC evidence"})
    publish(candidate, root, current_version(root))


def test_search_and_jev_keep_same_body_when_publication_reuses_chunk_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("campuspilot.tools.knowledge.campus_today", lambda: date(2026, 10, 14))
    root = tmp_path / "store"
    old, new = synthetic_snapshot("old"), synthetic_snapshot("new")
    assert old.chunks[0].chunk_id == new.chunks[0].chunk_id
    release(root, old)
    store = SnapshotStore(root)
    retriever = store.acquire()
    assert retriever is not None
    tool = HybridKnowledgeTool(store, None, "off")
    client, budget = Mock(spec=JevDecider), Mock(spec=SpendBudget)
    jev = JevPlugin(client, budget, snapshots=store)
    query = SnapshotQuery(query="graduate guideline", audience="graduate")

    with store.pin(retriever):
        before = tool.run(query)
        release(root, new)
        after = tool.run(query)
        rows = cast(list[dict[str, JsonValue]], before["hits"])
        assert rows and before == after
        resolved = jev.resolve(rows)
        assert len(resolved) == 1
        assert resolved[0].knowledge_version == old.version
        assert resolved[0].chunk.text == old.chunks[0].text
        assert resolved[0].chunk.text_sha256 == rows[0]["text_sha256"]

    acquired = store.acquire()
    assert acquired is not None and acquired.snapshot.version == new.version
    assert tool.run(query)["knowledge_version"] == new.version
    # Old rows must not silently resolve to different text outside the request scope.
    assert jev.resolve(rows) == ()
    legacy_rows = [
        {key: value for key, value in row.items() if key != "text_sha256"} for row in rows
    ]
    assert jev.resolve(legacy_rows)[0].knowledge_version == new.version
    assert client.mock_calls == budget.mock_calls == []


@pytest.mark.parametrize("damaged_file", ["raw/SYNTHETIC.txt", "snapshot.json"])
def test_next_request_still_detects_payload_damage_under_unchanged_pointer(
    tmp_path: Path, damaged_file: str
) -> None:
    root = tmp_path / "store"
    snapshot = synthetic_snapshot()
    release(root, snapshot)
    store = SnapshotStore(root)
    retriever = store.acquire()
    assert retriever is not None
    pointer = (root / "current.json").read_bytes()
    with store.pin(retriever):
        (root / "versions" / snapshot.version / damaged_file).write_bytes(b"SYNTHETIC damaged")
        assert store.acquire() is retriever
        assert not store.load_error
    assert (root / "current.json").read_bytes() == pointer
    assert store.acquire() is retriever
    assert store.load_error


def test_empty_snapshot_stays_empty_until_next_request(tmp_path: Path) -> None:
    root = tmp_path / "store"
    store = SnapshotStore(root)
    assert store.acquire() is None
    snapshot = synthetic_snapshot()
    with store.pin(None):
        release(root, snapshot)
        assert store.acquire() is None
    acquired = store.acquire()
    assert acquired is not None and acquired.snapshot == snapshot


def test_concurrent_request_scopes_and_tool_threads_are_isolated(tmp_path: Path) -> None:
    root = tmp_path / "store"
    release(root, synthetic_snapshot("old"))
    store = SnapshotStore(root)
    old = store.acquire()
    release(root, synthetic_snapshot("new"))
    new = store.acquire()
    assert old is not None and new is not None and old is not new

    async def requests() -> None:
        ready_old, ready_new, proceed = asyncio.Event(), asyncio.Event(), asyncio.Event()

        async def request(retriever: HybridRetriever, ready: asyncio.Event) -> None:
            with store.pin(retriever):
                ready.set()
                await proceed.wait()
                assert store.acquire() is retriever
                assert await asyncio.to_thread(store.acquire) is retriever

        first = asyncio.create_task(request(old, ready_old))
        second = asyncio.create_task(request(new, ready_new))
        await ready_old.wait()
        await ready_new.wait()
        try:
            assert await asyncio.to_thread(store.acquire) is new
        finally:
            proceed.set()
            await asyncio.gather(first, second)
        assert store.acquire() is new

    asyncio.run(requests())


@pytest.mark.parametrize("fault", [RuntimeError, asyncio.CancelledError])
def test_nested_pin_resets_after_error_and_is_specific_to_its_store(
    tmp_path: Path, fault: type[BaseException]
) -> None:
    root = tmp_path / "store"
    release(root, synthetic_snapshot("old"))
    store = SnapshotStore(root)
    old = store.acquire()
    release(root, synthetic_snapshot("new"))
    new = store.acquire()
    assert old is not None and new is not None
    other = SnapshotStore(root)
    with store.pin(old):
        with pytest.raises(fault), store.pin(None):
            assert store.acquire() is None
            raise fault()
        assert store.acquire() is old
        independent = other.acquire()
        assert independent is not None and independent.snapshot == new.snapshot
    assert store.acquire() is new
