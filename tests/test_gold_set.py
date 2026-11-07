from eob.evaluation import ROOT, evaluate_all, load_gold

FLAG_CODES = {
    "possible_duplicate_line",
    "high_patient_share",
    "unitemized_patient_amount",
    "noncovered_amount",
    "claim_has_reversals",
}


def test_gold_set_is_big_enough_and_ids_are_unique():
    cases = load_gold()["cases"]
    assert len(cases) >= 20
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids))


def test_every_case_file_exists():
    for case in load_gold()["cases"]:
        assert (ROOT / case["file"]).exists(), case["file"]


def test_every_flag_type_has_a_positive_example_and_there_are_negative_controls():
    cases = load_gold()["cases"]
    positives = {flag.split(":")[0] for case in cases for flag in case["expected"]["flags"]}
    assert positives == FLAG_CODES
    negatives = [case for case in cases if not case["expected"]["flags"]]
    assert len(negatives) >= 8


def test_canary_names_are_present_in_their_files_for_the_privacy_tests():
    with_canaries = [case for case in load_gold()["cases"] if case["canaries"]]
    assert len(with_canaries) >= 3
    for case in with_canaries:
        text = (ROOT / case["file"]).read_text(encoding="utf-8")
        for canary in case["canaries"]:
            assert canary in text


def test_the_gold_set_bans_the_overclaiming_words():
    banned = load_gold()["must_not_say"]
    assert "error" in banned
    assert "overcharg" in banned


def test_engine_matches_the_gold_set():
    results, summary = evaluate_all()
    problems = [f"{r.case_id}: {p}" for r in results for p in r.problems()]
    assert not problems, "\n" + "\n".join(problems)
    assert summary.money_accuracy == 1
    assert summary.flag_precision == 1
    assert summary.flag_recall == 1
