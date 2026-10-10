"""Bind independent quality, shadow and API latency artifacts before a staged release."""

import argparse
import json
from pathlib import Path

from campuspilot.knowledge_release import atomic_write
from campuspilot.rag import canonical, digest
from campuspilot.release_gate import assess

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("phase1", "phase2"), required=True)
    for name in ("baseline", "independent-qa", "api-answers", "shadow", "performance"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        documents: dict[str, object] = {}
        for name in ("baseline", "independent_qa", "api_answers", "shadow", "performance"):
            content = getattr(args, name).read_bytes()
            documents[name] = json.loads(content)
            documents[name + "_sha256"] = digest(content)
        report = assess(ROOT, documents, args.stage)
        atomic_write(args.output, canonical(report))
        print(
            "RELEASE GATE "
            + str(report["release_gate"])
            + "; "
            + str(len(report["blockers"]))
            + " blocking conditions"
        )
        if report["release_gate"] != "PASS":
            raise SystemExit(2)
    except OSError, ValueError, KeyError, TypeError:
        parser.exit(2, "Gate artifacts missing or invalid; release stays closed.\n")


if __name__ == "__main__":
    main()
