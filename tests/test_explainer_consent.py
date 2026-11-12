from support import FakeClient, good_reply, load_case, prepare_case

from eob.explainer import explain
from healthcore.llm.base import LLMError
from healthcore.privacy.pseudonymizer import Pseudonymizer

CASE = "syn_duplicate_same_day"  # provider "Dr. Alicia Moreno Family Medicine"


class BrokenClient:
    name = "cloud"

    def complete(self, system, user, max_tokens):
        raise LLMError("Claude API returned HTTP 529: overloaded")


def run(client, detector, confirm=None):
    eob, analysis, blocked = load_case(CASE)
    return explain(eob, analysis, client, Pseudonymizer(), detector, blocked, confirm=confirm)


def test_declining_sends_nothing_and_falls_back(detector):
    shown = []

    def decline(prepared):
        shown.append(prepared.json_text)
        return False

    client = FakeClient(["unused"])
    result = run(client, detector, decline)
    assert client.calls == []
    assert result.source == "template"
    assert result.problems == ("declined_by_user",)
    assert len(shown) == 1
    assert "alicia" not in shown[0].lower()


def test_what_the_user_approves_is_exactly_what_is_sent(detector):
    payload, _ = prepare_case(CASE, detector)
    client = FakeClient([good_reply(payload)])
    shown = []

    def approve(prepared):
        shown.append(prepared.json_text)
        return True

    result = run(client, detector, approve)
    assert result.source == "ai"
    assert shown[0] in client.calls[0][1]


def test_an_api_failure_falls_back_to_the_template_with_a_reason(detector):
    result = run(BrokenClient(), detector)
    assert result.source == "template"
    assert result.problems == ("api_error",)
    assert "529" in result.error
    assert result.attempts == 1
