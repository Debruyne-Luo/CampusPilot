"""Local maintenance commands. Credentials are read from the environment or private files."""

import argparse
import asyncio
import json
import os
from pathlib import Path

from campuspilot.config import Settings
from campuspilot.dify import ChatUnavailable
from campuspilot.dify_knowledge import DifyKnowledgeClient
from campuspilot.knowledge_release import (
    atomic_write,
    compile_dify,
    embed_candidate,
    import_approved_archive,
    preview,
    publish,
    read_candidate,
    rollback,
    sidecar_template,
    write_candidate,
)
from campuspilot.llm.embedding import CloudflareEmbedder, EmbeddingUnavailable
from campuspilot.migration_config import secret
from campuspilot.rag import KnowledgeSnapshot, canonical
from campuspilot.retrieval.vector import INDEX_NAME, build_index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    approved = sub.add_parser("import-approved")
    approved.add_argument("--archive", type=Path, required=True)
    approved.add_argument("--output", type=Path, required=True)
    export = sub.add_parser("export-dify")
    export.add_argument("--dataset", action="append", required=True)
    export.add_argument("--output", type=Path, required=True)
    compile_parser = sub.add_parser("compile")
    compile_parser.add_argument("--snapshot", type=Path, required=True)
    compile_parser.add_argument("--sidecar", type=Path, required=True)
    compile_parser.add_argument("--output", type=Path, required=True)
    template = sub.add_parser("init-sidecar")
    template.add_argument("--snapshot", type=Path, required=True)
    template.add_argument("--knowledge", type=Path, required=True)
    template.add_argument("--output", type=Path, required=True)
    for name in ("preview", "publish"):
        p = sub.add_parser(name)
        p.add_argument("--candidate", type=Path, required=True)
        p.add_argument("--store", type=Path, required=True)
        if name == "publish":
            p.add_argument("--quality-report", type=Path,
                           help="Passing 120-case acceptance for a whole directory/RAG bundle")
            p.add_argument("--expected-current", required=True, help="version ID or none")
            p.add_argument("--fallback-bundle", default="",
                           help="approved bundle for first-publication recovery")
    embed = sub.add_parser("embed", help="build vectors.sqlite for a candidate (Cloudflare)")
    embed.add_argument("--candidate", type=Path, required=True)
    bootstrap = sub.add_parser("embed-bootstrap", help="index for the bootstrap snapshot")
    bootstrap.add_argument("--store", type=Path, required=True)
    package = sub.add_parser("import-package", help="reviewed package dir -> candidate")
    package.add_argument("--package", type=Path, required=True)
    package.add_argument("--base", type=Path, required=True, help="base candidate dir or JSON")
    package.add_argument("--approval", type=Path, required=True, help="approval record JSON")
    package.add_argument("--output", type=Path, required=True)
    back = sub.add_parser("rollback")
    back.add_argument("--store", type=Path, required=True)
    back.add_argument("--version", required=True)
    back.add_argument("--expected-current", required=True)
    args = parser.parse_args()
    try:
        if args.command == "import-approved":
            snapshot, files = import_approved_archive(args.archive)
            write_candidate(args.output, snapshot, files)
            result: object = {
                "candidate_version": snapshot.version,
                "chunks": len(snapshot.chunks),
                "published": False,
            }
        elif args.command == "import-package":
            from campuspilot.knowledge_package import build

            approval = json.loads(args.approval.read_bytes())
            if approval.get("status") != "approved_by_product_owner":
                raise ValueError("Missing approval record")
            base = (
                KnowledgeSnapshot.model_validate_json(args.base.read_bytes())
                if args.base.is_file()
                else read_candidate(args.base)
            )
            snapshot, files, report = build(args.package, base, approval)
            write_candidate(args.output, snapshot, files, report["excluded"])
            result = {
                **report,
                "excluded": len(report["excluded"]),
                "stale_chunks": len(report["stale_chunks"]),
                "published": False,
            }
        elif args.command == "export-dify":
            key = secret("DIFY_DATASET")
            client = DifyKnowledgeClient(
                key, os.environ.get("DIFY_DATASET_BASE_URL", "https://api.dify.ai/v1")
            )
            raw = asyncio.run(client.export(tuple(args.dataset)))
            if args.output.exists():
                raise ValueError("Snapshot output already exists")
            atomic_write(args.output, canonical(raw))
            result = {"exported": True, "datasets": len(raw["datasets"]), "published": False}
        elif args.command == "init-sidecar":
            if args.output.exists():
                raise ValueError("Sidecar output exists")
            raw = json.loads(args.snapshot.read_bytes())
            known = KnowledgeSnapshot.model_validate_json(args.knowledge.read_bytes())
            atomic_write(args.output, canonical(sidecar_template(raw, known)))
            result = {"review_required": True, "published": False}
        elif args.command == "compile":
            raw = json.loads(args.snapshot.read_bytes())
            sidecar = json.loads(args.sidecar.read_bytes())
            snapshot = compile_dify(raw, sidecar)
            exclusions = [b for b in sidecar["bindings"] if b.get("exclude_reason")]
            write_candidate(
                args.output,
                snapshot,
                {"dify.json": canonical(raw), "sidecar.json": canonical(sidecar)},
                exclusions,
            )
            result = {"candidate_version": snapshot.version, "published": False}
        elif args.command in {"embed", "embed-bootstrap"}:
            settings = Settings.from_env()
            embedder = CloudflareEmbedder(
                settings.cf_account_id,
                settings.cf_api_token,
                model=settings.embedding_model,
                timeout=30,
                retries=3,
            )
            if args.command == "embed":
                rows = embed_candidate(
                    args.candidate, embedder.embed, embedder.model, embedder.dimensions
                )
            else:
                snapshot = KnowledgeSnapshot.model_validate_json(
                    (args.store / "bootstrap.json").read_bytes()
                )
                rows = build_index(
                    args.store / ("bootstrap." + INDEX_NAME),
                    snapshot,
                    embedder.embed,
                    embedder.model,
                    embedder.dimensions,
                )
            result = {"indexed_chunks": rows, "model": embedder.model, "published": False}
        elif args.command == "preview":
            result = preview(args.candidate, args.store)
        elif args.command == "publish":
            version = publish(
                args.candidate,
                args.store,
                None if args.expected_current == "none" else args.expected_current,
                fallback_bundle=args.fallback_bundle,
                quality_report=args.quality_report,
            )
            result = {"published_version": version}
        else:
            version = rollback(
                args.store,
                args.version,
                None if args.expected_current == "none" else args.expected_current,
            )
            result = {"rolled_back_version": version}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, TypeError, ChatUnavailable, EmbeddingUnavailable) as exc:
        # Pydantic errors and HTTP messages can contain body/key material: never echo them.
        parser.exit(
            2, f"Knowledge operation failed ({type(exc).__name__}); live pointer unchanged.\n"
        )


if __name__ == "__main__":
    main()
