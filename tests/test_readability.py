from eob.explanation import Explanation, MoneyPoint
from eob.readability import count_syllables, flesch_kincaid_grade, prose_text


def test_common_words_have_sensible_syllable_counts():
    expected = {"plan": 1, "billed": 1, "the": 1, "copay": 2, "service": 2, "insurer": 3, "explanation": 4}
    for word, count in expected.items():
        assert count_syllables(word) == count, word


def test_simple_text_scores_lower_than_dense_text():
    simple = "The plan paid the bill. You owe a small fee."
    dense = (
        "Notwithstanding the aforementioned administrative adjudication, beneficiaries remain "
        "responsible for coinsurance obligations."
    )
    assert flesch_kincaid_grade(simple) < flesch_kincaid_grade(dense)
    assert flesch_kincaid_grade(simple) < 4


def test_numbers_and_dollar_amounts_are_ignored():
    assert flesch_kincaid_grade("You owe $1,200.00 today.") == flesch_kincaid_grade("You owe today.")


def test_empty_or_numbers_only_text_has_no_grade():
    assert flesch_kincaid_grade("") is None
    assert flesch_kincaid_grade("$100.00 25% 3,000") is None


def test_prose_text_ends_every_part_with_a_full_stop_and_skips_labels():
    explanation = Explanation(
        what_happened="This is a claim",
        money_points=[MoneyPoint(label="Billed", amount="$1.00", explanation="What was charged")],
        next_steps="Call your insurer",
    )
    assert prose_text(explanation) == "This is a claim. What was charged. Call your insurer."
