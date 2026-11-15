from guards import forbid_network
from streamlit.testing.v1 import AppTest
from support import FakeClient, good_reply, prepare_case

from eob import app_logic
from eob.evaluation import ROOT

CASE = "syn_duplicate_same_day"
APP = str(ROOT / "app.py")


def new_app() -> AppTest:
    return AppTest.from_file(APP, default_timeout=120)


def sample_label(case_id: str) -> str:
    return next(label for label in app_logic.list_samples() if label.startswith(case_id + ":"))


def load_sample(at: AppTest, case_id: str = CASE) -> AppTest:
    at.selectbox(key="eob_sample").set_value(sample_label(case_id)).run()
    return at


def choose_cloud(at: AppTest) -> AppTest:
    mode = at.radio(key="eob_mode")
    mode.set_value(mode.options[1]).run()
    return at


def test_the_app_starts_and_invites_you_to_choose_a_claim():
    at = new_app().run()
    assert not at.exception
    assert at.title[0].value == "EOB Explainer"
    assert any("Choose a sample claim" in info.value for info in at.info)


def test_choosing_a_sample_shows_figures_tabs_and_questions_with_no_network():
    at = new_app().run()
    with forbid_network() as connections:
        load_sample(at)
    assert not at.exception
    assert connections == []
    figures = {metric.label: metric.value for metric in at.metric}
    assert figures["Billed"] == "$300.00"
    assert figures["You owe"] == "$36.00"
    assert len(at.tabs) == 4
    assert any("appears 2 times" in warning.value for warning in at.warning)


def test_cloud_mode_needs_approval_and_sends_only_the_shown_payload(detector, monkeypatch):
    payload, _ = prepare_case(CASE, detector)
    client = FakeClient([good_reply(payload)])
    monkeypatch.setattr(app_logic, "cloud_status", lambda: (True, "Model: fake-model"))
    monkeypatch.setattr(app_logic, "make_cloud_client", lambda: client)

    at = new_app().run()
    load_sample(at)
    choose_cloud(at)
    assert not at.exception
    assert at.button(key="eob_send").disabled  # not allowed until the payload is reviewed

    at.checkbox(key="eob_approved_0").check().run()
    assert not at.button(key="eob_send").disabled
    at.button(key="eob_send").click().run()
    assert not at.exception
    assert at.session_state["eob_result"].source == "ai"
    assert len(client.calls) == 1
    assert "alicia" not in client.calls[0][1].lower()  # the model never saw the provider's name
    assert any("Dr. Alicia Moreno Family Medicine" in text.value for text in at.markdown)  # restored here

    at.run()
    assert not at.checkbox(key="eob_approved_1").value  # a second send needs a fresh approval


def test_cloud_mode_without_a_key_cannot_send(monkeypatch):
    monkeypatch.setattr(app_logic, "cloud_status", lambda: (False, "ANTHROPIC_API_KEY is not set."))
    at = new_app().run()
    load_sample(at)
    choose_cloud(at)
    at.checkbox(key="eob_approved_0").check().run()
    assert at.button(key="eob_send").disabled
    assert any("ANTHROPIC_API_KEY" in error.value for error in at.error)


def test_clear_everything_erases_the_loaded_claim():
    at = new_app().run()
    load_sample(at)
    assert at.session_state["eob_claim"] is not None
    at.button(key="eob_clear").click().run()
    assert at.session_state.get("eob_claim") is None
    assert any("Choose a sample claim" in info.value for info in at.info)
