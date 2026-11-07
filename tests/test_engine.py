from pathlib import Path

from eob.engine import analyze
from eob.models import EobSummary
from eob.parser import parse_eob
from healthcore.fhir.helpers import load_resource

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "carin"


def load(name: str) -> EobSummary:
    return parse_eob(load_resource(FIXTURES / f"{name}.json"))


def test_professional1_is_clean():
    analysis = analyze(load("EOBProfessional1"))
    assert analysis.flags == []
    assert all(check.status == "ok" for check in analysis.checks)


def test_outpatient1_is_clean():
    assert analyze(load("EOBOutpatient1")).flags == []


def test_professional2_has_the_reversal_info_flag():
    # Line 2 is the exact negative of line 1 (seen in the data), so this flag must fire.
    codes = [flag.code for flag in analyze(load("EOBProfessional2")).flags]
    assert "claim_has_reversals" in codes


def test_professional2_reversals_net_out_PROVISIONAL():
    """PROVISIONAL: assumes line 6, which I have not seen, reverses line 4 (code 37228).
    If this fails, the failure message tells us what line 6 really is. That is useful
    information, not a bug in the test."""
    analysis = analyze(load("EOBProfessional2"))
    assert "possible_duplicate_line" not in [flag.code for flag in analysis.flags]
    assert [check for check in analysis.checks if check.status == "mismatch"] == []


def test_parse_warnings_are_passed_through():
    eob = load("EOBProfessional1")
    assert analyze(eob).parse_warnings == eob.parse_warnings
