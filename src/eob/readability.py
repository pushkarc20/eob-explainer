"""Reading-level estimate (Flesch-Kincaid grade) for the prose of an explanation.

A simple heuristic syllable counter, so there is no extra dependency. Absolute values are approximate:
use it to compare systems, not as a precise grade. Numbers and dollar amounts are removed first.
"""
import re

from eob.explanation import Explanation

_WORD = re.compile(r"[A-Za-z][A-Za-z'\u2019-]*")
_NUMBER = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")
_SENTENCE_END = re.compile(r"[.!?]+(?:\s|$)")


def count_syllables(word: str) -> int:
    letters = re.sub(r"[^a-z]", "", word.lower())
    if not letters:
        return 0
    count = len(re.findall(r"[aeiouy]+", letters))
    if count > 1 and letters.endswith("e") and not letters.endswith(("le", "ee")):
        count -= 1  # silent final e, as in "service"
    if count > 1 and letters.endswith("ed") and not letters.endswith(("ted", "ded")):
        count -= 1  # silent -ed, as in "billed"
    return max(count, 1)


def flesch_kincaid_grade(text: str) -> float | None:
    cleaned = _NUMBER.sub(" ", text)
    words = _WORD.findall(cleaned)
    sentences = [part for part in _SENTENCE_END.split(cleaned) if _WORD.search(part)]
    if not words or not sentences:
        return None
    syllables = sum(count_syllables(word) for word in words)
    return 0.39 * len(words) / len(sentences) + 11.8 * syllables / len(words) - 15.59


def _end(text: str) -> str:
    text = text.strip()
    return text if text.endswith((".", "!", "?")) else text + "."


def prose_text(explanation: Explanation) -> str:
    """Just the sentences (no labels, amounts or the fixed disclaimer), for readability scoring."""
    parts = [explanation.what_happened]
    parts += [point.explanation for point in explanation.money_points]
    for note in explanation.flag_notes:
        parts += [note.explanation, note.question]
    parts += explanation.not_reported
    parts.append(explanation.next_steps)
    return " ".join(_end(part) for part in parts if part and part.strip())
