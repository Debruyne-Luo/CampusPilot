"""Python 3.12 entry: run the pinned upstream recursion against the campus adapter."""

import json
import pathlib
import sys

from campus_adapter import CampusAdapter, MeteredProposer
from harness2.core.schedule import run_domain


def main() -> int:
    config = json.load(sys.stdin)
    root = pathlib.Path(config["run_dir"])
    tasks = json.loads(pathlib.Path(config["tasks_file"]).read_text())
    development = [t for t in tasks if t["split"] == "development"][:4]
    adapter = CampusAdapter(config, development, root)
    proposer = MeteredProposer(
        adapter.spec.channels["proposer"],
        audit_dir=root / "editor-audit",
        attempts=1,
        gateway=config["gateway"],
        token=config["gateway_token"],
    )
    result = run_domain(
        "campus",
        adapter.tasks(),
        1,
        adapter=adapter,
        prop=proposer,
        runs_root=adapter.spec.runs_root,
        library_root=root / "library",
        modes=("seq",),
        seed=20,
        pool_policy="finals",
    )
    (root / "optimizer-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return int(result["failed"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
