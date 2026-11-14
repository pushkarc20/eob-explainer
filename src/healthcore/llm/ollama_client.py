"""Local models through Ollama. This client only ever talks to this machine.

Privacy guards, enforced in code and covered by tests:
- the server address must be a loopback address (localhost, 127.0.0.1 or ::1);
- Ollama "cloud" model tags, which run on Ollama's servers, are refused;
- system proxy settings are ignored (trust_env=False), so local traffic cannot be routed elsewhere.
"""
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from healthcore.llm.base import LLMError, LLMResult

DEFAULT_URL = "http://localhost:11434"
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
CLOUD_TAG = re.compile(r"(^|[-:/])cloud$", re.IGNORECASE)
DEFAULT_TIMEOUT_SECONDS = 300.0  # the first request loads the model into memory, which can be slow
DEFAULT_NUM_CTX = 8192  # Ollama silently truncates prompts that exceed the context size
DEFAULT_MAX_OUTPUT_TOKENS = 2500  # small models in JSON mode can loop, so cap the output


def check_is_local(base_url: str, model: str) -> None:
    host = urlparse(base_url).hostname
    if host not in LOOPBACK_HOSTS:
        raise LLMError(f"Local mode only talks to this machine; refusing to use host '{host}'.")
    if CLOUD_TAG.search(model):
        raise LLMError(f"'{model}' is an Ollama cloud model that runs on Ollama's servers. Pick a local model.")


class OllamaClient:
    name = "local"

    def __init__(
        self,
        model: str,
        base_url: str = DEFAULT_URL,
        *,
        num_ctx: int = DEFAULT_NUM_CTX,
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
        think: bool | None = None,
        format_schema: dict[str, Any] | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        http: httpx.Client | None = None,
    ) -> None:
        check_is_local(base_url, model)
        self._model = model
        self._base = base_url.rstrip("/")
        self._num_ctx = num_ctx
        self._max_output_tokens = max_output_tokens
        self._think = think
        self._format = format_schema
        self._http = http if http is not None else httpx.Client(timeout=timeout, trust_env=False)

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = self._http.request(method, f"{self._base}{path}", json=body)
        except httpx.ConnectError:
            raise LLMError(f"Could not reach Ollama at {self._base}. Is the Ollama app running?") from None
        except httpx.TimeoutException:
            raise LLMError("The local model took too long to answer. Try a smaller model.") from None
        except httpx.HTTPError as error:
            raise LLMError(f"The local request failed: {type(error).__name__}") from None
        if response.status_code == 404:
            raise LLMError(f"Model '{self._model}' is not installed. Run: ollama pull {self._model}")
        if response.status_code != 200:
            raise LLMError(f"Ollama returned HTTP {response.status_code}: {response.text[:200]}")
        try:
            return response.json()
        except ValueError:
            raise LLMError("Ollama returned something that was not JSON.") from None

    def installed_models(self) -> list[str]:
        data = self._request("GET", "/api/tags")
        return [str(model.get("name")) for model in data.get("models", []) if model.get("name")]

    def complete(self, system: str, user: str, max_tokens: int) -> LLMResult:
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "options": {
                "temperature": 0,
                "seed": 0,
                "num_ctx": self._num_ctx,
                "num_predict": min(max_tokens, self._max_output_tokens),
            },
        }
        if self._format is not None:
            body["format"] = self._format
        if self._think is not None:
            body["think"] = self._think
        data = self._request("POST", "/api/chat", body)
        if data.get("done_reason") == "length":
            raise LLMError("The local model's reply was cut off. Try turning thinking off or a larger token limit.")
        content = (data.get("message") or {}).get("content") or ""  # thinking text, if any, is a separate field
        return LLMResult(
            text=content,
            model=str(data.get("model") or self._model),
            input_tokens=data.get("prompt_eval_count"),
            output_tokens=data.get("eval_count"),
        )
