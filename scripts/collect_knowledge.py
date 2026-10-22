"""Explicit free-only pilot, source inventory and checked capture packaging.

No command publishes knowledge. API keys come from the environment or a repository-external
file and never appear in reports. Existing public captures are reused by inventory.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from campuspilot.knowledge_release import atomic_write
from campuspilot.official_capture import (
    FirecrawlCollector,
    embedded_images,
    public_url,
    reviewed_capture,
)
from campuspilot.rag import KnowledgeSnapshot, canonical, digest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/cdut/rag/versions/kb-229ee34eba99ef34"
PILOT = [
    ("html", "https://lib.cdut.edu.cn/fw/ssfw/zzwyty.htm", "图书馆自助文印"),
    ("html", "https://clhq.cdut.edu.cn/fwdt1/lyfw.htm", "楼寓服务"),
    ("pdf", "https://dbxb.cdut.edu.cn/__local/7/B6/E5/"
     "006AC04D88A214D1AD8B1F5E540_16B4A5B7_C543C.pdf", "学籍管理办法"),
    ("html", "https://cist.cdut.edu.cn/szdw/JSML.htm", "教师名录"),
    ("html", "https://faculty.cdut.edu.cn/wanghonghui/zh_CN/index.htm", "教师主页"),
    ("html", "https://gra.cdut.edu.cn/info/1007/5283.htm", "研究生证明"),
    ("html", "https://jcc.cdut.edu.cn/info/1012/2724.htm", "缴费通知"),
    ("html", "https://aao.cdut.edu.cn/info/1171/7107.htm", "嵌入PDF通知"),
    ("html", "https://dag.cdut.edu.cn/info/1076/1753.htm", "档案附件"),
    ("html", "https://mee.cdut.edu.cn/info/1049/3682.htm", "毕业离校附件"),
    ("html", "https://mp.weixin.qq.com/s/37b1EidELwZnhfLEiCDtjA", "公众号缴费"),
    ("html", "https://mp.weixin.qq.com/s/BZ85K3YUUEtcyf7SqGl0ZA", "公众号票据图片"),
]


def inventory(base: Path, catalog: Path | None) -> dict:
    snapshot = KnowledgeSnapshot.model_validate_json((base / "snapshot.json").read_bytes())
    rows: dict[str, dict] = {}
    for source in snapshot.sources:
        parts = urlsplit(source.url)
        url = urlunsplit(("https", parts.netloc.lower(), parts.path, parts.query, ""))
        row = rows.setdefault(url, {
            "url": url, "source_ids": [], "topics": [], "status": "pending_recheck",
            "scope": "成都校区及全校通用政策；原文适用范围待逐项复核",
            "column_pagination_audited": False, "attachments_audited": False,
            "existing_knowledge_version": snapshot.version, "existing_chunk_ids": [],
        })
        row["source_ids"].append(source.source_id)
        for chunk in snapshot.chunks:
            if chunk.source_id == source.source_id:
                row["existing_chunk_ids"].append(chunk.chunk_id)
                row["topics"].append(chunk.topic_id)
        row["topics"] = sorted(set(row["topics"]))
    catalog_count = 0
    if catalog and catalog.exists():
        for service in json.loads(catalog.read_bytes()):
            audiences = set(service.get("audiences", []))
            in_scope = bool(audiences & {"undergraduate", "graduate", "all"})
            named_yibin = "宜宾" in str(service.get("name", ""))
            in_scope = in_scope and not named_yibin
            url = service.get("detail_url") or service.get("source_url")
            ident = "catalog:" + str(service.get("service_id") or service.get("code"))
            rows[ident] = {
                "url": url, "catalog_id": service.get("service_id"), "title": service.get("name"),
                "department": service.get("department"), "audiences": sorted(audiences),
                "status": "pending_recheck" if in_scope else "out_of_scope",
                "scope_reason": "student_catalog" if in_scope else (
                    "yibin_only" if named_yibin else "staff_or_audience_unknown"),
                "existing_capture_reused": True, "attachments_audited": False,
            }
            catalog_count += 1
    return {
        "schema_version": 1, "base_version": snapshot.version,
        "base_snapshot_sha256": digest((base / "snapshot.json").read_bytes()),
        "scope": {"campuses": ["成都校区", "全校通用"],
                  "audiences": ["undergraduate", "graduate"]},
        "coverage_denominator": "enumerated_sources_only_not_entire_university_web",
        "site_completeness_verified": False, "catalog_records_reused": catalog_count,
        "status_counts": dict(Counter(r["status"] for r in rows.values())),
        "items": list(rows.values()),
    }


def coverage(
    inventory_path: Path, collection_path: Path, source_review_path: Path | None = None,
) -> dict:
    result = json.loads(inventory_path.read_bytes())
    ledger = json.loads(collection_path.read_bytes())
    by_url = {row["url"]: row for row in ledger["requests"]}
    image_dependencies = []
    for request in ledger["requests"]:
        body_file = collection_path.parent / request["document_id"] / "body.md"
        if body_file.exists():
            image_dependencies.extend(embedded_images(request["url"],
                                      body_file.read_text(encoding="utf-8")))
    for row in result["items"]:
        request = by_url.get(row.get("url"))
        if request and row["status"] != "out_of_scope":
            row["status"] = request["status"]
            row["collection_reason"] = request["reason"]
            row["collection_record"] = request["document_id"]
            row["attachments_audited"] = False
    # Preserve this ledger's original pilot statuses. A later checked clause is a
    # separate stage; it does not make a whole source/site completely reviewed.
    result["inventory_status_counts"] = result["status_counts"]
    result["status_counts"] = dict(Counter(r["status"] for r in result["items"]))
    result["enumerated_scope"] = {
        "inventory_rows": len(result["items"]),
        "unique_urls": len({row["url"] for row in result["items"]}),
        "denominator_is_site_total": False,
        "status_counts_stage": "inventory_plus_original_provider_pilot",
        "catalog_rows_may_overlap_source_rows": True,
        "whole_site_coverage_percent": None,
        "column_pagination_audit_complete": False,
        "all_attachments_audit_complete": False,
    }
    article_images = [image for image in image_dependencies
                      if "#imgIndex=" in image["url"]]
    result["pilot"] = {
        "entries_attempted": len(ledger["requests"]),
        "status_counts": dict(Counter(r["status"] for r in ledger["requests"])),
        "reserved_credits": ledger["reserved_credits"],
        "initial_balance": ledger["initial_remaining_credits"],
        "last_observed_balance": ledger["requests"][-1].get("balance_after"),
        "discovered_attachments": ledger.get("discovered_attachments", []),
        "embedded_image_dependencies": image_dependencies,
        "embedded_image_reference_count": len(image_dependencies),
        "article_image_reference_count": len(article_images),
        "other_image_reference_count": len(image_dependencies) - len(article_images),
        "article_image_references_by_parent": dict(Counter(
            image["parent_url"] for image in article_images)),
        "image_reference_counts_are_not_unique_assets": True,
        "image_content_relevance_review_complete": False,
        "coverage_is_not_provider_completion": True,
        "provider_adoption_completed": False,
    }
    if source_review_path:
        review_bytes = source_review_path.read_bytes()
        review = json.loads(review_bytes)
        checked = [doc for doc in review["documents"]
                   if doc["status"].startswith("verified_source_clauses")]
        pending = [doc for doc in review["documents"] if doc["status"] == "pending_review"]
        checked_by_url = {}
        for doc in checked:
            source_id = "cdut:source:official:" + doc["document_id"]
            if doc.get("stable_clause_upsert"):
                source_id = doc["stable_clause_upsert"].replace(
                    "cdut:chunk:", "cdut:source:", 1).rsplit(":", 1)[0]
            for row in result["items"]:
                if source_id in row.get("source_ids", []):
                    checked_by_url[row["url"]] = doc
        matched_rows = 0
        for row in result["items"]:
            checked_doc = checked_by_url.get(row.get("url"))
            if checked_doc:
                row["targeted_review"] = {
                    "document_id": checked_doc["document_id"],
                    "status": "selected_clauses_checked_for_candidate",
                    "whole_source_review_complete": False,
                    "original_collection_status_preserved": True,
                }
                matched_rows += 1
        result["targeted_review"] = {
            "review_report_sha256": digest(review_bytes),
            "reviewed_on": review["reviewed_on"],
            "scope": "selected_clauses_in_five_existing_documents",
            "coverage": review["coverage"],
            "documents_checked_for_candidate": len(checked),
            "clauses_checked_for_candidate": review["coverage"]["new_image_clauses"]
            + review["coverage"]["legacy_clause_upserts"],
            "matched_inventory_rows": matched_rows,
            "matched_unique_urls": len(checked_by_url),
            "complete_source_count_not_claimed": True,
            "image_flow_transcriptions_checked": sum(
                doc.get("image_review") == "visual_original_png_checked" for doc in checked),
            "pdf_local_fallback": [
                {"document_id": doc["document_id"], "pages_downloaded": doc["pages"],
                 "pages_with_extracted_text": len(doc["text_chars_by_page"]),
                 "provider_previous_pages": doc["provider_previous_pages"],
                 "visual_pages_checked": doc["visual_pages_checked"],
                 "stable_clause_upsert": doc["stable_clause_upsert"],
                 "latest_policy_established": False}
                for doc in checked if doc.get("pages")
            ],
            "incomplete_wechat": [
                {"document_id": doc["document_id"], "url": doc["url"],
                 "article_image_references": doc["image_count"],
                 "images_checked": doc["images_checked"], "complete": False,
                 "last_success_preserved": doc["retains_last_success"]}
                for doc in pending
            ],
            "new_network_reads": review["network_reads_for_review"],
            "new_paid_calls": review["paid_calls"],
            "contract_validation": review.get("contract_validation", {}).get("status", "not_run"),
            "published": False,
            "original_status_counts_preserved": True,
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inv = sub.add_parser("inventory")
    inv.add_argument("--base", type=Path, default=BASE)
    inv.add_argument("--catalog", type=Path, default=ROOT / "data/cdut/rag/packages/"
                     "bsdt-services-20261017/services_full.json")
    inv.add_argument("--output", type=Path, required=True)
    pilot = sub.add_parser("pilot")
    pilot.add_argument("--output", type=Path, required=True)
    pilot.add_argument("--key-file", type=Path)
    pilot.add_argument("--free-plan-confirmed", action="store_true")
    pilot.add_argument("--credit-limit", type=int, default=150)
    pilot.add_argument("--first-three", action="store_true")
    pilot.add_argument("--max-followups", type=int, default=8)
    review = sub.add_parser("package-reviewed")
    review.add_argument("--captures", type=Path, required=True)
    review.add_argument("--reviews", type=Path, required=True)
    review.add_argument("--output", type=Path, required=True)
    cov = sub.add_parser("coverage")
    cov.add_argument("--inventory", type=Path, required=True)
    cov.add_argument("--collection", type=Path, required=True)
    cov.add_argument("--source-review", type=Path,
                     help="overlay targeted clause review without changing original pilot counts")
    cov.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "inventory":
            result = inventory(args.base, args.catalog)
            atomic_write(args.output, canonical(result))
            print(json.dumps({k: v for k, v in result.items() if k != "items"}, ensure_ascii=False))
        elif args.command == "coverage":
            result = coverage(args.inventory, args.collection, args.source_review)
            atomic_write(args.output, canonical(result))
            print(json.dumps({
                "status_counts": result["status_counts"],
                "enumerated_scope": result["enumerated_scope"],
                "pilot": {key: result["pilot"][key] for key in (
                    "entries_attempted", "status_counts", "reserved_credits",
                    "embedded_image_reference_count", "article_image_reference_count")},
                "targeted_review": {key: result.get("targeted_review", {}).get(key) for key in (
                    "documents_checked_for_candidate", "clauses_checked_for_candidate",
                    "image_flow_transcriptions_checked", "contract_validation")},
            }, ensure_ascii=False))
        elif args.command == "pilot":
            if args.key_file:
                if args.key_file.resolve().is_relative_to(ROOT):
                    raise ValueError("credential_file_must_be_outside_repository")
                key = args.key_file.read_text(encoding="utf-8").strip()
            else:
                key = os.environ.get("FIRECRAWL_API_KEY", "")
            items = [{"url": public_url(u), "format": f, "title": t} for f, u, t in PILOT]
            collector = FirecrawlCollector(key, args.output, credit_limit=args.credit_limit)
            result = collector.collect(items[:3] if args.first_three else items,
                free_plan_confirmed=args.free_plan_confirmed,
                max_followups=0 if args.first_three else args.max_followups)
            print(json.dumps({"reserved_credits": result["reserved_credits"],
                              "results": dict(Counter(r["status"] for r in result["requests"])),
                              "blocked_reason": result.get("blocked_reason"),
                              "adopted": False, "published": False}, ensure_ascii=False))
        else:
            if args.output.exists():
                raise ValueError("output_already_exists")
            ledger = json.loads((args.captures / "collection.json").read_bytes())
            reviews = json.loads(args.reviews.read_bytes())
            documents = []
            for row in ledger["requests"]:
                if row["document_id"] not in reviews:
                    continue
                document = reviewed_capture(args.captures, row, reviews[row["document_id"]])
                for filename in ("body_file", "original_file"):
                    relative = document[filename]
                    atomic_write(args.output / relative, (args.captures / relative).read_bytes())
                documents.append(document)
            if not documents:
                raise ValueError("no_reviewed_documents")
            atomic_write(args.output / "manifest.json", canonical({
                "schema_version": 1, "capture_tool": "firecrawl-v2",
                "documents": documents,
            }))
            print(json.dumps({"documents": len(documents), "adopted": False, "published": False}))
    except (OSError, ValueError, KeyError, TypeError):
        parser.exit(2, "Collection stopped; inspect the redacted ledger. "
                    "Active knowledge unchanged.\n")


if __name__ == "__main__":
    main()
