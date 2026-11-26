from decimal import Decimal

from eob.engine import analyze
from eob.evaluation import ROOT
from eob.models import AmountSet, EobSummary
from eob.parser import parse_eob
from healthcore.fhir.helpers import load_resource

IDENTITY = "allowed_equals_paid_plus_owed"


def identity_check(eob: EobSummary):
    return next(check for check in analyze(eob).checks if check.name == IDENTITY)


def with_totals(**amounts) -> EobSummary:
    return EobSummary(eob_id="t", totals=AmountSet(**amounts))


def test_the_held_out_secondary_payer_claim_now_reconciles():
    eob = parse_eob(load_resource(ROOT / "fixtures" / "heldout" / "ho_03_secondary_payer.json"))
    analysis = analyze(eob)
    assert [check for check in analysis.checks if check.status == "mismatch"] == []
    check = identity_check(eob)
    assert check.status == "ok"
    assert "another payer" in check.message


def test_without_a_prior_payer_the_check_and_its_message_are_unchanged():
    ok = identity_check(with_totals(eligible=Decimal(100), benefit=Decimal(70), member_liability=Decimal(30)))
    assert ok.status == "ok"
    assert ok.message == "The allowed amount equals what the plan paid plus the patient responsibility."
    bad = identity_check(with_totals(eligible=Decimal(100), benefit=Decimal(50), member_liability=Decimal(30)))
    assert bad.status == "mismatch"
    assert "another payer" not in bad.message


def test_a_prior_payer_amount_that_does_not_reconcile_is_still_reported_neutrally():
    check = identity_check(
        with_totals(
            eligible=Decimal(500),
            prior_payer_paid=Decimal(300),
            benefit=Decimal(140),
            member_liability=Decimal(100),
        )
    )
    assert check.status == "mismatch"
    assert "$300.00" in check.message and "another payer" in check.message
    assert "double-check" in check.message