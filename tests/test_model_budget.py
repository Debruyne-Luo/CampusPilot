"""Model budget configuration: env overrides stay within the documented bounds."""

import pytest
from campuspilot.migration_config import bounded_float, bounded_int, generation_model

BASE = "https://generativelanguage.googleapis.com/v1beta/openai"


def test_budgets_default_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CAMPUSPILOT_MODEL_TIMEOUT", raising=False)
    monkeypatch.delenv("CAMPUSPILOT_MODEL_MAX_TOKENS", raising=False)
    assert bounded_float("CAMPUSPILOT_MODEL_TIMEOUT", 14.0) == 14.0
    assert bounded_int("CAMPUSPILOT_MODEL_MAX_TOKENS", 700) == 700


def test_blank_budget_keeps_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAMPUSPILOT_MODEL_TIMEOUT", "   ")
    assert bounded_float("CAMPUSPILOT_MODEL_TIMEOUT", 14.0) == 14.0


@pytest.mark.parametrize(
    ("name", "value"),
    [("CAMPUSPILOT_MODEL_TIMEOUT", "soon"), ("CAMPUSPILOT_MODEL_MAX_TOKENS", "many")],
)
def test_non_numeric_budget_is_rejected(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        bounded_float(name, 14.0) if "TIMEOUT" in name else bounded_int(name, 700)


@pytest.mark.parametrize(
    ("name", "value"),
    [("CAMPUSPILOT_MODEL_TIMEOUT", "0"), ("CAMPUSPILOT_MODEL_MAX_TOKENS", "-5")],
)
def test_non_positive_budget_is_rejected(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        bounded_float(name, 14.0) if "TIMEOUT" in name else bounded_int(name, 700)


def test_generation_model_absent_without_base_and_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CAMPUSPILOT_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("CAMPUSPILOT_MODEL", raising=False)
    assert generation_model() is None


def test_generation_model_applies_env_budgets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAMPUSPILOT_MODEL_BASE_URL", BASE)
    monkeypatch.setenv("CAMPUSPILOT_MODEL", "SYNTHETIC model")
    monkeypatch.setenv("CAMPUSPILOT_MODEL_API_KEY", "SYNTHETIC-key")
    monkeypatch.setenv("CAMPUSPILOT_MODEL_TIMEOUT", "40")
    monkeypatch.setenv("CAMPUSPILOT_MODEL_MAX_TOKENS", "2000")
    model = generation_model()
    assert model is not None
    assert model.timeout_seconds == 40
    assert model.max_output_tokens == 2000


def test_generation_model_rejects_a_budget_over_the_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAMPUSPILOT_MODEL_BASE_URL", BASE)
    monkeypatch.setenv("CAMPUSPILOT_MODEL", "SYNTHETIC model")
    monkeypatch.setenv("CAMPUSPILOT_MODEL_API_KEY", "SYNTHETIC-key")
    monkeypatch.setenv("CAMPUSPILOT_MODEL_TIMEOUT", "120")
    with pytest.raises(ValueError):
        generation_model()
