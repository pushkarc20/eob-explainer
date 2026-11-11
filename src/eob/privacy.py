"""What may leave the device for one EOB (cloud mode), and how that payload is built.

Layers, in order:
1. Allow-list: only the fields below are ever copied. Names, member IDs, claim numbers, provider IDs,
   diagnoses and notes are not parsed at all, so they cannot be sent.
2. Known-value placeholders: provider/insurer names and service dates become [PROVIDER_1], [DATE_1], ...
3. Presidio scan of the few free-text strings that come from the source document.
4. Leak guard: fail closed if anything sensitive is still in the final text.
"""
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from eob.engine import Analysis
from eob.flags import nice_date
from eob.models import AmountSet, EobLine, EobSummary
from healthcore.privacy.detector import PiiDetector, default_detector, scrub_text
from healthcore.privacy.guard import check_outbound
from healthcore.privacy.pseudonymizer import Pseudonymizer

MAX_LINES = 40
MONEY_NAMES = (
    "billed", "allowed", "plan_paid", "patient_responsibility", "patient_paid",
    "deductible", "copay", "coinsurance", "noncovered", "prior_payer_paid",
)
AMOUNT_FIELDS = tuple(name for name in AmountSet.model_fields if name != "other")


class LinePayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    line: int
    service_code: str | None = None
    service_description: str | None = None
    date: str | None = None
    amounts: dict[str, str] = Field(default_factory=dict)


class FlagPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    severity: str
    title: str
    detail: str
    ask: str
    lines: list[int] = Field(default_factory=list)


class CloudPayload(BaseModel):
    """The ONLY thing that may be sent to a cloud model. Adding a field here is a privacy decision."""

    model_config = ConfigDict(frozen=True)

    claim_type: str | None = None
    claim_subtype: str | None = None
    provider: str | None = None
    insurer: str | None = None
    money: dict[str, dict[str, str | None]]
    lines: list[LinePayload]
    lines_omitted: int = 0
    flags: list[FlagPayload]
    check_notes: list[str]
    parse_warning_count: int = 0


@dataclass(frozen=True)
class PreparedPayload:
    payload: CloudPayload
    json_text: str
    replaced: dict[str, int]  # placeholder kind -> distinct values replaced (counts only)
    scrub_counts: dict[str, int]  # Presidio entity types found in free text (counts only)


def money_text(value: Decimal | None) -> str | None:
    return None if value is None else f"{value:.2f}"


def collect_blocked_values(resource: dict[str, Any], min_length: int = 4) -> list[str]:
    """Identifier-like strings from the RAW resource that must never appear in outbound text.

    Includes identifier values, ids and display names of referenced resources, free-text value strings,
    and name/contact/address parts. The parser already drops these; this list lets the leak guard prove it.
    """
    found: set[str] = set()

    def add(value: Any) -> None:
        if isinstance(value, str) and len(value) >= min_length:
            found.add(value)

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            reference = node.get("reference")
            if isinstance(reference, str):
                add(reference.rsplit("/", 1)[-1])
                add(node.get("display"))
            for key in ("valueString", "family", "birthDate", "postalCode", "city"):
                add(node.get(key))
            for key in ("given", "line"):
                parts = node.get(key)
                if isinstance(parts, list):
                    for part in parts:
                        add(part)
            for key in ("identifier", "telecom"):
                entries = node.get(key)
                for entry in entries if isinstance(entries, list) else []:
                    if isinstance(entry, dict):
                        add(entry.get("value"))
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(resource)
    return sorted(found)


def _merge_counts(into: dict[str, int], extra: dict[str, int]) -> None:
    for key, value in extra.items():
        into[key] = into.get(key, 0) + value


def _line_payload(
    line: EobLine,
    date_placeholders: dict[Any, str],
    pseudonymizer: Pseudonymizer,
    detector: PiiDetector,
    scrub_counts: dict[str, int],
) -> LinePayload:
    description = None
    if line.service_display:
        description, found = scrub_text(line.service_display, detector, pseudonymizer)
        _merge_counts(scrub_counts, found)
    amounts = {}
    for name in AMOUNT_FIELDS:
        value = getattr(line.amounts, name)
        if value is not None:
            amounts[name] = f"{value:.2f}"
    return LinePayload(
        line=line.sequence,
        service_code=line.service_code,
        service_description=description,
        date=date_placeholders.get(line.service_date),
        amounts=amounts,
    )


def prepare_cloud_payload(
    eob: EobSummary,
    analysis: Analysis,
    pseudonymizer: Pseudonymizer,
    detector: PiiDetector | None = None,
    blocked_values: Iterable[str] = (),
) -> PreparedPayload:
    """Build the outbound payload, run the leak guard, and return it. Raises LeakError if anything
    sensitive is still present. The caller keeps `pseudonymizer` to restore real values afterwards."""
    detector = detector or default_detector()
    pseudonymizer.block(*blocked_values)

    provider = pseudonymizer.register("PROVIDER", eob.provider_display) if eob.provider_display else None
    insurer = pseudonymizer.register("INSURER", eob.insurer_display) if eob.insurer_display else None
    days = sorted({line.service_date for line in eob.lines if line.service_date})
    date_placeholders = {
        day: pseudonymizer.register("DATE", nice_date(day), (day.isoformat(),)) for day in days
    }

    scrub_counts: dict[str, int] = {}
    shown = eob.lines[:MAX_LINES]
    lines = [_line_payload(line, date_placeholders, pseudonymizer, detector, scrub_counts) for line in shown]

    money = {
        name: {"amount": money_text(getattr(analysis.money, name).value), "source": getattr(analysis.money, name).source}
        for name in MONEY_NAMES
    }
    flags = [
        FlagPayload(
            code=flag.code,
            severity=flag.severity,
            title=pseudonymizer.apply(flag.title),
            detail=pseudonymizer.apply(flag.detail),
            ask=pseudonymizer.apply(flag.ask),
            lines=flag.line_sequences,
        )
        for flag in analysis.flags
    ]
    notes = [pseudonymizer.apply(c.message) for c in analysis.checks if c.status == "mismatch"]

    payload = CloudPayload(
        claim_type=eob.claim_type,
        claim_subtype=eob.claim_subtype,
        provider=provider,
        insurer=insurer,
        money=money,
        lines=lines,
        lines_omitted=max(0, len(eob.lines) - MAX_LINES),
        flags=flags,
        check_notes=notes,
        parse_warning_count=len(analysis.parse_warnings),
    )
    json_text = payload.model_dump_json()
    check_outbound(json_text, pseudonymizer, detector)
    return PreparedPayload(
        payload=payload,
        json_text=json_text,
        replaced=pseudonymizer.counts(),
        scrub_counts=scrub_counts,
    )
