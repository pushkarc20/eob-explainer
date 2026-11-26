"""Apply the pre-registered v0.2 decision rules (docs/v0.2_plan.md) mechanically to saved evaluation runs.

The thresholds below are copied from the plan, which was committed before any held-out case existed.
Comparisons are one-sided: a candidate that is better than the baseline passes.
"""
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from eob.ai_eval import summarize

JUDGE_VERSION = "j2"
BASELINE = "sonnet-medium-v2"
CANDIDATES = ("sonnet-low-v2", "haiku-v2")
EPSILON = 1e-9


@dataclass(frozen=True)
class Criterion:
    text: str
    passed: bool
    detail: str


def check_judge_version(run_file: dict[str, Any]) -> None:
    version = run_file.get("judge_prompt_version")
    if version != JUDGE_VERSION:
        raise ValueError(
            f"{run_file['config']} was scored with judge {version}, expected {JUDGE_VERSION}. Archive stale runs first."
        )


def _mean(summary: dict[str, Any], key: str) -> float:
    value = summary["judge"][key]
    if value is None:
        raise ValueError(f"{summary['config']}: no judge scores")
    return value


def rule_a(v1_file: dict[str, Any], v2_file: dict[str, Any]) -> list[Criterion]:
    """Does prompt v2 stay the default? Held-out set, v2 against v1."""
    check_judge_version(v1_file)
    check_judge_version(v2_file)
    s1, s2 = summarize(v1_file), summarize(v2_file)
    f1, f2 = _mean(s1, "faithfulness"), _mean(s2, "faithfulness")
    c1, c2 = _mean(s1, "concision"), _mean(s2, "concision")
    k1, k2 = _mean(s1, "key_point"), _mean(s2, "key_point")
    return [
        Criterion(
            "At least 14 of 15 v2 answers pass the code checks on the first try",
            s2["first_try"] >= 14,
            f"{s2['first_try']} of {s2['cases']}",
        ),
        Criterion("Faithfulness no more than 0.15 below v1", f2 >= f1 - 0.15 - EPSILON, f"v1 {f1:.2f}, v2 {f2:.2f}"),
        Criterion("Concision at least 0.3 above v1", c2 >= c1 + 0.3 - EPSILON, f"v1 {c1:.2f}, v2 {c2:.2f}"),
        Criterion("Key point no more than 0.2 below v1", k2 >= k1 - 0.2 - EPSILON, f"v1 {k1:.2f}, v2 {k2:.2f}"),
        Criterion(
            "No leaks and no overclaiming phrases (v2)",
            s2["leaks"] == 0 and s2["violation_cases"] == 0,
            f"leaks {s2['leaks']}, cases with overclaiming phrases {s2['violation_cases']}",
        ),
    ]


def outcome_a(criteria: list[Criterion]) -> str:
    failed = sum(1 for item in criteria if not item.passed)
    if failed >= 2:
        return f"{failed} criteria failed: the default returns to v1, and the README must say the v2 gain did not generalize."
    return f"{failed} criteria failed: v2 stays the default."


def rule_b(baseline_file: dict[str, Any], candidate_file: dict[str, Any]) -> list[Criterion]:
    """Is a cheaper configuration recommended over medium-effort v2? Both sets pooled."""
    check_judge_version(baseline_file)
    check_judge_version(candidate_file)
    b, c = summarize(baseline_file), summarize(candidate_file)
    fb, fc = _mean(b, "faithfulness"), _mean(c, "faithfulness")
    kb, kc = _mean(b, "key_point"), _mean(c, "key_point")
    share = c["first_try"] / c["cases"] if c["cases"] else 0.0
    cost_b, cost_c = b["cost_mean"], c["cost_mean"]
    cheaper = cost_b is not None and cost_c is not None and cost_c <= 0.7 * cost_b + EPSILON
    cost_detail = "cost not available" if cost_b is None or cost_c is None else f"baseline ${cost_b:.4f}, candidate ${cost_c:.4f}"
    return [
        Criterion("Faithfulness no more than 0.2 below medium-effort v2", fc >= fb - 0.2 - EPSILON, f"baseline {fb:.2f}, candidate {fc:.2f}"),
        Criterion("Key point no more than 0.3 below medium-effort v2", kc >= kb - 0.3 - EPSILON, f"baseline {kb:.2f}, candidate {kc:.2f}"),
        Criterion("At least 90% pass the code checks on the first try", share >= 0.9 - EPSILON, f"{c['first_try']} of {c['cases']}"),
        Criterion("Mean cost at least 30% lower", cheaper, cost_detail),
    ]


def load_run(directory: Path, name: str) -> dict[str, Any] | None:
    path = directory / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def pooled_run(name: str, directories: tuple[Path, ...]) -> dict[str, Any] | None:
    parts = [load_run(directory, name) for directory in directories]
    if any(part is None for part in parts):
        return None
    merged = dict(parts[0])
    merged["runs"] = [run for part in parts for run in part["runs"]]
    return merged


def _table(criteria: list[Criterion]) -> list[str]:
    rows = ["| Criterion | Result | Detail |", "|---|---|---|"]
    rows += [f"| {item.text} | {'PASS' if item.passed else 'FAIL'} | {item.detail} |" for item in criteria]
    return rows


def build_decisions(gold_runs: Path, heldout_runs: Path) -> str:
    lines = [
        "# v0.2 decisions",
        "",
        "The pre-registered rules in docs/v0.2_plan.md, applied mechanically by scripts/apply_v02_rules.py.",
        f"Every score is from judge {JUDGE_VERSION}. Generated {date.today().isoformat()}.",
        "",
        "## Rule A: does prompt v2 stay the default? (held-out set, v2 against v1)",
        "",
    ]
    v1 = load_run(heldout_runs, "sonnet-medium-v1")
    v2 = load_run(heldout_runs, "sonnet-medium-v2")
    if v1 and v2:
        criteria = rule_a(v1, v2)
        lines += _table(criteria) + ["", f"**Outcome:** {outcome_a(criteria)}", ""]
    else:
        lines += ["Not run yet.", ""]

    lines += ["## Rule B: is a cheaper configuration recommended? (both sets pooled, against medium-effort v2)", ""]
    baseline = pooled_run(BASELINE, (gold_runs, heldout_runs))
    for name in CANDIDATES:
        lines += [f"### {name}", ""]
        candidate = pooled_run(name, (gold_runs, heldout_runs))
        if baseline is None or candidate is None:
            lines += ["Not run on both sets yet.", ""]
            continue
        criteria = rule_b(baseline, candidate)
        verdict = "recommended over medium-effort v2" if all(item.passed for item in criteria) else "not recommended"
        lines += _table(criteria) + ["", f"**Outcome:** {name} is {verdict}.", ""]
    return "\n".join(lines)