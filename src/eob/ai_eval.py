"""Evaluate explanation systems (the built-in template and Claude configurations) on the gold set.

Only fixture files (synthetic or public example EOBs) may be evaluated. Every request sent to a model is
recorded and audited for the planted canary names and for any sensitive value the pipeline knows about.
The judge sees only placeholder text, never real names or dates.
"""
import json
import statistics
import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from eob.engine import analyze
from eob.evaluation import ROOT
from eob.explainer import ExplainResult, explain
from eob.explanation import render_text
from eob.judge import JUDGE_PROMPT_VERSION, judge_explanation
from eob.parser import parse_eob
from eob.privacy import collect_blocked_values, prepare_cloud_payload
from eob.readability import flesch_kincaid_grade, prose_text
from eob.safety import DISCLAIMER, find_banned
from eob.settings import estimate_cost
from eob.templates import template_explanation
from eob.validate import extract_amounts
from healthcore.fhir.helpers import load_resource
from healthcore.llm.base import LLMClient, LLMResult
from healthcore.privacy.detector import PiiDetector
from healthcore.privacy.pseudonymizer import Pseudonymizer

RUNS_DIR = ROOT / "docs" / "eval" / "runs"
REPORT_PATH = ROOT / "docs" / "eval_ai_results.md"
JUDGE_KEYS = ("faithfulness", "key_point", "clarity", "tone", "concision")


@dataclass(frozen=True)
class EvalConfig:
    name: str
    kind: Literal["template", "claude"]
    model: str | None = None
    effort: str | None = None
    prompt_version: str = "v1"


CONFIGS = {
    "template": EvalConfig("template", "template"),
    "sonnet-medium-v1": EvalConfig("sonnet-medium-v1", "claude", "claude-sonnet-5-5", "medium", "v1"),
    "sonnet-medium-v2": EvalConfig("sonnet-medium-v2", "claude", "claude-sonnet-5-5", "medium", "v2"),
    "sonnet-low-v2": EvalConfig("sonnet-low-v2", "claude", "claude-sonnet-5-5", "low", "v2"),
    "haiku-v2": EvalConfig("haiku-v2", "claude", "claude-haiku-5-5", None, "v2"),
}
ORDER = list(CONFIGS)


class RecordingClient:
    """Wraps a client and remembers every request, so a run can audit what was sent."""

    def __init__(self, inner: LLMClient) -> None:
        self.name = inner.name
        self._inner = inner
        self.requests: list[str] = []

    def complete(self, system: str, user: str, max_tokens: int) -> LLMResult:
        self.requests.append(system + "\n" + user)
        return self._inner.complete(system, user, max_tokens)


@dataclass
class CaseRun:
    case_id: str
    config: str
    source: str
    attempts: int
    problems: list[str]
    text: str  # what the user sees (real values restored)
    input_tokens: int
    output_tokens: int
    cost: float | None
    seconds: float
    money_expected: int
    money_shown: int
    violations: list[str]
    grade: float | None
    requests_sent: int
    leaks: int
    judge: dict[str, Any] | None
    judge_error: str | None
    judge_input_tokens: int
    judge_output_tokens: int


def assert_fixture(file: str) -> None:
    if not file.replace("\\", "/").startswith("fixtures/"):
        raise ValueError("Only files under fixtures/ (synthetic or public examples) may be evaluated.")


def count_leaks(requests: Iterable[str], sensitive: Iterable[str]) -> int:
    sent = "\n".join(requests).casefold()
    return sum(1 for value in set(sensitive) if len(value) >= 3 and value.casefold() in sent)


def run_case(
    case: dict[str, Any],
    config: EvalConfig,
    generator: LLMClient | None,
    judge_client: LLMClient | None,
    detector: PiiDetector,
    must_not_say: list[str],
) -> CaseRun:
    assert_fixture(case["file"])
    raw = load_resource(ROOT / case["file"])
    eob = parse_eob(raw)
    analysis = analyze(eob)
    blocked = collect_blocked_values(raw)
    pseudonymizer = Pseudonymizer()
    recorder = RecordingClient(generator) if generator is not None else None

    started = time.perf_counter()
    if recorder is None:
        result = ExplainResult(template_explanation(eob, analysis), "template")
    else:
        result = explain(
            eob, analysis, recorder, pseudonymizer, detector, blocked, prompt_version=config.prompt_version
        )
    seconds = time.perf_counter() - started

    text = render_text(result.explanation, DISCLAIMER)
    lowered = text.lower().replace("\u2019", "'")
    expected = [Decimal(value) for value in case["expected"]["money"].values() if value is not None]
    shown = extract_amounts(text)

    judge_data = None
    judge_error = None
    judge_in = judge_out = 0
    judge_recorder = None
    if judge_client is not None:
        judge_recorder = RecordingClient(judge_client)
        payload_json = prepare_cloud_payload(eob, analysis, pseudonymizer, detector, blocked).json_text
        if result.placeholder_explanation is not None:
            judged_text = render_text(result.placeholder_explanation, "").strip()
        else:
            judged_text = pseudonymizer.apply(render_text(result.explanation, "").strip())
        verdict = judge_explanation(
            judge_recorder, pseudonymizer, detector, payload_json, case["key_point"], judged_text
        )
        judge_data = verdict.scores.model_dump() if verdict.scores else None
        judge_error = verdict.error
        judge_in, judge_out = verdict.input_tokens, verdict.output_tokens

    sent = (recorder.requests if recorder else []) + (judge_recorder.requests if judge_recorder else [])
    sensitive = {*case["canaries"], *blocked, *pseudonymizer.sensitive_values()}
    return CaseRun(
        case_id=case["id"],
        config=config.name,
        source=result.source,
        attempts=result.attempts,
        problems=list(result.problems),
        text=text,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost=estimate_cost(config.model, result.input_tokens, result.output_tokens) if config.model else None,
        seconds=seconds,
        money_expected=len(expected),
        money_shown=sum(1 for value in expected if value in shown),
        violations=sorted({*find_banned(text), *(phrase for phrase in must_not_say if phrase in lowered)}),
        grade=flesch_kincaid_grade(prose_text(result.explanation)),
        requests_sent=len(sent),
        leaks=count_leaks(sent, sensitive),
        judge=judge_data,
        judge_error=judge_error,
        judge_input_tokens=judge_in,
        judge_output_tokens=judge_out,
    )


def save_run(config: EvalConfig, runs: list[CaseRun], judge_model: str | None) -> Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "config": config.name,
        "kind": config.kind,
        "model": config.model,
        "effort": config.effort,
        "prompt_version": config.prompt_version,
        "judge_model": judge_model,
        "judge_prompt_version": JUDGE_PROMPT_VERSION if judge_model else None,
        "date": date.today().isoformat(),
        "runs": [asdict(run) for run in runs],
    }
    path = RUNS_DIR / f"{config.name}.json"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def load_runs(directory: Path = RUNS_DIR) -> list[dict[str, Any]]:
    files = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("*.json"))]
    order = {name: index for index, name in enumerate(ORDER)}
    return sorted(files, key=lambda data: order.get(data["config"], 99))


def _mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def summarize(run_file: dict[str, Any]) -> dict[str, Any]:
    runs = run_file["runs"]
    cases = len(runs)
    is_claude = run_file["kind"] == "claude"
    ai_runs = [r for r in runs if r["source"] == "ai"]
    judged = [r for r in runs if r["judge"]]
    costs = [r["cost"] for r in runs if r["cost"] is not None]

    def judge_means(rows: list[dict[str, Any]]) -> dict[str, float | None]:
        return {key: _mean([r["judge"][key] for r in rows]) for key in JUDGE_KEYS}

    return {
        "config": run_file["config"],
        "kind": run_file["kind"],
        "model": run_file["model"],
        "effort": run_file["effort"],
        "prompt_version": run_file["prompt_version"],
        "judge_model": run_file["judge_model"],
        "cases": cases,
        "first_try": sum(1 for r in ai_runs if r["attempts"] == 1),
        "after_retry": sum(1 for r in ai_runs if r["attempts"] > 1),
        "fell_back": cases - len(ai_runs) if is_claude else 0,
        "expected": sum(r["money_expected"] for r in runs),
        "shown": sum(r["money_shown"] for r in runs),
        "violation_cases": sum(1 for r in runs if r["violations"]),
        "grade": _mean([r["grade"] for r in runs if r["grade"] is not None]),
        "judged": len(judged),
        "judge": judge_means(judged),
        "judge_ai": judge_means([r for r in judged if r["source"] == "ai"]),
        "unsupported": sum(len(r["judge"]["unsupported_claims"]) for r in judged),
        "requests": sum(r["requests_sent"] for r in runs),
        "leaks": sum(r["leaks"] for r in runs),
        "tokens_in": _mean([r["input_tokens"] for r in runs]) if is_claude else None,
        "tokens_out": _mean([r["output_tokens"] for r in runs]) if is_claude else None,
        "cost_mean": _mean(costs),
        "cost_total": sum(costs) if costs else None,
        "seconds_mean": _mean([r["seconds"] for r in runs]),
        "seconds_max": max((r["seconds"] for r in runs), default=None),
        "reasons": dict(Counter(code for r in runs for code in r["problems"])),
    }


def _fmt(value: float | None, spec: str = ".2f") -> str:
    return "n/a" if value is None else format(value, spec)


def _pct(part: int, whole: int) -> str:
    return "n/a" if not whole else f"{part / whole:.0%}"


def _review_notes(run_file: dict[str, Any]) -> list[str]:
    notes = []
    for run in run_file["runs"]:
        reasons = []
        if run_file["kind"] == "claude" and run["source"] == "template":
            reasons.append("fell back to the built-in explanation (" + ", ".join(run["problems"]) + ")")
        if run["judge"] and run["judge"]["faithfulness"] <= 3:
            reasons.append(f"judge faithfulness {run['judge']['faithfulness']}")
        if run["judge"] and run["judge"]["unsupported_claims"]:
            claims = "; ".join(claim[:140] for claim in run["judge"]["unsupported_claims"][:2])
            reasons.append(f"judge flagged: {claims}")
        if reasons:
            notes.append(f"- **{run_file['config']} / {run['case_id']}**: " + "; ".join(reasons))
    return notes


def format_report(run_files: list[dict[str, Any]]) -> str:
    summaries = [summarize(run_file) for run_file in run_files]
    if not summaries:
        return "# Evaluation results: explanation systems\n\nNo runs yet. Run scripts/run_ai_eval.py first.\n"

    def is_claude(s: dict[str, Any]) -> bool:
        return s["kind"] == "claude"

    rows: list[tuple[str, Any]] = [
        ("Model / effort", lambda s: f"{s['model']} / {s['effort'] or 'default'}" if is_claude(s) else "built-in"),
        ("Prompt version", lambda s: s["prompt_version"] if is_claude(s) else "n/a"),
        ("Cases", lambda s: str(s["cases"])),
        ("AI answer passed all checks on the first try", lambda s: f"{s['first_try']} of {s['cases']}" if is_claude(s) else "n/a"),
        ("AI answer passed after one retry", lambda s: str(s["after_retry"]) if is_claude(s) else "n/a"),
        ("Fell back to the built-in explanation", lambda s: str(s["fell_back"]) if is_claude(s) else "n/a"),
        ("Expected money figures shown", lambda s: f"{s['shown']} of {s['expected']} ({_pct(s['shown'], s['expected'])})"),
        ("Cases with overclaiming phrases", lambda s: str(s["violation_cases"])),
        ("Reading grade, lower is easier (target 8 or less)", lambda s: _fmt(s["grade"], ".1f")),
        ("Cases scored by the judge", lambda s: f"{s['judged']} of {s['cases']}"),
    ]
    labels = {
        "faithfulness": "Judge: faithfulness",
        "key_point": "Judge: key point",
        "clarity": "Judge: clarity",
        "tone": "Judge: tone and safety",
        "concision": "Judge: concision",
    }
    for key, label in labels.items():
        rows.append((f"{label} (1 to 5)", lambda s, k=key: _fmt(s["judge"][k])))
    rows += [
        ("Judge: faithfulness, AI-written answers only", lambda s: _fmt(s["judge_ai"]["faithfulness"]) if is_claude(s) else "n/a"),
        ("Unsupported claims the judge found", lambda s: str(s["unsupported"])),
        ("Outbound requests / planted-name leaks", lambda s: f"{s['requests']} / {s['leaks']}"),
        ("Mean tokens in / out", lambda s: f"{s['tokens_in']:.0f} / {s['tokens_out']:.0f}" if is_claude(s) else "n/a"),
        ("Mean cost per explanation", lambda s: "n/a" if s["cost_mean"] is None else f"${s['cost_mean']:.4f}"),
        ("Mean / slowest seconds per explanation", lambda s: f"{_fmt(s['seconds_mean'], '.1f')} / {_fmt(s['seconds_max'], '.1f')}"),
    ]

    names = [s["config"] for s in summaries]
    lines = [
        "# Evaluation results: explanation systems",
        "",
        "Gold set: HL7 CARIN examples plus synthetic scenarios.",
        "Judge: " + ", ".join(sorted({s["judge_model"] for s in summaries if s["judge_model"]}) or ["none"]) + ".",
        "",
        "| Metric | " + " | ".join(names) + " |",
        "|---|" + "---|" * len(names),
    ]
    for label, fn in rows:
        lines.append(f"| {label} | " + " | ".join(fn(s) for s in summaries) + " |")
    lines.append("")

    for s in summaries:
        if is_claude(s) and s["reasons"]:
            ordered = sorted(s["reasons"].items(), key=lambda item: -item[1])
            lines.append(f"Why {s['config']} answers were rejected: " + ", ".join(f"{c} x{n}" for c, n in ordered) + ".")
    lines.append("")

    notes = [note for run_file in run_files for note in _review_notes(run_file)]
    lines += ["## Cases to review", ""] + (notes[:30] or ["- none"]) + [""]
    lines += [
        "## What this measures, and what it does not",
        "",
        "- Measures: whether answers pass the code checks, show the expected figures, avoid overclaiming,",
        "  read easily, and score well against a fixed judge rubric, plus cost, speed and privacy audit.",
        "- Judge caveat: the judge is also a model, may favor similar writing, and is not a substitute for",
        "  human review. Treat its scores as a screening signal.",
        "- Small sample: 25 cases, one run each. Model output varies between runs, so differences of a few",
        "  percentage points are not meaningful.",
        "- Privacy audit: every request to a model, including the judge's, is scanned for the planted provider",
        "  names and every identifier the pipeline knows. A leak count of 0 means none were found.",
        "",
    ]
    return "\n".join(lines)


def write_report(directory: Path = RUNS_DIR, path: Path = REPORT_PATH) -> str:
    report = format_report(load_runs(directory))
    stamped = f"<!-- generated by scripts/run_ai_eval.py on {date.today().isoformat()} -->\n{report}"
    path.write_text(stamped, encoding="utf-8")
    return report
