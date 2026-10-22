"""Python 3.12 optional adapter. The optimizer executes CampusPilot in Python 3.14.

No pydantic/application imports here: only the JSON subprocess contract crosses runtimes.
Reference answers and review files are deliberately absent from this adapter.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import threading
from pathlib import Path

from harness2.core import tree
from harness2.core.proposer import Proposer
from harness2.core.spec import BenchPrompts, BenchSpec, ChannelSpec
from harness2.core.tree import SurfaceSpec

PIN = "1cfe254e8d25b15f37048c3730134686abe60335"
FILES = ("answer_guidance.md", "tool_guidance.md")
SURFACE = SurfaceSpec(
    name="campuspilot",
    always_on=FILES,
    always_on_max=12002,
    always_on_cap_reason="Only bounded guidance text is loaded by CampusPilot.",
    skill_dir="disabled_skills",
    skill_name_rule="unused",
    trigger_hint="",
    autotrigger_file=FILES[0],
    trigger_line="",
    subagent_requires_mode=True,
    plugin_dir=None,
    hooks_file=None,
)


def profile(values: dict[str, str]) -> dict:
    if set(values) != set(FILES) or any(len(v) > 6000 or "\x00" in v for v in values.values()):
        raise ValueError("Only the two bounded guidance files may be edited")
    if re.search(r"https?://|(?<!\w)\d{4,}|sk-[\w-]{16,}", "\n".join(values.values())):
        raise ValueError("Strategy must not contain URLs, credentials or factual identifiers")
    answer, tools = values[FILES[0]], values[FILES[1]]
    name = "h2-" + hashlib.sha256((answer + "\0" + tools).encode()).hexdigest()[:16]
    digest = hashlib.sha256(
        json.dumps([1, name, answer, tools], ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "schema_version": 1,
        "version": name,
        "answer_guidance": answer,
        "tool_guidance": tools,
        "sha256": digest,
    }


class CampusSubstrate:
    name = "campuspilot"

    def surface(self) -> SurfaceSpec:
        return SURFACE


class CampusAdapter:
    def __init__(self, config: dict, tasks: list[dict], root: Path) -> None:
        self.config, self.root = config, root.resolve()
        self._tasks = {row["id"]: row for row in tasks}
        self.substrate = CampusSubstrate()
        channel = ChannelSpec(
            "opencode", "campuspilot/deepseek-flash", effort="", steps=12, timeout=240
        )
        self.spec = BenchSpec(
            name="campuspilot",
            runs_root=self.root / "runs",
            install_mode="workspace_config",
            prompts=BenchPrompts(
                work="complete public campus information tasks with evidence",
                domain_word="campus assistance",
            ),
            channels={"proposer": channel, "selector": channel},
            allow_subagents=False,
            leak_globs=("*review*", "*gold*", "*holdout*"),
        )
        self.root.mkdir(parents=True, exist_ok=True)
        binding = {
            "tasks": tasks,
            "knowledge_version": config["knowledge_version"],
            "model": config["model"],
            "upstream": PIN,
            "code_identity": config["code_identity"],
            "directory_hashes": config["directory_hashes"],
        }
        identity = self.root / "binding.json"
        if identity.exists() and json.loads(identity.read_text()) != binding:
            raise ValueError("Cannot resume with changed tasks, source, knowledge or model")
        identity.write_text(json.dumps(binding, ensure_ascii=False, indent=2), encoding="utf-8")
        tree.write_tree(SURFACE, {FILES[0]: "", FILES[1]: ""}, self.base_harness(), stubs=False)
        self._lock = threading.Lock()

    def tasks(self, split: str = "development") -> list[str]:
        return [key for key, row in self._tasks.items() if row["split"] == split]

    def domain_of(self, task_id: str) -> str:
        return "campus"

    def task_prompt(self, task_id: str) -> str:
        return self._tasks[task_id]["question"]

    def task_files(self, task_id: str) -> None:
        return None

    def base_harness(self) -> Path:
        return self.root / "base"

    def validate_tree(self, values: dict[str, str]) -> None:
        profile(values)

    def execute(
        self, task_id: str, harness_dir: Path | None, run_id: str, *, timeout: int | None = None
    ) -> Path:
        run_dir = self.root / "executions" / run_id
        if not run_dir.resolve().is_relative_to(self.root / "executions"):
            raise ValueError("Invalid execution identity")
        with self._lock:
            if (run_dir / "result.json").exists():
                return run_dir
            if (run_dir / "started.json").exists():
                raise RuntimeError("Interrupted request outcome unknown; no automatic redispatch")
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "started.json").write_text(json.dumps({"task": task_id, "run": run_id}))
        rejected: list[str] = []
        values = tree.read_tree(SURFACE, harness_dir or self.base_harness(), rejected=rejected)
        self.validate_tree(values)
        if rejected:
            raise ValueError("Off-surface candidate files")
        selected = profile(values) if any(values.values()) else None
        payload = {
            key: self.config[key]
            for key in (
                "data_dir",
                "knowledge_version",
                "gateway",
                "gateway_token",
                "model",
                "jev_model",
            )
        }
        payload.update(
            question=self.task_prompt(task_id),
            profile=selected,
            jev_routing=False,
            jev_evidence=False,
            scratch=str(run_dir / "scratch"),
        )
        (run_dir / "profile.json").write_text(
            json.dumps(selected, ensure_ascii=False), encoding="utf-8"
        )
        result = subprocess.run(
            [self.config["campus_python"], self.config["worker"]],
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=timeout or 150,
            cwd=self.config["workspace"],
        )
        if result.returncode:
            (run_dir / "error.json").write_text(
                json.dumps({"status": "failed", "exit_code": result.returncode})
            )
            raise RuntimeError("CampusPilot worker failed; inspect local error record")
        output = json.loads(result.stdout)
        # Persist no ephemeral gateway token. The output contains only public fixtures.
        (run_dir / "result.json").write_text(
            json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        body = output["body"]
        transcript = "\n".join(
            "[ACTION] "
            + e["event"]
            + "\n[OBSERVATION] "
            + json.dumps(e["data"], ensure_ascii=False)
            for e in output["events"]
        )
        (run_dir / "trajectory.md").write_text(
            transcript + "\n[OBSERVATION] " + json.dumps(body, ensure_ascii=False), encoding="utf-8"
        )
        return run_dir

    def delivered(self, run_dir: Path) -> bool:
        return (run_dir / "result.json").is_file()

    def trajectory(self, run_dir: Path, *, obs_trunc: int) -> str:
        return (run_dir / "trajectory.md").read_text(encoding="utf-8")[:obs_trunc]

    def deliverable_text(self, run_dir: Path) -> str:
        return json.loads((run_dir / "result.json").read_text())["body"]["answer"]

    def deliverable_files(self, run_dir: Path) -> dict[str, str]:
        return {"answer.txt": self.deliverable_text(run_dir)}

    def score(self, run_dir: Path, task_id: str) -> None:
        # Independent answer reviews are collected after the optimizer has committed.
        return None


class MeteredProposer(Proposer):
    """Original OpenCode editing channel, using the campaign gateway for every LLM call."""

    def __init__(self, *args, gateway: str, token: str, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.gateway, self.token = gateway, token

    def env(self) -> dict[str, str]:
        env = {
            k: v
            for k, v in super().env().items()
            if not re.search(r"API_KEY|AUTH_TOKEN|PASSWORD|SECRET|KEY_FILE", k, re.I)
        }
        env["OPENCODE_CONFIG_CONTENT"] = json.dumps(
            {
                "$schema": "https://opencode.ai/config.json",
                "enabled_providers": ["campuspilot"],
                "provider": {
                    "campuspilot": {
                        "npm": "@ai-sdk/openai-compatible",
                        "name": "Metered",
                        "options": {"baseURL": self.gateway + "/v1", "apiKey": self.token},
                        "models": {
                            "deepseek-flash": {
                                "name": "deepseek-flash",
                                "limit": {"context": 128000, "output": 4096},
                            }
                        },
                    }
                },
                "permission": {
                    "bash": "deny",
                    "webfetch": "deny",
                    "websearch": "deny",
                    "task": "deny",
                    "external_directory": "deny",
                },
                "share": "disabled",
                "autoupdate": False,
            }
        )
        return env
