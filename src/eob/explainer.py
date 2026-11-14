"""Orchestrates one explanation: build the safe payload, ask the model, verify the answer, and
restore real values locally.

If the answer fails verification twice, the API fails, the user declines, or the leak guard blocks a
request, the user still gets a correct (plainer) explanation from the rules engine. The AI is an
enhancement, never a dependency.
"""
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal

from eob.engine import Analysis
from eob.explanation import Explanation, map_strings
from eob.models import EobSummary
from eob.privacy import CloudPayload, PreparedPayload, prepare_cloud_payload
from eob.prompts import DEFAULT_PROMPT_VERSION, build_user_message, get_system_prompt
from eob.templates import template_explanation
from eob.validate import Problem, validate_explanation
from healthcore.llm.base import LLMClient, LLMError
from healthcore.llm.json_reply import extract_json_object
from healthcore.privacy.detector import PiiDetector, default_detector
from healthcore.privacy.guard import LeakError, check_outbound
from healthcore.privacy.pseudonymizer import Pseudonymizer

MAX_ATTEMPTS = 2
# Claude Sonnet 5.5 thinks by default and thinking counts toward max_tokens, so leave generous room.
MAX_TOKENS = 6000


@dataclass(frozen=True)
class ExplainResult:
    explanation: Explanation
    source: Literal["ai", "template"]
    attempts: int = 0
    problems: tuple[str, ...] = ()  # problem codes, or "leak_guard_blocked" / "declined_by_user" / "api_error"
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None
    placeholder_explanation: Explanation | None = None  # the verified answer before real values were restored


def _parse(text: str) -> Explanation | None:
    blob = extract_json_object(text)
    if blob is None:
        return None
    try:
        return Explanation.model_validate_json(blob)
    except ValueError:  # pydantic's ValidationError is a ValueError
        return None


def _check(
    text: str, payload: CloudPayload, pseudonymizer: Pseudonymizer, detector: PiiDetector
) -> tuple[Explanation | None, list[Problem]]:
    explanation = _parse(text)
    if explanation is None:
        return None, [Problem("not_valid_json", "Respond with only the JSON object described, including every key.")]
    return explanation, validate_explanation(explanation, payload, pseudonymizer, detector)


def explain(
    eob: EobSummary,
    analysis: Analysis,
    client: LLMClient,
    pseudonymizer: Pseudonymizer,
    detector: PiiDetector | None = None,
    blocked_values: Iterable[str] = (),
    confirm: Callable[[PreparedPayload], bool] | None = None,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
) -> ExplainResult:
    """`confirm` receives the exact payload that will be sent; returning False cancels before any request."""
    detector = detector or default_detector()
    system_prompt = get_system_prompt(prompt_version)
    fallback = template_explanation(eob, analysis)
    try:
        prepared = prepare_cloud_payload(eob, analysis, pseudonymizer, detector, blocked_values)
    except LeakError:
        return ExplainResult(fallback, "template", 0, ("leak_guard_blocked",))
    if confirm is not None and not confirm(prepared):
        return ExplainResult(fallback, "template", 0, ("declined_by_user",))

    user = build_user_message(prepared.json_text)
    attempts = input_tokens = output_tokens = 0
    model: str | None = None
    codes: tuple[str, ...] = ()

    for _ in range(MAX_ATTEMPTS):
        try:
            check_outbound(system_prompt + "\n" + user, pseudonymizer, detector)
        except LeakError:
            codes = ("leak_guard_blocked",)
            break
        attempts += 1
        try:
            result = client.complete(system=system_prompt, user=user, max_tokens=MAX_TOKENS)
        except LLMError as error:
            return ExplainResult(
                fallback, "template", attempts, ("api_error",), model, input_tokens, output_tokens, str(error)
            )
        model = result.model
        input_tokens += result.input_tokens or 0
        output_tokens += result.output_tokens or 0

        explanation, problems = _check(result.text, prepared.payload, pseudonymizer, detector)
        if explanation is not None and not problems:
            restored = map_strings(explanation, pseudonymizer.restore)
            return ExplainResult(
                restored, "ai", attempts, (), model, input_tokens, output_tokens, None, explanation
            )
        codes = tuple(problem.code for problem in problems)
        user = build_user_message(prepared.json_text, feedback=[problem.message for problem in problems])

    return ExplainResult(fallback, "template", attempts, codes, model, input_tokens, output_tokens)
