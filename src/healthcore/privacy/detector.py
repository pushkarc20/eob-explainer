"""Local PII detection with Microsoft Presidio. Runs entirely on this machine.

Presidio finds spans of likely PII in free text. This is the SECOND line of defense: the first is
the allow-list model, which never carries identifiers in the first place.
"""
from collections.abc import Sequence
from dataclasses import dataclass

import spacy
from presidio_analyzer import (
    AnalyzerEngine,
    Pattern,
    PatternRecognizer,
    RecognizerRegistry,
)
from presidio_analyzer.nlp_engine import NlpEngineProvider

from healthcore.privacy.pseudonymizer import PLACEHOLDER_PATTERN, Pseudonymizer

DEFAULT_MODEL = "en_core_web_sm"

# Pattern/checksum-based identifiers. These are precise, so the leak guard blocks on any hit.
HARD_ENTITIES = [
    "US_SSN", "US_MBI", "EMAIL_ADDRESS", "PHONE_NUMBER", "US_NPI", "ID_LIKE", "CREDIT_CARD", "FULL_DATE",
]
# Scrubbing free text also uses the statistical NER model for people and places.
# DATE_TIME is deliberately excluded (it tags durations like "each 15 minutes"); FULL_DATE covers real dates.
SCRUB_ENTITIES = ["PERSON", "LOCATION", *HARD_ENTITIES]

KIND_FOR_ENTITY = {
    "PERSON": "PERSON", "LOCATION": "PLACE", "US_SSN": "SSN", "US_MBI": "MEMBER_ID",
    "EMAIL_ADDRESS": "EMAIL", "PHONE_NUMBER": "PHONE", "US_NPI": "PROVIDER_ID",
    "ID_LIKE": "ID", "CREDIT_CARD": "CARD", "FULL_DATE": "DATE",
}

# Medicare Beneficiary Identifier: 11 characters; letters never include S, L, O, I, B, Z.
_L = "[AC-HJKMNP-RT-Y]"
_LN = "[AC-HJKMNP-RT-Y0-9]"
MBI_REGEX = rf"\b[1-9]{_L}{_LN}[0-9]-?{_L}{_LN}[0-9]-?{_L}{_L}[0-9]{{2}}\b"
NPI_REGEX = r"\b\d{10}\b"
LONG_DIGITS_REGEX = r"\b\d{9,}\b"
MIXED_ID_REGEX = r"\b(?=[A-Za-z0-9-]*\d)(?=[A-Za-z0-9-]*[A-Za-z])[A-Za-z0-9-]{12,}\b"
_MONTHS = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
DATE_REGEXES = [
    r"\b\d{4}-\d{2}-\d{2}\b",
    r"\b\d{1,2}/\d{1,2}/(?:\d{4}|\d{2})\b",
    rf"\b{_MONTHS} \d{{1,2}},? \d{{4}}\b",
]


@dataclass(frozen=True)
class Finding:
    """A detected span. Deliberately holds no text, so findings are safe to print or log."""

    entity_type: str
    start: int
    end: int
    score: float


def _merge(findings: list[Finding]) -> list[Finding]:
    """Drop overlaps: earliest, longest, highest-scoring span wins."""
    kept: list[Finding] = []
    for finding in sorted(findings, key=lambda f: (f.start, -(f.end - f.start), -f.score)):
        if kept and finding.start < kept[-1].end:
            continue
        kept.append(finding)
    return kept


class PiiDetector:
    def __init__(self, model: str = DEFAULT_MODEL, threshold: float = 0.4) -> None:
        self._model = model
        self._threshold = threshold
        self._analyzer: AnalyzerEngine | None = None

    def _engine(self) -> AnalyzerEngine:
        if self._analyzer is not None:
            return self._analyzer
        # Check first so Presidio never downloads anything on its own while processing a document.
        if not spacy.util.is_package(self._model):
            raise RuntimeError(
                f"The spaCy model '{self._model}' is not installed. "
                f"Run: python -m spacy download {self._model}"
            )
        nlp_engine = NlpEngineProvider(nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": self._model}],
        }).create_engine()
        registry = RecognizerRegistry(supported_languages=["en"])
        registry.load_predefined_recognizers(languages=["en"], nlp_engine=nlp_engine)
        registry.add_recognizer(PatternRecognizer(
            supported_entity="US_MBI", supported_language="en",
            patterns=[Pattern("mbi", MBI_REGEX, 0.85)],
        ))
        registry.add_recognizer(PatternRecognizer(
            supported_entity="US_NPI", supported_language="en",
            patterns=[Pattern("npi", NPI_REGEX, 0.4)], context=["npi", "national provider"],
        ))
        registry.add_recognizer(PatternRecognizer(
            supported_entity="ID_LIKE", supported_language="en",
            patterns=[Pattern("long_digits", LONG_DIGITS_REGEX, 0.5), Pattern("mixed_id", MIXED_ID_REGEX, 0.5)],
        ))
        registry.add_recognizer(PatternRecognizer(
            supported_entity="FULL_DATE", supported_language="en",
            patterns=[Pattern(f"date_{i}", regex, 0.8) for i, regex in enumerate(DATE_REGEXES)],
        ))
        self._analyzer = AnalyzerEngine(
            nlp_engine=nlp_engine, registry=registry, supported_languages=["en"]
        )
        return self._analyzer

    def find(self, text: str, entities: Sequence[str] | None = None) -> list[Finding]:
        if not text.strip():
            return []
        results = self._engine().analyze(
            text=text,
            language="en",
            entities=list(entities or SCRUB_ENTITIES),
            score_threshold=self._threshold,
        )
        return _merge([Finding(r.entity_type, r.start, r.end, r.score) for r in results])


_default: PiiDetector | None = None


def default_detector() -> PiiDetector:
    global _default
    if _default is None:
        _default = PiiDetector()
    return _default


def scrub_text(text: str, detector: PiiDetector, pseudonymizer: Pseudonymizer) -> tuple[str, dict[str, int]]:
    """Replace known values, then anything Presidio finds, with placeholders.

    Returns the scrubbed text and a count per entity TYPE (never the values themselves).
    """
    text = pseudonymizer.apply(text)
    protected = [(m.start(), m.end()) for m in PLACEHOLDER_PATTERN.finditer(text)]
    findings = [
        finding for finding in detector.find(text)
        if not any(finding.start < end and start < finding.end for start, end in protected)
    ]
    # Register in reading order so numbering is natural, then substitute from the end so offsets stay valid.
    planned = [
        (finding, pseudonymizer.register(KIND_FOR_ENTITY.get(finding.entity_type, "REDACTED"),
                                         text[finding.start:finding.end]))
        for finding in findings
    ]
    counts: dict[str, int] = {}
    for finding, placeholder in reversed(planned):
        text = text[:finding.start] + placeholder + text[finding.end:]
        counts[finding.entity_type] = counts.get(finding.entity_type, 0) + 1
    return text, counts
