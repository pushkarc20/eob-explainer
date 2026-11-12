import pytest

from eob.settings import MissingKeyError, estimate_cost, load_cloud_settings


def test_a_missing_key_gives_a_clear_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(MissingKeyError, match=".env"):
        load_cloud_settings(env_file=None)


def test_defaults_apply_when_only_the_key_is_set(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    monkeypatch.delenv("EOB_CLOUD_MODEL", raising=False)
    monkeypatch.delenv("EOB_CLOUD_EFFORT", raising=False)
    settings = load_cloud_settings(env_file=None)
    assert settings.model == "claude-sonnet-5-5"
    assert settings.effort == "medium"


def test_model_and_effort_can_be_overridden(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    monkeypatch.setenv("EOB_CLOUD_MODEL", "claude-haiku-5-5")
    monkeypatch.setenv("EOB_CLOUD_EFFORT", "low")
    settings = load_cloud_settings(env_file=None)
    assert (settings.model, settings.effort) == ("claude-haiku-5-5", "low")


def test_cost_estimate_uses_per_million_token_prices():
    assert estimate_cost("claude-sonnet-5-5", 1_000_000, 1_000_000) == pytest.approx(12.0)
    assert estimate_cost("claude-sonnet-5-5", 2000, 800) == pytest.approx(0.012)
    assert estimate_cost("some-unknown-model", 1, 1) is None
