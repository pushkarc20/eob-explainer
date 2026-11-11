import json

from support import FakeClient, good_reply, load_case, prepare_case

from eob.evaluation import load_gold
from eob.explainer import explain
from eob.explanation import all_text
from healthcore.privacy.pseudonymizer import Pseudonymizer

CASE = "syn_duplicate_same_day"  # provider "Dr. Alicia Moreno Family Medicine"


def run(case_id, replies, detector, extra_blocked=()):
    eob, analysis, blocked = load_case(case_id)
    client = FakeClient(replies)
    result = explain(eob, analysis, client, Pseudonymizer(), detector, [*blocked, *extra_blocked])
    return result, client


def test_a_good_answer_is_accepted_and_real_values_are_restored_locally(detector):
    payload, _ = prepare_case(CASE, detector)
    result, client = run(CASE, [good_reply(payload)], detector)
    assert result.source == "ai"
    assert result.attempts == 1
    assert len(client.calls) == 1
    text = all_text(result.explanation)
    assert "Dr. Alicia Moreno Family Medicine" in text
    assert "Mar 5, 2024" in text
    assert "[PROVIDER_" not in text and "[DATE_" not in text
    assert result.model == "fake-model"
    assert (result.input_tokens, result.output_tokens) == (100, 50)


def test_the_model_never_sees_a_canary_name_in_any_request(detector):
    audited = 0
    for case in load_gold()["cases"]:
        if not case["canaries"]:
            continue
        payload, _ = prepare_case(case["id"], detector)
        _, client = run(case["id"], [good_reply(payload)], detector)
        sent = " ".join(system + " " + user for system, user in client.calls).lower()
        for canary in case["canaries"]:
            assert canary.lower() not in sent, case["id"]
        audited += 1
    assert audited >= 3


def test_invalid_json_triggers_one_retry_and_then_succeeds(detector):
    payload, _ = prepare_case(CASE, detector)
    result, client = run(CASE, ["Sure! Here is your explanation.", good_reply(payload)], detector)
    assert result.source == "ai"
    assert result.attempts == 2
    assert "only the JSON object" in client.calls[1][1]


def test_an_ungrounded_amount_triggers_a_retry_with_feedback(detector):
    payload, _ = prepare_case(CASE, detector)
    bad = json.loads(good_reply(payload))
    bad["what_happened"] = "You were charged $999.99 for this visit."
    result, client = run(CASE, [json.dumps(bad), good_reply(payload)], detector)
    assert result.source == "ai"
    assert result.attempts == 2
    assert "not in the data" in client.calls[1][1]


def test_two_bad_answers_fall_back_to_the_template(detector):
    result, _client = run(CASE, ["not json", "still not json"], detector)
    assert result.source == "template"
    assert result.attempts == 2
    assert result.problems == ("not_valid_json",)
    assert "Dr. Alicia Moreno Family Medicine" in all_text(result.explanation)


def test_a_banned_phrase_is_never_shown_even_if_the_model_insists(detector):
    payload, _ = prepare_case(CASE, detector)
    bad = json.loads(good_reply(payload))
    bad["what_happened"] = "This is clearly a billing error and you were overcharged."
    result, _ = run(CASE, [json.dumps(bad), json.dumps(bad)], detector)
    assert result.source == "template"
    assert "banned_phrase" in result.problems
    assert "overcharged" not in all_text(result.explanation)


def test_the_leak_guard_blocks_before_anything_is_sent(detector):
    result, client = run(CASE, ["unused"], detector, extra_blocked=["99213"])
    assert client.calls == []
    assert result.source == "template"
    assert result.problems == ("leak_guard_blocked",)
    assert result.attempts == 0


def test_a_fenced_json_answer_is_accepted(detector):
    payload, _ = prepare_case(CASE, detector)
    fenced = "```json\n" + good_reply(payload) + "\n```"
    result, _ = run(CASE, [fenced], detector)
    assert result.source == "ai"
