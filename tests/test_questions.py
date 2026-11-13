from eob.questions import QUESTIONS
from eob.safety import find_banned


def test_every_flag_code_has_a_first_person_question():
    assert set(QUESTIONS) == {
        "possible_duplicate_line",
        "high_patient_share",
        "unitemized_patient_amount",
        "noncovered_amount",
        "claim_has_reversals",
    }
    for code, question in QUESTIONS.items():
        assert question.startswith("Can you"), code
        assert question.endswith("?"), code
        assert find_banned(question) == [], code
