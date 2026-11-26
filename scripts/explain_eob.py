"""Explain one EOB file.

Default (template mode): runs entirely on this machine, needs no key, sends nothing.
--local: a local model through Ollama. Nothing leaves this machine.
--cloud: shows the exact payload and asks for your consent before anything goes to Claude.

Usage:
    python scripts/explain_eob.py fixtures/synthetic/syn_duplicate_same_day.json
    python scripts/explain_eob.py fixtures/synthetic/syn_duplicate_same_day.json --local
    python scripts/explain_eob.py fixtures/synthetic/syn_duplicate_same_day.json --cloud
"""
import argparse
import json
import sys
import time

from eob.engine import analyze
from eob.explainer import explain
from eob.explanation import Explanation, render_text
from eob.parser import parse_eob
from eob.privacy import PreparedPayload, collect_blocked_values
from eob.safety import DISCLAIMER
from eob.settings import (
    MissingKeyError,
    MissingLocalModelError,
    estimate_cost,
    load_cloud_settings,
    load_local_settings,
)
from eob.templates import template_explanation
from healthcore.fhir.helpers import load_resource
from healthcore.llm.anthropic_client import AnthropicClient
from healthcore.llm.base import LLMError
from healthcore.llm.ollama_client import OllamaClient
from healthcore.privacy.pseudonymizer import Pseudonymizer


def main() -> None:
    parser = argparse.ArgumentParser(description="Explain one EOB in plain language.")
    parser.add_argument("file", help="path to a FHIR R4 ExplanationOfBenefit JSON file")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--local", action="store_true", help="use a local model via Ollama (nothing leaves this machine)")
    mode.add_argument("--cloud", action="store_true", help="use Claude (shows the payload and asks first)")
    parser.add_argument("--yes", action="store_true", help="with --cloud: skip the consent prompt (synthetic data only)")
    args = parser.parse_args()

    raw = load_resource(args.file)
    eob = parse_eob(raw)
    analysis = analyze(eob)

    if not (args.local or args.cloud):
        print(render_text(template_explanation(eob, analysis), DISCLAIMER))
        return

    confirm = None
    if args.local:
        try:
            local = load_local_settings()
            client = OllamaClient(
                local.model, local.base_url, think=local.think, format_schema=Explanation.model_json_schema()
            )
        except (MissingLocalModelError, LLMError) as error:
            sys.exit(f"Problem: {error}")
        print(f"LOCAL MODE: nothing leaves this machine. Model: {local.model}")
        print("(The first request loads the model into memory and can take a while.)")
    else:
        try:
            settings = load_cloud_settings()
        except MissingKeyError as error:
            sys.exit(str(error))
        client = AnthropicClient(settings.model, settings.effort)

        def confirm(prepared: PreparedPayload) -> bool:
            print("=== WHAT WILL BE SENT TO CLAUDE ===")
            print(f"Model: {settings.model} (effort: {settings.effort or 'model default'})")
            print(json.dumps(json.loads(prepared.json_text), indent=2))
            print("\nAlso sent: a fixed instruction prompt (identical for every claim; it contains no claim data).")
            print("If the first answer fails verification, one retry sends the same data plus a list of problems.")
            replaced = ", ".join(f"{kind} x{count}" for kind, count in sorted(prepared.replaced.items()))
            print(f"Replaced locally by placeholders (counts only): {replaced or 'none'}")
            print("Real names and dates are restored on this machine after the reply.\n")
            if args.yes:
                print("(--yes given: sending without asking)")
                return True
            return input("Send this to Claude? Type y to send, anything else to cancel: ").strip().lower() == "y"

    started = time.perf_counter()
    result = explain(
        eob, analysis, client, Pseudonymizer(), blocked_values=collect_blocked_values(raw), confirm=confirm
    )
    elapsed = time.perf_counter() - started

    print()
    print(render_text(result.explanation, DISCLAIMER))
    print("\n--- run details ---")
    if result.source == "ai":
        print(f"Written by {result.model}. Checked in code: amounts, percentages, flags, wording, placeholders.")
    else:
        print("Showing the built-in explanation (no AI text was used).")
        if result.problems:
            print("Reason: " + ", ".join(result.problems))
        if result.error:
            print("Detail: " + result.error)
    if result.attempts:
        line = f"Requests: {result.attempts}; tokens in/out: {result.input_tokens}/{result.output_tokens}"
        if client.name == "local":
            line += "; cost: none (runs on this Mac)"
        else:
            cost = estimate_cost(result.model or "", result.input_tokens, result.output_tokens)
            if cost is not None:
                line += f"; estimated cost: ${cost:.4f}"
        print(line)
    print(f"Time: {elapsed:.1f} seconds")


if __name__ == "__main__":
    main()
