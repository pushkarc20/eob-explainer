import json

from support import FakeClient, prepare_case

from eob.judge import judge_explanation, parse_scores
from healthcore.llm.base import LLMError
from healthcore.privacy.pseudonymizer import Pseudonymizer

GOOD = {"faithfulness": 5, "key_point": 4, "clarity": 4, "tone": 5, "concision": 3, "unsupported_claims": ["x"]}


class BrokenClient:
    name = "cloud"

    def complete(self, system, user, max_tokens):
        raise LLMError("Claude API returned HTTP 529: overloaded")


def test_parse_scores_accepts_plain_and_fenced_json():
    assert parse_scores(json.dumps(GOOD)).faithfulness == 5
    assert parse_scores("```json\n" + json.dumps(GOOD) + "\n```").unsupported_claims == ["x"]


def test_parse_scores_rejects_bad_replies():
    missing = {**GOOD}
    del missing["clarity"]
    assert parse_scores("no json here") is None
    assert parse_scores(json.dumps({**GOOD, "faithfulness": 9})) is None
    assert parse_scores(json.dumps(missing)) is None


def test_the_judge_returns_scores_and_token_counts(detector):
    _, pseudonymizer = prepare_case("syn_duplicate_same_day", detector)
    client = FakeClient([json.dumps(GOOD)])
    result = judge_explanation(client, pseudonymizer, detector, "{}", "the key point", "Billed by [PROVIDER_1].")
    assert result.scores.faithfulness == 5
    assert (result.input_tokens, result.output_tokens) == (100, 50)
    assert "the key point" in client.calls[0][1]
    assert "[PROVIDER_1]" in client.calls[0][1]


def test_the_judge_never_sends_a_request_that_would_leak(detector):
    pseudonymizer = Pseudonymizer()
    pseudonymizer.block("Alicia Moreno")
    client = FakeClient(["unused"])
    result = judge_explanation(client, pseudonymizer, detector, "{}", "key", "seen by Alicia Moreno")
    assert result.scores is None
    assert result.error == "leak_guard_blocked"
    assert client.calls == []


def test_an_api_error_is_reported_not_raised(detector):
    result = judge_explanation(BrokenClient(), Pseudonymizer(), detector, "{}", "key", "text")
    assert result.scores is None
    assert "529" in result.error


def test_an_unparseable_reply_is_reported(detector):
    result = judge_explanation(FakeClient(["nope"]), Pseudonymizer(), detector, "{}", "key", "text")
    assert result.scores is None
    assert result.error == "unparseable"
