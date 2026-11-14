import pytest
from support import FakeClient, good_reply, load_case, prepare_case

from eob.engine import analyze
from eob.evaluation import ROOT, load_gold
from eob.explainer import explain
from eob.explanation import all_text
from eob.parser import parse_eob
from eob.prompts import DEFAULT_PROMPT_VERSION, PROMPTS, get_system_prompt
from eob.questions import QUESTIONS
from eob.templates import template_explanation
from healthcore.fhir.helpers import load_resource
from healthcore.privacy.pseudonymizer import Pseudonymizer

CASE = "syn_duplicate_same_day"


def template_for(case_id):
    eob, analysis, _ = load_case(case_id)
    return template_explanation(eob, analysis)


def test_one_name_for_provider_and_insurer_resolves_to_the_first_registered():
    ps = Pseudonymizer()
    ps.register("PROVIDER", "XXX Health Plan")
    ps.register("INSURER", "XXX Health Plan")
    assert ps.apply("billed by XXX Health Plan") == "billed by [PROVIDER_1]"
    assert ps.restore("[INSURER_1]") == "XXX Health Plan"


def test_the_duplicate_question_does_not_assume_a_number_of_lines():
    assert "two" not in QUESTIONS["possible_duplicate_line"].lower()


def test_the_share_note_names_coinsurance_when_it_explains_the_balance():
    _, analysis, _ = load_case("syn_high_coinsurance_plan")
    notes = [flag.ask for flag in analysis.flags if flag.code == "high_patient_share"]
    assert notes and "coinsurance" in notes[0]


def test_the_fallback_opens_with_a_plain_in_short_sentence():
    owed = template_for("syn_deductible_not_met").what_happened
    assert "In short: the plan reports a payment of $0.00, and the EOB says you owe $100.00." in owed
    unknown = template_for("syn_owed_not_reported").what_happened
    assert "In short: the plan reports a payment of $320.00, and this EOB does not state what you owe." in unknown


def test_the_fallback_no_longer_uses_the_paid_or_payable_gloss():
    for case in load_gold()["cases"]:
        eob = parse_eob(load_resource(ROOT / case["file"]))
        text = all_text(template_explanation(eob, analyze(eob)))
        assert "paid or payable" not in text, case["id"]


def test_the_verified_answer_is_kept_in_placeholder_form_for_the_judge(detector):
    payload, _ = prepare_case(CASE, detector)
    eob, analysis, blocked = load_case(CASE)
    result = explain(eob, analysis, FakeClient([good_reply(payload)]), Pseudonymizer(), detector, blocked)
    assert result.source == "ai"
    assert "[PROVIDER_1]" in all_text(result.placeholder_explanation)
    assert "[PROVIDER_1]" not in all_text(result.explanation)
    fallback = explain(eob, analysis, FakeClient(["no", "no"]), Pseudonymizer(), detector, blocked)
    assert fallback.placeholder_explanation is None


def test_prompt_versions_are_registered_and_v2_is_the_default():
    assert set(PROMPTS) == {"v1", "v2"}
    assert DEFAULT_PROMPT_VERSION == "v2"
    assert "paid or payable" in get_system_prompt("v1")  # v1 is kept exactly as first evaluated
    assert "Do not say what a service code means" in get_system_prompt("v2")
    assert "never swap them" in get_system_prompt("v2")
    with pytest.raises(ValueError, match="Unknown prompt version"):
        get_system_prompt("v9")


def test_the_requested_prompt_version_is_the_one_sent(detector):
    payload, _ = prepare_case(CASE, detector)
    eob, analysis, blocked = load_case(CASE)
    client = FakeClient([good_reply(payload)])
    explain(eob, analysis, client, Pseudonymizer(), detector, blocked, prompt_version="v2")
    assert client.calls[0][0] == get_system_prompt("v2")
