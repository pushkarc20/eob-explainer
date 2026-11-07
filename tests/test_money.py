from decimal import Decimal
from pathlib import Path

from eob.models import AmountSet, EobLine, EobSummary
from eob.money import build_money_view, check_consistency, fmt_money
from eob.parser import parse_eob
from healthcore.fhir.helpers import load_resource

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "carin"


def load(name: str) -> EobSummary:
    return parse_eob(load_resource(FIXTURES / f"{name}.json"))


def make_eob(**kwargs) -> EobSummary:
    return EobSummary(eob_id="t1", **kwargs)


def line(sequence: int, **amounts) -> EobLine:
    return EobLine(sequence=sequence, amounts=AmountSet(**amounts))


def checks_for(eob: EobSummary):
    return check_consistency(eob, build_money_view(eob))


def test_fmt_money():
    assert fmt_money(Decimal("1234.5")) == "$1,234.50"
    assert fmt_money(Decimal(0)) == "$0.00"
    assert fmt_money(Decimal("-68.8")) == "-$68.80"


def test_professional1_money_view():
    money = build_money_view(load("EOBProfessional1"))
    assert money.billed.value == Decimal(250)
    assert money.billed.source == "claim totals"
    assert money.plan_paid.value == Decimal(200)
    assert money.plan_paid.source == "claim totals"
    assert money.allowed.value is None
    assert money.allowed.source == "not reported"
    assert money.patient_responsibility.value is None
    assert money.patient_paid.value == Decimal(0)


def test_professional2_money_view():
    money = build_money_view(load("EOBProfessional2"))
    assert money.billed.value == Decimal(820)
    assert money.allowed.value == Decimal("258.91")
    assert money.plan_paid.value == Decimal("258.91")  # falls back to 'benefit'
    assert money.patient_responsibility.value == Decimal(0)
    assert money.patient_responsibility.source == "claim totals"
    assert money.noncovered.value == Decimal(0)


def test_outpatient1_money_view():
    money = build_money_view(load("EOBOutpatient1"))
    assert money.billed.value == Decimal(2650)
    assert money.plan_paid.value == Decimal(620)
    assert money.allowed.value is None
    assert money.patient_responsibility.value is None
    assert money.patient_paid.value == Decimal(0)


def test_sum_of_lines_is_used_when_claim_totals_are_absent():
    money = build_money_view(make_eob(lines=[line(1, submitted=Decimal(10)), line(2, submitted=Decimal(5))]))
    assert money.billed.value == Decimal(15)
    assert money.billed.source == "sum of lines"


def test_claim_header_amount_is_used_when_totals_are_absent():
    money = build_money_view(make_eob(header_amounts=AmountSet(paid_to_provider=Decimal(620))))
    assert money.plan_paid.value == Decimal(620)
    assert money.plan_paid.source == "claim header"


def test_payment_amount_is_the_last_resort_for_plan_paid():
    money = build_money_view(make_eob(payment_amount=Decimal(99)))
    assert money.plan_paid.value == Decimal(99)
    assert money.plan_paid.source == "claim payment"


def test_patient_responsibility_is_computed_from_cost_sharing_when_not_reported():
    eob = make_eob(totals=AmountSet(deductible=Decimal(40), copay=Decimal(20)))
    money = build_money_view(eob)
    assert money.patient_responsibility.value == Decimal(60)
    assert money.patient_responsibility.source == "computed"


def test_reported_member_liability_beats_computed():
    eob = make_eob(totals=AmountSet(member_liability=Decimal(10), deductible=Decimal(40)))
    money = build_money_view(eob)
    assert money.patient_responsibility.value == Decimal(10)
    assert money.patient_responsibility.source == "claim totals"


def test_noncovered_is_not_added_to_computed_responsibility():
    money = build_money_view(make_eob(totals=AmountSet(noncovered=Decimal(30))))
    assert money.patient_responsibility.value is None


def test_lines_vs_total_mismatch_is_reported_neutrally():
    eob = make_eob(
        totals=AmountSet(submitted=Decimal(100)),
        lines=[line(1, submitted=Decimal(60)), line(2, submitted=Decimal(30))],
    )
    mismatches = [c for c in checks_for(eob) if c.status == "mismatch"]
    assert len(mismatches) == 1
    assert "$90.00" in mismatches[0].message
    assert "$100.00" in mismatches[0].message


def test_lines_matching_total_is_ok():
    eob = make_eob(
        totals=AmountSet(submitted=Decimal(100)),
        lines=[line(1, submitted=Decimal(60)), line(2, submitted=Decimal(40))],
    )
    assert [c.status for c in checks_for(eob)] == ["ok"]


def test_allowed_vs_paid_plus_owed_mismatch():
    eob = make_eob(totals=AmountSet(eligible=Decimal(100), benefit=Decimal(50), member_liability=Decimal(30)))
    checks = checks_for(eob)
    assert [c.name for c in checks] == ["allowed_equals_paid_plus_owed"]
    assert checks[0].status == "mismatch"
    assert "$100.00" in checks[0].message
    assert "$50.00" in checks[0].message
    assert "$30.00" in checks[0].message


def test_professional1_checks_are_all_ok():
    checks = checks_for(load("EOBProfessional1"))
    assert {c.name for c in checks} == {"lines_vs_total:submitted", "lines_vs_total:benefit"}
    assert all(c.status == "ok" for c in checks)


def test_professional2_allowed_equals_paid_plus_owed():
    checks = {c.name: c for c in checks_for(load("EOBProfessional2"))}
    assert checks["allowed_equals_paid_plus_owed"].status == "ok"
