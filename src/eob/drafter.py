"""Draft a short written question to the insurer, assembled entirely on this machine.

Nothing here calls a model or the network. Values only the member knows (name, member ID) are typed
locally and used only here; they never reach the explainer or any cloud payload. The claim number comes
from the EOB and is likewise kept local.
"""
from dataclasses import dataclass

from eob.engine import Analysis
from eob.flags import nice_date
from eob.models import EobSummary
from eob.money import MoneyView, fmt_money
from eob.questions import question_for

CLAIM_NUMBER = "[CLAIM NUMBER]"
PROVIDER_NAME = "[PROVIDER NAME]"
DATE_OF_SERVICE = "[DATE OF SERVICE]"
YOUR_NAME = "[YOUR NAME]"
MEMBER_ID = "[MEMBER ID]"

CONFIRM_BALANCE = "Could you confirm the amount I owe for this claim ({amount}) and when payment is due?"
BALANCE_NOT_STATED = (
    "The EOB does not state the amount I owe. Could you tell me what my responsibility is for this claim?"
)

NOTE_REVIEW = "Review and edit before sending. Remove anything you do not want to share."
NOTE_SECURE = "If your insurer has a secure message portal, use it. Regular email is not private."
NOTE_SENSITIVE = "Do not include your Social Security number or bank or card details."
NOTE_DENIAL = (
    "If you want to formally ask for a review of something marked as not covered, the denial notice or your "
    "plan documents explain the process and deadlines. This tool cannot tell you your rights or deadlines."
)
NOTE_NONE = "Nothing on this EOB stood out as worth questioning. You may not need to send this."


@dataclass(frozen=True)
class MemberDetails:
    name: str = ""
    member_id: str = ""


@dataclass(frozen=True)
class Draft:
    subject: str
    body: str
    to_fill: tuple[str, ...]  # bracketed fields the member must fill in before sending
    notes: tuple[str, ...]  # guidance shown with the draft; never part of the message


def _fill(value: str | None, placeholder: str, to_fill: list[str]) -> str:
    cleaned = (value or "").strip()
    if cleaned:
        return cleaned
    if placeholder not in to_fill:
        to_fill.append(placeholder)
    return placeholder


def _service_dates(eob: EobSummary) -> str | None:
    days = sorted({line.service_date for line in eob.lines if line.service_date})
    if not days:
        return None
    if len(days) == 1:
        return nice_date(days[0])
    return f"{nice_date(days[0])} to {nice_date(days[-1])}"


def _figure_lines(money: MoneyView) -> list[str]:
    rows = (
        ("Billed", money.billed),
        ("Allowed", money.allowed),
        ("Paid by the plan", money.plan_paid),
        ("My responsibility", money.patient_responsibility),
    )
    return [f"- {label}: {fmt_money(figure.value)}" for label, figure in rows if figure.value is not None]


def draft_message(eob: EobSummary, analysis: Analysis, member: MemberDetails | None = None) -> Draft:
    member = member or MemberDetails()
    to_fill: list[str] = []
    claim = _fill(eob.claim_id, CLAIM_NUMBER, to_fill)
    provider = _fill(eob.provider_display, PROVIDER_NAME, to_fill)
    service_dates = _service_dates(eob)
    dates = _fill(service_dates, DATE_OF_SERVICE, to_fill)
    name = _fill(member.name, YOUR_NAME, to_fill)
    member_id = _fill(member.member_id, MEMBER_ID, to_fill)

    subject = f"Question about claim {claim}" + (f" (service {service_dates})" if service_dates else "")

    asked = [flag for flag in analysis.flags if flag.severity == "question"]
    items = [f"{flag.detail} {question_for(flag.code, flag.severity)}" for flag in asked]
    owed = analysis.money.patient_responsibility.value
    items.append(CONFIRM_BALANCE.format(amount=fmt_money(owed)) if owed is not None else BALANCE_NOT_STATED)

    lines = [
        "Hello,",
        "",
        ("I am writing about the claim below. I have reviewed my Explanation of Benefits (EOB) and have "
        "a few questions."),
        "",
        f"Claim number: {claim}",
        f"Provider: {provider}",
        f"Date(s) of service: {dates}",
        f"Member name: {name}",
        f"Member ID: {member_id}",
    ]
    figures = _figure_lines(analysis.money)
    if figures:
        lines += ["", "What my EOB shows:", *figures]
    lines += ["", "My questions:"]
    lines += [f"{number}. {text}" for number, text in enumerate(items, start=1)]
    lines += ["", "Thank you for your help. A written reply would help me keep a record.", "", "Sincerely,", name]

    notes = [NOTE_REVIEW, NOTE_SECURE, NOTE_SENSITIVE]
    if any(flag.code == "noncovered_amount" for flag in asked):
        notes.append(NOTE_DENIAL)
    if not asked:
        notes.append(NOTE_NONE)
    skipped = [flag.title for flag in analysis.flags if flag.severity == "info"]
    if skipped:
        notes.append("Noted but not turned into questions: " + "; ".join(skipped) + ".")

    return Draft(subject=subject, body="\n".join(lines), to_fill=tuple(to_fill), notes=tuple(notes))


def render_draft(draft: Draft) -> str:
    lines = ["BEFORE YOU SEND"]
    if draft.to_fill:
        lines.append("  Fill in: " + ", ".join(draft.to_fill))
    lines += [f"  - {note}" for note in draft.notes]
    lines += ["", f"SUBJECT: {draft.subject}", "", draft.body]
    return "\n".join(lines)
