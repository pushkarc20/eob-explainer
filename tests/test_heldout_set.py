import hashlib

from eob.evaluation import ROOT, load_gold

HELDOUT = ROOT / "fixtures" / "heldout"
FLAG_CODES = {
    "possible_duplicate_line",
    "high_patient_share",
    "unitemized_patient_amount",
    "noncovered_amount",
    "claim_has_reversals",
}


def heldout() -> dict:
    return load_gold(HELDOUT / "gold.json")


def test_fifteen_unique_cases_with_files_and_no_reuse_of_development_ids():
    cases = heldout()["cases"]
    ids = [case["id"] for case in cases]
    assert len(cases) == 15 and len(set(ids)) == 15
    assert all(case_id.startswith("ho_") for case_id in ids)
    assert not {case["id"] for case in load_gold()["cases"]} & set(ids)
    for case in cases:
        assert (ROOT / case["file"]).exists(), case["file"]


def test_every_flag_type_appears_and_there_are_clean_cases():
    cases = heldout()["cases"]
    flags = {flag.split(":")[0] for case in cases for flag in case["expected"]["flags"]}
    assert flags == FLAG_CODES
    assert sum(1 for case in cases if not case["expected"]["flags"]) >= 9


def test_planted_names_are_in_their_files_for_the_privacy_audit():
    with_canaries = [case for case in heldout()["cases"] if case["canaries"]]
    assert len(with_canaries) >= 3
    for case in with_canaries:
        text = (ROOT / case["file"]).read_text(encoding="utf-8")
        for canary in case["canaries"]:
            assert canary in text


def test_the_gold_answers_are_frozen():
    recorded = (HELDOUT / "gold.sha256").read_text().strip()
    actual = hashlib.sha256((HELDOUT / "gold.json").read_bytes()).hexdigest()
    assert actual == recorded, "gold.json changed after it was frozen; the plan forbids tuning against it"