"""Check an AI-written explanation against the facts it was given.

The model is never trusted: every number, flag and phrase is verified in code before anything reaches
the user. Problem messages contain no source identifiers, so they are safe to send back to the model.
Known limit: this cannot catch a true number used in the wrong place (for example "$0" where the EOB
reports nothing). The evaluation set and an LLM judge look for that in Step 9.
"""
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from eob.explanation import Explanation, all_text
from eob.privacy import CloudPayload
from eob.safety import find_banned
from healthcore.privacy.detector import HARD_ENTITIES, PiiDetector
from healthcore.privacy.pseudonymizer import Pseudonymizer

DOLLAR = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)")
BARE_DECIMAL = re.compile(r"(?<![\d$.,])(\d[\d,]*\.\d{2})(?!\d)")
PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s?(?:%|percent)", re.IGNORECASE)
GUIDANCE = re.compile(r"insurer|insurance|provider|billing office", re.IGNORECASE)


@dataclass(frozen=True)
class Problem:
    code: str
    message: str


def _decimal(value: str | None) -> Decimal | None:
    try:
        return Decimal(value)  # type: ignore[arg-type]
    except (InvalidOperation, TypeError):
        return None


def extract_amounts(text: str) -> set[Decimal]:
    found: set[Decimal] = set()
    for token in (*DOLLAR.findall(text), *BARE_DECIMAL.findall(text)):
        number = _decimal(token.replace(",", ""))
        if number is not None:
            found.add(number)
    return found


def _percents(text: str) -> set[Decimal]:
    return {number for token in PERCENT.findall(text) if (number := _decimal(token)) is not None}


def _grounding_texts(payload: CloudPayload) -> list[str]:
    texts = list(payload.check_notes)
    for flag in payload.flags:
        texts += [flag.title, flag.detail, flag.ask]
    return texts


def allowed_amounts(payload: CloudPayload) -> set[Decimal]:
    """Every dollar figure the model may use: structured amounts (either sign) and amounts in flag text."""
    values = [figure["amount"] for figure in payload.money.values()]
    for line in payload.lines:
        values.extend(line.amounts.values())
    allowed = {abs(number) for value in values if (number := _decimal(value)) is not None}
    for text in _grounding_texts(payload):
        allowed |= extract_amounts(text)
    return allowed


def validate_explanation(
    explanation: Explanation,
    payload: CloudPayload,
    pseudonymizer: Pseudonymizer,
    detector: PiiDetector,
) -> list[Problem]:
    problems: list[Problem] = []
    text = all_text(explanation)

    if len(explanation.what_happened.strip()) < 20:
        problems.append(Problem("empty_summary", "Write a 2 to 4 sentence summary in what_happened."))

    bad_amounts = sorted(extract_amounts(text) - allowed_amounts(payload))
    if bad_amounts:
        shown = ", ".join(f"${amount:,.2f}" for amount in bad_amounts)
        problems.append(Problem(
            "ungrounded_amount",
            f"These dollar amounts are not in the data: {shown}. Use only amounts given in the JSON.",
        ))

    allowed_percents: set[Decimal] = set()
    for source in _grounding_texts(payload):
        allowed_percents |= _percents(source)
    bad_percents = sorted(_percents(text) - allowed_percents)
    if bad_percents:
        shown = ", ".join(f"{number}%" for number in bad_percents)
        problems.append(Problem(
            "ungrounded_percent",
            f"These percentages are not in the data: {shown}. Do not calculate or state percentages.",
        ))

    banned = find_banned(text)
    if banned:
        problems.append(Problem(
            "banned_phrase",
            "Do not use these words or phrases: " + ", ".join(banned) + ". Flags are questions, never conclusions.",
        ))

    unknown = pseudonymizer.unknown_placeholders(text)
    if unknown:
        problems.append(Problem(
            "unknown_placeholder",
            "These placeholders are not in the data: " + ", ".join(unknown) + ". Use only placeholders from the JSON.",
        ))

    expected = {flag.code for flag in payload.flags}
    given = {note.flag_code for note in explanation.flag_notes}
    if expected - given:
        problems.append(Problem(
            "missing_flag_note",
            "Add a flag_notes entry for each of these flag codes: " + ", ".join(sorted(expected - given)) + ".",
        ))
    if given - expected:
        problems.append(Problem(
            "invented_flag",
            "Remove flag_notes entries that are not in the JSON flags: " + ", ".join(sorted(given - expected)) + ".",
        ))

    if not GUIDANCE.search(explanation.next_steps):
        problems.append(Problem(
            "missing_guidance",
            "next_steps must tell the person to contact their insurer or the provider's billing office.",
        ))

    identifier_kinds = sorted({finding.entity_type for finding in detector.find(text, HARD_ENTITIES)})
    if identifier_kinds:
        problems.append(Problem(
            "identifier_like_content",
            "Remove identifier-like content (" + ", ".join(identifier_kinds) + "). Use only data from the JSON.",
        ))
    return problems
