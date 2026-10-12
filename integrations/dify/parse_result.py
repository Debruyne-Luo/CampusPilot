"""Dify Code node: references come only from the actual authenticated HTTP response."""

import json
import re


def main(body: str, status_code: int) -> dict:
    failure = {
        "state": "unavailable",
        "context": "",
        "reply": "业务查询暂不可用，请稍后再试。",
        "references": json.dumps({"service_ids": [], "teacher_ids": [], "place_ids": []}),
    }
    try:
        data = json.loads(body)
        if status_code != 200 or not isinstance(data, dict):
            return failure
        state = data.get("status")
        if state not in ("success", "needs_clarification", "out_of_scope", "empty"):
            return failure
        reply = data.get("message")
        if not isinstance(reply, str) or not reply.strip() or len(reply) > 2000:
            return failure
        references = {}
        for plural, key, limit in (
            ("services", "service_id", 8),
            ("teachers", "teacher_id", 8),
            ("places", "place_id", 25),
        ):
            records = data.get(plural, [])
            if not isinstance(records, list) or len(records) > limit:
                return failure
            ids = []
            for record in records:
                if not isinstance(record, dict) or record.get("synthetic") is not False:
                    return failure
                ident = record.get(key)
                if not isinstance(ident, str) or not re.fullmatch(
                    r"cdut:[a-z0-9][a-z0-9:-]*", ident
                ):
                    return failure
                if ident not in ids:
                    ids.append(ident)
            references[key + "s"] = ids
        if state not in ("success", "needs_clarification") and any(references.values()):
            return failure
        if state == "success" and (not any(references.values()) or not data.get("evidence")):
            return failure
        return {
            "state": state,
            "context": json.dumps(data, ensure_ascii=False),
            "reply": reply,
            "references": json.dumps(references, ensure_ascii=False),
        }
    except (ValueError, TypeError):
        return failure
