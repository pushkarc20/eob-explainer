"""Deterministic explanation built from the rules engine. Used when the AI is unavailable, fails
verification, or the leak guard blocks a request. Runs locally and uses real values."""
from eob.engine import Analysis
from eob.explanation import Explanation, FlagNote, MoneyPoint
from eob.models import EobSummary
from eob.money import Figure, fmt_money

NOT_STATED = "This EOB does not state this amount."


def _point(label: str, figure: Figure, meaning: str) -> MoneyPoint:
    if figure.value is None:
        return MoneyPoint(label=label, amount=None, explanation=NOT_STATED)
    return MoneyPoint(label=label, amount=fmt_money(figure.value), explanation=meaning)


def template_explanation(eob: EobSummary, analysis: Analysis) -> Explanation:
    money = analysis.money
    count = len(eob.lines)
    kind = f"{eob.claim_type} " if eob.claim_type else ""
    what = f"This is a summary of one {kind}claim with {count} line item{'s' if count != 1 else ''}."
    if eob.provider_display:
        what += f" The provider listed is {eob.provider_display}."

    owed_meaning = (
        "Calculated from the deductible, copay and coinsurance listed on this EOB."
        if money.patient_responsibility.source == "computed"
        else "The amount the plan reports as your responsibility."
    )
    points = [
        _point("Billed by the provider", money.billed, "The amount the provider charged."),
        _point("Allowed amount", money.allowed, "The amount the plan treats as eligible for payment."),
        _point("Paid by your plan", money.plan_paid, "The amount the plan reports as paid or payable."),
        _point("Your responsibility", money.patient_responsibility, owed_meaning),
    ]

    grouped: dict[str, list] = {}
    for flag in analysis.flags:
        grouped.setdefault(flag.code, []).append(flag)
    notes = [
        FlagNote(
            flag_code=code,
            explanation=" ".join(flag.detail for flag in flags),
            question=flags[0].ask,
        )
        for code, flags in grouped.items()
    ]

    missing = [point.label for point in points if point.amount is None]
    return Explanation(
        what_happened=what,
        money_points=points,
        flag_notes=notes,
        not_reported=[f"{label}: not stated on this EOB." for label in missing],
        next_steps=(
            "If anything is unclear, contact your insurer or the provider's billing office "
            "and ask about the items above."
        ),
    )
