import json

import httpx
import pytest
from support import good_reply, load_case, prepare_case

from eob.explainer import explain
from eob.explanation import Explanation, all_text
from healthcore.llm.base import LLMError
from healthcore.llm.ollama_client import OllamaClient
from healthcore.privacy.pseudonymizer import Pseudonymizer

CASE = "syn_duplicate_same_day"  # provider "Dr. Alicia Moreno Family Medicine"


def chat_reply(content="{}", **extra):
    body = {
        "model": "qwen3:8b",
        "message": {"role": "assistant", "content": content},
        "done": True,
        "done_reason": "stop",
        "prompt_eval_count": 120,
        "eval_count": 45,
    }
    body.update(extra)
    return httpx.Response(200, json=body)


def make_client(handler, **kwargs):
    return OllamaClient("qwen3:8b", http=httpx.Client(transport=httpx.MockTransport(handler)), **kwargs)


def test_the_request_goes_to_localhost_with_the_documented_shape():
    seen = []

    def handler(request):
        seen.append(request)
        return chat_reply('{"ok": true}')

    result = make_client(handler).complete("system text", "user text", 6000)
    request = seen[0]
    body = json.loads(request.content)
    assert request.url.host == "localhost"
    assert request.url.path == "/api/chat"
    assert body["model"] == "qwen3:8b"
    assert body["stream"] is False
    assert body["messages"] == [
        {"role": "system", "content": "system text"},
        {"role": "user", "content": "user text"},
    ]
    assert body["options"]["temperature"] == 0
    assert body["options"]["num_ctx"] == 8192
    assert body["options"]["num_predict"] == 2500  # capped below the 6000 asked for
    assert "format" not in body and "think" not in body
    assert (result.text, result.input_tokens, result.output_tokens) == ('{"ok": true}', 120, 45)


def test_schema_and_think_are_sent_when_configured():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return chat_reply()

    schema = Explanation.model_json_schema()
    make_client(handler, format_schema=schema, think=False).complete("s", "u", 100)
    assert "what_happened" in seen[0]["format"]["properties"]
    assert seen[0]["think"] is False


def test_thinking_text_is_ignored_and_only_the_answer_is_read():
    reply = chat_reply("the answer", message={"role": "assistant", "content": "the answer", "thinking": "private"})
    result = make_client(lambda request: reply).complete("s", "u", 100)
    assert result.text == "the answer"


def test_a_truncated_reply_is_an_error():
    client = make_client(lambda request: chat_reply(done_reason="length"))
    with pytest.raises(LLMError, match="cut off"):
        client.complete("s", "u", 100)


def test_a_missing_model_says_how_to_install_it():
    client = make_client(lambda request: httpx.Response(404, json={"error": "model not found"}))
    with pytest.raises(LLMError, match="ollama pull qwen3:8b"):
        client.complete("s", "u", 100)


def test_ollama_not_running_gives_a_helpful_message():
    def refuse(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(LLMError, match="Is the Ollama app running"):
        make_client(refuse).complete("s", "u", 100)


def test_a_slow_model_times_out_cleanly():
    def slow(request):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(LLMError, match="too long"):
        make_client(slow).complete("s", "u", 100)


def test_installed_models_are_listed():
    def handler(request):
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": "qwen3:8b"}, {"name": "gemma4:e4b"}]})

    assert make_client(handler).installed_models() == ["qwen3:8b", "gemma4:e4b"]


def test_only_loopback_servers_are_allowed():
    for url in ("http://localhost:11434", "http://127.0.0.1:11434", "http://[::1]:11434"):
        OllamaClient("qwen3:8b", url, http=httpx.Client())
    for url in ("https://api.example.com", "http://192.168.1.20:11434", "http://my-server.local:11434"):
        with pytest.raises(LLMError, match="only talks to this machine"):
            OllamaClient("qwen3:8b", url)


def test_ollama_cloud_models_are_refused():
    for model in ("gpt-oss:120b-cloud", "some-model:cloud"):
        with pytest.raises(LLMError, match="cloud model"):
            OllamaClient(model)


def test_the_full_pipeline_runs_locally_and_the_model_never_sees_real_names(detector):
    payload, _ = prepare_case(CASE, detector)
    requests = []

    def handler(request):
        requests.append(request.content.decode())
        return chat_reply(good_reply(payload))

    eob, analysis, blocked = load_case(CASE)
    client = make_client(handler, format_schema=Explanation.model_json_schema())
    result = explain(eob, analysis, client, Pseudonymizer(), detector, blocked)
    assert result.source == "ai"
    assert "Dr. Alicia Moreno Family Medicine" in all_text(result.explanation)  # restored locally
    assert "alicia" not in requests[0].lower()  # never in the request
