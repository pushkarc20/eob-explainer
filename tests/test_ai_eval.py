import json

import pytest
from support import FakeClient, gold_case, good_reply, prepare_case

from eob.ai_eval import (
    CONFIGS,
    assert_fixture,
    count_leaks,
    format_report,
    run_case,
    summarize,
)
from eob.evaluation import load_gold

JUDGE_REPLY = json.dumps(
    {"faithfulness": 5, "key_point": 4, "clarity": 4, "tone": 5, "concision": 3, "unsupported_claims": []}
)


def test_the_template_system_is_clean_on_the_whole_gold_set(detector):
    gold = load_gold()
    for case in gold["cases"]:
        run = run_case(case, CONFIGS["template"], None, None, detector, gold["must_not_say"])
        assert run.source == "template", case["id"]
        assert run.money_shown == run.money_expected, case["id"]
        assert run.violations == [], case["id"]
        assert run.grade is not None, case["id"]
        assert (run.requests_sent, run.leaks) == (0, 0), case["id"]


def test_an_ai_system_is_measured_audited_and_costed(detector):
    gold = load_gold()
    case = gold_case("syn_duplicate_same_day")
    payload, _ = prepare_case(case["id"], detector)
    client = FakeClient([good_reply(payload)])
    run = run_case(case, CONFIGS["sonnet-medium-v1"], client, None, detector, gold["must_not_say"])
    assert (run.source, run.attempts) == ("ai", 1)
    assert (run.requests_sent, run.leaks) == (1, 0)
    assert (run.input_tokens, run.output_tokens) == (100, 50)
    assert run.cost == pytest.approx(0.0007)  # 100 x $2/M + 50 x $10/M
    assert run.money_shown == run.money_expected
    assert "Dr. Alicia Moreno Family Medicine" in run.text  # restored for the user
    assert run.judge is None


def test_the_judge_scores_are_recorded_and_it_never_sees_real_names(detector):
    gold = load_gold()
    case = gold_case("syn_duplicate_same_day")
    payload, _ = prepare_case(case["id"], detector)
    judge = FakeClient([JUDGE_REPLY])
    run = run_case(
        case, CONFIGS["sonnet-medium-v1"], FakeClient([good_reply(payload)]), judge, detector, gold["must_not_say"]
    )
    assert run.judge["faithfulness"] == 5
    assert len(judge.calls) == 1
    assert "alicia" not in judge.calls[0][1].lower()
    assert run.requests_sent == 2 and run.leaks == 0
    assert (run.judge_input_tokens, run.judge_output_tokens) == (100, 50)


def test_only_fixture_files_may_be_evaluated():
    assert_fixture("fixtures/synthetic/syn_clean_copay_visit.json")
    for path in ("data/raw/BBUser00001/x.json", "/Users/someone/real.json", "../outside.json"):
        with pytest.raises(ValueError):
            assert_fixture(path)


def test_leak_counting_finds_planted_values_case_insensitively():
    requests = ["billed by [PROVIDER_1]", "note: ALICIA MORENO called"]
    assert count_leaks(requests, ["Alicia Moreno", "Priya Raman"]) == 1
    assert count_leaks(requests, ["xy"]) == 0  # too short to audit


def fake_run(**changes):
    run = {
        "case_id": "c", "config": "x", "source": "ai", "attempts": 1, "problems": [], "text": "t",
        "input_tokens": 1000, "output_tokens": 500, "cost": 0.01, "seconds": 10.0,
        "money_expected": 4, "money_shown": 4, "violations": [], "grade": 8.0,
        "requests_sent": 2, "leaks": 0, "judge_error": None, "judge_input_tokens": 0, "judge_output_tokens": 0,
        "judge": {"faithfulness": 5, "key_point": 5, "clarity": 5, "tone": 5, "concision": 5, "unsupported_claims": []},
    }
    run.update(changes)
    return run


def make_run_file():
    judge3 = {"faithfulness": 3, "key_point": 4, "clarity": 4, "tone": 5, "concision": 2, "unsupported_claims": ["a", "b"]}
    runs = [
        fake_run(grade=6.0),
        fake_run(attempts=2, money_shown=3, grade=8.0, judge=judge3),
        fake_run(source="template", attempts=2, problems=["not_valid_json"], violations=["error"], grade=10.0, judge=None),
    ]
    return {
        "config": "x", "kind": "claude", "model": "claude-sonnet-5-5", "effort": "medium",
        "prompt_version": "v1", "judge_model": "claude-sonnet-5-5", "runs": runs,
    }


def test_summaries_count_retries_fallbacks_and_means():
    summary = summarize(make_run_file())
    assert (summary["first_try"], summary["after_retry"], summary["fell_back"]) == (1, 1, 1)
    assert (summary["expected"], summary["shown"]) == (12, 11)
    assert summary["violation_cases"] == 1
    assert summary["grade"] == pytest.approx(8.0)
    assert summary["judged"] == 2
    assert summary["judge"]["faithfulness"] == pytest.approx(4.0)
    assert summary["unsupported"] == 2
    assert summary["requests"] == 6 and summary["leaks"] == 0
    assert summary["cost_mean"] == pytest.approx(0.01)
    assert summary["reasons"] == {"not_valid_json": 1}


def test_the_report_has_a_table_review_notes_and_caveats():
    report = format_report([make_run_file()])
    assert "| Metric | x |" in report
    assert "| Prompt version | v1 |" in report
    assert "Why x answers were rejected: not_valid_json x1." in report
    assert "## Cases to review" in report
    assert "judge faithfulness 3" in report
    assert "fell back to the built-in explanation" in report
    assert "Judge caveat" in report


def test_an_empty_report_says_there_are_no_runs_yet():
    assert "No runs yet" in format_report([])
