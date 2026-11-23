from streamlit.testing.v1 import AppTest

from eob import app_logic
from eob.evaluation import ROOT

APP = str(ROOT / "app.py")
SUGGESTED = "syn_duplicate_same_day"


def new_app() -> AppTest:
    return AppTest.from_file(APP, default_timeout=120)


def suggested_label() -> str:
    return next(label for label in app_logic.list_samples() if label.startswith(SUGGESTED + ":"))


def test_the_start_screen_explains_how_to_try_it():
    at = new_app().run()
    assert not at.exception
    assert any("New here? Try this" in text.value for text in at.markdown)
    assert any(f"New here? Try {SUGGESTED}" in caption.value for caption in at.caption)


def test_the_start_guidance_goes_away_once_a_claim_is_loaded():
    at = new_app().run()
    at.selectbox(key="eob_sample").set_value(suggested_label()).run()
    assert not at.exception
    assert not any("New here? Try this" in text.value for text in at.markdown)


def test_cloud_mode_without_a_key_explains_how_to_set_one_up(monkeypatch):
    monkeypatch.setattr(app_logic, "cloud_status", lambda: (False, "ANTHROPIC_API_KEY is not set."))
    at = new_app().run()
    mode = at.radio(key="eob_mode")
    mode.set_value(mode.options[1]).run()
    assert any(".env.example" in caption.value for caption in at.caption)
    assert any("Built-in mode works without it" in caption.value for caption in at.caption)


def test_the_streamlit_config_keeps_the_app_local_and_quiet():
    config = (ROOT / ".streamlit" / "config.toml").read_text()
    for setting in (
        "gatherUsageStats = false",
        'address = "localhost"',
        'toolbarMode = "viewer"',
        'showErrorDetails = "type"',
    ):
        assert setting in config
