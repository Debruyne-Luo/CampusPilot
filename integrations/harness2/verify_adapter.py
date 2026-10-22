"""No-model contract exercise through the actual upstream recursion and campus surface."""

import json
import pathlib
import sys
import tempfile

from campus_adapter import CampusAdapter, profile
from harness2.core.proposer import Proposer, Reply
from harness2.core.schedule import run_domain


class ScriptedEditor(Proposer):
    def call(self, mission, context_dir, label, **kwargs):
        context = pathlib.Path(context_dir)
        workspace = None
        if label.startswith("experience."):
            text = "<edits>fixture edit</edits><experience>NO_ENTRY</experience>"
        else:
            workspace = context / "harness"
            (workspace / "answer_guidance.md").write_text(
                "SYNTHETIC protocol guidance: preserve the supported part.", encoding="utf-8"
            )
            text = "<notes>Synthetic protocol test; no quality claim.</notes>"
        reply = Reply(label=label, text=text, ok=True, attempts=1, workspace=workspace)
        self._calls.append(reply)
        return reply


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="campuspilot-adapter-test-") as temp:
        root = pathlib.Path(temp)
        worker = root / "fixture_worker.py"
        worker.write_text("""import json,sys
r=json.load(sys.stdin)
print(json.dumps({"body":{"answer":"SYNTHETIC protocol answer","result_status":"success"},
"events":[],"profile":r.get("profile"),"latency_ms":1}))
""")
        config = {
            "data_dir": str(root),
            "knowledge_version": "synthetic",
            "model": "synthetic",
            "jev_model": "synthetic",
            "code_identity": "synthetic",
            "directory_hashes": {},
            "gateway": "http://127.0.0.1:1",
            "gateway_token": "synthetic",
            "campus_python": sys.executable,
            "worker": str(worker),
            "workspace": str(root),
        }
        adapter = CampusAdapter(
            config,
            [{"id": "fixture", "split": "development", "question": "SYNTHETIC protocol task"}],
            root / "experiment",
        )
        editor = ScriptedEditor(adapter.spec.channels["proposer"])
        result = run_domain(
            "campus",
            adapter.tasks(),
            1,
            adapter=adapter,
            prop=editor,
            runs_root=adapter.spec.runs_root,
            library_root=root / "library",
            modes=("seq",),
            seed=20,
        )
        assert result["done"] == 1 and result["failed"] == 0, result
        assert len(editor._calls) >= 3
        for invalid in [
            {"answer_guidance.md": "x", "tools.py": "print(1)"},
            {"answer_guidance.md": "https://school.example", "tool_guidance.md": ""},
        ]:
            try:
                profile(invalid)
            except ValueError:
                pass
            else:
                raise AssertionError("Off-surface strategy accepted")
        print(
            json.dumps(
                {
                    "upstream_core": True,
                    "campus_surface": True,
                    "editor_calls": len(editor._calls),
                    "tasks_done": result["done"],
                    "live_model": False,
                }
            )
        )


if __name__ == "__main__":
    main()
