from types import SimpleNamespace

import pytest

from eob import app_logic
from eob.settings import load_cloud_settings


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "medium"),
        ("", "medium"),
        ("low", "low"),
        (" HIGH ", "high"),
        ("default", None),
        ("none", None),
        ("OFF", None),
    ],
)
def test_effort_is_parsed_and_default_leaves_it_out(monkeypatch, value, expected):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    if value is None:
        monkeypatch.delenv("EOB_CLOUD_EFFORT", raising=False)
    else:
        monkeypatch.setenv("EOB_CLOUD_EFFORT", value)
    assert load_cloud_settings(env_file=None).effort == expected


def test_the_app_says_model_default_when_no_effort_is_set(monkeypatch):
    monkeypatch.setattr(
        app_logic, "load_cloud_settings", lambda: SimpleNamespace(model="claude-haiku-5-5", effort=None)
    )
    assert app_logic.cloud_status() == (True, "Model: claude-haiku-5-5 (effort: model default)")