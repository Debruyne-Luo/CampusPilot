"""Single source of runtime settings, read once from the process environment."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from campuspilot.chat_runtime import Mode

DEFAULT_DIFY_BASE_URL = "https://api.dify.ai/v1"
MODES: frozenset[str] = frozenset({"legacy", "phase1", "phase2"})


def parse_mode(value: str) -> Mode:
    if value not in MODES:
        raise ValueError("Invalid runtime mode")
    return cast(Mode, value)


RETRIEVAL_MODES: frozenset[str] = frozenset({"lexical", "vector", "hybrid"})


def parse_retrieval_mode(value: str) -> str:
    if value not in RETRIEVAL_MODES:
        raise ValueError("Invalid retrieval mode")
    return value


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path("data/cdut")
    runtime_mode: Mode = "legacy"
    dify_api_key: str = field(default="", repr=False)
    dify_base_url: str = DEFAULT_DIFY_BASE_URL
    dify_structured_answers: bool = False
    api_token: str | None = field(default=None, repr=False)
    public_origin: str | None = None
    amap_key: str = field(default="", repr=False)
    amap_security_code: str = field(default="", repr=False)
    daily_chat_limit: int = 100
    direct_rules_report: str = ""
    retrieval_mode: str = "hybrid"
    cf_account_id: str = field(default="", repr=False)
    cf_api_token: str = field(default="", repr=False)
    embedding_model: str = "@cf/baai/bge-m3"
    embedding_timeout: float = 2.5
    agent_loop: bool = False
    # In-repo approved knowledge bundle used instead of bootstrap.json (e.g. approved-20261011).
    knowledge_bundle: str = ""

    @property
    def embeddings_configured(self) -> bool:
        return bool(self.cf_account_id and self.cf_api_token)

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if environ is None else environ
        return cls(
            data_dir=Path(env.get("CAMPUSPILOT_DATA_DIR", "data/cdut")),
            runtime_mode=parse_mode(env.get("CAMPUSPILOT_RUNTIME_MODE", "legacy")),
            dify_api_key=env.get("DIFY_API_KEY", ""),
            dify_base_url=env.get("DIFY_API_BASE_URL", DEFAULT_DIFY_BASE_URL),
            dify_structured_answers=env.get("DIFY_STRUCTURED_ANSWERS") == "1",
            api_token=env.get("CAMPUSPILOT_API_TOKEN"),
            public_origin=env.get("PUBLIC_ORIGIN"),
            amap_key=env.get("AMAP_JS_KEY", ""),
            amap_security_code=env.get("AMAP_SECURITY_JS_CODE", ""),
            daily_chat_limit=int(env.get("CAMPUSPILOT_DAILY_CHAT_LIMIT", "100")),
            direct_rules_report=env.get("CAMPUSPILOT_DIRECT_RULES_REPORT", ""),
            retrieval_mode=parse_retrieval_mode(env.get("CAMPUSPILOT_RETRIEVAL_MODE", "hybrid")),
            cf_account_id=env.get("CF_ACCOUNT_ID", ""),
            cf_api_token=env.get("CF_API_TOKEN", ""),
            embedding_model=env.get("CAMPUSPILOT_EMBEDDING_MODEL", "@cf/baai/bge-m3"),
            embedding_timeout=float(env.get("CAMPUSPILOT_EMBEDDING_TIMEOUT", "2.5")),
            agent_loop=env.get("CAMPUSPILOT_AGENT_LOOP", "off") == "on",
            knowledge_bundle=env.get("CAMPUSPILOT_KNOWLEDGE_BUNDLE", ""),
        )
