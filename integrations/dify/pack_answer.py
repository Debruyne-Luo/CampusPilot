"""Dify Code node: the model supplies prose only; it cannot select card identifiers."""

import json


def main(text: str, state: str, references: str) -> dict:
    ids = json.loads(references)
    # references is wired exclusively from parse_result, never from a model or sys.query.
    if state not in ("success", "needs_clarification", "out_of_scope", "empty", "unavailable"):
        raise ValueError("Invalid workflow state")
    if not isinstance(text, str) or not text.strip() or len(text) > 100_000:
        raise ValueError("Missing or oversized answer")
    return {
        "answer": json.dumps(
            {"schema_version": 1, "status": state, "answer": text, **ids}, ensure_ascii=False
        )
    }
