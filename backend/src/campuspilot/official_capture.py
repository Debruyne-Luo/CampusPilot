"""Bounded public-document collection; collection never grants knowledge authority.

Firecrawl is an adapter at the existing official capture-package seam. The ledger reserves
the conservative cost BEFORE submission, including unknown outcomes. No provider retry,
automatic recharge, model extraction, or unbounded discovery is enabled here.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urljoin, urlsplit

import httpx

from campuspilot.knowledge import official_url
from campuspilot.knowledge_release import atomic_write, publication_lock
from campuspilot.official_knowledge import CHALLENGE
from campuspilot.rag import canonical, digest

API = "https://api.firecrawl.dev/v2"
MAX_CREDITS = 150
MAX_BODY = 20_000_000
FORMATS = {"html", "pdf", "image", "office"}
BLOCKED_PATH = re.compile(r"/(?:cas|login|oauth|auth)(?:/|\b)", re.IGNORECASE)


def public_url(value: str) -> str:
    official_url(value, wechat=True)
    parts = urlsplit(value)
    credential_keys = {"password", "passwd", "pwd", "token", "access_token", "ticket",
                       "session", "sessionid", "cookie", "authorization"}
    if (BLOCKED_PATH.search(parts.path)
        or any(key.lower() in credential_keys for key, _ in parse_qsl(parts.query))):
        raise ValueError("authenticated_destination_not_collectable")
    return value


def request_options(item: dict[str, Any], max_pdf_pages: int = 10) -> dict[str, Any]:
    kind = item.get("format", "html")
    if kind not in {"html", "pdf"}:
        raise ValueError("format_cost_not_yet_verified")
    if not 1 <= max_pdf_pages <= 10:
        raise ValueError("invalid_pdf_page_budget")
    options: dict[str, Any] = {
        "url": public_url(item["url"]), "formats": ["markdown", "html", "links"],
        "onlyMainContent": True, "timeout": 60000,
        "parsers": [],  # HTML must not silently enter an unbudgeted attachment parser.
    }
    if kind == "pdf":
        options["formats"] = ["markdown"]
        options["parsers"] = [{"type": "pdf", "mode": "auto", "maxPages": max_pdf_pages,
                               "pages": True, "blocks": True}]
    return options


def reserved_cost(item: dict[str, Any], max_pdf_pages: int) -> int:
    request_options(item, max_pdf_pages)
    # Billing docs are inconsistent about base URL + PDF pages; reserve the higher cost.
    return 1 + max_pdf_pages if item.get("format") == "pdf" else 1


def classify_response(payload: dict[str, Any], kind: str, page_limit: int) -> dict[str, Any]:
    data = payload.get("data", {})
    if payload.get("success") is not True or not isinstance(data, dict):
        return {"status": "access_failed", "reason": "provider_unsuccessful"}
    metadata = data.get("metadata") or {}
    body = data.get("markdown") or ""
    if not isinstance(metadata, dict) or not isinstance(body, str):
        return {"status": "access_failed", "reason": "invalid_provider_document"}
    code = metadata.get("statusCode")
    if not isinstance(code, int) or not 200 <= code < 300:
        return {"status": "access_failed", "reason": "target_status_not_success",
                "target_status": code}
    if CHALLENGE.search(body) or CHALLENGE.search(str(data.get("html", ""))[:20000]):
        return {"status": "access_failed", "reason": "challenge_body"}
    if len(body.strip()) < 40:
        return {"status": "access_failed", "reason": "missing_document_body"}
    final_url = metadata.get("sourceURL") or metadata.get("url")
    if final_url:
        try:
            public_url(final_url)
        except (ValueError, TypeError):
            return {"status": "out_of_scope", "reason": "redirect_outside_public_sources"}
    warning = data.get("warning") or ""
    if warning and re.search(r"truncat|partial|limit|incomplete", str(warning), re.I):
        return {"status": "truncated", "reason": "provider_partial_document"}
    if kind == "pdf":
        total = metadata.get("totalPages") or metadata.get("numPages")
        pages = data.get("pages") or []
        if isinstance(total, int) and total > page_limit:
            return {"status": "truncated", "reason": "pdf_page_limit", "total_pages": total}
        if not isinstance(total, int) or not isinstance(pages, list) or len(pages) != total:
            return {"status": "pending_review", "reason": "pdf_completeness_unverified"}
    return {"status": "pending_review", "reason": "body_requires_source_review"}


def attachment_links(url: str, links: list[str]) -> list[dict[str, str]]:
    results = {}
    suffixes = {".pdf": "pdf", ".xlsx": "office", ".docx": "office", ".doc": "office",
                ".xls": "office", ".png": "image", ".jpg": "image", ".jpeg": "image"}
    for link in links:
        if not isinstance(link, str):
            continue
        absolute = urljoin(url, link)
        try:
            public_url(absolute)
        except ValueError:
            continue
        kind = suffixes.get(Path(urlsplit(absolute).path).suffix.lower())
        if kind:
            results[absolute] = {"url": absolute, "format": kind, "parent_url": url}
    return list(results.values())


def embedded_images(url: str, markdown: str) -> list[dict[str, str]]:
    """Inventory image dependencies without claiming OCR or fetching third-party assets."""
    images: dict[str, dict[str, str]] = {}
    wechat = urlsplit(url).hostname == "mp.weixin.qq.com"
    for match in re.finditer(r"!\[[^\]]*\]\((https://[^\s)]+)\)", markdown):
        original = match[1]
        parts = urlsplit(original)
        if parts.username or parts.password or parts.port not in (None, 443):
            continue
        host = parts.hostname or ""
        official = host == "cdut.edu.cn" or host.endswith(".cdut.edu.cn")
        attributed_wechat = wechat and host in {"mmbiz.qpic.cn", "mmecoa.qpic.cn"}
        if official or attributed_wechat:
            images[original] = {
                "url": original, "parent_url": url, "format": "image",
                "status": "missing_ocr", "reason": "embedded_image_not_parsed_as_text",
            }
    return list(images.values())


class FirecrawlCollector:
    def __init__(
        self, key: str, directory: Path, *, credit_limit: int = 150,
        max_pdf_pages: int = 10, client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not key.strip() or not 1 <= credit_limit <= MAX_CREDITS:
            raise ValueError("invalid_credential_or_budget")
        if not 1 <= max_pdf_pages <= 10:
            raise ValueError("invalid_pdf_page_budget")
        self.key, self.directory = key.strip(), directory
        self.limit, self.page_limit = credit_limit, max_pdf_pages
        self.client = client or httpx.Client(timeout=75, follow_redirects=False)
        self.sleep = sleep

    def _usage(self) -> dict[str, Any]:
        response = self.client.get(API + "/team/credit-usage",
                                   headers={"Authorization": "Bearer " + self.key})
        if response.status_code != 200:
            raise ValueError("credit_balance_unavailable")
        data = response.json().get("data", {})
        balance = data.get("remainingCredits")
        if (type(balance) not in (int, float) or not math.isfinite(balance)
            or balance < 0):
            raise ValueError("credit_balance_unavailable")
        return {k: data.get(k) for k in ("remainingCredits", "planCredits",
                                       "billingPeriodStart", "billingPeriodEnd")}

    def collect(
        self, items: list[dict[str, Any]], *, free_plan_confirmed: bool,
        max_followups: int = 8,
    ) -> dict[str, Any]:
        if not free_plan_confirmed:
            raise ValueError("free_billing_status_confirmation_required")
        if not 0 < len(items) <= 200 or not 0 <= max_followups <= 8:
            raise ValueError("invalid_collection_bounds")
        # Validate every URL before the first remote call or reservation.
        for item in items:
            public_url(item["url"])
            if item.get("format", "html") not in FORMATS:
                raise ValueError("unsupported_document_format")
        with publication_lock(self.directory):
            ledger_path = self.directory / "collection.json"
            ledger: dict[str, Any] = (
                json.loads(ledger_path.read_bytes()) if ledger_path.exists() else {
                "schema_version": 1, "provider": "firecrawl-v2", "requests": [],
                "reserved_credits": 0, "credit_limit": self.limit, "recharge_allowed": False,
                "published": False, "adopted": False, "max_pdf_pages": self.page_limit,
            })
            if (ledger.get("credit_limit") != self.limit
                or ledger.get("max_pdf_pages", 10) != self.page_limit
                or ledger.get("provider") != "firecrawl-v2"):
                raise ValueError("resume_budget_must_match")
            try:
                ledger["balance_before_run"] = self._usage()
            except (httpx.HTTPError, ValueError):
                ledger["blocked_reason"] = "credit_balance_unavailable"
                atomic_write(ledger_path, canonical(ledger))
                return ledger
            balance = ledger["balance_before_run"]["remainingCredits"]
            if ledger.get("initial_remaining_credits") is None:
                ledger["initial_remaining_credits"] = balance
            effective_limit = min(self.limit, ledger["initial_remaining_credits"])
            processed = {r["url"] for r in ledger["requests"]}
            queue = list(items)
            discovered = list(ledger.get("discovered_attachments", []))
            follows = 0
            for item in queue:
                if item["url"] in processed:
                    continue  # Includes uncertain timed-out submissions: no blind resubmit.
                kind = item.get("format", "html")
                if kind not in {"html", "pdf"}:
                    ledger.setdefault("deferred", []).append({
                        "url": item["url"], "reason": "format_cost_not_yet_verified"})
                    continue
                cost = reserved_cost(item, self.page_limit)
                if cost > balance or ledger["reserved_credits"] + cost > effective_limit:
                    ledger.setdefault("deferred", []).append({
                        "url": item["url"], "reason": "free_credit_budget_exhausted"})
                    continue
                options = request_options(item, self.page_limit)
                capture_id = "fc-" + digest(item["url"].encode())[:16]
                row: dict[str, Any] = {
                    "document_id": capture_id, "url": item["url"], "format": kind,
                    "collected_at": datetime.now(UTC).isoformat(), "reserved_credits": cost,
                    "request": options, "status": "unknown", "reason": "submission_in_progress",
                    "parent_url": item.get("parent_url"),
                }
                ledger["requests"].append(row)
                ledger["reserved_credits"] += cost
                atomic_write(ledger_path, canonical(ledger))
                try:
                    response = self.client.post(API + "/scrape", json=options,
                        headers={"Authorization": "Bearer " + self.key})
                    row["api_status"] = response.status_code
                    if response.status_code != 200:
                        row.update(status="access_failed", reason="provider_http_error")
                    else:
                        if len(response.content) > MAX_BODY:
                            raise ValueError("provider_payload_too_large")
                        payload = response.json()
                        if not isinstance(payload, dict):
                            raise ValueError("invalid_provider_document")
                        # Never persist a credential even if a provider reflects it in an error.
                        raw = canonical(payload).replace(self.key.encode(), b"[REDACTED]")
                        folder = self.directory / capture_id
                        atomic_write(folder / "response.json", raw)
                        row["response_sha256"] = digest(raw)
                        row.update(classify_response(payload, kind, self.page_limit))
                        data = payload.get("data") or {}
                        if isinstance(data, dict):
                            body = data.get("markdown")
                            if isinstance(body, str):
                                text = body.replace(self.key, "[REDACTED]").encode()
                                atomic_write(folder / "body.md", text)
                                row["body_sha256"] = digest(text)
                            for asset in attachment_links(item["url"], data.get("links") or []):
                                if asset["url"] not in {x["url"] for x in discovered}:
                                    discovered.append(asset)
                                    if follows < max_followups and asset["format"] == "pdf":
                                        queue.append(asset)
                                        follows += 1
                            for asset in embedded_images(item["url"], str(body or "")):
                                if asset["url"] not in {x["url"] for x in discovered}:
                                    discovered.append(asset)
                except (httpx.HTTPError, ValueError, KeyError, TypeError):
                    row.update(status="unknown", reason="submission_outcome_unconfirmed")
                processed.add(item["url"])
                ledger["discovered_attachments"] = discovered
                # A reservation is never released, even for failed/unknown outcomes.
                try:
                    after = self._usage()
                    row["balance_after"] = after["remainingCredits"]
                    balance = min(balance - cost, after["remainingCredits"])
                except (httpx.HTTPError, ValueError):
                    row["balance_after"] = None
                    ledger["blocked_reason"] = "credit_balance_unavailable_after_submission"
                    atomic_write(ledger_path, canonical(ledger))
                    break
                atomic_write(ledger_path, canonical(ledger))
                self.sleep(7)  # Below free-plan scrape RPM; never parallelize this loop.
            return ledger


def reviewed_capture(
    directory: Path, row: dict[str, Any], review: dict[str, Any],
) -> dict[str, Any]:
    """Convert one independently checked body to the established capture contract."""
    if row.get("status") != "pending_review":
        raise ValueError("capture_not_available_for_review")
    folder = directory / row["document_id"]
    body = (folder / "body.md").read_bytes()
    raw = (folder / "response.json").read_bytes()
    if digest(body) != review.get("body_sha256") or digest(raw) != row["response_sha256"]:
        raise ValueError("capture_review_hash_mismatch")
    if review.get("complete") is not True or not review.get("checked_by"):
        raise ValueError("capture_requires_completeness_review")
    if not review.get("required_text") or any(
        not isinstance(t, str) or not t or t not in body.decode() for t in review["required_text"]
    ):
        raise ValueError("capture_reference_text_not_verified")
    title, publisher = review.get("title"), review.get("publisher")
    if not title or not publisher:
        raise ValueError("missing_source_identity")
    return {
        "document_id": row["document_id"], "url": row["url"], "title": title,
        "publisher": publisher, "collected_at": row["collected_at"], "channel": "http",
        "content_kind": "guide", "access_scope": "public", "complete": True,
        "status": "success", "body_file": row["document_id"] + "/body.md",
        "original_file": row["document_id"] + "/response.json", "body_sha256": digest(body),
        "published_on": review.get("published_on"), "signed_on": None,
        "contains_personal_data": False,
        "collection_note": "Firecrawl body independently checked; clauses remain unadopted.",
        "source_capture": {"provider": "firecrawl-v2", "response_sha256": digest(raw),
                           "request": row["request"]},
    }
