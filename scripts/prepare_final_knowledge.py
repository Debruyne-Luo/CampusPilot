"""Assemble the independent collection with the integration baseline; never activate it.

Raw captures are immutable inputs. Adoption needs an explicit per-chunk review with
hash-bound local evidence; assembling a package alone never approves its contents.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from campuspilot.knowledge_release import read_candidate, write_candidate
from campuspilot.rag import RagChunk, RagSource, canonical, digest, make_snapshot

ROOT = Path(__file__).resolve().parents[1]
PAGES = {
    1: [8], 2: [8], 3: [9], 4: [10, 11], 5: [10, 11], 6: [11], 7: [11],
    8: [13], 9: [12, 14], 10: [14], 11: [15], 12: [16, 17], 13: [20],
    14: [21], 15: [21], 16: [30], 17: [31], 18: [36], 19: [37],
    20: [38, 39], 21: [39], 22: [40], 23: [40], 24: [41], 25: [42],
    26: [43], 27: [32, 33], 28: [35], 42: [12, 41], 45: [8, 10, 11, 13, 15, 20],
}


def assemble(source: Path, base: Path, output: Path, review: Path | None = None) -> dict[str, Any]:
    prior = read_candidate(base, check_index=False)
    manifest = json.loads((base / "manifest.json").read_bytes())
    raw = {name[4:]: (base / name).read_bytes()
           for name in manifest["files_sha256"] if name.startswith("raw/")}
    package = source / "data/cdut/rag/packages/pending-20261021-freshman"
    captures = source / "output/freshman-20261021/raw"
    for path in sorted(captures.rglob("*")):
        if path.is_symlink() or not path.resolve().is_relative_to(captures.resolve()):
            raise ValueError("unsafe_collection_path")
        if path.is_file() and path.suffix in {".md", ".html", ".json", ".jsonl", ".txt", ".jpg"}:
            raw["freshman/" + path.relative_to(captures).as_posix()] = path.read_bytes()
    for name in ("sources.json", "chunks.jsonl", "PACKAGE_README.md"):
        raw["freshman/package/" + name] = (package / name).read_bytes()
    sources = {s.source_id: s for s in prior.sources}
    chunks = {c.chunk_id: c for c in prior.chunks}
    # Keep the already source-checked official revisions from the earlier joint review.
    corrected = ROOT / "data/cdut/rag/candidates/rebuild-20261017"
    if corrected.exists():
        checked = read_candidate(corrected, check_index=False)
        for c in checked.chunks:
            if c.chunk_id in {
                "cdut:chunk:official:portal-1042:flow-image",
                "cdut:chunk:official:portal-1266:flow-image", "cdut:chunk:xjgl2019:16",
            }:
                chunks[c.chunk_id] = c
                sources[c.source_id] = next(
                    s for s in checked.sources if s.source_id == c.source_id
                )
        checked_manifest = json.loads((corrected / "manifest.json").read_bytes())
        for name in checked_manifest["files_sha256"]:
            if name.startswith("raw/"):
                key, data = name[4:], (corrected / name).read_bytes()
                if key in raw and raw[key] != data:
                    raw["prior-baseline/" + key] = raw[key]
                raw[key] = data
    extra = ROOT / "output/final-knowledge-20261021/source-review/extra-1-True.txt"
    if extra.exists() and "安全邮箱修改手机号" in extra.read_text(encoding="utf-8"):
        raw["final/identity-help-provider-extract.txt"] = extra.read_bytes()
    guide = source / "output/kb-expansion-20261020/raw"
    for path in guide.glob("07-*"):
        raw["final/library-borrowing-guide-provider-extract.txt"] = path.read_bytes()
    by_url = {s.url: s.source_id for s in prior.sources}
    remap = {}
    for item in json.loads((package / "sources.json").read_bytes()):
        sid = by_url.get(item["url"], item["source_id"])
        remap[item["source_id"]] = sid
        if sid not in sources:
            sources[sid] = RagSource.model_validate_json(canonical({
                key: item[key] for key in RagSource.model_fields if key in item
            }))
    edits = []
    lines = (package / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
    for item in map(json.loads, lines):
        number = int(item["chunk_id"].rsplit(":", 1)[1])
        item["source_id"] = remap[item["source_id"]]
        if item["chunk_id"] in chunks:
            raise ValueError("duplicate_increment_chunk")
        if number in PAGES:
            pages = PAGES[number]
            item["locator"] += "；电子书页序 " + ",".join(map(str, pages)) + "（含封面）"
            item["conditions"] = ["2026级本科新生入学须知记载；不推算其他届安排"]
            item["audiences"] = ["undergraduate"]
        # Cohort is not an academic year. Multi-campus clauses stay explicit and unexpanded.
        if number in {7, 17, 29, 43}:
            item["campuses"] = ["all"]
        elif number in {3, 5, 18, 20, 21, 22, 23, 24, 42}:
            item["campuses"] = ["chengdu"]
        if number == 1:
            item.update(valid_from="2026-08-29", valid_until="2026-08-30")
        if number == 5:
            item["valid_until"] = "2026-11-06"
        if number in {2, 12, 25, 34, 45}:
            item["kind"] = "historical"
        if number == 9:
            item["text"] += (
                " 指南说明2027年医保个人缴费标准尚未正式下达，400+48元是当时预估，"
                "不能作为已确定的当前医保账单。"
            )
        if number == 20:
            item["audiences"] = ["undergraduate", "graduate"]
            item["conditions"] = ["2026年入学须知所载；用电免费基数按本科/研究生分别适用"]
        if number == 37:
            item["topic_id"] = "official_entry"
        if number == 44:
            item["text"] = item["text"].split("学生邮箱 POP3")[0] + (
                " 本条仅保留2022年账号激活说明，客户端协议、端口和安全设置请查看网信处当前说明。"
            )
            item["stale"] = True
        if number == 36:
            item["text"] = item["text"].replace("页面显示30个部门入驻、共161个服务。", "")
        if number == 39:
            item["text"] = item["text"].replace("公开列出135项服务", "公开列出服务目录")
        item["text_sha256"] = digest(item["text"].encode())
        chunks[item["chunk_id"]] = RagChunk.model_validate_json(canonical({
            key: item[key] for key in RagChunk.model_fields if key in item
        }))
        edits.append({"chunk_id": item["chunk_id"], "pages": PAGES.get(number, []),
                      "status": "pending", "text_sha256": item["text_sha256"]})
    # Unresolved borrowing limits must not be selected as an authoritative current number.
    for cid in ("cdut:chunk:libfaq:03", "cdut:chunk:expand-lib:01"):
        if cid in chunks:
            chunks[cid] = chunks[cid].model_copy(update={"kind": "historical", "stale": True})
    faq = next(s for s in sources.values() if s.url.endswith("/fw/qtfw/cjwt.htm"))
    limitation = (
        "图书馆公开FAQ和借阅指南记载的借阅数量不一致，且两页未标明可比较的生效日期，"
        "当前不能确认本科生、研究生及教职工的统一借阅上限。请从图书馆官网登录本人读者账号"
        "查看实际借阅权限，或向图书馆总服务台核实；不把任一旧数字当作当前确定规则。"
    )
    chunks["cdut:chunk:library-borrowing-scope"] = RagChunk(
        chunk_id="cdut:chunk:library-borrowing-scope", source_id=faq.source_id,
        topic_id="library", title="图书馆借阅数量：官方页面口径待核定",
        text=limitation, text_sha256=digest(limitation.encode()),
        locator="FAQ借阅数量与借阅指南/gk/jyzn.htm交叉核验（资料限制）",
        aliases="本科生研究生借几本书 借阅上限 数量", kind="limitation",
        verification_status="official_document", reviewer="Codex-source-review-20261021",
        verified_at=date(2026, 10, 21), approval_id="CDUT-SOURCE-ADOPTION-20261021",
    )
    raw["final/integration-review.json"] = canonical({
        "base_version": prior.version, "increment": edits,
        "unresolved": ["library_borrowing_limit", "dorm_service_office_window"],
        "notes": "Assembly does not complete source review or quality acceptance.",
    })
    if review is not None:
        record = json.loads(review.read_bytes())
        for entry in record["chunks"]:
            cid = entry["chunk_id"]
            old = chunks[cid]
            if entry["text_sha256"] != old.text_sha256 or not entry.get("notes"):
                raise ValueError("review_body_or_notes_mismatch")
            if not entry.get("evidence"):
                raise ValueError("missing_review_evidence")
            for evidence in entry["evidence"]:
                data = raw[evidence["file"]]
                if digest(data) != evidence["sha256"]:
                    raise ValueError("review_evidence_hash_mismatch")
            chunks[cid] = old.model_copy(update={
                "verification_status": "official_document", "reviewer": record["checked_by"],
                "verified_at": date.fromisoformat(record["checked_on"]),
                "approval_id": record["adoption_id"],
            })
        for sid in {c.source_id for c in chunks.values()
                    if c.approval_id == record["adoption_id"]}:
            if all(c.verification_status != "pending"
                   for c in chunks.values() if c.source_id == sid):
                sources[sid] = sources[sid].model_copy(update={
                    "verification_status": "official_document", "reviewer": record["checked_by"],
                    "verified_at": date.fromisoformat(record["checked_on"]),
                })
        raw["final/source-adoption.json"] = review.read_bytes()
    identity = digest(canonical({name: digest(data) for name, data in raw.items()}))
    snapshot = make_snapshot(tuple(sources.values()), tuple(chunks.values()), identity)
    write_candidate(output, snapshot, raw)
    return {"version": snapshot.version, "sources": len(snapshot.sources),
            "chunks": len(snapshot.chunks), "pending": snapshot.pending,
            "pending_chunks": [c.chunk_id for c in snapshot.chunks
                               if c.verification_status == "pending"], "activated": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--review", type=Path)
    args = parser.parse_args()
    result = assemble(args.source, args.base, args.output, args.review)
    print(json.dumps(result, ensure_ascii=False))
