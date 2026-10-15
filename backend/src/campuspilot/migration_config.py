"""Explicit file-backed credentials and public evaluation configuration."""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

from campuspilot.chat_model import ChatCompletionsModel
from campuspilot.evaluation_budget import TokenPrice
from campuspilot.jev_shadow import JevShadowClient


def secret(prefix: str) -> str:
    inline, file_name = (
        os.environ.get(prefix + "_API_KEY", ""),
        os.environ.get(prefix + "_KEY_FILE", ""),
    )
    if inline and file_name:
        raise ValueError("Choose a key file or environment key, not both")
    if not file_name:
        return inline.strip()
    path = Path(file_name)
    if not path.is_absolute() or path.stat().st_size > 8192:
        raise ValueError("Invalid key file")
    repo = Path(__file__).resolve().parents[3]
    if path.resolve().is_relative_to(repo):
        raise ValueError("Credential files must stay outside the repository")
    key = path.read_text(encoding="utf-8-sig").strip()
    if not key or any(c.isspace() for c in key):
        raise ValueError("Key file must contain one nonempty key")
    return key


def bounded_float(name: str, default: float) -> float:
    """Positive numeric budget from the environment; blank or unset means the default."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def bounded_int(name: str, default: int) -> int:
    """Integer budget from the environment; blank or unset means the default."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def price(prefix: str) -> TokenPrice:
    names = (prefix + "_INPUT_USD_PER_MILLION", prefix + "_OUTPUT_USD_PER_MILLION")
    values = [os.environ.get(n, "").strip() for n in names]
    if not all(values):
        raise ValueError("Known input and output prices are required before paid evaluation")
    return TokenPrice(Decimal(values[0]), Decimal(values[1]))


def generation_model() -> ChatCompletionsModel | None:
    base, model = (
        os.environ.get("CAMPUSPILOT_MODEL_BASE_URL", ""),
        os.environ.get("CAMPUSPILOT_MODEL", ""),
    )
    if not base and not model:
        return None
    return ChatCompletionsModel(
        base_url=base,
        model=model,
        api_key=secret("CAMPUSPILOT_MODEL"),
        timeout_seconds=bounded_float("CAMPUSPILOT_MODEL_TIMEOUT", 14.0),
        max_output_tokens=bounded_int("CAMPUSPILOT_MODEL_MAX_TOKENS", 700),
    )


def shadow_client() -> JevShadowClient:
    return JevShadowClient(
        api_key=secret("CAMPUSPILOT_JEV"),
        price=price("CAMPUSPILOT_JEV"),
        model=os.environ.get("CAMPUSPILOT_JEV_MODEL", "typesafe/jev-1.13"),
    )
