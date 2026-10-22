"""Offline evidence metrics and explicit, observation-bound knowledge acceptance reviews.

Retrieval overlap is deliberately separate from answer and citation support. This module
does not call providers, infer no-answer labels from missing IDs, or manufacture reviews.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from typing import Any, Literal, Self, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

Category = Literal["common", "applicability", "temporal", "formats", "multi_clause", "insufficient"]
Behavior = Literal["answer", "partial", "clarify", "refuse", "unlabeled"]
ReviewStatus = Literal["draft", "source_checked"]
CRITICAL_KINDS = {"amount", "deadline", "eligibility", "location", "procedure"}
CATEGORIES: tuple[Category, ...] = (
    "common",
    "applicability",
    "temporal",
    "formats",
    "multi_clause",
    "insufficient",
)


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def fingerprint(value: object) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode())


def normalized(value: str) -> str:
    return re.sub(r"\s+", "", value)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceAnchor(StrictModel):
    evidence_id: str
    source_id: str
    source_url: str
    knowledge_version: str
    source_revision_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    revision_kind: Literal["raw_body", "raw_attachment", "snapshot_extract"]
    locator: str
    quote: str = Field(min_length=1)
    necessary_fact: str = Field(min_length=1)
    chunk_ids: tuple[str, ...] = ()
    raw_file: str | None = None
    raw_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    # A checked extraction is an agent source check, never a human-review claim.
    check_status: ReviewStatus = "draft"
    checked_by: str | None = None
    checked_at: date | None = None

    @model_validator(mode="after")
    def checked_provenance(self) -> Self:
        if self.check_status == "source_checked" and not (
            self.raw_file and self.raw_sha256 and self.checked_by and self.checked_at
        ):
            raise ValueError("source_checked evidence requires a checked local raw artifact")
        return self


class QualityCase(StrictModel):
    case_id: str
    question: str
    messages: tuple[str, ...] = ()
    category: Category
    split: Literal["development", "holdout"]
    issue_group: str
    expected_behavior: Behavior
    # Archived evidence may justify a limitation label without being eligible for current retrieval.
    retrieval_required: bool = True
    # Conditions are explicit test input, rather than inferred from the source publication date.
    audience: str = "all"
    campus: str | None = None
    today: date = date(2026, 10, 17)
    academic_year: str | None = None
    evidence: tuple[EvidenceAnchor, ...] = ()
    forbidden_conclusions: tuple[str, ...] = ()
    expected_next_step: str
    label_status: ReviewStatus = "draft"
    label_checked_by: str | None = None
    label_checked_at: date | None = None
    public_fixture: Literal[True] = True

    @model_validator(mode="after")
    def valid_gold(self) -> Self:
        if self.expected_behavior in {"answer", "partial"} and not self.evidence:
            raise ValueError("answerable gold requires evidence; missing labels are unlabeled")
        if self.label_status == "source_checked" and not (
            self.label_checked_by
            and self.label_checked_at
            and self.evidence
            and all(e.check_status == "source_checked" for e in self.evidence)
        ):
            raise ValueError("case source check requires all evidence checks and label provenance")
        return self


class Observation(StrictModel):
    case_id: str
    case_sha256: str
    knowledge_version: str
    ranked_chunk_ids: tuple[str, ...] = ()
    shown_chunk_ids: tuple[str, ...] = ()
    cited_source_ids: tuple[str, ...] = ()
    # None means an answer was not run. An empty retrieval result is not an answer.
    answer: str | None = None
    behavior: Behavior | None = None
    latency_ms: float = Field(default=0, ge=0)
    cost_usd: float = Field(default=0, ge=0)
    execution_mode: str = "offline_retrieval"


class AnswerReview(StrictModel):
    case_id: str
    observation_sha256: str
    status: Literal["pending", "source_checked"] = "pending"
    reviewed_by: str | None = None
    reviewed_at: date | None = None
    fact_correct: bool | None = None
    necessary_facts_complete: bool | None = None
    citation_support: bool | None = None
    citation_coverage: bool | None = None
    behavior_correct: bool | None = None
    actionable_next_step: bool | None = None
    # Reviewer explains support against evidence IDs; this is not an LLM score.
    support_notes: str = ""
    critical_errors: tuple[
        Literal["amount", "deadline", "eligibility", "location", "procedure"], ...
    ] = ()

    @model_validator(mode="after")
    def explicit_review(self) -> Self:
        if self.status == "source_checked" and not (
            self.reviewed_by and self.reviewed_at and self.support_notes.strip()
        ):
            raise ValueError("checked review requires reviewer, date and evidence support notes")
        return self


def legacy_behavior(row: Mapping[str, Any]) -> Behavior:
    """Only explicit semantic labels establish refusal/clarification; absent IDs do not."""
    explicit = row.get("expected_behavior") or row.get("answer_strategy")
    if explicit in {"answer", "partial", "clarify", "refuse", "unlabeled"}:
        return cast(Behavior, explicit)
    if explicit in {"direct", "generate"}:
        return "answer"
    if row.get("chunk_ids") or row.get("target_chunk_ids") or row.get("gold"):
        return "answer"
    return "unlabeled"


def validate_suite(cases: Sequence[QualityCase], *, require_full: bool = False) -> dict[str, Any]:
    if len({c.case_id for c in cases}) != len(cases):
        raise ValueError("duplicate case IDs")
    groups: dict[str, set[str]] = defaultdict(set)
    sources: dict[str, set[str]] = defaultdict(set)
    urls: dict[str, set[str]] = defaultdict(set)
    questions: dict[str, set[str]] = defaultdict(set)
    for case in cases:
        groups[case.issue_group].add(case.split)
        questions[normalized(case.question)].add(case.split)
        for evidence in case.evidence:
            sources[evidence.source_id].add(case.split)
            urls[evidence.source_url.rstrip("/")].add(case.split)
    for label, items in (
        ("issue", groups),
        ("source", sources),
        ("URL", urls),
        ("question", questions),
    ):
        leaks = sorted(k for k, values in items.items() if len(values) > 1)
        if leaks:
            raise ValueError(f"development/holdout {label} leakage: {leaks}")
    categories = Counter(c.category for c in cases)
    splits = Counter(c.split for c in cases)
    if require_full and (
        len(cases) != 120
        or splits != {"development": 60, "holdout": 60}
        or any(categories[category] != 20 for category in CATEGORIES)
        or any(
            sum(c.category == cat and c.split == split for c in cases) != 10
            for cat in CATEGORIES
            for split in ("development", "holdout")
        )
    ):
        raise ValueError("expected 120 cases: 60/60, six categories of 20, each split 10/category")
    return {
        "total": len(cases),
        "splits": dict(splits),
        "categories": dict(categories),
        "labels": dict(Counter(c.label_status for c in cases)),
        "issue_groups": len(groups),
        "source_documents": len(sources),
        "suite_sha256": fingerprint([c.model_dump(mode="json") for c in cases]),
        "leakage_check": "passed",
    }


def anchor_matches(anchor: EvidenceAnchor, chunk: Any) -> bool:
    """Quote and source identity survive chunk-ID changes; IDs are diagnostic mappings only."""
    return anchor.source_id == chunk.source_id and normalized(anchor.quote) in normalized(
        chunk.text
    )


def wrong_applicability(case: QualityCase, chunk: Any, source: Any) -> bool:
    audiences = set(chunk.audiences)
    if (
        case.audience != "all"
        and not audiences & {"all", "unknown"}
        and case.audience not in audiences
    ):
        return True
    if chunk.academic_year and case.academic_year and chunk.academic_year != case.academic_year:
        return True
    if chunk.valid_from and chunk.valid_from > case.today:
        return True
    if chunk.valid_until and chunk.valid_until < case.today:
        return True
    campuses = set(getattr(chunk, "campuses", ()))
    if campuses and case.campus and not campuses & {case.campus, "all", "unknown"}:
        return True
    return (
        not chunk.enabled
        or chunk.kind in {"historical", "deprecated"}
        or source.temporal_status == "superseded"
        or (source.temporal_status == "historical" and not getattr(chunk, "stale", False))
    )


def uncertain_applicability(case: QualityCase, chunk: Any, source: Any) -> bool:
    """Unknown applicability and possibly-old facts are risks, not proven scope violations."""
    return (
        "unknown" in set(getattr(chunk, "campuses", ()))
        or "unknown" in set(chunk.audiences)
        or bool(getattr(chunk, "stale", False))
        or source.temporal_status == "unknown"
    )


def _mean(values: Iterable[float]) -> float | None:
    rows = tuple(values)
    return round(sum(rows) / len(rows), 4) if rows else None


def evaluate_quality(
    cases: Sequence[QualityCase],
    snapshot: Any,
    observations: Sequence[Observation],
    reviews: Sequence[AnswerReview] = (),
    *,
    required_checks_passed: bool = False,
    raw_anchors_validated: bool = False,
) -> dict[str, Any]:
    suite = validate_suite(cases)
    case_map = {c.case_id: c for c in cases}
    for label, records in (("observation", observations), ("review", reviews)):
        ids = [r.case_id for r in records]
        if len(ids) != len(set(ids)) or set(ids) - set(case_map):
            raise ValueError(f"duplicate or unknown {label} case ID")
    obs_map = {o.case_id: o for o in observations}
    review_map = {r.case_id: r for r in reviews}
    chunks = {c.chunk_id: c for c in snapshot.chunks}
    sources = {s.source_id: s for s in snapshot.sources}
    rows: list[dict[str, Any]] = []
    for case in cases:
        obs, review = obs_map.get(case.case_id), review_map.get(case.case_id)
        if obs and (
            obs.case_sha256 != fingerprint(case.model_dump(mode="json"))
            or obs.knowledge_version != snapshot.version
        ):
            raise ValueError(f"observation binding mismatch: {case.case_id}")
        if obs and set(obs.ranked_chunk_ids + obs.shown_chunk_ids) - set(chunks):
            raise ValueError(f"unknown retrieved chunk: {case.case_id}")
        if review and (
            not obs or review.observation_sha256 != fingerprint(obs.model_dump(mode="json"))
        ):
            raise ValueError(f"review binding mismatch: {case.case_id}")
        ranked = [chunks[i] for i in obs.ranked_chunk_ids] if obs else []
        matched = {
            e.evidence_id
            for e in case.evidence
            if any(anchor_matches(e, chunk) for chunk in ranked[:5])
        }
        answerable = case.expected_behavior in {"answer", "partial"}
        rank = next(
            (
                i + 1
                for i, ch in enumerate(ranked[:20])
                if any(anchor_matches(e, ch) for e in case.evidence)
            ),
            None,
        )
        checks = (
            (
                review.fact_correct,
                review.necessary_facts_complete,
                review.citation_support,
                review.citation_coverage,
                review.behavior_correct,
                review.actionable_next_step,
            )
            if review
            else ()
        )
        reviewed = bool(
            review
            and review.status == "source_checked"
            and obs
            and obs.answer is not None
            and obs.behavior is not None
        )
        passed = bool(
            case.label_status == "source_checked"
            and review is not None
            and obs is not None
            and reviewed
            and checks
            and all(check is True for check in checks)
            and not review.critical_errors
            and obs.behavior == case.expected_behavior
        )
        shown = [chunks[i] for i in obs.shown_chunk_ids] if obs else []
        rows.append(
            {
                "case_id": case.case_id,
                "split": case.split,
                "category": case.category,
                "expected_behavior": case.expected_behavior,
                "label_status": case.label_status,
                "observation_present": obs is not None,
                "answer_reviewed": reviewed,
                "retrieval_evidence_recall@5": len(matched) / len(case.evidence)
                if case.evidence and answerable and case.retrieval_required and obs
                else None,
                "retrieval_reciprocal_rank@20": (1 / rank if rank else 0)
                if case.evidence and answerable and case.retrieval_required and obs
                else None,
                "retrieval_complete_evidence@5": float(len(matched) == len(case.evidence))
                if case.evidence and answerable and case.retrieval_required and obs
                else None,
                "wrong_applicability_hits@5": sum(
                    wrong_applicability(case, c, sources[c.source_id]) for c in ranked[:5]
                ),
                "uncertain_applicability_hits@5": sum(
                    uncertain_applicability(case, c, sources[c.source_id]) for c in ranked[:5]
                ),
                "retrieved_count@5": len(ranked[:5]),
                "shown_excerpt_gold_overlap": sum(
                    any(anchor_matches(e, ch) for e in case.evidence) for ch in shown
                )
                / len(shown)
                if shown
                else None,
                "critical_errors": list(review.critical_errors) if review else [],
                "passed": passed,
                "status": "passed" if passed else "failed" if reviewed else "unassessed",
            }
        )
    metrics: dict[str, Any] = {}
    for split in ("development", "holdout"):
        selected = [r for r in rows if r["split"] == split]
        metrics[split] = {
            "n": len(selected),
            "retrieval_n": sum(r["retrieval_evidence_recall@5"] is not None for r in selected),
            **{
                name: _mean(r[name] for r in selected if r[name] is not None)
                for name in (
                    "retrieval_evidence_recall@5",
                    "retrieval_reciprocal_rank@20",
                    "retrieval_complete_evidence@5",
                    "shown_excerpt_gold_overlap",
                )
            },
            "wrong_applicability_hit_rate@5": (
                sum(r["wrong_applicability_hits@5"] for r in selected)
                / sum(r["retrieved_count@5"] for r in selected)
            )
            if sum(r["retrieved_count@5"] for r in selected)
            else None,
            "answerable": _answer_counts(selected, {"answer", "partial"}),
            "uncertain_applicability_hit_rate@5": (
                sum(r["uncertain_applicability_hits@5"] for r in selected)
                / sum(r["retrieved_count@5"] for r in selected)
            ) if sum(r["retrieved_count@5"] for r in selected) else None,
            "clarification_or_refusal": _answer_counts(selected, {"clarify", "refuse"}),
            "categories": {
                cat: {
                    "n": sum(r["category"] == cat for r in selected),
                    "passed": sum(r["category"] == cat and r["passed"] for r in selected),
                }
                for cat in CATEGORIES
            },
        }
    holdout = [r for r in rows if r["split"] == "holdout"]
    blocked: list[str] = []
    try:
        validate_suite(cases, require_full=True)
    except ValueError:
        blocked.append("suite_requires_120_balanced_disjoint_cases")
    if len(holdout) != 60:
        blocked.append("holdout_requires_60_cases")
    if any(c.label_status != "source_checked" for c in cases):
        blocked.append("gold_labels_not_all_source_checked")
    if any(not r["answer_reviewed"] for r in holdout):
        blocked.append("holdout_answer_reviews_incomplete")
    if sum(r["passed"] for r in holdout) < 54:
        blocked.append("holdout_passes_below_54")
    if any(r["critical_errors"] for r in rows):
        blocked.append("critical_factual_error")
    if not required_checks_passed:
        blocked.append("required_regression_checks_not_recorded_passed")
    if not raw_anchors_validated:
        blocked.append("raw_anchor_audit_not_complete")
    return {
        "schema_version": 1,
        "knowledge_version": snapshot.version,
        "suite": suite,
        "metrics": metrics,
        "per_case": rows,
        "release_gate": {
            "passed": not blocked,
            "blockers": blocked,
            "holdout_passed": sum(r["passed"] for r in holdout),
            "holdout_required": 54,
            "holdout_total_required": 60,
        },
        "measurement": {
            "cost_usd": sum(o.cost_usd for o in observations),
            "latency_ms_total": sum(o.latency_ms for o in observations),
            "execution_modes": sorted({o.execution_mode for o in observations}),
            "answer_quality_is_not_retrieval_overlap": True,
        },
    }


def _answer_counts(rows: Sequence[dict[str, Any]], behaviors: set[str]) -> dict[str, int]:
    selected = [r for r in rows if r["expected_behavior"] in behaviors]
    return {
        "n": len(selected),
        "reviewed": sum(r["answer_reviewed"] for r in selected),
        "passed": sum(r["passed"] for r in selected),
    }
