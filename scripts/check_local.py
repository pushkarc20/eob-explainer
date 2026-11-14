"""Check that local mode is ready: Ollama is running, your model is installed, and it can answer.

Usage: python scripts/check_local.py
"""
import sys
import time

from eob.settings import MissingLocalModelError, load_local_settings
from healthcore.llm.base import LLMError
from healthcore.llm.ollama_client import OllamaClient


def main() -> None:
    try:
        settings = load_local_settings()
        client = OllamaClient(settings.model, settings.base_url, think=settings.think)
        installed = client.installed_models()
    except (MissingLocalModelError, LLMError) as error:
        sys.exit(f"Problem: {error}")
    print(f"Ollama is running at {settings.base_url}. Installed models: {', '.join(installed) or 'none'}")
    if settings.model not in installed and f"{settings.model}:latest" not in installed:
        sys.exit(f"Problem: model '{settings.model}' is not installed. Run: ollama pull {settings.model}")
    print(f"Asking {settings.model} a tiny question (the first request loads the model, which can take a while)...")
    started = time.perf_counter()
    try:
        result = client.complete("Answer with one short sentence.", "Say that you are ready.", 200)
    except LLMError as error:
        sys.exit(f"Problem: {error}")
    print(f"Reply: {result.text.strip()}")
    print(f"Took {time.perf_counter() - started:.1f} seconds. Local mode is ready.")


if __name__ == "__main__":
    main()
