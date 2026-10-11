"""Offline calibration of the Jev plugin on recorded raw Jev answers (no API calls).

Input: an eval_jev_arms.py report run with ``--jev live``. Uses arm C (shadow): each case
has the unchanged baseline answer plus Jev's raw answer_mode distribution / confidence,
sufficient probability and per-chunk rank confidences. For each candidate Calibration the
``on`` arm is simulated: a case is refused when the baseline refused, or when the plugin
decision is insufficient / clarify and no non-knowledge evidence was found (the rule in
AgentRunner._with_jev). Selection: highest refusal recall with false refusal <= --max-fr.

With ``--baseline A.json --arm D_jev_on`` the baseline answers come from arm A and the
Jev records from arm D's planned-phase call (``phase`` absent); in-loop (``phase: answer``)
records change what the model sees and cannot be replayed offline, so they are ignored.

The selection is in-sample on dev; confirm on a held-out set before trusting the numbers.
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from typing import Any

from campuspilot.jev_plugin import DEFAULT_CALIBRATION, Calibration, combine
from campuspilot.jev_shadow import ShadowResult


def simulate(rows: list[dict[str, Any]], cal: Calibration) -> dict[str, Any]:
    ans = [r for r in rows if r["gold"]]
    ref = [r for r in rows if not r["gold"]]
    calls = unsure = 0
    refused: dict[str, bool] = {}
    decisions: dict[str, str] = {}
    for r in rows:
        rec = r.get("jev_record") or {}
        decision = "unknown"
        raw = rec.get("raw") or {}
        if rec:
            calls += 1
        if raw:
            result = ShadowResult(
                status="ok",
                answer_mode=raw["mode"],
                chunk_scores=tuple((x["chunk_id"], x["score"]) for x in raw["ranks"]),
                sufficient_probability=raw["sufficient"],
                raw=raw,
            )
            original = tuple(x["chunk_id"] for x in raw["ranks"]) + tuple(
                c
                for c in rec.get("dropped_ids") or []
                if c not in {x["chunk_id"] for x in raw["ranks"]}
            )
            a = combine(result, str(rec.get("local_grounding")), original, cal)
            unsure += a.status != "ok"
            decision = a.decision
        elif rec:
            unsure += 1  # unknown / timeout / error: no raw answers
        decisions[r["id"]] = decision
        refused[r["id"]] = r["refused"] or (
            decision in {"insufficient", "clarify"} and not rec.get("other_evidence")
        )
    rr = sum(refused[r["id"]] for r in ref)
    fr = sum(refused[r["id"]] for r in ans)
    return {
        "refusal_recall": rr / len(ref) if ref else 0.0,
        "false_refusal": fr / len(ans) if ans else 0.0,
        "refused": f"{rr}/{len(ref)}",
        "false_refused": f"{fr}/{len(ans)}",
        "unsure_rate": unsure / calls if calls else None,
        "jev_calls": calls,
        "false_refusal_ids": [r["id"] for r in ans if refused[r["id"]]],
        "decision_counts": {d: list(decisions.values()).count(d) for d in set(decisions.values())},
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("report", type=Path)
    p.add_argument("--arm", default="C_jev_shadow")
    p.add_argument("--max-fr", type=float, default=0.02)
    p.add_argument("--baseline", type=Path, help="report whose arm A supplies baseline answers")
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    rows = json.loads(a.report.read_text())["arms"][a.arm]["cases"]
    if a.baseline:
        base = {
            r["id"]: r for r in json.loads(a.baseline.read_text())["arms"]["A_current"]["cases"]
        }
        merged = []
        for r in rows:
            planned = [x for x in r.get("jev_records") or [] if not x.get("phase")]
            merged.append(
                {
                    **r,
                    "refused": base[r["id"]]["refused"],
                    "jev_record": planned[0] if planned else None,
                }
            )
        rows = merged
    baseline = simulate(rows, DEFAULT_CALIBRATION)
    grid = itertools.product(
        (0.0, 0.5, 0.6, 0.65, 0.7, 0.75),  # mode_confidence
        (0.0, 0.05, 0.1, 0.15),  # mode_margin
        (0.0, 0.5, 0.6, 0.7, 0.75),  # rank_confidence
        (0.6, 0.7, 0.8),  # sufficient_at
        (0.2, 0.3, 0.4, 0.5),  # insufficient_at
    )
    results = []
    for mc, mm, rc, sa, ia in grid:
        if ia >= sa:
            continue
        cal = Calibration(mc, mm, rc, DEFAULT_CALIBRATION.drop_below, sa, ia)
        results.append((cal, simulate(rows, cal)))
    ok = [x for x in results if x[1]["false_refusal"] <= a.max_fr]
    # Max recall; ties: fewest false refusals, then the strictest (most conservative) rule.
    ok.sort(
        key=lambda x: (
            -x[1]["refusal_recall"],
            x[1]["false_refusal"],
            -x[0].mode_confidence - x[0].mode_margin - x[0].rank_confidence,
            -x[0].sufficient_at + x[0].insufficient_at,
        )
    )
    best = ok[0] if ok else None
    report = {
        "arm": a.arm,
        "max_false_refusal": a.max_fr,
        "baseline_answers_only": simulate(rows, Calibration(2, 2, 2)),  # never certain
        "default": {"calibration": DEFAULT_CALIBRATION.__dict__, **baseline},
        "best": {"calibration": best[0].__dict__, **best[1]} if best else None,
        "top10": [{"calibration": c.__dict__, **m} for c, m in ok[:10]],
        "grid_size": len(results),
        "feasible": len(ok),
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if a.output:
        a.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
