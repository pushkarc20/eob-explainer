import re
from decimal import Decimal

from eob.engine import analyze
from eob.evaluation import ROOT, load_gold
from eob.explanation import all_text
from eob.money import fmt_money
from eob.parser import parse_eob
from eob.safety import find_banned
from eob.templates import template_explanation
from healthcore.fhir.helpers import load_resource


def test_the_fallback_is_safe_and_complete_for_every_gold_case():
    for case in load_gold()["cases"]:
        eob = parse_eob(load_resource(ROOT / case["file"]))
        analysis = analyze(eob)
        explanation = template_explanation(eob, analysis)
        text = all_text(explanation)
        assert find_banned(text) == [], case["id"]
        assert re.search(r"insurer|provider", explanation.next_steps, re.IGNORECASE), case["id"]
        assert {note.flag_code for note in explanation.flag_notes} == {f.code for f in analysis.flags}, case["id"]
        for name, value in case["expected"]["money"].items():
            if value is not None:
                assert fmt_money(Decimal(value)) in text, f"{case['id']}: {name}"


def test_unreported_amounts_say_so_instead_of_showing_zero():
    case = next(c for c in load_gold()["cases"] if c["id"] == "syn_owed_not_reported")
    eob = parse_eob(load_resource(ROOT / case["file"]))
    explanation = template_explanation(eob, analyze(eob))
    owed = next(p for p in explanation.money_points if p.label == "Your responsibility")
    assert owed.amount is None
    assert "does not state" in owed.explanation
    assert any("Your responsibility" in item for item in explanation.not_reported)
