"""Score the deterministic engine against the gold set (fixtures/gold/gold.json).

The expected answers are written by hand in scripts/build_eval_set.py, independently of the
engine, so this is a real test of the engine and not the engine grading itself.
"""
import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from eob.engine import analyze
from eob.parser import parse_eob
from healthcore.fhir.helpers import load_resource

ROOT = Path(__file__).resolve().parents[2]
GOLD_PATH = ROOT / "fixtures" / "gold" / "gold.json"
MONEY_FIELDS = ("billed", "allowed", "plan_paid", "patient_responsibility")


@dataclass
class CaseResult:
    case_id: str
    money_total: int = 0
    money_correct: int = 0
    money_misses: list[str] = field(default_factory=list)
    expected_flags: set[str] = field(default_factory=set)
    found_flags: set[str] = field(default_factory=set)
    expected_mismatches: set[str] = field(default_factory=set)
    found_mismatches: set[str] = field(default_factory=set)
    expected_warnings: int = 0
    found_warnings: int = 0

    def problems(self) -> list[str]:
        found = list(self.money_misses)
        missing = sorted(self.expected_flags - self.found_flags)
        extra = sorted(self.found_flags - self.expected_flags)
        if missing:
            found.append("missing flags: " + ", ".join(missing))
        if extra:
            found.append("unexpected flags: " + ", ".join(extra))
        if self.expected_mismatches != self.found_mismatches:
            found.append(
                f"check mismatches: expected {sorted(self.expected_mismatches)}, "
                f"got {sorted(self.found_mismatches)}"
            )
        if self.expected_warnings != self.found_warnings:
            found.append(f"parse warnings: expected {self.expected_warnings}, got {self.found_warnings}")
        return found

    @property
    def passed(self) -> bool:
        return not self.problems()


@dataclass
class Summary:
    cases: int
    passed: int
    money_total: int
    money_correct: int
    flag_tp: int
    flag_fp: int
    flag_fn: int
    clean_cases: int
    clean_false_alarm_cases: int
    checks_correct: int
    warnings_correct: int

    @property
    def pass_rate(self) -> float:
        return self.passed / self.cases if self.cases else 1.0

    @property
    def money_accuracy(self) -> float:
        return self.money_correct / self.money_total if self.money_total else 1.0

    @property
    def flag_precision(self) -> float:
        raised = self.flag_tp + self.flag_fp
        return self.flag_tp / raised if raised else 1.0

    @property
    def flag_recall(self) -> float:
        wanted = self.flag_tp + self.flag_fn
        return self.flag_tp / wanted if wanted else 1.0


def load_gold(path: Path = GOLD_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_case(case: dict[str, Any], root: Path = ROOT) -> CaseResult:
    analysis = analyze(parse_eob(load_resource(root / case["file"])))
    expected = case["expected"]
    result = CaseResult(case_id=case["id"])

    for name in MONEY_FIELDS:
        if name not in expected["money"]:
            continue
        wanted = expected["money"][name]
        figure = getattr(analysis.money, name)
        result.money_total += 1
        if wanted is None:
            correct = figure.value is None
        else:
            correct = figure.value is not None and figure.value == Decimal(wanted)
        if correct:
            result.money_correct += 1
        else:
            got = "not reported" if figure.value is None else str(figure.value)
            result.money_misses.append(f"{name}: expected {wanted}, got {got}")

    result.expected_flags = set(expected["flags"])
    result.found_flags = {f"{flag.code}:{flag.severity}" for flag in analysis.flags}
    result.expected_mismatches = set(expected["check_mismatches"])
    result.found_mismatches = {check.name for check in analysis.checks if check.status == "mismatch"}
    result.expected_warnings = expected["parse_warnings"]
    result.found_warnings = len(analysis.parse_warnings)
    return result


def summarize(results: list[CaseResult]) -> Summary:
    clean = [r for r in results if not r.expected_flags]
    return Summary(
        cases=len(results),
        passed=sum(1 for r in results if r.passed),
        money_total=sum(r.money_total for r in results),
        money_correct=sum(r.money_correct for r in results),
        flag_tp=sum(len(r.expected_flags & r.found_flags) for r in results),
        flag_fp=sum(len(r.found_flags - r.expected_flags) for r in results),
        flag_fn=sum(len(r.expected_flags - r.found_flags) for r in results),
        clean_cases=len(clean),
        clean_false_alarm_cases=sum(1 for r in clean if r.found_flags),
        checks_correct=sum(1 for r in results if r.expected_mismatches == r.found_mismatches),
        warnings_correct=sum(1 for r in results if r.expected_warnings == r.found_warnings),
    )


def evaluate_all(path: Path = GOLD_PATH) -> tuple[list[CaseResult], Summary]:
    results = [evaluate_case(case) for case in load_gold(path)["cases"]]
    return results, summarize(results)


def _pct(value: float) -> str:
    return f"{value:.1%}"


def format_report(summary: Summary, results: list[CaseResult]) -> str:
    lines = [
        "# Evaluation results: deterministic rules engine",
        "",
        f"Gold set: {summary.cases} cases (HL7 CARIN examples plus synthetic scenarios).",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Cases fully correct | {summary.passed} of {summary.cases} ({_pct(summary.pass_rate)}) |",
        f"| Money figures correct | {summary.money_correct} of {summary.money_total} ({_pct(summary.money_accuracy)}) |",
        f"| Flag precision | {_pct(summary.flag_precision)} ({summary.flag_tp} right, {summary.flag_fp} wrongly raised) |",
        f"| Flag recall | {_pct(summary.flag_recall)} ({summary.flag_fn} missed) |",
        f"| False alarms on clean claims | {summary.clean_false_alarm_cases} of {summary.clean_cases} clean cases |",
        f"| Consistency-check results correct | {summary.checks_correct} of {summary.cases} |",
        f"| Parse-warning counts correct | {summary.warnings_correct} of {summary.cases} |",
        "",
    ]
    failing = [r for r in results if not r.passed]
    if failing:
        lines += ["## Cases that need attention", ""]
        for r in failing:
            lines.append(f"- **{r.case_id}**: " + "; ".join(r.problems()))
        lines.append("")
    lines += [
        "## What this measures (and what it does not)",
        "",
        "- Measures: whether the rules engine computes the right money figures and raises the right",
        "  flags, with expectations written by hand independently of the code.",
        "- Does not measure: the quality of AI-written explanations, readability, safety wording of",
        "  model output, or privacy leakage. Those are evaluated in later steps.",
        "- Caveat: the cases are small and synthetic, so a perfect score here means the rules do what",
        "  I intended, not that they will be right on every real-world claim.",
        "",
    ]
    return "\n".join(lines)
