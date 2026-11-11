from support import good_reply, prepare_case

from eob.evaluation import load_gold
from eob.explanation import Explanation
from eob.validate import validate_explanation


def valid(payload) -> Explanation:
    return Explanation.model_validate_json(good_reply(payload))


def codes_for(explanation, payload, ps, detector) -> set[str]:
    return {problem.code for problem in validate_explanation(explanation, payload, ps, detector)}


def test_a_valid_answer_has_no_problems_for_every_gold_case(detector):
    for case in load_gold()["cases"]:
        payload, ps = prepare_case(case["id"], detector)
        problems = validate_explanation(valid(payload), payload, ps, detector)
        assert problems == [], f"{case['id']}: {[p.code for p in problems]}"


def test_amounts_in_any_common_format_are_accepted(detector):
    payload, ps = prepare_case("syn_coinsurance_20pct", detector)
    text = "The provider billed $1,200.00, which is 1200.00 or $1200 in other formats."
    answer = valid(payload).model_copy(update={"what_happened": text})
    assert codes_for(answer, payload, ps, detector) == set()


def test_an_ungrounded_amount_is_caught(detector):
    payload, ps = prepare_case("syn_coinsurance_20pct", detector)
    answer = valid(payload).model_copy(update={"what_happened": "You were charged $999.99 for this visit."})
    assert "ungrounded_amount" in codes_for(answer, payload, ps, detector)


def test_a_calculated_amount_is_caught(detector):
    payload, ps = prepare_case("syn_coinsurance_20pct", detector)
    answer = valid(payload).model_copy(update={"what_happened": "Your plan and you together paid $1,000.00 and $5.00."})
    assert "ungrounded_amount" in codes_for(answer, payload, ps, detector)


def test_an_ungrounded_percentage_is_caught_but_a_grounded_one_is_allowed(detector):
    payload, ps = prepare_case("syn_deductible_not_met", detector)  # its flag text says "about 100%"
    bad = valid(payload).model_copy(update={"what_happened": "You owe about 75% of the allowed amount."})
    assert "ungrounded_percent" in codes_for(bad, payload, ps, detector)
    good = valid(payload).model_copy(update={"what_happened": "You owe about 100% of the allowed amount."})
    assert "ungrounded_percent" not in codes_for(good, payload, ps, detector)


def test_a_banned_phrase_is_caught(detector):
    payload, ps = prepare_case("syn_duplicate_same_day", detector)
    answer = valid(payload).model_copy(update={"what_happened": "This looks like a billing error by the provider."})
    assert "banned_phrase" in codes_for(answer, payload, ps, detector)


def test_an_unknown_placeholder_is_caught(detector):
    payload, ps = prepare_case("syn_duplicate_same_day", detector)
    answer = valid(payload).model_copy(update={"what_happened": "This claim was billed by [PROVIDER_9] last week."})
    assert "unknown_placeholder" in codes_for(answer, payload, ps, detector)


def test_missing_and_invented_flag_notes_are_caught(detector):
    payload, ps = prepare_case("syn_duplicate_same_day", detector)
    answer = valid(payload)
    assert "missing_flag_note" in codes_for(answer.model_copy(update={"flag_notes": []}), payload, ps, detector)
    invented = answer.flag_notes[0].model_copy(update={"flag_code": "made_up_flag"})
    assert "invented_flag" in codes_for(
        answer.model_copy(update={"flag_notes": [*answer.flag_notes, invented]}), payload, ps, detector
    )


def test_next_steps_must_point_to_the_insurer_or_provider(detector):
    payload, ps = prepare_case("syn_clean_copay_visit", detector)
    answer = valid(payload).model_copy(update={"next_steps": "Thank you for reading."})
    assert "missing_guidance" in codes_for(answer, payload, ps, detector)


def test_an_invented_phone_number_is_caught(detector):
    payload, ps = prepare_case("syn_clean_copay_visit", detector)
    answer = valid(payload).model_copy(update={"next_steps": "Call your insurer at (415) 555-0123."})
    assert "identifier_like_content" in codes_for(answer, payload, ps, detector)


def test_an_empty_summary_is_caught(detector):
    payload, ps = prepare_case("syn_clean_copay_visit", detector)
    answer = valid(payload).model_copy(update={"what_happened": "Ok."})
    assert "empty_summary" in codes_for(answer, payload, ps, detector)
