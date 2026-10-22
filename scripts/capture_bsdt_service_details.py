"""Collect the public per-service detail published by the Yanhu Yiban service hall.

Two public `/nonlogin/` reads per service: the structured `extends.htm` record (handling
mode, channel, hours, phone numbers, nature, time limits, on-site visits) and the
introduction page that carries the publisher's advisory notes. Both are open to visitors, so
no campus session and no credentials are used, and any path outside the public prefix is
refused. Steps, materials and forms stay behind the identity provider and are not collected.

Output is a candidate capture layer artifact: it does not classify a service into the
directory store and does not touch the published knowledge pointer.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HOST = "https://bsdt.cdut.edu.cn"
EXTENDS = "/EIP/nonlogin/elobby/service/introduction/extends.htm"
INTRODUCTION = "/EIP/nonlogin/elobby/service/introduction/{service_id}.htm"
PUBLIC_PREFIX = "/EIP/nonlogin/"
CHALLENGE = re.compile(
    r"\b412\s+Precondition|access denied|verify (?:you are|your browser)|"
    r"checking your browser|安全验证|访问过于频繁|请开启JavaScript", re.IGNORECASE)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": HOST + "/EIP/nonlogin/onewebsitehande/toPersonalCenterPage.htm",
}
# Fields the service hall publishes about handling. Absent keys are dropped, never defaulted.
STRUCTURED = {
    "applyType": "handling_mode_text",
    "entry": "handling_entry_text",
    "serviceType": "matter_nature_text",
    "serviceRoutine": "handling_hours_text",
    "serviceTime": "service_validity_text",
    "contactNumber": "enquiry_phone",
    "supervisionNumber": "supervision_phone",
    "promiseTime": "promised_days",
    "promiseTimeType": "promised_unit",
    "promiseTimeDesc": "promised_note",
    "presentTime": "onsite_visits",
    "presentDesc": "onsite_note",
    "deptName": "department",
    "serviceCode": "code",
}


class CaptureError(ValueError):
    """Reasons carry no source body, credential or personal detail."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise CaptureError(reason)


def _get(url: str, timeout: int) -> str:
    _require(urllib.parse.urlsplit(url).path.startswith(PUBLIC_PREFIX),
             "only_public_nonlogin_paths")
    request = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            _require(response.status == 200, "unexpected_status")
            text = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise CaptureError(f"http_{exc.code}") from exc
    except urllib.error.URLError as exc:
        raise CaptureError("network_unavailable") from exc
    _require(not CHALLENGE.search(text[:8000]), "challenge_or_access_denied")
    return text


def _visible(fragment: str) -> str:
    """Publisher markup to plain lines, preserving one note per line."""
    text = fragment.replace("</p>", "\n").replace("</h4>", "\n").replace("<br/>", "\n")
    text = text.replace("<br>", "\n").replace("</li>", "\n").replace("</div>", "\n")
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace("\xa0", " ")
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _advisory(page: str) -> str:
    """The advisory body the publisher injects into the `otherContent` panel.

    The introduction page carries this markup inside a script string that gates the panel,
    so read it from there rather than from the rendered container skeleton.
    """
    for pattern in (
        r"""if\(\s*(['"])(?P<body>.*?)\1\s*\)\s*\{\s*\$\("#otherContent"\)""",
        r"""\$\("#otherContent"\)\.html\(\s*(['"])(?P<body>.*?)\1\s*\)""",
    ):
        match = re.search(pattern, page, re.DOTALL)
        if match:
            body = match.group("body")
            body = body.replace("\\'", "'").replace('\\"', '"').replace("\\/", "/")
            return _visible(body)
    return ""


def fetch_detail(service_id: str, timeout: int) -> dict:
    _require(re.fullmatch(r"[a-z0-9]{8,64}", service_id or ""), "invalid_service_id")
    query = urllib.parse.urlencode({"serviceId": service_id})
    payload = json.loads(_get(f"{HOST}{EXTENDS}?{query}", timeout))
    _require(payload.get("code") == 200 and isinstance(payload.get("data"), dict),
             "unexpected_payload_shape")
    raw = payload["data"]
    detail: dict = {"service_id": service_id}
    for source_key, name in STRUCTURED.items():
        value = raw.get(source_key)
        if value in (None, ""):
            continue
        detail[name] = str(value).strip() or None
    for key in ("promise",):
        if key in raw:
            detail[key] = raw[key]

    page = _get(f"{HOST}{INTRODUCTION.format(service_id=service_id)}", timeout)
    detail["advisory_text"] = _advisory(page) or None
    visits = re.search(r"parseCount\((\d+)\)", page)
    if visits:
        detail["visits"] = int(visits.group(1))
    return {k: v for k, v in detail.items() if v is not None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--delay", type=float, default=0.6)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    records = json.loads(args.index.read_bytes())
    _require(isinstance(records, list) and records, "invalid_service_index")
    targets = [r for r in records if r.get("service_id")]
    if args.limit:
        targets = targets[:args.limit]

    details: list[dict] = []
    failures: list[dict] = []
    for number, record in enumerate(targets, 1):
        try:
            details.append(fetch_detail(record["service_id"], args.timeout))
        except (CaptureError, KeyError, TypeError, json.JSONDecodeError) as exc:
            failures.append({"service_id": record.get("service_id"),
                             "name": record.get("name"), "reason": str(exc)})
        if number % 20 == 0 or number == len(targets):
            print(f"{number}/{len(targets)} captured, {len(failures)} failed")
        time.sleep(args.delay)

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "service_details.json").write_text(
        json.dumps(details, ensure_ascii=False, indent=1), encoding="utf-8")
    if failures:
        (args.output / "service_details_failures.json").write_text(
            json.dumps(failures, ensure_ascii=False, indent=1), encoding="utf-8")

    keys = ("enquiry_phone", "handling_hours_text", "matter_nature_text",
            "promised_unit", "advisory_text", "handling_entry_text")
    coverage = {k: sum(1 for d in details if d.get(k)) for k in keys}
    print(f"Captured {len(details)} details, {len(failures)} failed")
    print(f"coverage: {coverage}")


if __name__ == "__main__":
    main()
