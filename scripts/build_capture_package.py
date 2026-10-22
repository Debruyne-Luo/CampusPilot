"""Build a capture package from rendered page bodies captured by a browser.

Input is a JSON array of captures produced outside this repository (Firecrawl, a Playwright
run, or a manual save). This command only assembles and validates files; it does not crawl,
authenticate, adopt records, or touch the active knowledge pointer. Feed the resulting
package to `scripts/official_knowledge.py extract`.

Only pages reachable without a login belong here. Pages behind the campus identity provider
carry a personal centre entry URL and must stay as navigation links, not captured bodies.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))

from campuspilot.knowledge import official_url  # noqa: E402
from campuspilot.official_knowledge import CHALLENGE, load_package  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,95}$")
TAG = re.compile(r"<(?:html|script|iframe)\b", re.IGNORECASE)
MIN_BODY = 40
MAX_DOCUMENTS = 200


class CaptureError(ValueError):
    """Reasons carry no source body, credential or exception detail."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise CaptureError(reason)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _document_id(value: object, index: int) -> str:
    if value is None:
        return f"capture-{index:04d}"
    _require(isinstance(value, str) and bool(ID.fullmatch(value)), "invalid_document_id")
    return str(value)


def _day(value: object, field: str) -> date | None:
    if value in (None, ""):
        return None
    _require(isinstance(value, str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)),
             f"invalid_{field}")
    return date.fromisoformat(str(value))


def build_document(capture: dict, index: int) -> tuple[dict, bytes]:
    _require(isinstance(capture, dict), "invalid_capture")
    url = capture.get("url")
    _require(isinstance(url, str) and bool(url), "invalid_source_url")
    official_url(url)
    collected = _day(capture.get("collected_on"), "collected_on")
    _require(collected is not None, "collected_on_required")
    published = _day(capture.get("published_on"), "published_on")
    _require(published is None or published <= collected, "future_source_date")

    access_scope = capture.get("access_scope", "public")
    _require(access_scope in {"public", "authenticated_general"}, "unknown_access_scope")
    channel = capture.get("channel", "browser_dom")
    _require(channel == "browser_dom", "capture_requires_rendered_dom")
    _require(not capture.get("contains_personal_data", False), "personal_data_forbidden")

    content_kind = capture.get("content_kind", "guide")
    _require(content_kind in {"article", "guide"}, "not_document_body")
    _require(capture.get("complete", True) is True, "incomplete_document")

    title = str(capture.get("title") or "").strip()
    publisher = str(capture.get("publisher") or "").strip()
    _require(bool(title) and bool(publisher), "missing_source_identity")

    body = str(capture.get("body") or "").replace("\r\n", "\n").strip()
    _require(len(body) >= MIN_BODY, "empty_or_short_body")
    _require(not CHALLENGE.search(body), "challenge_or_access_denied_body")
    _require(not TAG.search(body), "body_must_be_visible_text")

    payload = body.encode("utf-8")
    document = {
        "document_id": _document_id(capture.get("document_id"), index),
        "status": "success",
        "url": url,
        "complete": True,
        "content_kind": content_kind,
        "channel": channel,
        "access_scope": access_scope,
        "contains_personal_data": False,
        "title": title,
        "publisher": publisher,
        "collected_on": collected.isoformat(),
        "collection_precision": "day",
        "published_on": published.isoformat() if published else None,
        "signed_on": None,
        "body_file": f"bodies/{_document_id(capture.get('document_id'), index)}.md",
        "body_sha256": _digest(payload),
    }
    return document, payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True,
                        help="JSON array of {url, title, publisher, body, collected_on, ...}")
    parser.add_argument("--output", type=Path, required=True, help="Package directory")
    parser.add_argument("--check-only", action="store_true",
                        help="Validate the assembled manifest without writing")
    args = parser.parse_args()

    raw = json.loads(args.input.read_bytes())
    _require(isinstance(raw, list) and 0 < len(raw) <= MAX_DOCUMENTS, "invalid_capture_count")

    documents: list[dict] = []
    bodies: dict[str, bytes] = {}
    seen: set[str] = set()
    for index, capture in enumerate(raw, 1):
        document, payload = build_document(capture, index)
        _require(document["document_id"] not in seen, "duplicate_document_id")
        seen.add(document["document_id"])
        documents.append(document)
        bodies[document["body_file"]] = payload

    if args.check_only:
        print(f"Captures validated: {len(documents)}")
        return

    manifest = {"schema_version": 1, "capture_tool": "external_browser_render",
                "documents": documents}
    for name, payload in bodies.items():
        target = args.output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    loaded = load_package(args.output)
    print(f"Package written: {args.output} ({len(loaded['documents'])} documents)")


if __name__ == "__main__":
    main()
