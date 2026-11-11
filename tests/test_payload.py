import json
import re
from datetime import date, timedelta
from decimal import Decimal

from eob.engine import analyze
from eob.evaluation import ROOT, load_gold
from eob.models import AmountSet, EobLine, EobSummary
from eob.parser import parse_eob
from eob.privacy import collect_blocked_values, prepare_cloud_payload
from healthcore.fhir.helpers import load_resource
from healthcore.privacy.pseudonymizer import Pseudonymizer

ALLOWED_TOP_LEVEL_KEYS = {
    "claim_type", "claim_subtype", "provider", "insurer", "money", "lines",
    "lines_omitted", "flags", "check_notes", "parse_warning_count",
}
ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
MONTH_DATE = re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2}, \d{4}\b")


def prepare(case, detector):
    raw = load_resource(ROOT / case["file"])
    eob = parse_eob(raw)
    ps = Pseudonymizer()
    prepared = prepare_cloud_payload(
        eob, analyze(eob), ps, detector, blocked_values=collect_blocked_values(raw)
    )
    return raw, prepared, ps


def test_every_gold_case_passes_the_leak_guard(detector):
    for case in load_gold()["cases"]:
        prepare(case, detector)  # raises LeakError if anything sensitive remains (or on a false block)


def test_the_payload_has_only_the_allowed_top_level_fields(detector):
    for case in load_gold()["cases"]:
        _, prepared, _ = prepare(case, detector)
        assert set(json.loads(prepared.json_text)) == ALLOWED_TOP_LEVEL_KEYS, case["id"]


def test_canary_names_never_appear_but_their_placeholder_does(detector):
    checked = 0
    for case in load_gold()["cases"]:
        if not case["canaries"]:
            continue
        _, prepared, _ = prepare(case, detector)
        for canary in case["canaries"]:
            assert canary.lower() not in prepared.json_text.lower(), case["id"]
        assert '"provider":"[PROVIDER_1]"' in prepared.json_text
        checked += 1
    assert checked >= 3


def test_no_identifier_from_the_source_document_survives(detector):
    for case in load_gold()["cases"]:
        raw, prepared, _ = prepare(case, detector)
        text = prepared.json_text.lower()
        for value in collect_blocked_values(raw):
            assert value.lower() not in text, f"{case['id']}: a source identifier leaked"


def test_dates_are_replaced_by_placeholders(detector):
    for case in load_gold()["cases"]:
        _, prepared, _ = prepare(case, detector)
        assert not ISO_DATE.search(prepared.json_text), case["id"]
        assert not MONTH_DATE.search(prepared.json_text), case["id"]
        assert "[DATE_1]" in prepared.json_text, case["id"]


def test_money_figures_survive_redaction(detector):
    for case in load_gold()["cases"]:
        _, prepared, _ = prepare(case, detector)
        for name, value in case["expected"]["money"].items():
            if value is not None:
                assert f"{Decimal(value):.2f}" in prepared.json_text, f"{case['id']}: {name}"


def test_code_descriptions_are_not_mangled_by_the_scan(detector):
    case = next(c for c in load_gold()["cases"] if c["id"] == "carin_professional1")
    _, prepared, _ = prepare(case, detector)
    assert "Therapeutic procedure" in prepared.json_text
    assert prepared.scrub_counts == {}


def test_placeholders_restore_to_real_values_locally(detector):
    case = next(c for c in load_gold()["cases"] if c["id"] == "syn_duplicate_same_day")
    _, prepared, ps = prepare(case, detector)
    assert ps.restore("Ask [PROVIDER_1].") == "Ask Dr. Alicia Moreno Family Medicine."
    flag_text = prepared.payload.flags[0].detail
    assert "[DATE_1]" in flag_text
    restored = ps.restore(flag_text)
    assert "Mar 5, 2024" in restored
    assert "[DATE_" not in restored


def test_long_claims_are_truncated_and_say_so(detector):
    lines = [
        EobLine(
            sequence=n, service_code="99213", service_date=date(2024, 3, 1) + timedelta(days=n),
            amounts=AmountSet(submitted=Decimal(10 + n)),
        )
        for n in range(1, 61)
    ]
    eob = EobSummary(eob_id="long", lines=lines)
    prepared = prepare_cloud_payload(eob, analyze(eob), Pseudonymizer(), detector)
    assert len(prepared.payload.lines) == 40
    assert prepared.payload.lines_omitted == 20
