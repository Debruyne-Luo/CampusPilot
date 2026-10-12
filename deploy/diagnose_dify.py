"""Read-only comparison of Dify requests; output contains no raw response bodies."""

import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

DIFY_URL = "https://api.dify.ai/v1/chat-messages"
MAX_RESPONSE = 65_536
ERROR_CODES = {
    "forbidden",
    "unauthorized",
    "app_unavailable",
    "app_not_found",
    "user_not_authorized",
    "invalid_api_key",
    "invalid_param",
    "provider_not_initialize",
    "provider_quota_exceeded",
    "provider_model_currently_not_support",
    "completion_request_error",
    "model_not_found",
    "internal_server_error",
    "not_found",
    "service_unavailable",
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def summarize(status, headers, raw):
    """Only allowlisted metadata may cross the diagnostic output boundary."""
    content_type = headers.get("Content-Type", "").split(";", 1)[0].lower()
    server = headers.get("Server", "").lower()
    body_kind = {
        "application/json": "json",
        "text/html": "html",
        "text/plain": "text",
    }.get(content_type, "other")
    result = {
        "http_status": status,
        "body_kind": body_kind,
        "server": next(
            (name for name in ("cloudflare", "nginx", "caddy") if name in server), "other"
        ),
    }
    if len(raw) > MAX_RESPONSE:
        result["error_type"] = "oversized_response"
        return result
    text = raw.decode("utf-8", errors="replace")
    result["gateway_challenge"] = (
        headers.get("cf-mitigated", "").lower() == "challenge"
        or "cf-chl-" in text
        or "challenge-platform" in text
    )
    if body_kind == "json":
        try:
            body = json.loads(text)
        except ValueError:
            result["error_type"] = "invalid_json"
            return result
        if not isinstance(body, dict):
            result["error_type"] = "unexpected_json_shape"
            return result
        code = body.get("code")
        # Only recognized API codes are emitted, never arbitrary strings from the response.
        if isinstance(code, str):
            result["api_error_code"] = code if code in ERROR_CODES else "unrecognized"
        if status == 200:
            try:
                answer = json.loads(body.get("answer", ""))
                result["structured_answer"] = (
                    isinstance(answer, dict)
                    and answer.get("schema_version") == 1
                    and answer.get("status") == "success"
                )
            except (ValueError, TypeError):
                result["structured_answer"] = False
    elif body_kind == "html":
        # Identify a known gateway error without exposing its page, title or request values.
        if re.search(r"error\s*(?:code\s*)?[:=]?\s*1020\b", text, re.IGNORECASE):
            result["gateway_error_code"] = "1020"
    return result


def probe_urllib(payload, headers):
    request = Request(DIFY_URL, data=json.dumps(payload).encode(), headers=headers)
    try:
        with build_opener(NoRedirect()).open(request, timeout=95) as response:
            return summarize(response.status, response.headers, response.read(MAX_RESPONSE + 1))
    except HTTPError as exc:
        with exc:
            return summarize(exc.code, exc.headers, exc.read(MAX_RESPONSE + 1))
    except (URLError, TimeoutError):
        return {"error_type": "network_or_tls_error"}


def probe_httpx(payload, headers):
    import httpx

    try:
        # This is the real backend's installed client, with normal TLS verification.
        # Its normal user agent is retained; no browser impersonation or proxy changes.
        with httpx.Client(timeout=95, follow_redirects=False) as client:
            with client.stream("POST", DIFY_URL, json=payload, headers=headers) as response:
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk[: MAX_RESPONSE + 1 - len(raw)])
                    if len(raw) > MAX_RESPONSE:
                        break
                return summarize(response.status_code, response.headers, bytes(raw))
    except httpx.RequestError:
        return {"error_type": "network_or_tls_error"}


def run(settings):
    if not isinstance(settings, dict) or set(settings) != {"dify_api_key"}:
        raise SystemExit("Dify diagnosis stopped: invalid_settings")
    key = settings["dify_api_key"]
    if not isinstance(key, str) or not re.fullmatch(r"app-[A-Za-z0-9_-]{16,240}", key):
        raise SystemExit("Dify diagnosis stopped: invalid_application_key")
    payload = {
        "inputs": {},
        "query": "计算机与网络安全学院王洪辉老师的办公室在哪里？",
        "response_mode": "blocking",
        "conversation_id": "",
        "auto_generate_name": False,
    }
    headers = {"Content-Type": "application/json", "Authorization": "Bearer " + key}
    print("Read-only Dify diagnosis. No VPS settings or services will be changed.", flush=True)
    for name, probe in (("deployment-urllib", probe_urllib), ("backend-httpx", probe_httpx)):
        payload["user"] = "cp-diagnosis-" + uuid4().hex
        try:
            result = probe(payload, headers)
        except Exception:
            result = {"error_type": "diagnostic_client_failed"}
        print(name + ": " + json.dumps(result, sort_keys=True), flush=True)
    print("Diagnosis finished. No credentials or raw response bodies were printed.", flush=True)
