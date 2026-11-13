from support import load_case

from eob.drafter import MemberDetails, draft_message, render_draft
from eob.engine import analyze
from eob.evaluation import load_gold
from eob.models import EobLine, EobSummary
from eob.privacy import prepare_cloud_payload
from eob.questions import QUESTIONS
from eob.safety import find_banned
from healthcore.privacy.pseudonymizer import Pseudonymizer


def draft_for(case_id, member=None):
    eob, analysis, _ = load_case(case_id)
    return draft_message(eob, analysis, member), eob


def test_the_draft_uses_the_eob_and_the_members_own_details():
    member = MemberDetails("Jane Q. Member", "ABC123456")
    draft, _ = draft_for("syn_duplicate_same_day", member)
    assert "SYN-syn_duplicate_same_day" in draft.subject
    for text in (
        "SYN-syn_duplicate_same_day", "Dr. Alicia Moreno Family Medicine", "Mar 5, 2024",
        "$300.00", "$180.00", "$144.00", "$36.00", "Jane Q. Member", "ABC123456",
    ):
        assert text in draft.body, text
    assert QUESTIONS["possible_duplicate_line"] in draft.body
    assert draft.to_fill == ()


def test_missing_member_details_become_visible_fill_in_fields():
    draft, _ = draft_for("syn_duplicate_same_day")
    assert "[YOUR NAME]" in draft.body and "[MEMBER ID]" in draft.body
    assert set(draft.to_fill) == {"[YOUR NAME]", "[MEMBER ID]"}


def test_info_flags_are_not_turned_into_questions_but_are_noted():
    for case_id, code in (("syn_deductible_not_met", "high_patient_share"),
                          ("syn_charge_reversal_recharge", "claim_has_reversals")):
        draft, _ = draft_for(case_id)
        assert QUESTIONS[code] not in draft.body, case_id
        assert any("Noted but not turned into questions" in note for note in draft.notes), case_id
        assert "Could you confirm the amount I owe" in draft.body, case_id


def test_a_denial_gets_the_question_and_the_rights_and_deadlines_guardrail():
    draft, _ = draft_for("syn_noncovered_service")
    assert QUESTIONS["noncovered_amount"] in draft.body
    assert any("deadlines" in note and "cannot tell you your rights" in note for note in draft.notes)


def test_an_unreported_balance_is_asked_about_instead_of_assumed():
    draft, _ = draft_for("syn_owed_not_reported")
    assert "does not state the amount I owe" in draft.body
    assert "confirm the amount I owe" not in draft.body


def test_several_service_dates_are_shown_as_a_range():
    draft, _ = draft_for("syn_same_code_different_days")
    assert "Mar 4, 2024 to Mar 11, 2024" in draft.body


def test_a_clean_claim_says_there_may_be_nothing_to_send():
    draft, _ = draft_for("syn_clean_copay_visit")
    assert any("You may not need to send this" in note for note in draft.notes)
    assert "Could you confirm the amount I owe" in draft.body


def test_missing_eob_fields_become_fill_in_fields():
    eob = EobSummary(eob_id="t", lines=[EobLine(sequence=1)])
    draft = draft_message(eob, analyze(eob))
    assert draft.subject == "Question about claim [CLAIM NUMBER]"
    assert set(draft.to_fill) == {
        "[CLAIM NUMBER]", "[PROVIDER NAME]", "[DATE OF SERVICE]", "[YOUR NAME]", "[MEMBER ID]",
    }


def test_every_gold_case_gets_a_safe_complete_draft():
    for case in load_gold()["cases"]:
        eob, analysis, _ = load_case(case["id"])
        draft = draft_message(eob, analysis)
        text = draft.subject + "\n" + draft.body + "\n" + "\n".join(draft.notes)
        assert find_banned(text) == [], case["id"]
        assert "Thank you" in draft.body, case["id"]
        assert "1. " in draft.body, case["id"]
        if eob.claim_id:
            assert eob.claim_id in draft.body, case["id"]
        for flag in analysis.flags:
            if flag.severity == "question":
                assert QUESTIONS[flag.code] in draft.body, case["id"]
            else:
                assert QUESTIONS[flag.code] not in draft.body, case["id"]


def test_the_claim_number_and_member_details_stay_out_of_the_cloud_payload(detector):
    eob, analysis, blocked = load_case("syn_duplicate_same_day")
    draft = draft_message(eob, analysis, MemberDetails("Jane Q. Member", "ABC123456"))
    prepared = prepare_cloud_payload(eob, analysis, Pseudonymizer(), detector, blocked)
    assert eob.claim_id in draft.body
    assert eob.claim_id not in prepared.json_text
    for private in ("Jane Q. Member", "ABC123456"):
        assert private not in prepared.json_text


def test_the_rendered_draft_shows_guidance_before_the_message():
    draft, _ = draft_for("syn_duplicate_same_day")
    rendered = render_draft(draft)
    assert rendered.startswith("BEFORE YOU SEND")
    assert "SUBJECT: " + draft.subject in rendered
    assert rendered.index("BEFORE YOU SEND") < rendered.index("SUBJECT:") < rendered.index("Hello,")
