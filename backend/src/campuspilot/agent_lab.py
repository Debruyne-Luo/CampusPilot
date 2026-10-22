"""Read-only public experiment contracts, independent of the optimizer runtime."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from campuspilot.chat_runtime import public_input

ID_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,95}$"


class LabModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LabTrial(LabModel):
    label: str = Field(max_length=80)
    answer: str = Field(max_length=6000)
    tools: tuple[str, ...] = Field(default=(), max_length=24)
    status: str = Field(max_length=64)
    latency_ms: float = Field(ge=0, allow_inf_nan=False)
    cost_usd: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    profile_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class LabExperiment(LabModel):
    schema_version: Literal[1] = 1
    id: str = Field(pattern=ID_PATTERN)
    title: str = Field(max_length=120)
    kind: Literal["upstream_demo", "campus_public_experiment"]
    status: Literal["running", "completed", "failed", "budget_exhausted"]
    upstream_commit: Literal["1cfe254e8d25b15f37048c3730134686abe60335"]
    code_identity: str = Field(max_length=160)
    knowledge_version: str = Field(max_length=100)
    model: str = Field(max_length=120)
    question: str = Field(max_length=2000)
    stages: tuple[str, ...] = Field(default=(), max_length=40)
    changes: str = Field(default="", max_length=12000)
    lessons: str = Field(default="", max_length=6000)
    trials: tuple[LabTrial, ...] = Field(default=(), max_length=20)
    conclusion: str = Field(default="", max_length=4000)
    adopted: bool = False
    cost_usd: float | None = Field(default=None, ge=0, le=20, allow_inf_nan=False)
    limitation: str = Field(max_length=2000)

    @model_validator(mode="after")
    def public_only(self) -> LabExperiment:
        # Numeric timing/cost values are not private coordinates. Inspect exported text,
        # rather than applying the chat privacy regex to the serialized numeric fields.
        text = "\n".join(
            [
                self.title,
                self.question,
                self.changes,
                self.lessons,
                self.conclusion,
                self.limitation,
                self.code_identity,
                *(trial.answer for trial in self.trials),
            ]
        )
        if not public_input(text) or re.search(
            r"Bearer\s+|sk-[a-zA-Z0-9]{12,}|BEGIN .*PRIVATE KEY|[A-Z]:\\|/home/|/root/",
            text,
        ):
            raise ValueError("Experiment export contains private material")
        if self.adopted and self.status != "completed":
            raise ValueError("Incomplete experiments cannot be adopted")
        return self


class LabRecords:
    def __init__(self, root: Path | None) -> None:
        self.root = root.resolve() if root is not None else None

    def read(self, ident: str) -> LabExperiment:
        if self.root is None or re.fullmatch(ID_PATTERN, ident) is None:
            raise FileNotFoundError("Experiment unavailable")
        path = self.root / (ident + ".json")
        if path.is_symlink() or not path.resolve().is_relative_to(self.root):
            raise ValueError("Invalid experiment path")
        if path.stat().st_size > 262144:
            raise ValueError("Experiment too large")
        return LabExperiment.model_validate_json(path.read_bytes())

    def list(self) -> list[LabExperiment]:
        if self.root is None or not self.root.is_dir():
            return []
        result = []
        for path in sorted(self.root.glob("*.json"), reverse=True)[:50]:
            try:
                result.append(self.read(path.stem))
            except OSError, ValueError:
                # Invalid exports are not served; operators can validate them with the CLI.
                continue
        return result
