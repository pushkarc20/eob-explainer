from streamlit.testing.v1 import AppTest
from support import load_case

from eob import app_logic
from eob.drafter import draft_message
from eob.evaluation import ROOT
from eob.questions import GENERIC_QUESTION, INFO_QUESTIONS, QUESTIONS, question_for
from eob.safety import find_banned
from eob.templates import template_explanation

APP = str(ROOT / "app.py")


def template_question(case_id: str, code: str) -> str:
    eob, analysis, _ = load_case(case_id)
    explanation = template_explanation(eob, analysis)
    return next(note.question for note in explanation.flag_notes if note.flag_code == code)


def test_question_for_uses_the_info_wording_only_where_one_exists():
    assert question_for("high_patient_share", "info") == INFO_QUESTIONS["high_patient_share"]
    assert question_for("high_patient_share", "question") == QUESTIONS["high_patient_share"]
    assert question_for("noncovered_amount", "info") == QUESTIONS["noncovered_amount"]
    assert question_for("made_up_code") == GENERIC_QUESTION


def test_info_wording_is_a_clean_question_and_does_not_ask_what_the_eob_itemizes():
    for code, question in INFO_QUESTIONS.items():
        assert question.startswith("Can you"), code
        assert question.endswith("?"), code
        assert find_banned(question) == [], code
        assert "coinsurance" not in question, code


def test_an_itemized_large_share_gets_the_deductible_limit_question():
    for case_id in ("syn_deductible_not_met", "syn_high_coinsurance_plan"):
        assert template_question(case_id, "high_patient_share") == INFO_QUESTIONS["high_patient_share"], case_id


def test_an_unexplained_large_share_keeps_the_original_question():
    assert template_question("syn_high_share_unexplained", "high_patient_share") == QUESTIONS["high_patient_share"]


def test_the_message_to_the_insurer_does_not_ask_the_info_question():
    eob, analysis, _ = load_case("syn_deductible_not_met")
    assert INFO_QUESTIONS["high_patient_share"] not in draft_message(eob, analysis).body


def test_the_questions_tab_uses_the_info_wording_for_an_itemized_share():
    at = AppTest.from_file(APP, default_timeout=120).run()
    label = next(label for label in app_logic.list_samples() if label.startswith("syn_deductible_not_met:"))
    at.selectbox(key="eob_sample").set_value(label).run()
    assert not at.exception
    assert any(INFO_QUESTIONS["high_patient_share"] in info.value for info in at.info)