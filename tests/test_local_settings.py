import pytest

from eob.settings import MissingLocalModelError, load_local_settings


def test_a_missing_model_gives_a_clear_error(monkeypatch):
    monkeypatch.delenv("EOB_LOCAL_MODEL", raising=False)
    with pytest.raises(MissingLocalModelError, match="EOB_LOCAL_MODEL"):
        load_local_settings(env_file=None)


def test_defaults_apply_when_only_the_model_is_set(monkeypatch):
    monkeypatch.setenv("EOB_LOCAL_MODEL", "qwen3:8b")
    monkeypatch.delenv("EOB_LOCAL_URL", raising=False)
    monkeypatch.delenv("EOB_LOCAL_THINK", raising=False)
    settings = load_local_settings(env_file=None)
    assert settings.model == "qwen3:8b"
    assert settings.base_url == "http://localhost:11434"
    assert settings.think is None


def test_think_is_parsed_from_the_environment(monkeypatch):
    monkeypatch.setenv("EOB_LOCAL_MODEL", "qwen3:8b")
    for text, expected in (("false", False), ("TRUE", True), ("", None), ("maybe", None)):
        monkeypatch.setenv("EOB_LOCAL_THINK", text)
        assert load_local_settings(env_file=None).think is expected, text
