from eob.ai_eval import MAX_REVIEW_PER_CONFIG, format_report


def flagged_run(case_id, faithfulness):
    return {
        "case_id": case_id, "config": "x", "source": "ai", "attempts": 1, "problems": [], "text": "t",
        "input_tokens": 1000, "output_tokens": 500, "cost": 0.01, "seconds": 10.0,
        "money_expected": 4, "money_shown": 4, "violations": [], "grade": 8.0,
        "requests_sent": 2, "leaks": 0, "judge_error": None, "judge_input_tokens": 0, "judge_output_tokens": 0,
        "judge": {
            "faithfulness": faithfulness, "key_point": 4, "clarity": 4, "tone": 5, "concision": 4,
            "unsupported_claims": ["something unsupported"],
        },
    }


def run_file(name, faithfulness_values):
    runs = [flagged_run(f"{name}_case_{i}", value) for i, value in enumerate(faithfulness_values)]
    return {
        "config": name, "kind": "claude", "model": "claude-sonnet-5-5", "effort": "medium",
        "prompt_version": "v1", "judge_model": "claude-sonnet-5-5", "runs": runs,
    }


def test_every_configuration_gets_its_own_review_list():
    report = format_report([run_file("a", [4] * 15), run_file("b", [4] * 15)])
    assert report.count("- **a / ") == MAX_REVIEW_PER_CONFIG
    assert report.count("- **b / ") == MAX_REVIEW_PER_CONFIG


def test_the_worst_cases_are_listed_first_and_survive_the_cap():
    report = format_report([run_file("a", [5] * 14 + [1])])
    assert "a / a_case_14" in report  # faithfulness 1, last in case order
    assert report.index("a_case_14") < report.index("a_case_0")
