from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from eob.models import AmountSet, EobLine, EobSummary
from eob.parser import EobParseError, parse_eob
from healthcore.fhir.helpers import load_resource

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "carin"


def load(name: str) -> EobSummary:
    return parse_eob(load_resource(FIXTURES / f"{name}.json"))


def minimal(**extra) -> dict:
    return {"resourceType": "ExplanationOfBenefit", "id": "t1", **extra}


def total_entry(code: str, value, currency: str = "USD") -> dict:
    return {"category": {"coding": [{"code": code}]}, "amount": {"value": value, "currency": currency}}


def test_professional1_header_and_totals():
    eob = load("EOBProfessional1")
    assert eob.eob_id == "EOBProfessional1"
    assert eob.claim_id == "AW123412341234123412341234123413"
    assert eob.claim_type == "professional"
    assert eob.status == "active"
    assert eob.outcome == "partial"
    assert eob.use == "claim"
    assert eob.billable_start == date(2019, 1, 1)
    assert eob.billable_end == date(2019, 10, 31)
    assert eob.insurer_display == "XXX Health Plan"
    assert eob.header_statuses == {
        "billingnetworkstatus": "innetwork",
        "renderingnetworkstatus": "innetwork",
    }
    assert eob.totals.submitted == Decimal(250)
    assert eob.totals.benefit == Decimal(200)
    assert eob.totals.paid_to_provider == Decimal(200)
    assert eob.totals.paid_by_patient == Decimal(0)
    assert eob.totals.eligible is None  # not reported is None, not 0
    assert eob.payment_amount == Decimal(200)
    assert eob.payment_adjustment == Decimal(-50)
    assert eob.parse_warnings == []


def test_professional1_line():
    eob = load("EOBProfessional1")
    assert len(eob.lines) == 1
    line = eob.lines[0]
    assert line.sequence == 1
    assert line.service_code == "97110"
    assert line.service_code_system == "http://www.ama-assn.org/go/cpt"
    assert line.service_date == date(2019, 7, 2)
    assert line.amounts.submitted == Decimal(250)
    assert line.amounts.benefit == Decimal(200)
    assert line.amounts.eligible is None
    assert line.statuses == {"benefitpaymentstatus": "other"}


def test_professional2_totals():
    eob = load("EOBProfessional2")
    assert eob.eob_id == "EOBProfessional2"
    assert len(eob.lines) == 6
    totals = eob.totals
    assert totals.submitted == Decimal(820)
    assert totals.eligible == Decimal("258.91")
    assert totals.deductible == Decimal(0)
    assert totals.copay == Decimal(0)
    assert totals.noncovered == Decimal(0)
    assert totals.benefit == Decimal("258.91")
    assert totals.member_liability == Decimal(0)


def test_professional2_keeps_reversal_lines_with_their_sign():
    eob = load("EOBProfessional2")
    original, reversal = eob.lines[0], eob.lines[1]
    assert original.service_code == "75710"
    assert original.service_date == date(2020, 8, 4)
    assert original.amounts.submitted == Decimal("68.8")
    assert original.amounts.eligible == Decimal("34.8")
    assert original.amounts.benefit == Decimal("34.8")
    assert reversal.amounts.submitted == Decimal("-68.8")
    assert reversal.amounts.eligible == Decimal("-34.8")


def test_professional2_noncovered_line_then_paid_line():
    eob = load("EOBProfessional2")
    denied, paid = eob.lines[3], eob.lines[4]
    assert denied.sequence == 4 and paid.sequence == 5
    assert denied.service_code == paid.service_code == "37228"
    assert denied.amounts.noncovered == Decimal("224.11")
    assert denied.amounts.benefit == Decimal(0)
    assert paid.amounts.benefit == Decimal("224.11")


def test_outpatient1_header_level_amounts_and_empty_line():
    eob = load("EOBOutpatient1")
    assert eob.eob_id == "EOBOutpatient1"
    assert eob.header_amounts.paid_to_provider == Decimal(620)
    assert eob.header_amounts.paid_by_patient == Decimal(0)
    assert eob.totals.submitted == Decimal(2650)
    assert eob.totals.paid_to_provider == Decimal(620)
    assert len(eob.lines) == 1
    line = eob.lines[0]
    assert line.service_code == "not-applicable"
    assert line.service_date == date(2019, 11, 2)
    assert line.amounts.is_empty()


def test_unknown_category_is_kept_under_other_with_a_warning():
    eob = parse_eob(minimal(total=[total_entry("mystery", 5)]))
    assert eob.totals.other == {"mystery": Decimal(5)}
    assert any("mystery" in warning for warning in eob.parse_warnings)


def test_repeated_category_is_summed_with_a_warning():
    eob = parse_eob(minimal(total=[total_entry("submitted", 10), total_entry("submitted", 5)]))
    assert eob.totals.submitted == Decimal(15)
    assert any("more than once" in warning for warning in eob.parse_warnings)


def test_non_usd_currency_is_flagged():
    eob = parse_eob(minimal(total=[total_entry("submitted", 10, currency="EUR")]))
    assert any("EUR" in warning for warning in eob.parse_warnings)


def test_rejects_non_eob_resources():
    with pytest.raises(EobParseError):
        parse_eob({"resourceType": "Patient", "id": "p1"})


def test_rejects_older_stu3_style_eobs():
    stu3 = minimal(item=[{"sequence": 1, "service": {"coding": [{"code": "99203"}]}}])
    with pytest.raises(EobParseError):
        parse_eob(stu3)


def test_model_has_no_patient_identity_fields():
    forbidden = {"patient", "name", "address", "birth_date", "mbi", "phone", "email", "member_id", "npi"}
    declared = set(EobSummary.model_fields) | set(EobLine.model_fields) | set(AmountSet.model_fields)
    assert not (forbidden & declared)


def test_patient_reference_is_not_carried_over():
    eob = load("EOBProfessional1")  # the source file has "patient": {"reference": "Patient/Patient2"}
    assert "Patient2" not in eob.model_dump_json()
