"""Claude through the Anthropic API.

The key is read from the ANTHROPIC_API_KEY environment variable by the SDK; it is never stored in code
or logged. Only text blocks are read from the reply (the model may also return thinking blocks).
"""
from typing import Any

import anthropic

from healthcore.llm.base import LLMError, LLMResult

DEFAULT_TIMEOUT_SECONDS = 90.0


class AnthropicClient:
    name = "cloud"

    def __init__(
        self,
        model: str,
        effort: str | None = "medium",
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        sdk: Any = None,
    ) -> None:
        self._model = model
        self._effort = effort
        self._sdk = sdk if sdk is not None else anthropic.Anthropic(timeout=timeout, max_retries=2)

    def complete(self, system: str, user: str, max_tokens: int) -> LLMResult:
        # Do not pass temperature, top_p or top_k: Claude Sonnet 5.5 rejects them with a 400 error.
        params: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if self._effort:
            params["output_config"] = {"effort": self._effort}
        try:
            response = self._sdk.messages.create(**params)
        except anthropic.APIStatusError as error:
            raise LLMError(f"Claude API returned HTTP {error.status_code}: {str(error.message)[:200]}") from None
        except anthropic.APIConnectionError:
            raise LLMError("Could not reach the Claude API (network error or timeout).") from None
        except anthropic.APIError as error:
            raise LLMError(f"Claude API error: {type(error).__name__}") from None

        if response.stop_reason not in ("end_turn", "stop_sequence"):
            raise LLMError(f"The reply was cut off or declined (stop reason: {response.stop_reason}).")
        text = "".join(block.text for block in response.content if block.type == "text")
        usage = response.usage
        return LLMResult(
            text=text,
            model=getattr(response, "model", self._model),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )
