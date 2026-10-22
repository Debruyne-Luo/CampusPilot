"""Export one public record per task, preserving the actual upstream stage evidence."""

from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Any

from campuspilot.agent_lab import LabExperiment
from campuspilot.harness_profile import HarnessProfile
from campuspilot.knowledge_release import atomic_write

PIN = "1cfe254e8d25b15f37048c3730134686abe60335"


def export_optimizer_run(
    root: Path,
    destination: Path,
    binding: dict[str, Any],
    tasks: list[dict[str, Any]],
    campaign_usd: float,
    running: bool,
) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    optimizer = root / "optimizer"
    results: dict[str, list[Path]] = {}
    for path in sorted((optimizer / "executions").rglob("result.json")):
        task_id = path.parent.parent.name
        results.setdefault(task_id, []).append(path)
    published = []
    task_map = {task["id"]: task for task in tasks}
    for ident, paths in results.items():
        if ident not in task_map:
            raise ValueError("Unknown exported task")
        stages, trials, changes = ["base"], [], []
        for path in paths:
            try:
                raw = json.loads(path.read_bytes())
            except OSError, ValueError:
                continue  # A concurrently written result is not yet publishable.
            body = raw["body"]
            prof = raw.get("profile")
            label = path.parent.name
            trials.append(
                {
                    "label": label,
                    "answer": body.get("answer", ""),
                    "tools": [
                        e["data"]["tool"] for e in raw["events"] if e["event"] == "tool_start"
                    ],
                    "status": body.get("result_status", "unknown"),
                    "latency_ms": round(raw["latency_ms"], 1),
                    "cost_usd": None,
                    "profile_sha256": prof["sha256"]
                    if prof
                    else HarnessProfile.create("baseline").sha256,
                }
            )
            profile_path = path.parent / "profile.json"
            candidate = json.loads(profile_path.read_bytes()) if profile_path.exists() else None
            if candidate:
                p = HarnessProfile.model_validate(candidate)
                delta = difflib.unified_diff(
                    [],
                    (p.answer_guidance + "\n" + p.tool_guidance).splitlines(),
                    fromfile="baseline",
                    tofile=p.version,
                    lineterm="",
                )
                changes.append("\n".join(delta))
            if not label.startswith("base"):
                if "propose" not in stages:
                    stages.extend(["propose", "probe"])
            if label.startswith("final") or label.startswith("seq") or label.startswith("c"):
                if "compose" not in stages:
                    stages.append("compose")
        summaries = list((optimizer / "runs").glob("*/" + ident + "/summary.json"))
        summary = json.loads(summaries[0].read_bytes()) if summaries else None
        lessons = ""
        if summary:
            selections = summary.get("selections", {})
            for selected in selections.values():
                if selected.get("experience"):
                    lessons += json.dumps(selected["experience"], ensure_ascii=False)
            if any("experience" in selected for selected in selections.values()):
                stages.append("experience")
                if not lessons:
                    lessons = "上游反思已完成，返回 NO_ENTRY：本轮未保存可复用经验。"
        status = (
            "completed"
            if summary and summary.get("status") == "ok"
            else "running"
            if running
            else "failed"
        )
        record = LabExperiment.model_validate(
            {
                "id": "campus-harness2-" + ident,
                "title": "校园策略优化 · " + task_map[ident]["category"],
                "kind": "campus_public_experiment",
                "status": status,
                "upstream_commit": PIN,
                "code_identity": binding["code_identity"],
                "knowledge_version": binding["knowledge_version"],
                "model": binding["model"],
                "question": task_map[ident]["question"],
                "stages": stages,
                "trials": trials[:20],
                "changes": "\n\n".join(changes)[:12000],
                "lessons": lessons[:6000],
                "cost_usd": campaign_usd,
                "limitation": (
                    "公开固定任务，词法检索。页面金额为整个实验活动的累计保守预算占用；"
                    "单次执行费用未单独拆分。完成递归不代表候选已通过独立验收。"
                ),
                "conclusion": "同一问题的真实执行对照；采用与否以独立开发/保留审查记录为准。",
            }
        )
        path = destination / (record.id + ".json")
        atomic_write(path, record.model_dump_json(indent=2).encode())
        published.append(path)
    return published
