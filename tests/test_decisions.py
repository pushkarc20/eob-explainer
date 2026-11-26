import json

import pytest

from eob.decisions import (
    build_decisions,
    check_judge_version,
    outcome_a,
    rule_a,
    rule_b,
)


def fake_runs(n, faithfulness=4, key_point=4, concision=4, first_try=None, cost=0.01):
    first_try = n if first_try is None else first_try
    return [
        {
            "case_id": f"c{i}", "config": "x", "source": "ai", "attempts": 1 if i < first_try else 2,
            "problems": [], "text": "t", "input_tokens": 1000, "output_tokens": 500, "cost": cost, "seconds": 5.0,
            "money_expected": 4, "money_shown": 4, "violations": [], "grade": 6.0, "requests_sent": 2, "leaks": 0,
            "judge": {
                "faithfulness": faithfulness, "key_point": key_point, "clarity": 4, "tone": 5,
                "concision": concision, "unsupported_claims": [],
            },
            "judge_error": None, "judge_input_tokens": 0, "judge_output_tokens": 0,
        }
        for i in range(n)
    ]


def fake_file(config, runs, judge_version="j2"):
    return {
        "config": config, "kind": "claude", "model": "claude-sonnet-5-5", "effort": "medium",
        "prompt_version": "v2", "judge_model": "claude-sonnet-5-5", "judge_prompt_version": judge_version,
        "runs": runs,
    }


def test_rule_a_passes_when_v2_is_as_faithful_more_concise_and_clean():
    v1 = fake_file("sonnet-medium-v1", fake_runs(15, concision=3))
    v2 = fake_file("sonnet-medium-v2", fake_runs(15, concision=4, first_try=14))
    criteria = rule_a(v1, v2)
    assert all(item.passed for item in criteria)
    assert outcome_a(criteria) == "0 criteria failed: v2 stays the default."


def test_one_failed_criterion_keeps_v2_but_two_send_the_default_back_to_v1():
    v1 = fake_file("sonnet-medium-v1", fake_runs(15, concision=3))
    one_fail = fake_file("sonnet-medium-v2", fake_runs(15, concision=4, first_try=13))
    assert "v2 stays the default" in outcome_a(rule_a(v1, one_fail))
    two_fail = fake_file("sonnet-medium-v2", fake_runs(15, faithfulness=3, concision=3))
    criteria = rule_a(v1, two_fail)
    assert [item.passed for item in criteria] == [True, False, False, True, True]
    assert "returns to v1" in outcome_a(criteria)


def test_rule_a_boundaries_are_inclusive():
    v1 = fake_file("sonnet-medium-v1", fake_runs(10, faithfulness=4, concision=3, key_point=4) + fake_runs(5, faithfulness=4, concision=3, key_point=4))
    # v2 exactly 0.3 more concise, exactly 0.15 less faithful, exactly 0.2 lower key point
    v2_runs = fake_runs(15, faithfulness=4, key_point=4, concision=3)
    for i, run in enumerate(v2_runs):
        run["judge"]["concision"] = 4 if i < 5 else 3.0 + 0.0
    v2 = fake_file("sonnet-medium-v2", v2_runs)
    concision_item = rule_a(v1, v2)[2]
    assert concision_item.detail == "v1 3.00, v2 3.33" and concision_item.passed


def test_stale_judge_versions_are_refused():
    stale = fake_file("sonnet-medium-v1", fake_runs(3), judge_version="j1")
    with pytest.raises(ValueError, match="Archive stale runs"):
        check_judge_version(stale)


def test_rule_b_recommends_only_a_cheaper_configuration_that_stays_close():
    baseline = fake_file("sonnet-medium-v2", fake_runs(40, cost=0.0100))
    cheap_and_close = fake_file("haiku-v2", fake_runs(40, faithfulness=4, key_point=4, cost=0.0010))
    assert all(item.passed for item in rule_b(baseline, cheap_and_close))
    not_cheap_enough = fake_file("sonnet-low-v2", fake_runs(40, cost=0.0080))
    assert [item.passed for item in rule_b(baseline, not_cheap_enough)] == [True, True, True, False]
    too_unfaithful = fake_file("haiku-v2", fake_runs(40, faithfulness=3, cost=0.0010))
    assert rule_b(baseline, too_unfaithful)[0].passed is False


def test_the_report_pools_both_sets_and_says_when_runs_are_missing(tmp_path):
    gold_dir, held_dir = tmp_path / "gold", tmp_path / "held"
    gold_dir.mkdir()
    held_dir.mkdir()
    for directory, n in ((gold_dir, 25), (held_dir, 15)):
        (directory / "sonnet-medium-v1.json").write_text(json.dumps(fake_file("sonnet-medium-v1", fake_runs(n, concision=3))))
        (directory / "sonnet-medium-v2.json").write_text(json.dumps(fake_file("sonnet-medium-v2", fake_runs(n, cost=0.0100))))
    (gold_dir / "haiku-v2.json").write_text(json.dumps(fake_file("haiku-v2", fake_runs(25, cost=0.0010))))
    text = build_decisions(gold_dir, held_dir)
    assert "v2 stays the default" in text
    assert "### sonnet-low-v2\n\nNot run on both sets yet." in text
    assert "### haiku-v2\n\nNot run on both sets yet." in text  # present on one set only
    (held_dir / "haiku-v2.json").write_text(json.dumps(fake_file("haiku-v2", fake_runs(15, cost=0.0010))))
    assert "haiku-v2 is recommended over medium-effort v2" in build_decisions(gold_dir, held_dir)


def test_without_any_runs_the_report_says_not_run_yet(tmp_path):
    text = build_decisions(tmp_path / "a", tmp_path / "b")
    assert text.count("Not run yet.") == 1
    assert text.count("Not run on both sets yet.") == 2

def test_the_outcome_line_uses_the_right_singular_and_plural():
    v1 = fake_file("sonnet-medium-v1", fake_runs(15, concision=3))
    one = fake_file("sonnet-medium-v2", fake_runs(15, concision=4, first_try=13))
    assert outcome_a(rule_a(v1, one)).startswith("1 criterion failed:")
