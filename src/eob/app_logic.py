"""The logic behind the web app, with no Streamlit in it, so it can be tested without a browser.

Everything works on in-memory objects: nothing here writes to disk or logs document content.
Cloud mode runs only when the caller asks for it, and only if the payload being sent is exactly the
one the user was shown.
"""
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from eob.drafter import Draft, MemberDetails, draft_message
from eob.engine import Analysis, analyze
from eob.evaluation import ROOT, load_gold
from eob.explainer import ExplainResult, explain
from eob.explanation import Explanation
from eob.models import EobSummary
from eob.money import fmt_money
from eob.parser import EobParseError, parse_eob
from eob.privacy import PreparedPayload, collect_blocked_values, prepare_cloud_payload
from eob.settings import MissingKeyError, load_cloud_settings
from eob.templates import template_explanation
from healthcore.llm.anthropic_client import AnthropicClient
from healthcore.llm.base import LLMClient
from healthcore.privacy.detector import PiiDetector, default_detector
from healthcore.privacy.pseudonymizer import Pseudonymizer

MAX_UPLOAD_BYTES = 1_000_000
FIXTURES = ROOT / "fixtures"


class DocumentError(ValueError):
    """The file could not be used. The message is safe to show: it never contains file content."""


@dataclass(frozen=True)
class LoadedClaim:
    """Everything the app keeps about a loaded claim. The raw file is deliberately not kept."""

    label: str
    eob: EobSummary
    analysis: Analysis
    template: Explanation
    blocked_values: tuple[str, ...]


def _single_eob(document: object) -> dict:
    if isinstance(document, dict) and document.get("resourceType") == "Bundle":
        found = [
            entry["resource"]
            for entry in document.get("entry") or []
            if isinstance(entry, dict)
            and isinstance(entry.get("resource"), dict)
            and entry["resource"].get("resourceType") == "ExplanationOfBenefit"
        ]
        if len(found) != 1:
            raise DocumentError(
                f"This file is a Bundle with {len(found)} ExplanationOfBenefit resources. Please provide exactly one."
            )
        return found[0]
    if isinstance(document, dict):
        return document
    raise DocumentError("This file is not a FHIR resource.")


def load_claim_from_bytes(data: bytes, label: str) -> LoadedClaim:
    if len(data) > MAX_UPLOAD_BYTES:
        raise DocumentError("That file is larger than 1 MB. An EOB should be much smaller.")
    try:
        document = json.loads(data, parse_float=Decimal)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise DocumentError("That file is not valid JSON.") from None
    raw = _single_eob(document)
    try:
        eob = parse_eob(raw)
    except EobParseError as error:
        raise DocumentError(str(error)) from None
    except ValueError:  # never show str(error): validation messages can echo file content
        raise DocumentError("The file looks like an EOB, but its structure is not one this tool can read.") from None
    analysis = analyze(eob)
    return LoadedClaim(label, eob, analysis, template_explanation(eob, analysis), tuple(collect_blocked_values(raw)))


def load_claim_from_path(path: Path, label: str) -> LoadedClaim:
    try:
        path.resolve().relative_to(FIXTURES)
    except ValueError:
        raise DocumentError("Sample claims must come from the fixtures folder.") from None
    return load_claim_from_bytes(path.read_bytes(), label)


def list_samples() -> dict[str, Path]:
    return {f"{case['id']}: {case['story']}": ROOT / case["file"] for case in load_gold()["cases"]}


def headline_figures(claim: LoadedClaim) -> list[tuple[str, str]]:
    money = claim.analysis.money
    rows = (
        ("Billed", money.billed),
        ("Allowed", money.allowed),
        ("Plan paid", money.plan_paid),
        ("You owe", money.patient_responsibility),
    )
    return [(label, "Not stated" if fig.value is None else fmt_money(fig.value)) for label, fig in rows]


def make_draft(claim: LoadedClaim, name: str, member_id: str) -> Draft:
    return draft_message(claim.eob, claim.analysis, MemberDetails(name=name.strip(), member_id=member_id.strip()))


def cloud_status() -> tuple[bool, str]:
    try:
        settings = load_cloud_settings()
    except MissingKeyError as error:
        return False, str(error)
    effort = settings.effort or "model default"
    return True, f"Model: {settings.model} (effort: {effort})"


def make_cloud_client() -> LLMClient:
    settings = load_cloud_settings()
    return AnthropicClient(settings.model, settings.effort)


def preview_payload(
    claim: LoadedClaim, pseudonymizer: Pseudonymizer, detector: PiiDetector | None = None
) -> PreparedPayload:
    """The exact payload that cloud mode would send. Raises LeakError if it cannot be made safe."""
    return prepare_cloud_payload(
        claim.eob, claim.analysis, pseudonymizer, detector or default_detector(), claim.blocked_values
    )


def run_cloud(
    claim: LoadedClaim,
    client: LLMClient,
    pseudonymizer: Pseudonymizer,
    approved_json: str,
    detector: PiiDetector | None = None,
) -> ExplainResult:
    """Ask the model, but only if the payload built now is exactly the one the user approved."""

    def same_as_approved(prepared: PreparedPayload) -> bool:
        return prepared.json_text == approved_json

    return explain(
        claim.eob,
        claim.analysis,
        client,
        pseudonymizer,
        detector or default_detector(),
        claim.blocked_values,
        confirm=same_as_approved,
    )


def describe_fallback(result: ExplainResult) -> str:
    codes = set(result.problems)
    if "leak_guard_blocked" in codes:
        return "the safety check blocked the request, so nothing was sent."
    if "declined_by_user" in codes:
        return "what would be sent no longer matched what you reviewed, so nothing was sent."
    if "api_error" in codes:
        return f"the request to Claude failed ({result.error})."
    if codes:
        return "the answer did not pass verification (" + ", ".join(sorted(codes)) + ")."
    return "no AI answer was available."
