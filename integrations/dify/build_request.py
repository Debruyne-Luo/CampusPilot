"""Dify Code node: validate extracted intent; never accept identifiers or URLs."""

import json
import re


def main(text: str) -> dict:
    blank = {
        "kind": "unknown",
        "query": "",
        "service_key": "unknown",
        "audience": "unknown",
        "academic_year": None,
    }
    try:
        data = json.loads(text)
        if not isinstance(data, dict) or set(data) - set(blank):
            raise ValueError()
        body = {**blank, **data}
        if body["kind"] not in ("service", "teacher", "place", "unknown"):
            raise ValueError()
        if body["service_key"] not in (
            "campus_card_loss",
            "campus_card_replacement",
            "enrollment_proof",
            "tuition_receipt",
            "unknown",
        ):
            raise ValueError()
        if body["audience"] not in ("graduate", "undergraduate", "staff", "unknown"):
            raise ValueError()
        if not isinstance(body["query"], str) or len(body["query"]) > 120:
            raise ValueError()
        year = body["academic_year"]
        if year is not None and (
            not isinstance(year, str) or not re.fullmatch(r"\d{4}-\d{4}", year)
        ):
            raise ValueError()
        # A recognized service key already identifies a service. The model can otherwise
        # return kind=unknown alongside campus_card_replacement for a clear normal question.
        if body["kind"] == "unknown" and body["service_key"] != "unknown":
            body["kind"] = "service"
        blank = body
    except (ValueError, TypeError):
        pass
    return {"body": json.dumps(blank, ensure_ascii=False)}
