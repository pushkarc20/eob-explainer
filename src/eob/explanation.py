"""The structured explanation: the same shape whether a model or the fallback template wrote it."""
from collections.abc import Callable

from pydantic import BaseModel, Field


class MoneyPoint(BaseModel):
    label: str
    amount: str | None = None
    explanation: str


class FlagNote(BaseModel):
    flag_code: str
    explanation: str
    question: str


class Explanation(BaseModel):
    what_happened: str
    money_points: list[MoneyPoint] = Field(default_factory=list)
    flag_notes: list[FlagNote] = Field(default_factory=list)
    not_reported: list[str] = Field(default_factory=list)
    next_steps: str


def all_text(explanation: Explanation) -> str:
    parts = [explanation.what_happened, explanation.next_steps]
    for point in explanation.money_points:
        parts += [point.label, point.amount or "", point.explanation]
    for note in explanation.flag_notes:
        parts += [note.flag_code, note.explanation, note.question]
    parts += explanation.not_reported
    return "\n".join(parts)


def map_strings(explanation: Explanation, fn: Callable[[str], str]) -> Explanation:
    """Apply `fn` to every human-readable string (used to restore real values locally)."""
    return Explanation(
        what_happened=fn(explanation.what_happened),
        money_points=[
            MoneyPoint(
                label=fn(point.label),
                amount=None if point.amount is None else fn(point.amount),
                explanation=fn(point.explanation),
            )
            for point in explanation.money_points
        ],
        flag_notes=[
            FlagNote(flag_code=note.flag_code, explanation=fn(note.explanation), question=fn(note.question))
            for note in explanation.flag_notes
        ],
        not_reported=[fn(item) for item in explanation.not_reported],
        next_steps=fn(explanation.next_steps),
    )


def render_text(explanation: Explanation, disclaimer: str) -> str:
    lines = ["WHAT HAPPENED", explanation.what_happened, "", "THE MONEY"]
    for point in explanation.money_points:
        lines.append(f"  {point.label}: {point.amount or 'not stated'}")
        lines.append(f"      {point.explanation}")
    if explanation.flag_notes:
        lines += ["", "WORTH ASKING ABOUT"]
        for note in explanation.flag_notes:
            lines.append(f"  - {note.explanation}")
            lines.append(f"      Question to ask: {note.question}")
    if explanation.not_reported:
        lines += ["", "NOT STATED ON THIS EOB"]
        lines += [f"  - {item}" for item in explanation.not_reported]
    lines += ["", "NEXT STEPS", explanation.next_steps, "", disclaimer]
    return "\n".join(lines)
