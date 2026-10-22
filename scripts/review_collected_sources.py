"""Reproduce the 2026-10-17 local source review without network or model calls.

Inputs are the immutable 322-chunk baseline, saved Firecrawl public responses and
the separately recorded one-request public PDF probe. Manually checked image
transcriptions are explicit below; legacy OCR assertions are not inherited.
Only the dedicated review package/report are written. No active pointer changes.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
import tempfile
from html import unescape
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/cdut/rag/versions/kb-229ee34eba99ef34"
PACKAGE = ROOT / "data/cdut/rag/packages/rechecked-20261017"
PROVIDER = ROOT / "output/knowledge-rebuild-20261017/firecrawl"
REPORT = ROOT / "output/knowledge-rebuild-20261017/source-review.json"
DAY = "2026-10-17"

# Checked against original PNG bytes using view_image on DAY. Line wrapping in
# the flow boxes is flattened; wording, branch order and conditions are retained.
TRANSCRIPTS = {
    "portal-1266": (
        "登录“砚湖易办”\n进入“事务中心”\n选择党委武装部、保卫处\n"
        "填写《借户口本申请》并提交审批\n审批通过后，到保卫处综合科线下领取户口本\n"
    ),
    "portal-1042": (
        "方式一\n电脑登录“砚湖易办”\n进入“事务中心”\n填写“心理咨询预约”\n"
        "预约成功后，到心理健康教育中心线下进行咨询\n\n"
        "方式二\n手机关注学校官方微信企业号“成都理工大学”\n登录“砚湖易办”\n"
        "进入“事务中心”的“学生事务板块”\n填写“心理咨询预约”\n"
        "预约成功后，到心理健康教育中心线下进行咨询\n"
    ),
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def put(name: str, content: bytes) -> None:
    target = PACKAGE / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def clause(
    doc: dict[str, Any],
    ident: str,
    title: str,
    quote: str,
    filename: str,
    *,
    app: dict[str, Any],
    limitation: str | None = None,
) -> dict[str, Any]:
    body_bytes = (PACKAGE / doc["body_file"]).read_bytes()
    content_bytes = (PACKAGE / filename).read_bytes()
    text = content_bytes.decode("utf-8")
    start = text.index(quote)
    review = {
        "checked_by": "official-source-validator",
        "checked_at": DAY,
        "body_sha256": sha(body_bytes),
    }
    if filename != doc["body_file"]:
        asset = next(a for a in doc["capture_assets"] if a.get("text_file") == filename)
        review.update(
            {
                "content_sha256": sha(content_bytes),
                "attachment_sha256": sha((PACKAGE / asset["file"]).read_bytes()),
            }
        )
    return {
        "clause_id": ident,
        "topic_id": "proof" if doc["document_id"] == "xjgl2019" else "campus",
        "title": title,
        "quote": quote,
        "locator": {"file": filename, "start": start, "end": start + len(quote)},
        "review": review,
        "applicability": app,
        "disposition": "limitation" if limitation else "adopt",
        **({"limitation": limitation} if limitation else {}),
    }


def review_portal(provenance: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source_manifest = load(ROOT / "data/cdut/rag/packages/portal-20261014/manifest.json")
    documents, rows = [], []
    for ident, transcript in TRANSCRIPTS.items():
        doc = copy.deepcopy(
            next(d for d in source_manifest["documents"] if d["document_id"] == ident)
        )
        prior = provenance["documents"][ident]
        version = prior["versions"][prior["current_revision"]]
        # Copy only baseline-manifest-addressed original files after hash checks.
        for name, file in version["files"].items():
            data = (BASE / "raw" / file["path"]).read_bytes()
            if sha(data) != file["sha256"]:
                raise ValueError("baseline_source_hash_mismatch")
            put(name, data)
        asset = doc["capture_assets"][0]
        text_file = str(Path(asset["file"]).with_suffix(".checked.txt")).replace("\\", "/")
        put(text_file, transcript.encode())
        asset.update(
            {
                "text_file": text_file,
                "text_verified": True,
                "transcription_method": "manual_visual_source_check",
                "transcription_checked_on": DAY,
            }
        )
        condition = "学生申请者需是户口在学校的学生，才能办理"
        app = {
            "audiences": ["undergraduate", "graduate"],
            "audience_quote": "学生",
            "campuses": [],
            "conditions": [condition] if ident == "portal-1266" else [],
            "exceptions": [],
            "academic_year": None,
            "valid_from": None,
            "valid_until": None,
            "evidence_quotes": {},
        }
        new_clause = clause(
            doc,
            "flow-image",
            doc["title"] + "：官方流程图",
            transcript.strip(),
            text_file,
            app=app,
            limitation="原指南未标明校区及发布日期；使用前仍需核对实际系统可用性。",
        )
        doc["clauses"] = [new_clause]
        doc["collection_note"] += (
            " 原始采集日期不变；2026-10-17复用不可变基线图片，人工逐字核验流程图；"
            "本次为官方文档采纳，不代表人工现场核验或真实预约/领取成功。"
        )
        documents.append(doc)
        rows.append(
            {
                "document_id": ident,
                "status": "verified_source_clauses",
                "adoption": "official_document",
                "original_capture_reused": True,
                "prior_revision": prior["current_revision"],
                "new_clause_id": f"cdut:chunk:official:{ident}:flow-image",
                "image_sha256": asset["sha256"],
                "transcript_sha256": sha(transcript.encode()),
                "image_review": "visual_original_png_checked",
                "limitations": ["校区未知", "发布日期未知", "未操作学校系统"],
            }
        )
    return documents, rows


def review_pdf() -> tuple[dict[str, Any], dict[str, Any]]:
    probe = load(PACKAGE / "pdf-probe.json")
    pdf = (PACKAGE / "official-student-management.pdf").read_bytes()
    if probe["status"] != 200 or not pdf.startswith(b"%PDF-") or sha(pdf) != probe["sha256"]:
        raise ValueError("pdf_probe_not_verified")
    from pypdf import PdfReader

    reader = PdfReader(PACKAGE / "official-student-management.pdf")
    pages = [page.extract_text() or "" for page in reader.pages]
    if len(pages) != 18 or any(len(page.strip()) < 80 for page in pages):
        raise ValueError("pdf_page_completeness_not_verified")
    body = "\n\n".join(f"[page {i + 1}]\n{page}" for i, page in enumerate(pages))
    put("official-student-management.txt", body.encode())
    doc = {
        "document_id": "xjgl2019",
        "url": probe["url"],
        "title": (
            "关于印发《成都理工大学全日制普通本科学生学籍管理办法》的通知（成理校教〔2019〕18号）"
        ),
        "publisher": "成都理工大学（教务处负责解释）",
        "collected_at": probe["collected_at"],
        "channel": "http",
        "body_file": "official-student-management.txt",
        "original_file": "official-student-management.pdf",
        "body_sha256": sha(body.encode()),
        "published_on": "2019-12-31",
        "signed_on": "2019-12-31",
        "complete": True,
        "content_kind": "article",
        "access_scope": "public",
        "contains_personal_data": False,
        "status": "success",
        "attachments": [],
        "capture_assets": [],
        "legacy_source_ids": ["cdut:source:xjgl2019"],
        "collection_note": "一次免费公开HTTP读取获得完整18页PDF；pypdf本地提取全部页面。"
        "第2、18页已渲染并目视核对；仅采纳第56至58条，未认定2019办法仍为最新版本。",
    }
    first = body.index("第五十六条")
    last = body.index("第十四章", first)
    date_start = body.index("第六十条")
    date_end = body.index("第六十一条", date_start)
    app = {
        "audiences": ["undergraduate"],
        "audience_quote": "普通本科学生学籍管理办法",
        "campuses": [],
        "conditions": [],
        "exceptions": [],
        "academic_year": None,
        "valid_from": "2020-01-01",
        "valid_until": None,
        "evidence_quotes": {"valid_from": body[date_start:date_end].strip()},
    }
    checked = clause(
        doc,
        "cdut:chunk:xjgl2019:16",
        "证书遗失证明与成绩单",
        body[first:last].strip(),
        doc["body_file"],
        app=app,
        limitation="2019年办法，明确自2020年1月1日执行；截至本次采集未完成后续修订检索，"
        "不得单凭该旧文件断言2026年现行流程。仅适用普通本科学生，校区未明确。",
    )
    checked["source_id"] = "cdut:source:xjgl2019"
    doc["clauses"] = [checked]
    return doc, {
        "document_id": "xjgl2019",
        "status": "verified_source_clauses_with_limitation",
        "adoption": "official_document",
        "http_reads": 1,
        "bytes": len(pdf),
        "sha256": sha(pdf),
        "pages": len(pages),
        "text_chars_by_page": list(map(len, pages)),
        "visual_pages_checked": [2, 18],
        "provider_previous_pages": 10,
        "stable_clause_upsert": "cdut:chunk:xjgl2019:16",
        "new_source": False,
        "limitations": ["尚未完成后续修订检索", "校区未知", "全日制普通本科范围"],
    }


def review_wechat() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    legacy = ROOT / "data/cdut/rag/packages/approved-20261011b-wechat"
    sources = load(legacy / "sources.json")
    old_chunks = [
        json.loads(line)
        for line in (legacy / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    collection = load(PROVIDER / "collection.json")
    docs, rows = [], []
    for ident in ["fc-616bc08fbdd03d18", "fc-e32ab7bb28a38b35"]:
        capture = next(r for r in collection["requests"] if r["document_id"] == ident)
        response_bytes = (PROVIDER / ident / "response.json").read_bytes()
        response = json.loads(response_bytes)["data"]
        body_bytes = (PROVIDER / ident / "body.md").read_bytes()
        body = body_bytes.decode()
        old = next(s for s in sources if s["url"] == capture["url"])
        images = list(dict.fromkeys(re.findall(r"!\[Image\]\(([^)]+#imgIndex=\d+)\)", body)))
        for name, data in [
            (f"{ident}/response.json", response_bytes),
            (f"{ident}/body.md", body_bytes),
        ]:
            put(name, data)
        relevant = [
            c for c in old_chunks if c["source_id"] == old["source_id"] and not c.get("ocr")
        ]

        def normal(text: str) -> str:
            text = re.sub(r"!\[[^]]*\]\([^)]+\)", "", text)
            text = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", text)
            return re.sub(r"[\s*#\\]", "", unescape(text))

        # Compare individual old plain-text lines; report mismatches rather than
        # labelling the older text or inaccessible OCR corpus newly verified.
        comparisons = []
        for c in relevant:
            lines = [line for line in c["text"].splitlines() if len(normal(line)) > 8]
            matched = [line for line in lines if normal(line) in normal(body)]
            comparisons.append(
                {
                    "chunk_id": c["chunk_id"],
                    "checked_lines": len(lines),
                    "matching_lines": len(matched),
                    "unmatched_lines": [line for line in lines if line not in matched],
                }
            )
        html = response.get("html", "")
        publisher_present = old["publisher"] in html and old["publisher"] in body
        published = re.search(r'id="publish_time"[^>]*>([^<]+)', html)
        doc = {
            "document_id": ident,
            "url": capture["url"],
            "title": old["title"],
            "publisher": old["publisher"],
            "collected_at": capture["collected_at"],
            "channel": "http",
            "content_kind": "guide",
            "access_scope": "public",
            "contains_personal_data": False,
            "status": "success",
            "complete": False,
            "body_file": f"{ident}/body.md",
            "body_sha256": sha(body_bytes),
            "original_file": f"{ident}/response.json",
            "published_on": None,
            "signed_on": None,
            "clauses": [],
            "source_capture": {"provider": "firecrawl-v2", "response_sha256": sha(response_bytes)},
            "missing_attachments": images,
            "collection_note": "原始提供方结果未重新抓取。正文图未取得及复核，"
            "微信界面尾部噪声保留在原始证据；"
            "不继承旧包的OCR核验声明，不提交正式采纳。",
        }
        docs.append(doc)
        rows.append(
            {
                "document_id": ident,
                "url": capture["url"],
                "status": "pending_review",
                "adoption": None,
                "existing_source_id": old["source_id"],
                "publisher_text_present": publisher_present,
                "publication_display": unescape(published.group(1)) if published else None,
                "publication_timezone": response["metadata"].get("timezone"),
                "published_on": None,
                "image_count": len(images),
                "images_checked": 0,
                "plain_text_comparisons": comparisons,
                "limitations": [
                    "缺少原图字节及新OCR核验",
                    "正文含微信交互噪声",
                    "展示时间为America/New_York，不沿用旧包日期推定为采集证据",
                ],
                "retains_last_success": True,
            }
        )
    return docs, rows


def verify_contracts() -> dict[str, Any]:
    """Check observable adoption/rollback behavior, including corrupt input failures."""
    from campuspilot.knowledge_release import read_candidate
    from campuspilot.official_knowledge import build

    base = read_candidate(BASE)
    baseline_manifest = load(BASE / "manifest.json")
    raw = {
        name[4:]: (BASE / name).read_bytes()
        for name in baseline_manifest["files_sha256"]
        if name.startswith("raw/")
    }
    snapshot, merged, report = build(PACKAGE, base, prior_raw=raw)
    assert len(report["adopted"]) == 3 and len(report["failed"]) == 2
    assert {item["reason"] for item in report["failed"]} == {"incomplete_document"}
    assert len(snapshot.chunks) == len(base.chunks) + 2
    assert len(snapshot.sources) == len(base.sources)
    old = {chunk.chunk_id: chunk for chunk in base.chunks}
    new = {chunk.chunk_id: chunk for chunk in snapshot.chunks}
    pdf = new["cdut:chunk:xjgl2019:16"]
    assert pdf.source_id == "cdut:source:xjgl2019"
    assert "第五十六条" in pdf.text and "第五十八条" in pdf.text
    assert "第六十条" not in pdf.text
    assert (
        next(s for s in snapshot.sources if s.source_id == pdf.source_id).temporal_status
        == "unknown"
    )
    second, raw2, report2 = build(PACKAGE, snapshot, prior_raw=merged)
    assert report2["unchanged"] and second.version == snapshot.version and raw2 == merged
    with tempfile.TemporaryDirectory(prefix="campuspilot-source-review-") as temporary:
        test = Path(temporary)
        shutil.copytree(PACKAGE, test, dirs_exist_ok=True)
        manifest = load(test / "manifest.json")
        document = manifest["documents"][0]
        asset = test / document["capture_assets"][0]["file"]
        asset.write_bytes(asset.read_bytes() + b"tampered")
        failed, _, invalid = build(test, base, prior_raw=raw)
        assert (
            next(r for r in invalid["failed"] if r["document_id"] == "portal-1266")["reason"]
            == "attachment_hash_mismatch"
        )
        assert "cdut:chunk:official:portal-1266:flow-image" not in {
            chunk.chunk_id for chunk in failed.chunks
        }
        assert (
            next(
                chunk
                for chunk in failed.chunks
                if chunk.chunk_id == "cdut:chunk:official:portal-1266:guide-body"
            )
            == old["cdut:chunk:official:portal-1266:guide-body"]
        )
        asset.write_bytes((PACKAGE / document["capture_assets"][0]["file"]).read_bytes())
        body = test / document["body_file"]
        body.write_bytes(body.read_bytes() + b"\nchanged")
        _, _, invalid = build(test, base, prior_raw=raw)
        assert (
            next(r for r in invalid["failed"] if r["document_id"] == "portal-1266")["reason"]
            == "capture_body_hash_mismatch"
        )
    changed = [
        chunk
        for chunk in snapshot.chunks
        if chunk.chunk_id not in old or chunk.text_sha256 != old[chunk.chunk_id].text_sha256
    ]
    assert len(changed) == 3
    return {
        "status": "passed",
        "candidate_written": False,
        "compiled_version": snapshot.version,
        "checks": [
            "three_checked_documents_adopted",
            "two_incomplete_wechat_preserved",
            "two_new_chunks_no_duplicate_source",
            "stable_pdf_clause_scope",
            "pdf_temporal_status_remains_unknown",
            "repeat_build_idempotent",
            "image_hash_tampering_rejected",
            "body_hash_tampering_rejected",
            "last_success_preserved",
        ],
        "changed_chunks": [
            {
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "text_sha256": chunk.text_sha256,
                "prior_text_sha256": old[chunk.chunk_id].text_sha256
                if chunk.chunk_id in old
                else None,
            }
            for chunk in changed
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="check positive/negative contracts")
    args = parser.parse_args()
    provenance = load(BASE / "raw/official/provenance.json")
    portal_docs, portal_rows = review_portal(provenance)
    pdf_doc, pdf_row = review_pdf()
    wx_docs, wx_rows = review_wechat()
    documents = [*portal_docs, pdf_doc, *wx_docs]
    save(PACKAGE / "manifest.json", {"schema_version": 1, "documents": documents})
    save(
        PACKAGE / "annotations.json",
        {
            "schema_version": 1,
            "authority": "official_document",
            "documents": [
                {"document_id": d["document_id"], "clauses": d["clauses"]} for d in documents
            ],
        },
    )
    report = {
        "schema_version": 1,
        "reviewed_on": DAY,
        "baseline": BASE.name,
        "published": False,
        "active_pointer_changed": False,
        "network_reads_for_review": 1,
        "paid_calls": 0,
        "documents": [*portal_rows, pdf_row, *wx_rows],
        "coverage": {
            "verified_source_documents": 3,
            "pending_review_documents": 2,
            "new_image_clauses": 2,
            "legacy_clause_upserts": 1,
        },
        "limitations": [
            "本报告只覆盖5个定向复核文档，不代表全库复核完成",
            "official_document是来源采纳，不是人工现场核验",
            "本脚本只复现本地证据包，原HTTP读取记录在pdf-probe.json",
        ],
    }
    if args.verify:
        report["contract_validation"] = verify_contracts()
    save(REPORT, report)
    print(
        json.dumps(
            {
                "package": str(PACKAGE),
                "report": str(REPORT),
                "verified_documents": 3,
                "pending_documents": 2,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
