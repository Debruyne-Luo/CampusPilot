"""Bounded real-Agent answer collection. No scoring and no embedding-provider calls.

Only an external, explicitly free-only configuration permits chat requests. Each HTTP
completion reserves one durable request before dispatch; unknown outcomes never retry.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import JsonValue

from campuspilot.agent.executor import AgentRunner
from campuspilot.chat_runtime import ConversationContext
from campuspilot.dify import ChatUnavailable
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.knowledge import KnowledgeStore, campus_clock
from campuspilot.knowledge_evaluation import Observation, QualityCase, fingerprint, sha256
from campuspilot.knowledge_release import (
    atomic_write,
    load_candidate_index,
    publication_lock,
    read_candidate,
)
from campuspilot.llm.chat_model import ChatCompletionsModel, Completion, validate_endpoint
from campuspilot.rag import RetrievalFilters, SnapshotStore, canonical
from campuspilot.retrieval.hybrid import ChannelResult, HybridRetriever
from campuspilot.tools import agent_registry
from campuspilot.tools.base import ToolRegistry


class CollectionError(Exception):
    """A stable, secret-free diagnostic code; never interpolate provider/config input."""


@dataclass(frozen=True)
class FreeModelConfig:
    base_url: str
    model: str
    max_requests: int
    api_key: str = field(repr=False)
    config_path: Path = field(repr=False)
    timeout_seconds: float = 30
    max_output_tokens: int = 1500

    @property
    def identity(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "model": self.model,
            "free_only": True,
            "max_requests": self.max_requests,
            "timeout_seconds": self.timeout_seconds,
            "max_output_tokens": self.max_output_tokens,
        }

    @property
    def ledger_path(self) -> Path:
        # Independent of output, split and --limit: resuming/changing outputs cannot
        # reset the configured profile's request allowance.
        identity = fingerprint({"base_url": self.base_url, "model": self.model})[:16]
        return self.config_path.parent / ".campuspilot-answer-budget" / (identity + ".json")


def load_free_config(path: Path, workspace: Path) -> FreeModelConfig:
    """Read credentials only outside this repository; all validation errors redact input."""
    try:
        path = path.resolve(strict=True)
        if path.is_relative_to(workspace.resolve()) or path.stat().st_size > 65_536:
            raise ValueError
        raw = json.loads(path.read_bytes())
        allowed = {
            "base_url",
            "model",
            "api_key",
            "api_key_file",
            "free_only",
            "max_requests",
            "timeout_seconds",
            "max_output_tokens",
        }
        if not isinstance(raw, dict) or set(raw) - allowed or raw.get("free_only") is not True:
            raise ValueError
        if ("api_key" in raw) == ("api_key_file" in raw):
            raise ValueError
        key = raw.get("api_key")
        if "api_key_file" in raw:
            key_path = (path.parent / raw["api_key_file"]).resolve(strict=True)
            if key_path.is_relative_to(workspace.resolve()) or key_path.stat().st_size > 4096:
                raise ValueError
            key = key_path.read_text(encoding="utf-8").strip()
        if not isinstance(key, str) or not key or len(key) > 4096 or any(c.isspace() for c in key):
            raise ValueError
        endpoint, model = raw["base_url"], raw["model"]
        if not isinstance(endpoint, str) or len(endpoint) > 500:
            raise ValueError
        validate_endpoint(endpoint)
        if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9_./:@+\-]{1,160}", model):
            raise ValueError
        if key in endpoint or key in model:
            raise ValueError
        count = raw["max_requests"]
        timeout, tokens = raw.get("timeout_seconds", 30), raw.get("max_output_tokens", 1500)
        if type(count) is not int or not 1 <= count <= 10_000:
            raise ValueError
        if type(timeout) not in (int, float) or not 0 < timeout <= 60:
            raise ValueError
        if type(tokens) is not int or not 1 <= tokens <= 4000:
            raise ValueError
        return FreeModelConfig(endpoint, model, count, key, path, float(timeout), tokens)
    except OSError, ValueError, KeyError, TypeError:
        raise CollectionError("external_free_model_config_invalid") from None


class RequestLedger:
    def __init__(self, config: FreeModelConfig) -> None:
        self.path = config.ledger_path
        self.limit = config.max_requests
        self.profile = {"base_url": config.base_url, "model": config.model, "free_only": True}

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "schema_version": 1,
                "profile": self.profile,
                "max_requests": self.limit,
                "requests": [],
            }
        try:
            raw = json.loads(self.path.read_bytes())
            if (
                raw["profile"] != self.profile
                or raw["max_requests"] != self.limit
                or not isinstance(raw["requests"], list)
            ):
                raise ValueError
            return dict(raw)
        except OSError, ValueError, KeyError, TypeError:
            raise CollectionError("request_ledger_invalid_or_limit_changed") from None

    def reserve(self, case_key: str) -> str:
        with publication_lock(self.path.parent):
            raw = self._read()
            if any(r.get("case_key") == case_key and r.get("status") in {"reserved", "unknown"}
                   for r in raw["requests"]):
                raise CollectionError("case_request_outcome_unknown_no_automatic_retry")
            if len(raw["requests"]) >= self.limit:
                raise CollectionError("request_budget_exhausted")
            ident = f"request-{len(raw['requests']) + 1}"
            raw["requests"].append({"id": ident, "case_key": case_key, "status": "reserved"})
            atomic_write(self.path, canonical(raw))
            return ident

    def settle(self, ident: str, status: Literal["completed", "unknown"]) -> None:
        with publication_lock(self.path.parent):
            raw = self._read()
            item = next(r for r in raw["requests"] if r["id"] == ident)
            if item["status"] != "reserved":
                raise CollectionError("request_already_settled")
            item["status"] = status
            # Every reservation remains counted, including unknown/malformed outcomes.
            atomic_write(self.path, canonical(raw))

    def report(self) -> dict[str, Any]:
        with publication_lock(self.path.parent):
            raw = self._read()
            return {
                "max_requests": self.limit,
                "reserved_requests": len(raw["requests"]),
                "unknown_requests": sum(r["status"] != "completed" for r in raw["requests"]),
            }


class ReservedChatModel:
    """Use only the existing chat-completions adapter, with an outer request barrier."""

    def __init__(
        self,
        model: ChatCompletionsModel,
        ledger: RequestLedger,
        case_key: str,
    ) -> None:
        self.model, self.ledger, self.case_key = model, ledger, case_key
        self.records: list[dict[str, Any]] = []
        self.stopped = False

    async def complete(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]] | None = None,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> Completion:
        if self.stopped:
            raise ChatUnavailable("evaluation_previous_call_failed")
        try:
            ident = self.ledger.reserve(self.case_key)
        except CollectionError as exc:
            self.stopped = True
            self.records.append({"status": "blocked", "reason": str(exc)})
            raise ChatUnavailable("evaluation_" + str(exc)) from None
        record: dict[str, Any] = {"reservation_id": ident, "status": "reserved"}
        self.records.append(record)
        started = time.perf_counter()
        try:
            reply = await self.model.complete(
                messages,
                tools,
                json_mode,
                min(max_tokens or self.model.max_output_tokens, self.model.max_output_tokens),
            )
        except BaseException:
            self.stopped = True
            record["status"] = "unknown"
            self.ledger.settle(ident, "unknown")
            raise
        else:
            self.ledger.settle(ident, "completed")
            record.update(
                status="completed",
                input_tokens=reply.input_tokens,
                output_tokens=reply.output_tokens,
            )
            return reply
        finally:
            record["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)


class RecordingRegistry(ToolRegistry):
    def __init__(self, registry: ToolRegistry) -> None:
        super().__init__(registry.tools)
        self.records: list[dict[str, Any]] = []

    def call(self, name: str, arguments: dict[str, JsonValue]) -> dict[str, JsonValue]:
        row: dict[str, Any] = {"tool": name, "arguments": arguments}
        self.records.append(row)
        try:
            result = super().call(name, arguments)
        except Exception:
            row["error"] = "tool_failed"
            raise
        # Agent presentation may subsequently bound/filter the returned dictionary.
        # Keep a separate copy of exactly what the real permission-checked tool returned.
        row["result"] = json.loads(json.dumps(result, ensure_ascii=False))
        return result


class FixtureClockRetriever(HybridRetriever):
    """Preserve production parsing/ranking; only the explicit fixture clock is locked."""

    def __init__(self, retriever: HybridRetriever, case: QualityCase) -> None:
        super().__init__(
            retriever.snapshot,
            mode=retriever.mode,
            index=retriever.index,
            query_vector=retriever.query_vector,
            candidates=retriever.candidates,
            rrf_k=retriever.rrf_k,
            weights=retriever.weights,
            stale_weight=retriever.stale_weight,
            min_similarity=retriever.min_similarity,
            service_links=retriever.service_links,
        )
        self.today = case.today
        self.records: list[dict[str, Any]] = []

    def search_channels(
        self,
        query: str,
        filters: RetrievalFilters,
        top_k: int = 12,
        query_vector: Sequence[float] | None = None,
    ) -> ChannelResult:
        filters = filters.model_copy(update={"today": self.today})
        result = super().search_channels(query, filters, top_k, query_vector)
        self.records.append(
            {
                "query": query,
                "filters": filters.model_dump(mode="json"),
                "requested_mode": self.mode,
                "effective_mode": "lexical" if self.degraded else self.mode,
                "degraded": self.degraded,
                "ranked_chunk_ids": [h.chunk.chunk_id for h in result.hits],
            }
        )
        return result


@dataclass(frozen=True)
class CachedQueries:
    model: str
    dimensions: int
    queries: dict[str, list[float]]

    def cached(self, text: str) -> list[float] | None:
        return self.queries.get(text.strip()[:4000])


def load_query_vectors(path: Path | None) -> CachedQueries | None:
    """Explicit local cache format: model, dimensions, queries{text: float[]} only."""
    if path is None:
        return None
    try:
        raw = json.loads(path.read_bytes())
        model, dimensions, queries = raw["model"], raw["dimensions"], raw["queries"]
        if (
            not isinstance(model, str)
            or type(dimensions) is not int
            or not 1 <= dimensions <= 4096
            or not isinstance(queries, dict)
        ):
            raise ValueError
        clean = {}
        for question, vector in queries.items():
            if (
                not isinstance(question, str)
                or not question.strip()
                or not isinstance(vector, list)
                or len(vector) != dimensions
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in vector)
            ):
                raise ValueError
            clean[question.strip()[:4000]] = [float(v) for v in vector]
        return CachedQueries(model, dimensions, clean)
    except OSError, ValueError, KeyError, TypeError:
        raise CollectionError("query_vector_cache_invalid") from None


def redact(value: Any, secret: str) -> Any:
    if isinstance(value, str):
        return value.replace(secret, "[REDACTED]")
    if isinstance(value, dict):
        return {str(k).replace(secret, "[REDACTED]"): redact(v, secret) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [redact(v, secret) for v in value]
    return value


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    atomic_write(path, ("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)).encode())


async def collect_answers(
    cases: Sequence[QualityCase],
    *,
    config: FreeModelConfig,
    release: Path,
    directory: Path,
    output: Path,
    split: Literal["development", "holdout", "all"] = "development",
    limit: int | None = None,
    query_vectors: Path | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    """Collect real Agent outputs, with an initial two-case smoke and conservative resume."""
    selected = [c for c in cases if split == "all" or c.split == split]
    if not selected or (limit is not None and limit < 1):
        raise CollectionError("invalid_case_selection")
    if len({c.case_id for c in cases}) != len(cases):
        raise CollectionError("duplicate_case_id")
    snapshot = read_candidate(release, check_index=False)
    if snapshot.pending:
        raise CollectionError("pending_snapshot_not_servable")
    cache = load_query_vectors(query_vectors)
    structured = release / "directory" if (release / "directory").is_dir() else directory
    directory_hashes = {p.name: sha256(p.read_bytes()) for p in sorted(structured.glob("*.json"))}
    binding = {
        "schema_version": 1,
        "suite_sha256": fingerprint([c.model_dump(mode="json") for c in cases]),
        "snapshot_sha256": sha256((release / "snapshot.json").read_bytes()),
        "manifest_sha256": sha256((release / "manifest.json").read_bytes()),
        "knowledge_version": snapshot.version,
        "model_config": config.identity,
        "directory_sha256": directory_hashes,
        "split": split,
        "query_vectors_sha256": sha256(query_vectors.read_bytes()) if query_vectors else None,
        "fixture_clock": selected[0].today.isoformat(),
        "scope_policy": "production parsing; initial fixture context; no gold scope override",
    }
    state_path, detail_path = output.with_suffix(".run.json"), output.with_suffix(".details.jsonl")
    output.parent.mkdir(parents=True, exist_ok=True)
    with publication_lock(output.parent):
        if state_path.exists():
            state = json.loads(state_path.read_bytes())
            if state.get("binding") != binding:
                raise CollectionError("resume_binding_mismatch")
        else:
            if output.exists() or detail_path.exists():
                raise CollectionError("unbound_existing_output")
            state = {"binding": binding, "cases": {}, "blocked": None}
        observed = [Observation.model_validate(r) for r in _read_rows(output)]
        by_case = {c.case_id: c for c in cases}
        if len({o.case_id for o in observed}) != len(observed):
            raise CollectionError("duplicate_existing_observation")
        for obs in observed:
            case = by_case.get(obs.case_id)
            if (
                case is None
                or obs.case_sha256 != fingerprint(case.model_dump(mode="json"))
                or obs.knowledge_version != snapshot.version
                or obs.answer is None
            ):
                raise CollectionError("existing_observation_binding_mismatch")
        detail_map = {r["case_id"]: r for r in _read_rows(detail_path)}
        if any(
            detail_map.get(o.case_id, {}).get("observation_sha256")
            != fingerprint(o.model_dump(mode="json"))
            for o in observed
        ):
            raise CollectionError("existing_answer_details_binding_mismatch")
        complete = {o.case_id for o in observed}
        # The two complete artifacts are durable before the state commit. Recover a
        # crash between them and that commit without redispatching a complete case.
        for case_id in complete:
            state["cases"][case_id] = "complete"
        if any(status == "running" for status in state["cases"].values()):
            state["blocked"] = "interrupted_case_outcome_unknown_no_automatic_retry"
        if not complete and limit != min(2, len(selected)):
            raise CollectionError("initial_smoke_requires_limit_2")
        atomic_write(state_path, canonical(state))
    ledger = RequestLedger(config)
    if state["blocked"]:
        return {
            "status": "blocked",
            "reason": state["blocked"],
            "completed_cases": len(complete),
            "request_budget": ledger.report(),
        }
    pending = [c for c in selected if c.case_id not in complete]
    if limit is not None:
        pending = pending[:limit]
    model = ChatCompletionsModel(
        config.base_url,
        config.model,
        config.api_key,
        transport,
        config.timeout_seconds,
        config.max_output_tokens,
    )
    with tempfile.TemporaryDirectory(prefix="campuspilot-answer-eval-") as temporary:
        root = Path(temporary)
        copied = root / "versions" / snapshot.version
        shutil.copytree(release, copied)
        atomic_write(
            root / "current.json",
            canonical(
                {
                    "kind": "published",
                    "version": snapshot.version,
                    "sha256": binding["snapshot_sha256"],
                    "manifest_sha256": binding["manifest_sha256"],
                }
            ),
        )
        store = SnapshotStore(root, "lexical")
        base = store.acquire()
        if base is None:
            raise CollectionError("isolated_snapshot_unavailable")
        index_status = "not_requested"
        if cache:
            try:
                index = load_candidate_index(
                    copied,
                    snapshot,
                    json.loads((copied / "manifest.json").read_bytes()),
                    model=cache.model,
                    prefer="python",
                )
            except OSError, ValueError:
                index_status = "unavailable_lexical_fallback"
            else:
                if index.dimensions != cache.dimensions:
                    raise CollectionError("query_vector_dimension_mismatch")
                base = HybridRetriever(
                    snapshot,
                    mode="hybrid",
                    index=index,
                    query_vector=cache.cached,
                    service_links=base.service_links,
                )
                index_status = "available_python_backend"
        repo = DirectoryRepository.load(
            copied / "directory" if (copied / "directory").is_dir() else directory
        )
        for case in pending:
            with publication_lock(output.parent):
                state = json.loads(state_path.read_bytes())
                if case.case_id in state["cases"]:
                    continue
                state["cases"][case.case_id] = "running"
                atomic_write(state_path, canonical(state))
            started = time.perf_counter()
            reserved = ReservedChatModel(
                model,
                ledger,
                fingerprint(
                    {
                        "run": binding,
                        "case": case.model_dump(mode="json"),
                    }
                ),
            )
            registry = RecordingRegistry(agent_registry(repo, KnowledgeStore(()), store))
            traces: list[dict[str, Any]] = []

            def trace(
                kind: str, record: dict[str, JsonValue], sink: list[dict[str, Any]] = traces
            ) -> None:
                sink.append({"kind": kind, **record})

            runner = AgentRunner(
                registry,
                repo,
                reserved,
                snapshots=store,
                trace=trace,
            )
            retriever = FixtureClockRetriever(base, case)
            context = ConversationContext(
                audience="unknown" if case.audience == "all" else case.audience,
                academic_year=case.academic_year,
                campus=case.campus or "chengdu",
            )
            turns = []
            try:
                with campus_clock(case.today), store.pin(retriever):
                    for question in (*case.messages, case.question):
                        final_retrieval_start = len(retriever.records)
                        body = await runner.run(question, context)
                        answer = str(body.get("answer") or "")
                        turns.append({"question": question, "response": body})
                        context.remember(question, answer or "[empty answer]")
                await runner.drain()
                final_retrieval = retriever.records[final_retrieval_start:]
                ranked = tuple(
                    dict.fromkeys(cid for row in final_retrieval for cid in row["ranked_chunk_ids"])
                )
                excerpts = body.get("excerpts") or []
                if not isinstance(excerpts, list):
                    excerpts = []
                shown = tuple(
                    str(row["chunk_id"])
                    for row in excerpts
                    if isinstance(row, dict) and row.get("chunk_id")
                )
                sources = {s.source_id for s in snapshot.sources}
                chunk_sources = {c.chunk_id: c.source_id for c in snapshot.chunks}
                source_ids = body.get("source_ids")
                cited = tuple(
                    dict.fromkeys(
                        chunk_sources.get(str(v), str(v))
                        for v in (source_ids if isinstance(source_ids, list) else [])
                        if str(v) in sources or str(v) in chunk_sources
                    )
                )
                mode = (
                    (
                        "hybrid"
                        if base.index and not any(r["degraded"] for r in final_retrieval)
                        else "lexical"
                    )
                    if final_retrieval
                    else "not_used"
                )
                observation = Observation(
                    case_id=case.case_id,
                    case_sha256=fingerprint(case.model_dump(mode="json")),
                    knowledge_version=snapshot.version,
                    ranked_chunk_ids=ranked,
                    shown_chunk_ids=shown,
                    cited_source_ids=cited,
                    answer=redact(answer, config.api_key),
                    behavior=None,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    cost_usd=0,
                    execution_mode="real_agent_"
                    + mode
                    + ("_model_incomplete" if reserved.stopped else ""),
                )
                details = redact(
                    {
                        "case_id": case.case_id,
                        "case_sha256": observation.case_sha256,
                        "observation_sha256": fingerprint(observation.model_dump(mode="json")),
                        "knowledge_version": snapshot.version,
                        "turns": turns,
                        "tool_records": registry.records,
                        "retrieval_records": retriever.records,
                        "model_requests": reserved.records,
                        "trace": traces,
                        "citations": body.get("citations"),
                        "fixture_clock": case.today.isoformat(),
                        "behavior_review": "unassessed; assign via independent answer review",
                        "cost_basis": (
                            "external config confirms free_only; no price inferred from token usage"
                        ),
                        "index_status": index_status,
                        "final_context": {
                            "audience": context.audience,
                            "campus": context.campus,
                            "academic_year": context.academic_year,
                        },
                    },
                    config.api_key,
                )
                with publication_lock(output.parent):
                    rows, detail_rows = _read_rows(output), _read_rows(detail_path)
                    rows.append(observation.model_dump(mode="json"))
                    detail_rows.append(details)
                    _write_rows(detail_path, detail_rows)
                    _write_rows(output, rows)
                    state = json.loads(state_path.read_bytes())
                    state["cases"][case.case_id] = "complete"
                    if reserved.stopped:
                        state["blocked"] = "request_failed_or_budget_exhausted_no_automatic_retry"
                    atomic_write(state_path, canonical(state))
            except Exception:
                with publication_lock(output.parent):
                    state = json.loads(state_path.read_bytes())
                    state["cases"][case.case_id] = "unknown"
                    state["blocked"] = "case_failed_outcome_unknown_no_automatic_retry"
                    atomic_write(state_path, canonical(state))
                raise CollectionError("case_failed_outcome_unknown_no_automatic_retry") from None
            complete.add(case.case_id)
            if state["blocked"]:
                break
    return {
        "status": "blocked" if state["blocked"] else "collected",
        "reason": state["blocked"],
        "selected_cases": len(selected),
        "completed_cases": len(complete),
        "remaining_cases": len(selected) - len(complete),
        "request_budget": ledger.report(),
        "behavior_review": "unassessed",
        "observation_file": str(output),
        "details_file": str(detail_path),
        "knowledge_version": snapshot.version,
    }
