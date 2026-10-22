"""Quality evaluation contracts; generated fixtures are explicitly synthetic."""

import importlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from campuspilot.knowledge_evaluation import (
    CATEGORIES,
    AnswerReview,
    EvidenceAnchor,
    Observation,
    QualityCase,
    ReviewStatus,
    anchor_matches,
    evaluate_quality,
    fingerprint,
    legacy_behavior,
    validate_suite,
    wrong_applicability,
)

ROOT = Path(__file__).resolve().parents[1]


def synthetic_case(index: int = 0, *, checked: bool = False) -> QualityCase:
    check: ReviewStatus = "source_checked" if checked else "draft"
    anchor = EvidenceAnchor(
        evidence_id=f"synthetic:evidence:{index}",
        source_id=f"synthetic:source:{index}",
        source_url=f"https://synthetic.invalid/public/{index}",
        knowledge_version="synthetic-v1",
        source_revision_sha256="a" * 64,
        revision_kind="raw_body",
        locator="synthetic section 1",
        quote="SYNTHETIC rule requires approval",
        necessary_fact="SYNTHETIC approval required",
        chunk_ids=(f"synthetic:old-chunk:{index}",),
        raw_file="synthetic/test-only.txt",
        raw_sha256="b" * 64,
        check_status=check,
        checked_by="synthetic-source-checker" if checked else None,
        checked_at=date(2026, 10, 17) if checked else None,
    )
    return QualityCase(
        case_id=f"synthetic:{index}",
        question=f"SYNTHETIC question {index}",
        category=cast(Any, CATEGORIES[(index % 60) // 10]),
        split="development" if index < 60 else "holdout",
        issue_group=f"synthetic:issue:{index}",
        expected_behavior="answer",
        evidence=(anchor,),
        expected_next_step="SYNTHETIC next step",
        label_status=check,
        label_checked_by="synthetic-checker" if checked else None,
        label_checked_at=date(2026, 10, 17) if checked else None,
    )


def synthetic_chunk(index: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        chunk_id=f"synthetic:new-chunk:{index}",
        source_id=f"synthetic:source:{index}",
        text="SYNTHETIC rule requires approval. SYNTHETIC exception requires confirmation.",
        audiences=("all",),
        campuses=(),
        academic_year=None,
        valid_from=None,
        valid_until=None,
        enabled=True,
        kind="fact",
    )


def synthetic_snapshot(count: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        version="synthetic-v1",
        chunks=tuple(synthetic_chunk(i) for i in range(count)),
        sources=tuple(
            SimpleNamespace(source_id=f"synthetic:source:{i}", temporal_status="current")
            for i in range(count)
        ),
    )


def observation(case: QualityCase, *, answer: bool = False) -> Observation:
    index = int(case.case_id.split(":")[-1])
    return Observation(
        case_id=case.case_id,
        case_sha256=fingerprint(case.model_dump(mode="json")),
        knowledge_version="synthetic-v1",
        ranked_chunk_ids=(f"synthetic:new-chunk:{index}",),
        shown_chunk_ids=(f"synthetic:new-chunk:{index}",),
        answer="SYNTHETIC checked answer" if answer else None,
        behavior="answer" if answer else None,
    )


def review(obs: Observation) -> AnswerReview:
    return AnswerReview(
        case_id=obs.case_id,
        observation_sha256=fingerprint(obs.model_dump(mode="json")),
        status="source_checked",
        reviewed_by="synthetic-reviewer",
        reviewed_at=date(2026, 10, 17),
        fact_correct=True,
        necessary_facts_complete=True,
        citation_support=True,
        citation_coverage=True,
        behavior_correct=True,
        actionable_next_step=True,
        support_notes="SYNTHETIC evidence supports each synthetic assertion",
    )


def test_missing_gold_is_unlabeled_not_refusal() -> None:
    assert legacy_behavior({"chunk_ids": []}) == "unlabeled"
    assert legacy_behavior({"gold": []}) == "unlabeled"
    assert legacy_behavior({"chunk_ids": [], "answer_strategy": "direct"}) == "answer"
    assert legacy_behavior({"expected_behavior": "refuse"}) == "refuse"


def test_archived_reference_can_support_limit_without_requiring_current_retrieval() -> None:
    case = synthetic_case().model_copy(update={"retrieval_required": False})
    obs = observation(case).model_copy(update={"ranked_chunk_ids": (), "shown_chunk_ids": ()})
    report = evaluate_quality([case], synthetic_snapshot(), [obs])
    assert report["metrics"]["development"]["retrieval_n"] == 0
    assert report["per_case"][0]["retrieval_evidence_recall@5"] is None
    assert report["per_case"][0]["status"] == "unassessed"


def test_possibly_old_fact_is_distinct_from_proven_expiry() -> None:
    chunk = synthetic_chunk()
    chunk.stale = True
    source = SimpleNamespace(temporal_status="historical")
    case = synthetic_case()
    assert not wrong_applicability(case, chunk, source)
    chunk.valid_until = date(2020, 1, 1)
    assert wrong_applicability(case, chunk, source)


def test_answer_gold_without_evidence_is_invalid() -> None:
    with pytest.raises(ValueError, match="answerable gold requires evidence"):
        QualityCase.model_validate({**synthetic_case().model_dump(), "evidence": []})


@pytest.mark.parametrize(
    "field,value",
    [
        ("issue_group", "synthetic:issue:0"),
        ("evidence", synthetic_case().evidence),
        ("question", "SYNTHETIC question 0"),
    ],
)
def test_split_leakage_blocks_suite(field: str, value: object) -> None:
    held = synthetic_case(60).model_copy(update={field: value})
    with pytest.raises(ValueError, match="leakage"):
        validate_suite([synthetic_case(), held])


def test_source_url_alias_leakage_is_detected() -> None:
    first, held = synthetic_case(), synthetic_case(60)
    changed = held.evidence[0].model_copy(update={"source_url": first.evidence[0].source_url + "/"})
    with pytest.raises(ValueError, match="URL leakage"):
        validate_suite([first, held.model_copy(update={"evidence": (changed,)})])


def test_rechunked_ids_match_quote_without_claiming_answer_correctness() -> None:
    case = synthetic_case()
    assert anchor_matches(case.evidence[0], synthetic_chunk())
    report = evaluate_quality([case], synthetic_snapshot(), [observation(case)])
    row = report["per_case"][0]
    assert row["retrieval_evidence_recall@5"] == 1
    assert row["retrieval_complete_evidence@5"] == 1
    assert row["shown_excerpt_gold_overlap"] == 1
    assert row["status"] == "unassessed"
    assert not report["release_gate"]["passed"]


def test_complete_evidence_requires_all_clauses() -> None:
    case = synthetic_case()
    other = case.evidence[0].model_copy(
        update={"evidence_id": "synthetic:absent", "quote": "SYNTHETIC missing exception"}
    )
    case = case.model_copy(update={"evidence": (*case.evidence, other)})
    row = evaluate_quality([case], synthetic_snapshot(), [observation(case)])["per_case"][0]
    assert row["retrieval_evidence_recall@5"] == 0.5
    assert row["retrieval_complete_evidence@5"] == 0


def test_wrong_audience_is_separate_from_relevance() -> None:
    case = synthetic_case().model_copy(update={"audience": "graduate"})
    snapshot = synthetic_snapshot()
    snapshot.chunks[0].audiences = ("undergraduate",)
    row = evaluate_quality([case], snapshot, [observation(case)])["per_case"][0]
    assert row["retrieval_evidence_recall@5"] == 1
    assert row["wrong_applicability_hits@5"] == 1


def test_observation_and_review_bind_exact_case_and_output() -> None:
    case = synthetic_case()
    obs = observation(case, answer=True)
    with pytest.raises(ValueError, match="observation binding"):
        evaluate_quality(
            [case], synthetic_snapshot(), [obs.model_copy(update={"case_sha256": "changed"})]
        )
    with pytest.raises(ValueError, match="review binding"):
        evaluate_quality(
            [case],
            synthetic_snapshot(),
            [obs.model_copy(update={"answer": "changed"})],
            [review(obs)],
        )


def test_no_answer_and_unlabeled_are_separate_from_answerable() -> None:
    first = synthetic_case()
    second = synthetic_case(1).model_copy(update={"expected_behavior": "clarify"})
    third = synthetic_case(2).model_copy(update={"expected_behavior": "unlabeled", "evidence": ()})
    report = evaluate_quality([first, second, third], synthetic_snapshot(3), [])
    assert report["metrics"]["development"]["answerable"]["n"] == 1
    assert report["metrics"]["development"]["clarification_or_refusal"]["n"] == 1
    assert report["metrics"]["development"]["retrieval_n"] == 0


def test_gate_accepts_54_of_60_with_checked_gold_reviews_and_regressions() -> None:
    cases = [synthetic_case(i, checked=True) for i in range(120)]
    observations = [observation(c, answer=True) for c in cases]
    reviews = [review(o) for o in observations]
    for i in range(114, 120):
        reviews[i] = reviews[i].model_copy(update={"necessary_facts_complete": False})
    report = evaluate_quality(
        cases,
        synthetic_snapshot(120),
        observations,
        reviews,
        required_checks_passed=True,
        raw_anchors_validated=True,
    )
    assert report["release_gate"]["passed"]
    assert report["release_gate"]["holdout_passed"] == 54
    reviews[113] = reviews[113].model_copy(update={"citation_support": False})
    report = evaluate_quality(
        cases,
        synthetic_snapshot(120),
        observations,
        reviews,
        required_checks_passed=True,
        raw_anchors_validated=True,
    )
    assert "holdout_passes_below_54" in report["release_gate"]["blockers"]


def test_critical_error_or_unreviewed_gold_blocks_gate() -> None:
    cases = [synthetic_case(i, checked=True) for i in range(120)]
    observations = [observation(c, answer=True) for c in cases]
    reviews = [review(o) for o in observations]
    reviews[0] = reviews[0].model_copy(update={"critical_errors": ("amount",)})
    report = evaluate_quality(
        cases,
        synthetic_snapshot(120),
        observations,
        reviews,
        required_checks_passed=True,
        raw_anchors_validated=True,
    )
    assert "critical_factual_error" in report["release_gate"]["blockers"]
    cases[0] = synthetic_case()
    observations[0] = observation(cases[0], answer=True)
    reviews[0] = review(observations[0])
    report = evaluate_quality(
        cases,
        synthetic_snapshot(120),
        observations,
        reviews,
        required_checks_passed=True,
        raw_anchors_validated=True,
    )
    assert "gold_labels_not_all_source_checked" in report["release_gate"]["blockers"]


def test_frozen_public_suite_balanced_and_bound_to_manifest() -> None:
    path = ROOT / "evaluation/knowledge-quality-20261017/cases.jsonl"
    cases = [
        QualityCase.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    manifest = json.loads(path.with_name("manifest.json").read_text(encoding="utf-8"))
    report = validate_suite(cases, require_full=True)
    assert report["suite_sha256"] == manifest["suite_sha256"]
    assert report["total"] == 120
    assert all(c.public_fixture for c in cases)
    assert report["labels"] == {"draft": 82, "source_checked": 38}
    assert sum(not c.retrieval_required for c in cases) == 32
    for case in cases:
        if case.label_status == "source_checked":
            assert case.label_checked_by == "agent-independent-gold-review-20261017"
            assert case.label_checked_at == date(2026, 10, 17)
            assert all(e.raw_file and e.raw_sha256 and e.check_status == "source_checked"
                       for e in case.evidence)
    assert len({c.issue_group for c in cases}) == 24


def test_legacy_retrieval_does_not_call_empty_results_correct_refusals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "evaluation"))
    legacy = importlib.import_module("eval_colloquial")

    class EmptyRetriever:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def search(self, *args: object, **kwargs: object) -> list[object]:
            return []

    monkeypatch.setattr(legacy, "HybridRetriever", EmptyRetriever)
    result, _ = legacy.evaluate(
        [{"id": "synthetic", "question": "SYNTHETIC", "gold": []}], None, None, {}, ["lexical"]
    )
    assert "refusal_correct" not in result["lexical"]
    assert result["lexical"]["no_gold_empty_retrieval"] == "1/1"


def test_legacy_excerpt_overlap_is_not_citation_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "evaluation"))
    legacy = importlib.import_module("eval_jev_arms")
    row = {
        "id": "synthetic",
        "gold": [],
        "refused": True,
        "excerpt_ids": [],
        "citations": [],
        "jev_status": None,
        "latency_ms": 1,
        "jev_latency_ms": None,
    }
    result = legacy.summarize([row], Decimal(0))
    assert result["n_unlabeled"] == 1
    assert result["refusal_recall"] == "0/0"
    assert "citation_precision" not in result
    assert result["citation_factual_support"] == "UNASSESSED_REQUIRES_CLAIM_REVIEW"
