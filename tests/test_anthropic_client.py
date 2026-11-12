from types import SimpleNamespace

import anthropic
import httpx
import pytest

from healthcore.llm.anthropic_client import AnthropicClient
from healthcore.llm.base import LLMError

TEXT = SimpleNamespace(type="text", text='{"ok": true}')
THINKING = SimpleNamespace(type="thinking", thinking="private reasoning")


class FakeMessages:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.kwargs = response, error, None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.response


class FakeSDK:
    def __init__(self, response=None, error=None):
        self.messages = FakeMessages(response, error)


def reply(blocks, stop_reason="end_turn"):
    return SimpleNamespace(
        content=blocks,
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=11, output_tokens=7),
        model="claude-sonnet-5-5",
    )


def test_only_text_blocks_are_read_and_usage_is_reported():
    client = AnthropicClient("claude-sonnet-5-5", sdk=FakeSDK(reply([THINKING, TEXT])))
    result = client.complete("system text", "user text", 100)
    assert result.text == '{"ok": true}'
    assert (result.input_tokens, result.output_tokens) == (11, 7)
    assert result.model == "claude-sonnet-5-5"


def test_the_request_has_the_documented_shape_and_no_sampling_parameters():
    sdk = FakeSDK(reply([TEXT]))
    AnthropicClient("claude-sonnet-5-5", effort="medium", sdk=sdk).complete("sys", "usr", 123)
    kwargs = sdk.messages.kwargs
    assert kwargs["model"] == "claude-sonnet-5-5"
    assert kwargs["max_tokens"] == 123
    assert kwargs["system"] == "sys"
    assert kwargs["messages"] == [{"role": "user", "content": "usr"}]
    assert kwargs["output_config"] == {"effort": "medium"}
    for forbidden in ("temperature", "top_p", "top_k"):
        assert forbidden not in kwargs  # Claude Sonnet 5.5 returns a 400 error for these


def test_effort_can_be_left_to_the_models_default():
    sdk = FakeSDK(reply([TEXT]))
    AnthropicClient("claude-sonnet-5-5", effort=None, sdk=sdk).complete("s", "u", 10)
    assert "output_config" not in sdk.messages.kwargs


def test_a_truncated_reply_is_an_error_not_a_silent_partial_answer():
    client = AnthropicClient("claude-sonnet-5-5", sdk=FakeSDK(reply([TEXT], stop_reason="max_tokens")))
    with pytest.raises(LLMError, match="cut off"):
        client.complete("s", "u", 10)


def test_network_errors_become_llm_errors_without_leaking_the_request():
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    sdk = FakeSDK(error=anthropic.APIConnectionError(request=request))
    with pytest.raises(LLMError) as error:
        AnthropicClient("claude-sonnet-5-5", sdk=sdk).complete("s", "secret user text", 10)
    assert "secret user text" not in str(error.value)
    assert "Could not reach" in str(error.value)
