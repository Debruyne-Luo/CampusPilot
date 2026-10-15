"""Package previously saved public CDUT captures; this script has no network/browser API.

Run with the existing isolated collector venv (BeautifulSoup is already installed).
PDF/XLSX text files are produced separately with campuspilot.official_knowledge.
Full-page responses, browser profiles, cookies and challenge state are never copied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin
from zipfile import ZipFile

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "output/official-tools/public-capture"
PACKAGE = ROOT / "data/cdut/rag/packages/official-20261014"
CONFIG = [
    ("libhours", "成都理工大学图书馆", "-成都理工大学--图书馆", None),
    ("netfaq2023", "成都理工大学网络与信息化处", "-网络与信息化处", "2023-03-01"),
    ("winter2026", "成都理工大学网络与信息化处", "-网络与信息化处", "2026-01-29"),
    ("graduate-proof-2023", "成都理工大学研究生院", "-研究生院", "2023-09-12"),
    ("tuition-2026", "成都理工大学财务处", "-成都理工大学财务处", "2026-06-30"),
    ("portal2020", "成都理工大学网络与信息化处", "-网络与信息化处", "2020-11-18"),
    ("identity2026", "成都理工大学网络与信息化处", "-网络与信息化处", "2026-03-26"),
    ("netcarrier2025", "成都理工大学网络与信息化处", "-网络与信息化处", "2025-09-02"),
    ("proofindex", "成都理工大学教务处", "-成都理工大学教务处", "2026-03-12"),
    ("gradesindex", "成都理工大学教务处", "-成都理工大学教务处", "2026-03-16"),
]


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def dump(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def copy_asset(source: Path, target: Path, record: dict) -> None:
    raw = source.read_bytes()
    assert sha(raw) == record["sha256"] and len(raw) == record["bytes"]
    fmt = record["format"]
    magic = {
        "png": b"\x89PNG\r\n\x1a\n",
        "jpeg": b"\xff\xd8\xff",
        "pdf": b"%PDF-",
        "xlsx": b"PK\x03\x04",
    }
    assert raw.startswith(magic[fmt])
    if fmt == "xlsx":
        with ZipFile(source) as archive:
            assert {"[Content_Types].xml", "xl/workbook.xml"} <= set(archive.namelist())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)


def main() -> None:
    report = json.loads((CAPTURE / "report.json").read_text(encoding="utf-8"))
    documents = []
    old = []
    for ident, *_ in CONFIG[:5]:
        source = PACKAGE / f"bodies/{ident}.txt"
        if source.exists():
            raw = source.read_bytes()
            target = (
                ROOT / f"output/official-tools/prior-transcript-backups/{ident}-{sha(raw)[:12]}.txt"
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(raw)
            old.append(
                {
                    "file": str(target.relative_to(ROOT)).replace("\\", "/"),
                    "sha256": sha(raw),
                    "note": "Earlier normalized transcript backup; not adopted as raw capture.",
                }
            )
    dump(ROOT / "output/official-tools/prior-transcript-backups/manifest.json", old)
    for number, (attempt, config) in enumerate(zip(report["attempts"], CONFIG, strict=True), 1):
        ident, publisher, suffix, published = config
        folder = CAPTURE / f"trial-1-drission-{number}"
        page_raw = (folder / "rendered.html").read_bytes()
        soup = BeautifulSoup(page_raw.decode("utf-8"), "html.parser")
        title = attempt["title"].removesuffix(suffix)
        article = (
            soup.select_one("#vsb_content_503")
            if number == 4
            else max(
                soup.select("#vsb_content, #vsb_content_2, #vsb_content_1021"),
                key=lambda node: len(node.get_text()),
                default=None,
            )
        )
        assert article is not None
        dates = [
            n.get_text(" ", strip=True)
            for n in soup.select(".article-date, .contcon14_2_art_info, .conttime, .main_contit")
        ]
        if published:
            assert any(published in text for text in dates), (ident, dates)
        raw_dom = (
            (folder / "body.html").read_bytes()
            if (folder / "body.html").exists()
            else str(article).encode("utf-8")
        )
        assert b"$_ts" not in raw_dom
        dom_file = f"raw_dom/{ident}.html"
        (PACKAGE / "raw_dom").mkdir(parents=True, exist_ok=True)
        (PACKAGE / dom_file).write_bytes(raw_dom)
        body = (
            (folder / "body.txt").read_text(encoding="utf-8")
            if (folder / "body.txt").exists()
            else "\n\n".join(p.get_text(" ", strip=True) for p in article.select("p"))
        )
        notes = ["Body is derived UTF-8 text: actual page title plus saved visible article text."]
        if number == 4:
            notes.append(
                "Original probe selector missed #vsb_content_503; recove"
                "red offline from saved rendered DOM. Original failed at"
                "tempt retained in collector report."
            )
        assets = list(attempt.get("asset_downloads", []))
        if number == 9:
            extra = json.loads((folder / "public-http-attachment.json").read_text(encoding="utf-8"))
            assets.append(extra)
            assert extra["status"] == "downloaded"
            body = (PACKAGE / "assets/aao6960/text.txt").read_text(encoding="utf-8")
            notes.append(
                "Article embeds PDF; one ordinary public HTTP request do"
                "wnloaded the exact iframe PDF without browser state. Al"
                "l three PDF pages were parsed and visually checked. Scr"
                "eenshot internals are not transcribed."
            )
        attachments, missing = [], []
        for j, asset in enumerate(assets, 1):
            if asset["status"] != "downloaded":
                missing.append(
                    {
                        "url": asset["url"],
                        "status": asset["status"],
                        "error_type": asset.get("error_type"),
                    }
                )
                continue
            filename = f"assets/{ident}/{asset['file']}"
            copy_asset(folder / asset["file"], PACKAGE / filename, asset)
            annex = {
                "attachment_id": f"asset-{j}",
                "url": asset["url"],
                "file": filename,
                "format": asset["format"],
                "sha256": asset["sha256"],
                "bytes": asset["bytes"],
                "text_verified": False,
            }
            if asset.get("collected_at"):
                annex["collected_at"] = asset["collected_at"]
                annex["collection_channel"] = "http"
                annex["request_method"] = asset.get("method")
            if asset["format"] in {"pdf", "xlsx"}:
                text = PACKAGE / (
                    "assets/aao6960/text.txt" if number == 9 else "assets/winter2026/text.txt"
                )
                annex["text_file"] = text.relative_to(PACKAGE).as_posix()
                annex["text_verified"] = True
                annex["text_method"] = (
                    "pypdf_all_pages_visual_checked"
                    if number == 9
                    else "all_worksheet_rows_raw_xml_including_cell_references"
                )
                annex["complete_transcription"] = number != 9
                if number == 3:
                    annex["limitation"] = (
                        "Title states 2026; 32 date cells A3:A34 store 2022 date serials. "
                        "Built-in numFmtId 58 in zh-cn displays only month/day. "
                        "Raw values remain unchanged; "
                        "do not adopt the hidden storage year as the duty-schedu"
                        "le applicability year."
                    )
            if number == 10:
                target = PACKAGE / "assets/gradesindex/checked-menu-labels.txt"
                target.write_text(
                    "红色编号1：考试管理\n红色编号2：查卷申请\n红色编号3：申请\n", encoding="utf-8"
                )
                annex.update(
                    text_file=target.relative_to(PACKAGE).as_posix(),
                    text_verified=True,
                    complete_transcription=False,
                    text_method="visual_checked_partial_labels",
                    limitation="Right-side UI text touches image boundary; only numbere"
                    "d readable labels transcribed.",
                )
            attachments.append(annex)
        downloaded_urls = {a["url"] for a in attachments}
        for img in article.select("img[src]"):
            url = urljoin(attempt["url"], img["src"])
            if url not in downloaded_urls and url not in {m["url"] for m in missing}:
                missing.append({"url": url, "status": "not_collected_image"})
        if number in {3, 8}:
            notes.append(
                "All referenced unique article images preserved; their i"
                "nternal text is not transcribed. Adopt only exact suppo"
                "rted body/annex text."
            )
        if number == 6:
            notes.append(
                "Complete link-index article; linked PDF manual download"
                " failed. This capture cannot stand in for that manual."
            )
        body_file = f"bodies/{ident}.txt"
        (PACKAGE / "bodies").mkdir(parents=True, exist_ok=True)
        normalized = (title + "\n\n" + body).encode("utf-8")
        (PACKAGE / body_file).write_bytes(normalized)
        documents.append(
            {
                "document_id": ident,
                "url": attempt["url"],
                "title": title,
                "publisher": publisher,
                "collected_at": attempt["finished_at"],
                "channel": "browser_dom",
                "body_file": body_file,
                "original_file": dom_file,
                "published_on": published,
                "signed_on": "2026-06-29" if number == 5 else None,
                "complete": True,
                "content_kind": "article",
                "access_scope": "public",
                "status": "success",
                "body_sha256": sha(normalized),
                "attachments": attachments,
                "missing_attachments": missing,
                "collection_note": " ".join(notes),
                "source_capture": {
                    "saved_dom_sha256": sha(page_raw),
                    "article_dom_sha256": sha(raw_dom),
                    "original_probe_candidate": attempt["full_body_candidate"],
                    "publication_metadata": dates,
                },
            }
        )
    manifest_path = PACKAGE / "manifest.json"
    if manifest_path.exists():
        prior = json.loads(manifest_path.read_text(encoding="utf-8"))
        owned = {d["document_id"] for d in documents}
        documents += [d for d in prior["documents"] if d["document_id"] not in owned]
    dump(manifest_path, {"schema_version": 1, "documents": documents})
    print(
        json.dumps(
            {
                "documents": len(documents),
                "attachments": sum(len(d["attachments"]) for d in documents),
                "manifest": str(PACKAGE / "manifest.json"),
            },
            ensure_ascii=False,
        )
    )


def collector_report() -> None:
    """Preserve original experiment outcomes separately from later offline recovery."""
    variants = [
        "chrome-system",
        "chrome-system-drission-fixed",
        "chrome-system-headful",
        "chrome-system-headful-repeat",
        "public-capture",
    ]
    summaries = []
    environment_keys = {
        "recorded_at",
        "python",
        "platform",
        "package_versions",
        "dns",
        "browser",
        "proxy_mode",
        "headless",
        "fresh_profile_per_attempt",
        "user_profile_or_credentials_copied",
        "browser_download_required",
        "challenge_vendor",
        "environment_proxy_variable_names",
    }
    attempt_keys = {
        "started_at",
        "finished_at",
        "tool",
        "trial",
        "url",
        "title",
        "full_body_candidate",
        "article_node_found",
        "article_chars",
        "reason",
        "html_bytes",
        "html_sha256",
        "body_sha256",
        "tables",
        "images",
        "attachment_links",
        "observed_document_http_statuses",
        "initial_http_status",
        "http_status",
        "error_type",
        "challenge_marker_present",
    }
    for variant in variants:
        path = ROOT / f"output/official-tools/{variant}/report.json"
        report = json.loads(path.read_text(encoding="utf-8"))
        attempts = [{k: v for k, v in a.items() if k in attempt_keys} for a in report["attempts"]]
        counts = {}
        for tool in sorted({a["tool"] for a in report["attempts"]}):
            rows = [a for a in report["attempts"] if a["tool"] == tool]
            api_errors = sum(a.get("error_type") == "TypeError" for a in rows)
            counts[tool] = {
                "attempts": len(rows),
                "full_body_candidates": sum(a.get("full_body_candidate", False) for a in rows),
                "api_parameter_errors": api_errors,
                "content_attempts_excluding_api_parameter_errors": len(rows) - api_errors,
            }
        summaries.append(
            {
                "variant": variant,
                "source_report_sha256": sha(path.read_bytes()),
                "environment": {
                    k: v for k, v in report["environment"].items() if k in environment_keys
                },
                "counts": counts,
                "attempts": attempts,
            }
        )
    manifest = json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))
    downloaded = json.loads(
        (CAPTURE / "trial-1-drission-9/public-http-attachment.json").read_text(encoding="utf-8")
    )
    safe_download = {
        k: v
        for k, v in downloaded.items()
        if k
        in {
            "url",
            "method",
            "timeout_seconds",
            "http_status",
            "content_type",
            "bytes",
            "sha256",
            "status",
            "format",
            "collected_at",
            "collection_precision",
        }
    }
    dump(
        ROOT / "docs/research/official-collector-probe-20261014.json",
        {
            "schema_version": 1,
            "report_generated_at": datetime.now(UTC).isoformat(),
            "scope": "saved public captures only; no browser profiles/cookies/state exported",
            "original_experiments": summaries,
            "interpretation": [
                "The headful-repeat experiment produced 18/18 article-bo"
                "dy candidates, across 3 seed URLs, 3 trials, 2 tools. C"
                "andidate detection is not semantic acceptance.",
                "The initial headless experiment produced 0/18 candidate"
                "s, but 6 Drission TypeError parameter failures did not "
                "reach a body check. Fixed Drission separately produced "
                "0/9 candidates with HTTP 412.",
                "Crawl4AI headful final response status is unavailable; "
                "initial HTTP 412 is not a claim that rendered article c"
                "ontent was absent.",
                "Public-capture original results remain 8/10 candidates;"
                " offline selector recovery and a separate PDF download "
                "made all 10 target documents usable.",
            ],
            "offline_adaptations": [
                {
                    "document_id": "graduate-proof-2023",
                    "original_probe_status": "missing_or_empty_article",
                    "adaptation": "Select actual saved #vsb_content_503; complete textual "
                    "article recovered without network.",
                },
                {
                    "document_id": "proofindex",
                    "original_probe_status": "missing_or_empty_article",
                    "adaptation": "Source article is a PDF carrier; exact saved iframe URL"
                    " downloaded once by ordinary HTTP. All 3 pages parsed a"
                    "nd visually checked.",
                    "attachment": safe_download,
                },
            ],
            "package": {
                "manifest": str(PACKAGE / "manifest.json"),
                "target_documents": [
                    {
                        "document_id": d["document_id"],
                        "title": d["title"],
                        "published_on": d.get("published_on"),
                        "signed_on": d.get("signed_on"),
                        "status": d.get("status", "success"),
                        "body_sha256": d["body_sha256"],
                        "missing_attachments": d.get("missing_attachments", []),
                        "collection_note": d.get("collection_note"),
                    }
                    for d in manifest["documents"]
                    if d["document_id"] in {c[0] for c in CONFIG}
                ],
            },
            "attachment_limits": [
                "Original experiment: wxc1241 linked manual PDF download failed. "
                "Subsequent acquisitions in the curated manifest retain that failure "
                "history and may resolve it; inspect current attachment metadata.",
                "Student-guide fourth edition: 41-page original PDF sha2"
                "56 825729937cfd2791c768c2682d1bc1ac41b57a4a6ded57033b0d"
                "e63f419239b9; every page text layer parsed, image inter"
                "nals not fully transcribed. Await exact publishing-page"
                " provenance before binding as document.",
                "Winter duty XLSX: Sheet1 A1:E34, 32 date cells A3:A34 s"
                "tore 2022 serial values while heading states 2026; buil"
                "t-in numFmtId 58 in zh-cn displays month/day only. Pres"
                "erve raw values and both facts; do not correct silently"
                ".",
                "Grade-review image: only numbered labels 考试管理 / 查卷申请 / "
                "申请 visually transcribed; boundary-clipped UI text remai"
                "ns unverified.",
            ],
            "format_reference": "https://learn.microsoft.com/en-us/dotnet/api/documentfo"
            "rmat.openxml.spreadsheet.numberingformat",
        },
    )
    print("Saved sanitized collector audit with original outcomes and offline adaptations.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--output", type=Path, help="new capture package directory")
    args = parser.parse_args()
    if not args.report_only:
        if args.output is None or args.output.exists():
            parser.error("Packaging requires --output pointing to a new directory")
        PACKAGE = args.output.resolve()
        main()
    collector_report()
