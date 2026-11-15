import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from support import FakeClient, good_reply, prepare_case

from eob import app_logic
from eob.evaluation import ROOT, load_gold
from eob.explainer import ExplainResult
from eob.settings import MissingKeyError
from healthcore.privacy.pseudonymizer import Pseudonymizer

CASE = "syn_duplicate_same_day"


def case_file(case_id):
    return ROOT / next(case["file"] for case in load_gold()["cases"] if case["id"] == case_id)


def sample_bytes(case_id=CASE):
    return case_file(case_id).read_bytes()


def claim_for(case_id=CASE):
    return app_logic.load_claim_from_path(case_file(case_id), case_id)


def test_every_gold_case_is_offered_as_a_sample_from_the_fixtures_folder():
    samples = app_logic.list_samples()
    assert len(samples) == len(load_gold()["cases"])
    for path in samples.values():
        assert path.exists() and "fixtures" in path.parts


def test_a_sample_loads_with_figures_questions_and_a_fallback_explanation():
    claim = claim_for()
    assert claim.label == CASE
    assert dict(app_logic.headline_figures(claim))["Billed"] == "$300.00"
    assert any(flag.code == "possible_duplicate_line" for flag in claim.analysis.flags)
    assert claim.template.what_happened


def test_an_uploaded_file_loads_under_its_own_name():
    claim = app_logic.load_claim_from_bytes(sample_bytes(), "mine.json")
    assert claim.label == "mine.json"
    assert dict(app_logic.headline_figures(claim))["You owe"] == "$36.00"


def test_unreported_figures_are_shown_as_not_stated():
    figures = dict(app_logic.headline_figures(claim_for("syn_owed_not_reported")))
    assert figures["You owe"] == "Not stated"
    assert figures["Allowed"] == "Not stated"


def test_a_session_keeps_parsed_data_only_never_the_raw_file():
    assert set(app_logic.LoadedClaim.__dataclass_fields__) == {
        "label", "eob", "analysis", "template", "blocked_values",
    }


def test_bad_files_get_friendly_messages_that_never_echo_the_content():
    with pytest.raises(app_logic.DocumentError, match="larger than"):
        app_logic.load_claim_from_bytes(b" " * (app_logic.MAX_UPLOAD_BYTES + 1), "x")
    with pytest.raises(app_logic.DocumentError, match="not valid JSON") as error:
        app_logic.load_claim_from_bytes(b"not json at all, Alicia Moreno", "x")
    assert "Alicia" not in str(error.value)
    with pytest.raises(app_logic.DocumentError, match="ExplanationOfBenefit"):
        app_logic.load_claim_from_bytes(json.dumps({"resourceType": "Patient"}).encode(), "x")
    with pytest.raises(app_logic.DocumentError, match="not a FHIR resource"):
        app_logic.load_claim_from_bytes(b"[1, 2, 3]", "x")


def test_an_older_fhir_version_is_explained_not_crashed_on():
    old = {"resourceType": "ExplanationOfBenefit", "item": [{"sequence": 1, "service": {"coding": [{"code": "1"}]}}]}
    with pytest.raises(app_logic.DocumentError, match="STU3"):
        app_logic.load_claim_from_bytes(json.dumps(old).encode(), "x")


def test_a_bundle_must_contain_exactly_one_eob():
    resource = json.loads(sample_bytes())
    entry = {"resource": resource}
    one = json.dumps({"resourceType": "Bundle", "entry": [entry]}).encode()
    assert app_logic.load_claim_from_bytes(one, "bundle.json").eob.eob_id == resource["id"]
    for entries in ([], [entry, entry]):
        data = json.dumps({"resourceType": "Bundle", "entry": entries}).encode()
        with pytest.raises(app_logic.DocumentError, match="exactly one"):
            app_logic.load_claim_from_bytes(data, "bundle.json")


def test_sample_claims_must_come_from_the_fixtures_folder():
    with pytest.raises(app_logic.DocumentError, match="fixtures"):
        app_logic.load_claim_from_path(Path(__file__), "x")


def test_cloud_runs_only_when_the_payload_matches_what_was_approved(detector):
    claim = claim_for()
    payload, _ = prepare_case(CASE, detector)
    pseudonymizer = Pseudonymizer()
    shown = app_logic.preview_payload(claim, pseudonymizer, detector).json_text

    client = FakeClient([good_reply(payload)])
    approved = app_logic.run_cloud(claim, client, pseudonymizer, shown, detector)
    assert approved.source == "ai"
    assert shown in client.calls[0][1]

    other = FakeClient([good_reply(payload)])
    tampered = app_logic.run_cloud(claim, other, pseudonymizer, shown + " ", detector)
    assert other.calls == []
    assert tampered.source == "template"
    assert tampered.problems == ("declined_by_user",)


def test_fallback_reasons_are_written_for_people(detector):
    claim = claim_for()

    def reason(**fields):
        return app_logic.describe_fallback(ExplainResult(claim.template, "template", **fields))

    assert "nothing was sent" in reason(problems=("leak_guard_blocked",))
    assert "no longer matched" in reason(problems=("declined_by_user",))
    assert "failed (boom)" in reason(problems=("api_error",), error="boom")
    assert "ungrounded_amount" in reason(problems=("ungrounded_amount",))
    assert reason() == "no AI answer was available."


def test_the_draft_uses_the_members_details_locally():
    draft = app_logic.make_draft(claim_for(), " Jane Q. Member ", "ABC123456")
    assert "Jane Q. Member" in draft.body and "ABC123456" in draft.body
    assert draft.to_fill == ()


def test_cloud_status_reports_a_missing_key_or_the_chosen_model(monkeypatch):
    def missing():
        raise MissingKeyError("ANTHROPIC_API_KEY is not set.")

    monkeypatch.setattr(app_logic, "load_cloud_settings", missing)
    assert app_logic.cloud_status() == (False, "ANTHROPIC_API_KEY is not set.")
    monkeypatch.setattr(
        app_logic, "load_cloud_settings", lambda: SimpleNamespace(model="m", effort="medium")
    )
    assert app_logic.cloud_status() == (True, "Model: m (effort: medium)")
