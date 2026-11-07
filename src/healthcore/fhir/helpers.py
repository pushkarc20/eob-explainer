"""Small, generic FHIR helpers. Nothing here is specific to ExplanationOfBenefit,
so the future prior-authorization project can reuse it unchanged."""
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


def load_resource(path: str | Path) -> dict[str, Any]:
    """Read a FHIR JSON file. Decimal numbers are kept as Decimal (never float),
    so money values stay exact."""
    with open(path, encoding="utf-8") as handle:
        return json.load(handle, parse_float=Decimal)


def to_decimal(value: Any) -> Decimal | None:
    """Convert a JSON number or numeric string to Decimal; None if it isn't a finite number."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def parse_fhir_date(value: Any) -> date | None:
    """Return a date for 'YYYY-MM-DD' or a dateTime that starts with one.
    Partial dates ('2019', '2019-07') and invalid values return None."""
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def first_coding(concept: Any) -> dict[str, Any]:
    """First coding of a CodeableConcept, or {} if there isn't one."""
    if isinstance(concept, dict):
        codings = concept.get("coding")
        if isinstance(codings, list) and codings and isinstance(codings[0], dict):
            return codings[0]
    return {}


def all_codes(concept: Any) -> list[str]:
    """Every 'code' in a CodeableConcept's codings, in order."""
    if not isinstance(concept, dict):
        return []
    codings = concept.get("coding")
    if not isinstance(codings, list):
        return []
    return [str(c["code"]) for c in codings if isinstance(c, dict) and c.get("code") is not None]


def reference_display(reference: Any) -> str | None:
    """The human-readable 'display' text of a FHIR Reference, if present."""
    if isinstance(reference, dict):
        display = reference.get("display")
        if isinstance(display, str) and display:
            return display
    return None
