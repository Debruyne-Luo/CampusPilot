"""Collect the public Yanhu Yiban service catalogue into a local raw capture.

The catalogue endpoint is published under `/nonlogin/`, so it reads without a campus
session. This command refuses any URL outside that public prefix, never sends credentials,
and writes raw payloads plus a flattened index for review. It does not decide what belongs
to which store, adopt records, or touch the active knowledge pointer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

LIST_ENDPOINT = "https://bsdt.cdut.edu.cn/EIP/nonlogin/serGuide/serviceGuideList.htm"
PUBLIC_PREFIX = "/EIP/nonlogin/"
PAGE_SIZE = 21
# The list answers two disjoint query shapes. `pageIndex` pages the bulk of the catalogue;
# the request without it returns a second, non-overlapping slice that pageIndex never yields.
# Both are needed to cover the reported total.
QUERY_SHAPES = ("pageIndex", "default")
CHALLENGE = re.compile(
    r"\$_ts|\b412\s+Precondition|access denied|verify (?:you are|your browser)|"
    r"checking your browser|安全验证|访问过于频繁|请开启JavaScript", re.IGNORECASE)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/140.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://bsdt.cdut.edu.cn/EIP/nonlogin/onewebsitehande/"
               "toPersonalCenterPage.htm?activePersonalHomeTab=false",
}


class CaptureError(ValueError):
    """Reasons carry no source body, credential or exception detail."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise CaptureError(reason)


def _fetch(url: str, timeout: int) -> dict:
    _require(urllib.parse.urlsplit(url).path.startswith(PUBLIC_PREFIX),
             "only_public_nonlogin_paths")
    request = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            _require(response.status == 200, "unexpected_status")
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise CaptureError(f"http_{exc.code}") from exc
    except urllib.error.URLError as exc:
        raise CaptureError("network_unavailable") from exc
    text = raw.decode("utf-8", "replace")
    _require(not CHALLENGE.search(text[:8000]), "challenge_or_access_denied")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CaptureError("response_is_not_json") from exc
    _require(isinstance(payload, dict) and payload.get("code") == 200
             and isinstance(payload.get("data"), dict), "unexpected_payload_shape")
    return payload


def _audiences(record: dict) -> list[str]:
    """Map catalogue role codes onto the repository's audience vocabulary."""
    codes = {str(r.get("rolecode", "")).lower()
             for r in record.get("role", []) if isinstance(r, dict)}
    names = set()
    auth = record.get("auth")
    if isinstance(auth, dict):
        names = {n.strip() for n in str(auth.get("roleName") or "").split(",") if n.strip()}
    tags: list[str] = []
    if {"student", "99"} & codes or any("学生" in n for n in names):
        tags.append("undergraduate")
    if {"graduate", "33"} & codes or any("研究生" in n for n in names):
        tags.append("graduate")
    if {"teacher", "66", "jzjs"} & codes or any("教师" in n or "教职工" in n for n in names):
        tags.append("staff")
    if any("校友" in n for n in names) or any("XIAOYOU" in c.upper() for c in codes):
        tags.append("alumni")
    if "visitorAuth" in codes or any("访客" in n for n in names):
        tags.append("visitor")
    return tags or ["all"]


def _flatten(record: dict) -> dict:
    auth = record.get("auth") if isinstance(record.get("auth"), dict) else {}
    return {
        "service_id": record.get("id"),
        "code": (record.get("code") or "").strip(),
        "name": (record.get("name") or "").strip(),
        "pinyin": record.get("pinyin"),
        "department": (record.get("deptName") or "").strip(),
        "department_id": record.get("deptId"),
        "service_object_text": auth.get("roleName"),
        "audiences": _audiences(record),
        "description_html": record.get("desc"),
        "start_date": record.get("startDate") or None,
        "end_date": record.get("endDate") or None,
        "updated_at_ms": record.get("opdate"),
        "source_url": LIST_ENDPOINT,
    }


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _discovery(rows: list[dict], pages: list[dict], reported_total: int,
               page_size: int, shape_pages: dict[str, int]) -> dict:
    """Mirror the established catalog-discovery artifact shape; candidate authority only."""
    return {
        "schema_version": 1,
        "method": "public_nonlogin_json_api_paged",
        "endpoint": LIST_ENDPOINT,
        "query_shapes": [
            {"shape": shape, "page_size": page_size, "pages": count}
            for shape, count in shape_pages.items()
        ],
        "collected_at": date.today().isoformat(),
        "collection_precision": "day",
        "authority": "candidate_only",
        "network_access": True,
        "browser_access": False,
        "credentials_used": False,
        "personal_data_collected": False,
        "official_url_only": True,
        "public_prefix_enforced": PUBLIC_PREFIX,
        "reported_total": reported_total,
        "captured_unique": len(rows),
        "full_coverage_claimed": bool(reported_total) and len(rows) == reported_total,
        "raw_page_sha256": [
            _digest(json.dumps(payload, ensure_ascii=False).encode()) for payload in pages],
        "known_limits": [
            "Catalogue metadata only: no service steps, materials, fees or contacts.",
            "Pages behind the campus identity provider are not collected.",
            "description_html is publisher markup, not an adopted body.",
            "A directory listing does not establish that a service is currently open.",
        ],
        "items": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--page-size", type=int, default=PAGE_SIZE)
    parser.add_argument("--delay", type=float, default=0.8, help="Seconds between pages")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    _require(args.page_size > 0, "invalid_page_size")

    pages: list[dict] = []
    rows: list[dict] = []
    seen: set[str] = set()
    reported_total = 0
    shape_pages: dict[str, int] = {}
    for shape in QUERY_SHAPES:
        page, total_pages = 1, 1
        shape_pages[shape] = 0
        while page <= total_pages:
            params = {"pageSize": args.page_size}
            if shape == "pageIndex":
                params["pageIndex"] = page
            url = LIST_ENDPOINT + "?" + urllib.parse.urlencode(params)
            payload = _fetch(url, args.timeout)
            block = payload["data"]
            total_pages = int(block.get("totalPage") or 1) if shape == "pageIndex" else 1
            reported_total = max(reported_total, int(block.get("total") or 0))
            batch = block.get("data") or []
            _require(isinstance(batch, list), "unexpected_payload_shape")
            pages.append(payload)
            shape_pages[shape] += 1
            fresh = 0
            for record in batch:
                if not isinstance(record, dict):
                    continue
                flat = _flatten(record)
                if not flat["service_id"] or flat["service_id"] in seen:
                    continue
                seen.add(flat["service_id"])
                rows.append(flat)
                fresh += 1
            print(f"{shape} page {page}/{total_pages}: {len(batch)} rows, {fresh} new "
                  f"(unique so far {len(rows)} of {reported_total} reported)")
            if shape == "default":
                break
            page += 1
            if page <= total_pages:
                time.sleep(args.delay)
        time.sleep(args.delay)

    _require(bool(rows), "no_records_captured")
    if reported_total and len(rows) != reported_total:
        print(f"NOTE: captured {len(rows)} unique of {reported_total} reported; review the "
              f"query shapes before adopting.")

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "raw_pages.json").write_text(
        json.dumps(pages, ensure_ascii=False, indent=1), encoding="utf-8")
    (args.output / "service_index.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    discovery = _discovery(rows, pages, reported_total, args.page_size, shape_pages)
    (args.output / "discovery.json").write_text(
        json.dumps(discovery, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Captured {len(rows)} catalogue entries "
          f"(full coverage: {discovery['full_coverage_claimed']}) -> {args.output}")


if __name__ == "__main__":
    main()
