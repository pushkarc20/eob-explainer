"""Evaluate explanation systems on the gold set and write docs/eval_ai_results.md.

Sends only synthetic or public example data (fixtures/) to Claude, and asks before spending anything.

Usage:
    python scripts/run_ai_eval.py --configs template,sonnet-medium-v1,sonnet-medium-v2 --limit 3    (quick wiring check)
    python scripts/run_ai_eval.py --configs template,sonnet-medium-v1,sonnet-medium-v2
    python scripts/run_ai_eval.py --configs sonnet-low-v2,haiku-v2
    python scripts/run_ai_eval.py --report-only
"""
import argparse
import os
import sys

from eob.ai_eval import CONFIGS, REPORT_PATH, run_case, save_run, write_report
from eob.evaluation import load_gold
from eob.settings import MissingKeyError, estimate_cost, load_cloud_settings
from healthcore.llm.anthropic_client import AnthropicClient
from healthcore.privacy.detector import default_detector


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate explanation systems on the gold set.")
    parser.add_argument("--configs", default="template,sonnet-medium-v1,sonnet-medium-v2", help="comma-separated: " + ", ".join(CONFIGS))
    parser.add_argument("--limit", type=int, help="only the first N cases (for a quick check)")
    parser.add_argument("--no-judge", action="store_true", help="skip the judge model")
    parser.add_argument("--report-only", action="store_true", help="rebuild the report from saved runs")
    parser.add_argument("--yes", action="store_true", help="do not ask before spending (synthetic data only)")
    args = parser.parse_args()

    if args.report_only:
        write_report()
        print(f"Report written to {REPORT_PATH}")
        return

    names = [name.strip() for name in args.configs.split(",") if name.strip()]
    unknown = [name for name in names if name not in CONFIGS]
    if unknown:
        sys.exit(f"Unknown config(s): {', '.join(unknown)}. Choose from: {', '.join(CONFIGS)}")
    gold = load_gold()
    cases = gold["cases"][: args.limit] if args.limit else gold["cases"]
    claude_configs = [name for name in names if CONFIGS[name].kind == "claude"]

    judge_model = None
    judge_client = None
    if claude_configs or not args.no_judge:
        try:
            load_cloud_settings()
        except MissingKeyError as error:
            sys.exit(str(error))
    if not args.no_judge:
        judge_model = os.environ.get("EOB_JUDGE_MODEL") or "claude-sonnet-5-5"
        judge_client = AnthropicClient(judge_model, "low")

    generation_calls = len(cases) * len(claude_configs)
    judge_calls = 0 if args.no_judge else len(cases) * len(names)
    print(f"Configs: {', '.join(names)}  |  cases: {len(cases)}  |  judge: {judge_model or 'off'}")
    print(f"This will make about {generation_calls} generation and {judge_calls} judge calls to Claude,")
    print(f"roughly ${0.012 * (generation_calls + judge_calls):.2f} in total. Only synthetic or public example data is sent.")
    asking = bool(generation_calls or judge_calls) and not args.yes
    if asking and input("Continue? Type y to run, anything else to cancel: ").strip().lower() != "y":
        sys.exit("Cancelled.")

    detector = default_detector()
    for name in names:
        config = CONFIGS[name]
        generator = AnthropicClient(config.model, config.effort) if config.kind == "claude" else None
        runs = []
        for index, case in enumerate(cases, start=1):
            run = run_case(case, config, generator, judge_client, detector, gold["must_not_say"])
            runs.append(run)
            score = f", faithfulness {run.judge['faithfulness']}" if run.judge else ""
            print(f"[{name}] {index}/{len(cases)} {case['id']}: {run.source}, {run.seconds:.1f}s{score}")
        path = save_run(config, runs, judge_model)
        judge_cost = estimate_cost(
            judge_model or "", sum(r.judge_input_tokens for r in runs), sum(r.judge_output_tokens for r in runs)
        )
        generation_cost = sum(r.cost or 0 for r in runs)
        print(
            f"[{name}] saved {path.name}. Generation cost ${generation_cost:.3f}"
            + (f", judge cost ${judge_cost:.3f}" if judge_cost is not None else "")
        )

    write_report()
    print(f"\nReport written to {REPORT_PATH}")


if __name__ == "__main__":
    main()
