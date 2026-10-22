"""Strict answer schema with an equivalent escape repair for literal line breaks only."""

import json

from pydantic import ValidationError

from campuspilot.llm.chat_model import GroundedAnswer


def parse_answer(content: str) -> tuple[GroundedAnswer, bool]:
    """Return validated JSON and whether literal whitespace needed JSON escaping.

    Some providers emit real newlines in an answer string instead of ``\\n``. JSON's
    permissive string parser preserves their exact value; re-encoding only fixes escaping.
    It must not fill missing fields, close truncated JSON, or coerce the answer schema.
    """
    try:
        return GroundedAnswer.model_validate_json(content), False
    except ValidationError as original:
        # No other control characters are eligible, including NUL inside quoted strings.
        if any(ord(char) < 32 and char not in "\n\r\t" for char in content):
            raise
        try:
            json.loads(content)
        except json.JSONDecodeError as exc:
            if not exc.msg.startswith("Invalid control character"):
                raise original from None
        else:
            raise original from None  # Valid JSON with an invalid schema is never repaired.
        try:
            value = json.loads(content, strict=False)
            return GroundedAnswer.model_validate_json(json.dumps(value)), True
        except (ValueError, TypeError):
            raise original from None
