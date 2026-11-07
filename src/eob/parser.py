"""Parse a FHIR R4 ExplanationOfBenefit (CARIN C4BB style) into an EobSummary.

Principles: copy only allow-listed fields, never guess, and record anything
unexpected in parse_warnings instead of silently dropping or inventing it.
"""
from decimal import Decimal
from typing import Any

from eob.models import AmountSet, EobLine, EobSummary
from healthcore.fhir.helpers import (
    all_codes,
    first_coding,
    parse_fhir_date,
    reference_display,
    to_decimal,
)

# FHIR adjudication category code -> AmountSet field.
# Only codes actually seen in the CARIN example data are listed. Anything else lands in
# AmountSet.other with a warning, and gets added here once checked against the IG's code list.
CATEGORY_TO_FIELD = {
    "submitted": "submitted",
    "eligible": "eligible",
    "benefit": "benefit",
    "deductible": "deductible",
    "copay": "copay",
    "noncovered": "noncovered",
    "memberliability": "member_liability",
    "paidtoprovider": "paid_to_provider",
    "paidbypatient": "paid_by_patient",
}


class EobParseError(ValueError):
    """The input can't be treated as a supported EOB."""


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _money_value(parent: Any, key: str) -> Decimal | None:
    """parent[key] is a FHIR Money object ({'value': ..., 'currency': ...}); return its value."""
    if not isinstance(parent, dict):
        return None
    node = parent.get(key)
    return to_decimal(node.get("value")) if isinstance(node, dict) else None


def _category_code(entry: dict[str, Any]) -> str | None:
    codes = all_codes(entry.get("category"))
    for code in codes:
        if code in CATEGORY_TO_FIELD:
            return code
    return codes[0] if codes else None


def _accumulate(target: dict, key: str, value: Decimal, where: str, warnings: list[str]) -> None:
    if key in target:
        warnings.append(f"{where}: category '{key}' appears more than once; amounts were summed")
        target[key] += value
    else:
        target[key] = value


def _extract(entries: Any, where: str, warnings: list[str]) -> tuple[AmountSet, dict[str, str]]:
    """Read an adjudication/total list into (amounts, statuses).

    Entries with an 'amount' become dollar amounts. Entries with only a 'reason'
    (e.g. network status) become statuses.
    """
    known: dict[str, Decimal] = {}
    other: dict[str, Decimal] = {}
    statuses: dict[str, str] = {}
    if not isinstance(entries, list):
        return AmountSet(), statuses
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        code = _category_code(entry)
        if code is None:
            warnings.append(f"{where}: an entry without a category code was skipped")
            continue
        amount = entry.get("amount")
        if isinstance(amount, dict):
            value = to_decimal(amount.get("value"))
            if value is None:
                warnings.append(f"{where}: amount for '{code}' is missing or not a number; skipped")
                continue
            currency = amount.get("currency")
            if currency not in (None, "USD"):
                warnings.append(f"{where}: amount for '{code}' is in {currency}, not USD")
            field = CATEGORY_TO_FIELD.get(code)
            if field is None:
                warnings.append(f"{where}: unrecognized category '{code}' kept under 'other'")
                _accumulate(other, code, value, where, warnings)
            else:
                _accumulate(known, field, value, where, warnings)
        else:
            reasons = all_codes(entry.get("reason"))
            if reasons:
                statuses[code] = reasons[0]
    return AmountSet(**known, other=other), statuses


def _parse_line(item: dict[str, Any], position: int, warnings: list[str]) -> EobLine:
    raw_sequence = item.get("sequence")
    is_int = isinstance(raw_sequence, int) and not isinstance(raw_sequence, bool)
    sequence = raw_sequence if is_int else position
    coding = first_coding(item.get("productOrService"))

    serviced = parse_fhir_date(item.get("servicedDate"))
    if serviced is None and isinstance(item.get("servicedPeriod"), dict):
        serviced = parse_fhir_date(item["servicedPeriod"].get("start"))

    quantity_obj = item.get("quantity")
    quantity = to_decimal(quantity_obj.get("value")) if isinstance(quantity_obj, dict) else None

    amounts, statuses = _extract(item.get("adjudication"), f"line {sequence}", warnings)
    return EobLine(
        sequence=sequence,
        service_code=_text(coding.get("code")),
        service_code_system=_text(coding.get("system")),
        service_display=_text(coding.get("display")),
        service_date=serviced,
        quantity=quantity,
        amounts=amounts,
        statuses=statuses,
    )


def _claim_id(resource: dict[str, Any]) -> str | None:
    identifiers = resource.get("identifier")
    if not isinstance(identifiers, list):
        return None
    candidates = [i for i in identifiers if isinstance(i, dict) and i.get("value") is not None]
    for ident in candidates:
        if "uc" in all_codes(ident.get("type")):  # 'uc' = unique claim ID (CARIN code system)
            return str(ident["value"])
    return str(candidates[0]["value"]) if candidates else None


def parse_eob(resource: dict[str, Any]) -> EobSummary:
    if not isinstance(resource, dict) or resource.get("resourceType") != "ExplanationOfBenefit":
        raise EobParseError("Input is not an ExplanationOfBenefit resource.")

    raw_items = resource.get("item")
    items = [i for i in raw_items if isinstance(i, dict)] if isinstance(raw_items, list) else []
    if any("service" in i and "productOrService" not in i for i in items):
        raise EobParseError("This looks like an older FHIR (STU3) EOB. Only FHIR R4 EOBs are supported.")

    warnings: list[str] = []
    header_amounts, header_statuses = _extract(resource.get("adjudication"), "claim header", warnings)
    totals, _ = _extract(resource.get("total"), "claim totals", warnings)
    lines = [_parse_line(item, pos, warnings) for pos, item in enumerate(items, start=1)]

    period = resource.get("billablePeriod")
    period = period if isinstance(period, dict) else {}
    payment = resource.get("payment")

    return EobSummary(
        eob_id=str(resource.get("id") or "unknown"),
        claim_id=_claim_id(resource),
        claim_type=(all_codes(resource.get("type")) or [None])[0],
        claim_subtype=(all_codes(resource.get("subType")) or [None])[0],
        status=_text(resource.get("status")),
        outcome=_text(resource.get("outcome")),
        use=_text(resource.get("use")),
        billable_start=parse_fhir_date(period.get("start")),
        billable_end=parse_fhir_date(period.get("end")),
        insurer_display=reference_display(resource.get("insurer")),
        provider_display=reference_display(resource.get("provider")),
        header_amounts=header_amounts,
        header_statuses=header_statuses,
        totals=totals,
        payment_amount=_money_value(payment, "amount"),
        payment_adjustment=_money_value(payment, "adjustment"),
        lines=lines,
        parse_warnings=warnings,
    )
