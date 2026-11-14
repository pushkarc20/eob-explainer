"""LLM-as-judge scoring of explanations. Used only for evaluation, on synthetic or public data.

The judge sees placeholder text only (never real names or dates), and every request goes through the
leak guard. Known limits: the judge is a model too, so it can be lenient or inconsistent, and a judge
from the same family may favor similar writing. Treat scores as a screening signal and confirm with
human review.
"""
from dataclasses import dataclass

from pydantic import BaseModel, Field

from healthcore.llm.base import LLMClient, LLMError
from healthcore.llm.json_reply import extract_json_object
from healthcore.privacy.detector import PiiDetector
from healthcore.privacy.guard import LeakError, check_outbound
from healthcore.privacy.pseudonymizer import Pseudonymizer

JUDGE_PROMPT_VERSION = "j1"
JUDGE_MAX_TOKENS = 4000

JUDGE_SYSTEM = """You are a careful reviewer of plain-language explanations of a health insurance Explanation of Benefits (EOB).
You are given: (1) the structured facts the explanation was written from, as JSON; (2) the one key point a good explanation must convey; (3) the explanation to review. Placeholders such as [PROVIDER_1] stand for real names and are fine.

Score each criterion from 1 to 5 (5 is excellent):
- faithfulness: every statement is supported by the facts. Penalize any claim about causes, relationships or meanings that the facts do not support, even when each number is correct. 5 means nothing unsupported.
- key_point: conveys the key point clearly.
- clarity: plain language an average adult can follow; billing terms explained briefly where needed.
- tone: calm and non-accusatory; flags framed as questions; never says or implies a bill is wrong; gives no medical or legal advice; points to the insurer or billing office.
- concision: no padding. Penalize filler such as long lists of things the EOB does not state when they do not matter to this claim.

List each unsupported claim you find as a short string in unsupported_claims (an empty list if there are none).
Respond with ONLY a JSON object: {"faithfulness": int, "key_point": int, "clarity": int, "tone": int, "concision": int, "unsupported_claims": [string]}"""


class JudgeScores(BaseModel):
    faithfulness: int = Field(ge=1, le=5)
    key_point: int = Field(ge=1, le=5)
    clarity: int = Field(ge=1, le=5)
    tone: int = Field(ge=1, le=5)
    concision: int = Field(ge=1, le=5)
    unsupported_claims: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class JudgeResult:
    scores: JudgeScores | None
    error: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0


def parse_scores(text: str) -> JudgeScores | None:
    blob = extract_json_object(text)
    if blob is None:
        return None
    try:
        return JudgeScores.model_validate_json(blob)
    except ValueError:  # pydantic's ValidationError is a ValueError
        return None


def judge_explanation(
    client: LLMClient,
    pseudonymizer: Pseudonymizer,
    detector: PiiDetector,
    payload_json: str,
    key_point: str,
    explanation_text: str,
) -> JudgeResult:
    user = (
        f"Facts (JSON):\n{payload_json}\n\nKey point:\n{key_point}\n\n"
        f"Explanation to review:\n{explanation_text}"
    )
    try:
        check_outbound(JUDGE_SYSTEM + "\n" + user, pseudonymizer, detector)
    except LeakError:
        return JudgeResult(None, "leak_guard_blocked")
    try:
        reply = client.complete(JUDGE_SYSTEM, user, JUDGE_MAX_TOKENS)
    except LLMError as error:
        return JudgeResult(None, f"api_error: {error}")
    scores = parse_scores(reply.text)
    return JudgeResult(
        scores,
        None if scores else "unparseable",
        reply.input_tokens or 0,
        reply.output_tokens or 0,
    )
