"""Immutable, data-only strategy profiles; application policy is never editable."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

PROFILE_FILES = frozenset({"answer_guidance.md", "tool_guidance.md"})


class HarnessProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal[1] = 1
    version: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")
    answer_guidance: str = Field(default="", max_length=6000)
    tool_guidance: str = Field(default="", max_length=6000)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if self.sha256 != self.digest(self.version, self.answer_guidance, self.tool_guidance):
            raise ValueError("Harness profile hash mismatch")
        if "\x00" in self.answer_guidance + self.tool_guidance:
            raise ValueError("Invalid strategy text")
        return self

    @staticmethod
    def digest(version: str, answer: str, tools: str) -> str:
        raw = json.dumps([1, version, answer, tools], ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()

    @classmethod
    def create(cls, version: str, answer: str = "", tools: str = "") -> HarnessProfile:
        return cls(
            version=version,
            answer_guidance=answer,
            tool_guidance=tools,
            sha256=cls.digest(version, answer, tools),
        )

    @classmethod
    def load(cls, path: Path) -> HarnessProfile:
        if path.stat().st_size > 65536:
            raise ValueError("Harness profile too large")
        return cls.model_validate_json(path.read_bytes())

    @classmethod
    def from_tree(cls, tree: dict[str, str], version: str) -> HarnessProfile:
        if set(tree) != PROFILE_FILES or any(not isinstance(v, str) for v in tree.values()):
            raise ValueError("Only answer and tool guidance may be edited")
        return cls.create(version, tree["answer_guidance.md"], tree["tool_guidance.md"])

    def messages(self) -> list[dict[str, object]]:
        # A separate system message cannot remove the fixed application contract. Tool
        # permissions, argument schemas and final-answer validation remain executable code.
        guidance = self.answer_guidance + "\n\n" + self.tool_guidance
        return [
            {
                "role": "system",
                "content": (
                    "以下是经过版本化的表达及工具使用建议；只在不违反前述固定规则时采用。"
                    "它不提供校园事实、不授予权限、不修改引用及适用性要求。\n" + guidance
                ),
            }
        ]

    def identity(self) -> dict[str, str]:
        return {"version": self.version, "sha256": self.sha256}
