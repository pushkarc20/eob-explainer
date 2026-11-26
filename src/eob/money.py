"""Turn a parsed EOB into a plain 'money waterfall' and check that the numbers are consistent.

Rules of the road:
- Never invent a number. A figure is reported by the EOB, computed from reported figures
  (and labelled 'computed'), or None.
- Every figure records where it came from, so an explanation can say 'the claim total shows...'.
- Amounts are Decimal, never float.
"""
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from eob.models import EobSummary

Source = Literal[
    "claim totals", "claim header", "claim payment", "sum of lines", "computed", "not reported"
]
TOLERANCE = Decimal("0.01")

CATEGORY_LABELS = {
    "submitted": "billed amount",
    "eligible": "allowed amount",
    "benefit": "plan benefit amount",
    "deductible": "deductible",
    "copay": "copay",
    "coinsurance": "coinsurance",
    "noncovered": "non-covered amount",
    "member_liability": "patient responsibility",
    "prior_payer_paid": "amount paid by a prior payer",
    "paid_to_provider": "payment to the provider",
    "paid_by_patient": "amount paid by the patient",
}


def fmt_money(value: Decimal) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


class Figure(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: Decimal | None = None
    source: Source = "not reported"


class MoneyView(BaseModel):
    """The 'waterfall': billed -> allowed -> plan paid -> patient responsibility."""

    model_config = ConfigDict(frozen=True)

    billed: Figure
    allowed: Figure
    plan_paid: Figure
    patient_responsibility: Figure
    patient_paid: Figure  # what the patient has already paid, if reported (not the same as owed)
    deductible: Figure
    copay: Figure
    coinsurance: Figure
    noncovered: Figure
    prior_payer_paid: Figure


class Check(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    status: Literal["ok", "mismatch"]
    message: str


def _sum_lines(eob: EobSummary, field: str) -> Decimal | None:
    values = []
    for line in eob.lines:
        value = getattr(line.amounts, field)
        if value is not None:
            values.append(value)
    return sum(values, Decimal(0)) if values else None


def _pick(eob: EobSummary, field: str) -> Figure:
    """Claim totals first, then claim-header amounts, then the sum of line items."""
    for source, amounts in (("claim totals", eob.totals), ("claim header", eob.header_amounts)):
        value = getattr(amounts, field)
        if value is not None:
            return Figure(value=value, source=source)
    total = _sum_lines(eob, field)
    if total is not None:
        return Figure(value=total, source="sum of lines")
    return Figure()


def _plan_paid(eob: EobSummary) -> Figure:
    for field in ("paid_to_provider", "benefit"):
        figure = _pick(eob, field)
        if figure.value is not None:
            return figure
    if eob.payment_amount is not None:
        return Figure(value=eob.payment_amount, source="claim payment")
    return Figure()


def _patient_responsibility(eob: EobSummary, cost_sharing: list[Figure]) -> Figure:
    reported = _pick(eob, "member_liability")
    if reported.value is not None:
        return reported
    parts = [figure.value for figure in cost_sharing if figure.value is not None]
    if parts:
        return Figure(value=sum(parts, Decimal(0)), source="computed")
    return Figure()


def build_money_view(eob: EobSummary) -> MoneyView:
    deductible = _pick(eob, "deductible")
    copay = _pick(eob, "copay")
    coinsurance = _pick(eob, "coinsurance")
    return MoneyView(
        billed=_pick(eob, "submitted"),
        allowed=_pick(eob, "eligible"),
        plan_paid=_plan_paid(eob),
        patient_responsibility=_patient_responsibility(eob, [deductible, copay, coinsurance]),
        patient_paid=_pick(eob, "paid_by_patient"),
        deductible=deductible,
        copay=copay,
        coinsurance=coinsurance,
        noncovered=_pick(eob, "noncovered"),
        prior_payer_paid=_pick(eob, "prior_payer_paid"),
    )


def check_consistency(eob: EobSummary, money: MoneyView) -> list[Check]:
    """Do the numbers agree with each other? Mismatches are worded neutrally: insurers
    report amounts in different ways, so a mismatch is a reason to double-check, not proof
    of a problem."""
    checks: list[Check] = []

    for field, label in CATEGORY_LABELS.items():
        claim_total = getattr(eob.totals, field)
        line_total = _sum_lines(eob, field)
        if claim_total is None or line_total is None:
            continue  # nothing to compare
        if abs(claim_total - line_total) <= TOLERANCE:
            checks.append(Check(
                name=f"lines_vs_total:{field}",
                status="ok",
                message=f"The line items match the claim total for the {label}.",
            ))
        else:
            checks.append(Check(
                name=f"lines_vs_total:{field}",
                status="mismatch",
                message=(
                    f"The line items add up to {fmt_money(line_total)} for the {label}, "
                    f"but the claim total says {fmt_money(claim_total)}."
                ),
            ))

    allowed = money.allowed.value
    paid = money.plan_paid.value
    owed = money.patient_responsibility.value
    prior = money.prior_payer_paid.value or Decimal(0)  # another payer's payment counts toward the allowed amount
    if allowed is not None and paid is not None and owed is not None:
        if abs(allowed - (prior + paid + owed)) <= TOLERANCE:
            checks.append(Check(
                name="allowed_equals_paid_plus_owed",
                status="ok",
                message=(
                    "The allowed amount equals what the plan paid, plus what another payer paid, plus the patient responsibility."
                    if prior
                    else "The allowed amount equals what the plan paid plus the patient responsibility."
                ),
            ))
        else:
            checks.append(Check(
                name="allowed_equals_paid_plus_owed",
                status="mismatch",
                message=(
                    f"The allowed amount ({fmt_money(allowed)}) does not equal what the plan paid "
                    f"({fmt_money(paid)})"
                    + (f", plus what another payer paid ({fmt_money(prior)})," if prior else "")
                    + f" plus the patient responsibility ({fmt_money(owed)}). "
                    "Insurers report these amounts differently, so this is a reason to "
                    "double-check, not proof of a problem."
                ),
            ))
    return checks
