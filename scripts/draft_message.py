"""Draft a short written question to your insurer about one EOB.

Runs entirely on this machine: no network, no AI, nothing stored. Your name and member ID are typed here
and used only to fill in the draft (leave them blank to fill in yourself later).

Usage:
    python scripts/draft_message.py fixtures/synthetic/syn_duplicate_same_day.json
    python scripts/draft_message.py fixtures/synthetic/syn_duplicate_same_day.json --no-prompt
"""
import argparse

from eob.drafter import MemberDetails, draft_message, render_draft
from eob.engine import analyze
from eob.parser import parse_eob
from healthcore.fhir.helpers import load_resource


def main() -> None:
    parser = argparse.ArgumentParser(description="Draft a short written question to your insurer.")
    parser.add_argument("file", help="path to a FHIR R4 ExplanationOfBenefit JSON file")
    parser.add_argument("--no-prompt", action="store_true", help="do not ask for your name and member ID")
    args = parser.parse_args()

    eob = parse_eob(load_resource(args.file))
    member = MemberDetails()
    if not args.no_prompt:
        print("Typed here, used only to fill in the draft, never stored or sent. Press Enter to skip.")
        name = input("Your name: ").strip()
        member_id = input("Your member ID: ").strip()
        member = MemberDetails(name=name, member_id=member_id)
        print()
    print(render_draft(draft_message(eob, analyze(eob), member)))


if __name__ == "__main__":
    main()
