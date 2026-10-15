"""Import complete official browser exports into a local RAG candidate.

Use extract to obtain unapproved exact-text candidates, annotate them after checking the
actual document, and compile. Embed/preview/publish/rollback remain knowledge_release.py
commands. This command never changes the active knowledge pointer.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from campuspilot.knowledge_release import atomic_write, read_candidate, write_candidate
from campuspilot.official_knowledge import (
    build,
    capture_artifacts,
    discovery_files,
    extract,
    load_package,
    parse_attachment,
)
from campuspilot.rag import KnowledgeSnapshot, canonical

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    extraction = sub.add_parser("extract", help="complete captures -> unapproved exact paragraphs")
    extraction.add_argument("--package", type=Path, required=True)
    extraction.add_argument("--output", type=Path, required=True)
    compilation = sub.add_parser("compile", help="checked clauses -> immutable candidate")
    compilation.add_argument("--package", type=Path, required=True)
    compilation.add_argument("--annotations", type=Path)
    compilation.add_argument("--base", type=Path,
                             default=ROOT / "data/cdut/rag/approved-20261011b")
    compilation.add_argument("--output", type=Path, required=True)
    compilation.add_argument("--check-only", action="store_true")
    attachment = sub.add_parser("parse-attachment", help="local PDF/XLSX -> unchecked text")
    attachment.add_argument("--file", type=Path, required=True)
    attachment.add_argument("--format", choices=["pdf", "xlsx"], required=True)
    attachment.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError("Output already exists")
        if args.command == "extract":
            result = extract(args.package)
            atomic_write(args.output, canonical(result))
            report: object = {"candidate_documents": len(result["documents"]),
                              "adopted": False, "published": False}
        elif args.command == "parse-attachment":
            text = parse_attachment(args.file, args.format)
            atomic_write(args.output, text.encode())
            report = {"characters": len(text), "transcription_checked": False,
                      "published": False}
        else:
            prior_raw: dict[str, bytes] = {}
            if args.base.is_file():
                base = KnowledgeSnapshot.model_validate_json(args.base.read_bytes())
            else:
                base = read_candidate(args.base)
                manifest = json.loads((args.base / "manifest.json").read_bytes())
                prior_raw = {name[4:]: (args.base / name).read_bytes()
                             for name in manifest["files_sha256"] if name.startswith("raw/")}
            package = args.package
            # A separate annotation file leaves the original browser capture immutable.
            with tempfile.TemporaryDirectory(prefix="campuspilot-official-") as temporary:
                if args.annotations:
                    capture = load_package(package)
                    annotations = json.loads(args.annotations.read_bytes())
                    if not isinstance(annotations, dict) or not isinstance(
                        annotations.get("documents"), list
                    ):
                        raise ValueError("Invalid annotation documents")
                    rows = annotations["documents"]
                    if any(not isinstance(row, dict)
                           or not isinstance(row.get("document_id"), str)
                           or not isinstance(row.get("clauses"), list) for row in rows):
                        raise ValueError("Invalid annotation record")
                    by_id = {row["document_id"]: row["clauses"] for row in rows}
                    captured_ids = {document["document_id"] for document in capture["documents"]
                                    if isinstance(document, dict)
                                    and isinstance(document.get("document_id"), str)}
                    if len(by_id) != len(rows) or set(by_id) - captured_ids:
                        raise ValueError("Invalid annotation document mapping")
                    for document in capture["documents"]:
                        if isinstance(document, dict) and document.get("document_id") in by_id:
                            document["clauses"] = by_id[document["document_id"]]
                    # Copy only explicitly referenced capture files; never copy browser profiles.
                    staged = Path(temporary)
                    for name, content in discovery_files(package, capture).items():
                        target = staged / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(content)
                    for document in capture["documents"]:
                        if not isinstance(document, dict):
                            continue  # build() records the malformed row as one failed capture.
                        try:
                            names = [document.get("body_file"), document.get("original_file")]
                            for item in capture_artifacts(document):
                                names.extend((item.get("file"), item.get("text_file")))
                            for name in filter(None, names):
                                from campuspilot.official_knowledge import _file

                                data = _file(package, name)
                                target = staged / name.replace("\\", "/")
                                target.parent.mkdir(parents=True, exist_ok=True)
                                target.write_bytes(data)
                        except (ValueError, OSError, KeyError, TypeError):
                            # One bad capture must not prevent the other checked documents
                            # from producing a candidate; keep its last successful clauses.
                            document["status"] = "failed"
                            document["failure_reason"] = "invalid_capture_file"
                    (staged / "manifest.json").write_bytes(canonical(capture))
                    package = staged
                snapshot, raw, report = build(package, base, prior_raw=prior_raw)
                if not args.check_only and not report["unchanged"]:
                    write_candidate(args.output, snapshot, raw, report["excluded"])
                report = {**report, "candidate_written": not args.check_only
                          and not report["unchanged"]}
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"Official knowledge operation failed ({type(exc).__name__}); "
                    "active knowledge unchanged.\n")


if __name__ == "__main__":
    main()
