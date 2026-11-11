"""Explain one EOB file. Template mode needs no API key and sends nothing anywhere.
(Cloud mode is added in Step 6b.)

Usage:
    python scripts/explain_eob.py fixtures/synthetic/syn_duplicate_same_day.json
"""
import sys

from eob.engine import analyze
from eob.explanation import render_text
from eob.parser import parse_eob
from eob.safety import DISCLAIMER
from eob.templates import template_explanation
from healthcore.fhir.helpers import load_resource


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python scripts/explain_eob.py path/to/eob.json")
    eob = parse_eob(load_resource(sys.argv[1]))
    print(render_text(template_explanation(eob, analyze(eob)), DISCLAIMER))


if __name__ == "__main__":
    main()
