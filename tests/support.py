"""Helpers shared by the explainer tests: a fake model and a builder for valid answers."""
import json
from decimal import Decimal

from eob.engine import analyze
from eob.evaluation import ROOT, load_gold
from eob.parser import parse_eob
from eob.privacy import CloudPayload, collect_blocked_values, prepare_cloud_payload
from healthcore.fhir.helpers import load_resource
from healthcore.llm.base import LLMResult
from healthcore.privacy.pseudonymizer import Pseudonymizer


def gold_case(case_id: str) -> dict:
    return next(case for case in load_gold()["cases"] if case["id"] == case_id)


def load_case(case_id: str):
    raw = load_resource(ROOT / gold_case(case_id)["file"])
    eob = parse_eob(raw)
    return eob, analyze(eob), collect_blocked_values(raw)


def prepare_case(case_id: str, detector):
    eob, analysis, blocked = load_case(case_id)
    pseudonymizer = Pseudonymizer()
    prepared = prepare_cloud_payload(eob, analysis, pseudonymizer, detector, blocked)
    return prepared.payload, pseudonymizer


def good_reply(payload: CloudPayload) -> str:
    """A valid model answer built from the payload (placeholders included)."""
    points = []
    for name in ("billed", "allowed", "plan_paid", "patient_responsibility"):
        amount = payload.money[name]["amount"]
        if amount is not None:
            points.append({
                "label": name,
                "amount": f"${Decimal(amount):,.2f}",
                "explanation": "This comes from the claim data.",
            })
    notes = []
    for code in sorted({flag.code for flag in payload.flags}):
        detail = next(flag.detail for flag in payload.flags if flag.code == code)
        notes.append({"flag_code": code, "explanation": detail, "question": "Can you explain this item?"})
    provider = payload.provider or "your provider"
    return json.dumps({
        "what_happened": f"This claim was billed by {provider} for services on the dates shown.",
        "money_points": points,
        "flag_notes": notes,
        "not_reported": [],
        "next_steps": "Contact your insurer or the provider's billing office with any questions.",
    })


class FakeClient:
    """Stands in for a model. Records every request so tests can audit what would have been sent."""

    name = "cloud"

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str, max_tokens: int) -> LLMResult:
        self.calls.append((system, user))
        return LLMResult(text=self._replies.pop(0), model="fake-model", input_tokens=100, output_tokens=50)
