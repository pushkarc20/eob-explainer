"""Rule-based 'worth asking about' flags.

Wording discipline (enforced by tests):
- Flags are QUESTIONS, never conclusions. Nothing says a bill is wrong, an error, or an overcharge.
- Every flag names who to ask (the insurer or the provider's billing office).
- The text is templated and uses only numbers from the EOB, so the tool still works without an LLM.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from eob.models import EobLine, EobSummary
from eob.money import MoneyView, fmt_money

_RANK = {"question": 0, "info": 1}


class Thresholds(BaseModel):
    """Tunable defaults. They are product judgments, not medical or legal facts."""

    model_config = ConfigDict(frozen=True)

    share_threshold: Decimal = Decimal("0.50")  # patient share of the allowed amount
    share_min_dollars: Decimal = Decimal(50)  # ignore small balances
    unitemized_tolerance: Decimal = Decimal("1.00")
    explained_fraction: Decimal = Decimal("0.90")  # share of the balance that itemized parts must cover


class Flag(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    severity: Literal["info", "question"]
    title: str
    detail: str
    ask: str
    line_sequences: list[int] = Field(default_factory=list)


def _nice_date(day: date) -> str:
    return f"{day:%b} {day.day}, {day.year}"


def _seq_text(sequences: list[int]) -> str:
    return ", ".join(str(number) for number in sequences)


def _duplicate_flags(eob: EobSummary) -> list[Flag]:
    """Same code + same day + same billed amount, with reversals netted out.

    Charge, reversal, recharge nets to ONE (no flag). Two plain charges net to TWO (flag).
    Limits: lines are compared within one claim only, and modifiers are not compared, so a
    legitimate repeated service (e.g. two units billed on separate lines) can look the same.
    That's why this is worded as a question.
    """
    groups: dict[tuple[str, date, Decimal], list[EobLine]] = defaultdict(list)
    for line in eob.lines:
        billed = line.amounts.submitted
        if not line.service_code or line.service_date is None or not billed:
            continue
        groups[(line.service_code, line.service_date, abs(billed))].append(line)

    flags = []
    ordered = sorted(groups.items(), key=lambda item: (item[0][1], item[0][0]))
    for (code, day, unit), lines in ordered:
        total = sum((line.amounts.submitted for line in lines), Decimal(0))
        count = int((total / unit).to_integral_value())
        if count < 2:
            continue
        sequences = [line.sequence for line in lines]
        flags.append(Flag(
            code="possible_duplicate_line",
            severity="question",
            title="The same service appears more than once on the same day",
            detail=(
                f"Service code {code} on {_nice_date(day)} appears {count} times at "
                f"{fmt_money(unit)} each, after any reversals are netted out "
                f"(line items {_seq_text(sequences)})."
            ),
            ask=(
                "Ask the provider's billing office whether these were separate services or a "
                "repeated entry. Your insurer can also tell you how each line was processed."
            ),
            line_sequences=sequences,
        ))
    return flags


def _share_flag(money: MoneyView, th: Thresholds) -> Flag | None:
    owed = money.patient_responsibility.value
    allowed = money.allowed.value
    if owed is None or allowed is None or allowed <= 0 or owed < th.share_min_dollars:
        return None
    share = owed / allowed
    if share < th.share_threshold:
        return None

    itemized = [
        (name, figure.value)
        for name, figure in (
            ("deductible", money.deductible),
            ("copay", money.copay),
            ("coinsurance", money.coinsurance),
        )
        if figure.value is not None and figure.value > 0
    ]
    explained = sum((value for _, value in itemized), Decimal(0))
    percent = (share * 100).quantize(Decimal(1))
    detail = (
        f"Your responsibility is {fmt_money(owed)}, about {percent}% of the "
        f"{fmt_money(allowed)} allowed amount."
    )
    if itemized:
        detail += " The EOB itemizes " + ", ".join(
            f"{fmt_money(value)} {name}" for name, value in itemized
        ) + "."

    if explained >= owed * th.explained_fraction:
        severity: Literal["info", "question"] = "info"
        ask = (
            "A large share is common when a deductible or copay applies. Your insurer can show "
            "how much of your deductible and out-of-pocket limit has been used."
        )
    else:
        severity = "question"
        ask = (
            "Ask your insurer how this amount was calculated and which parts are deductible, "
            "copay or coinsurance."
        )
    return Flag(
        code="high_patient_share",
        severity=severity,
        title="You are responsible for a large share of the allowed amount",
        detail=detail,
        ask=ask,
    )


def _unitemized_flag(money: MoneyView, th: Thresholds) -> Flag | None:
    owed = money.patient_responsibility
    if owed.value is None or owed.source == "computed" or owed.value <= 0:
        return None
    reported = [
        figure.value
        for figure in (money.deductible, money.copay, money.coinsurance, money.noncovered)
        if figure.value is not None
    ]
    if not reported:
        return None  # the EOB gives no breakdown at all, so there is nothing to compare against
    itemized = sum(reported, Decimal(0))
    gap = owed.value - itemized
    if gap <= th.unitemized_tolerance:
        return None
    return Flag(
        code="unitemized_patient_amount",
        severity="question",
        title="Part of what you owe is not broken down",
        detail=(
            f"Your responsibility is {fmt_money(owed.value)}, but the EOB itemizes only "
            f"{fmt_money(itemized)} as deductible, copay, coinsurance or non-covered. "
            f"About {fmt_money(gap)} is not broken down."
        ),
        ask="Ask your insurer what makes up the remaining amount.",
    )


def _noncovered_flag(eob: EobSummary, money: MoneyView) -> Flag | None:
    amount = money.noncovered.value
    if amount is None or amount <= 0:
        return None
    sequences = [
        line.sequence
        for line in eob.lines
        if line.amounts.noncovered is not None and line.amounts.noncovered > 0
    ]
    detail = f"The insurer marked {fmt_money(amount)} as not covered."
    if sequences:
        detail += f" This appears on line item(s) {_seq_text(sequences)}."
    return Flag(
        code="noncovered_amount",
        severity="question",
        title="Part of this claim was not covered",
        detail=detail,
        ask=(
            "Ask your insurer why this amount was not covered and whether an appeal or a "
            "corrected claim is possible. Your provider's billing office can confirm how it was coded."
        ),
        line_sequences=sequences,
    )


def _reversal_flag(eob: EobSummary) -> Flag | None:
    sequences = [
        line.sequence
        for line in eob.lines
        if line.amounts.submitted is not None and line.amounts.submitted < 0
    ]
    if not sequences:
        return None
    return Flag(
        code="claim_has_reversals",
        severity="info",
        title="This claim includes adjustment lines",
        detail=(
            f"Line item(s) {_seq_text(sequences)} have negative amounts, which often means an "
            "earlier charge was reversed or corrected."
        ),
        ask="If these amounts differ from an earlier statement, ask your insurer what changed.",
        line_sequences=sequences,
    )


def detect_flags(eob: EobSummary, money: MoneyView, thresholds: Thresholds) -> list[Flag]:
    flags = _duplicate_flags(eob)
    for flag in (
        _share_flag(money, thresholds),
        _unitemized_flag(money, thresholds),
        _noncovered_flag(eob, money),
        _reversal_flag(eob),
    ):
        if flag is not None:
            flags.append(flag)
    return sorted(flags, key=lambda flag: (_RANK[flag.severity], flag.code))
