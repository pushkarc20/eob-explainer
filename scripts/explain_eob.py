"""Explain one EOB file.

Default (template mode): runs entirely on this machine, needs no key, sends nothing.
--cloud: shows the exact payload and asks for your consent before anything goes to Claude.

Usage:
    python scripts/explain_eob.py fixtures/synthetic/syn_duplicate_same_day.json
    python scripts/explain_eob.py fixtures/synthetic/syn_duplicate_same_day.json --cloud
"""
import argparse
import json
import sys

from eob.engine import analyze
from eob.explainer import explain
from eob.explanation import render_text
from eob.parser import parse_eob
from eob.privacy import PreparedPayload, collect_blocked_values
from eob.safety import DISCLAIMER
from eob.settings import MissingKeyError, estimate_cost, load_cloud_settings
from eob.templates import template_explanation
from healthcore.fhir.helpers import load_resource
from healthcore.llm.anthropic_client import AnthropicClient
from healthcore.privacy.pseudonymizer import Pseudonymizer


def main() -> None:
    parser = argparse.ArgumentParser(description="Explain one EOB in plain language.")
    parser.add_argument("file", help="path to a FHIR R4 ExplanationOfBenefit JSON file")
    parser.add_argument("--cloud", action="store_true", help="use Claude (shows the payload and asks first)")
    parser.add_argument("--yes", action="store_true", help="skip the consent prompt (synthetic test data only)")
    args = parser.parse_args()

    raw = load_resource(args.file)
    eob = parse_eob(raw)
    analysis = analyze(eob)

    if not args.cloud:
        print(render_text(template_explanation(eob, analysis), DISCLAIMER))
        return

    try:
        settings = load_cloud_settings()
    except MissingKeyError as error:
        sys.exit(str(error))
    client = AnthropicClient(settings.model, settings.effort)

    def confirm(prepared: PreparedPayload) -> bool:
        print("=== WHAT WILL BE SENT TO CLAUDE ===")
        print(f"Model: {settings.model} (effort: {settings.effort})")
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

    result = explain(
        eob, analysis, client, Pseudonymizer(), blocked_values=collect_blocked_values(raw), confirm=confirm
    )

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
        cost = estimate_cost(result.model or "", result.input_tokens, result.output_tokens)
        if cost is not None:
            line += f"; estimated cost: ${cost:.4f}"
        print(line)


if __name__ == "__main__":
    main()
