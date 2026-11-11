"""Last line of defense: fail closed if sensitive content is still in text about to leave the device."""
import re

from healthcore.privacy.detector import HARD_ENTITIES, PiiDetector
from healthcore.privacy.pseudonymizer import Pseudonymizer


class LeakError(RuntimeError):
    """Raised when outbound text still contains sensitive content.

    The message describes what was found by count and type only, never the content itself.
    """


def _count_known(text: str, values: set[str]) -> int:
    return sum(
        1
        for value in values
        if re.search(rf"(?<!\w){re.escape(value)}(?!\w)", text, flags=re.IGNORECASE)
    )


def check_outbound(text: str, pseudonymizer: Pseudonymizer, detector: PiiDetector) -> None:
    problems: list[str] = []
    known = _count_known(text, pseudonymizer.sensitive_values())
    if known:
        problems.append(f"{known} known sensitive value(s) from the source document are still present")
    hard = detector.find(text, entities=HARD_ENTITIES)
    if hard:
        kinds = sorted({finding.entity_type for finding in hard})
        problems.append(f"identifier-like content detected ({', '.join(kinds)})")
    if problems:
        raise LeakError("Blocked: " + "; ".join(problems) + ". Nothing was sent.")
