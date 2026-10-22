"""JSON subprocess seam: run the real CampusPilot AgentRunner, never the optimizer.

Input is supplied on stdin; output is one JSON object. Credentials are limited to the
ephemeral loopback gateway token. Reference answers are deliberately not accepted.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

from campuspilot.agent.executor import AgentRunner
from campuspilot.chat_runtime import ConversationContext, public_input
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.evaluation_budget import OnlineBudget, TokenPrice
from campuspilot.experiment_budget import GatewayTransport
from campuspilot.harness_profile import HarnessProfile
from campuspilot.jev_plugin import JevPlugin
from campuspilot.jev_shadow import JevShadowClient
from campuspilot.knowledge import KnowledgeStore
from campuspilot.llm.chat_model import ChatCompletionsModel
from campuspilot.rag import SnapshotStore
from campuspilot.tools import agent_registry
from campuspilot.tools.base import ToolRegistry


async def execute(raw: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "question",
        "data_dir",
        "knowledge_version",
        "profile",
        "gateway",
        "gateway_token",
        "model",
        "jev_model",
        "jev_routing",
        "jev_evidence",
        "scratch",
    }
    if set(raw) - allowed or not public_input(raw["question"]):
        raise ValueError("Only public task inputs are accepted")
    data = Path(raw["data_dir"])
    repository = DirectoryRepository.load(data)
    snapshots = SnapshotStore(data / "rag", "lexical")
    retriever = snapshots.acquire()
    if retriever is None or retriever.snapshot.version != raw["knowledge_version"]:
        raise ValueError("Knowledge snapshot changed; experiment binding rejected")
    profile = HarnessProfile.model_validate(raw["profile"]) if raw.get("profile") else None
    transport = GatewayTransport(raw["gateway"], raw["gateway_token"])
    model = ChatCompletionsModel(
        "https://api.deepseek.com",
        raw["model"],
        "gateway-only",
        transport=transport,
        timeout_seconds=45,
        max_output_tokens=1500,
    )
    judge = None
    if raw.get("jev_routing") or raw.get("jev_evidence"):
        judge = JevPlugin(
            JevShadowClient(
                "gateway-only",
                TokenPrice(Decimal("0.042"), Decimal(0)),
                model=raw["jev_model"],
                transport=transport,
                timeout_seconds=2,
            ),
            # This per-worker safety ledger is secondary. The gateway campaign ledger
            # meters the actual external request once across every process and date.
            OnlineBudget(Path(raw["scratch"]), Decimal(20), 100),
            "on",
            snapshots,
        )
    records: list[dict[str, Any]] = []

    async def emit(event: str, payload: dict[str, Any]) -> None:
        records.append({"event": event, "data": payload})

    base = agent_registry(
        repository,
        KnowledgeStore.load(data / "knowledge.json"),
        snapshots,
        roster=data / "teachers_roster.json",
    )
    tool_records: list[dict[str, Any]] = []

    class ObservedRegistry(ToolRegistry):
        def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            result = super().call(name, arguments)
            tool_records.append({"tool": name, "arguments": arguments, "result": result})
            return result

    registry = ObservedRegistry(base.tools)
    runner = AgentRunner(
        registry,
        repository,
        model,
        snapshots=snapshots,
        profile=profile,
        jev=judge,
        jev_routing=bool(raw.get("jev_routing")),
        jev_evidence=bool(raw.get("jev_evidence")),
    )
    started = time.perf_counter()
    # One held retriever is used even if the on-disk active pointer changes mid-turn.
    with snapshots.pin(retriever):
        body = await runner.run(raw["question"], ConversationContext(), emit)
        await runner.drain()
    return {
        "body": body,
        "events": records,
        "latency_ms": (time.perf_counter() - started) * 1000,
        "tool_records": tool_records,
        "knowledge_version": retriever.snapshot.version,
        "retrieval_mode": "lexical",
        "profile": profile.identity() if profile else None,
        "directory_hashes": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(data.glob("*.json"))
        },
    }


if __name__ == "__main__":
    try:
        value = asyncio.run(execute(json.load(sys.stdin)))
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__, "status": "failed"}))
        raise SystemExit(1) from None
    print(json.dumps(value, ensure_ascii=False))
