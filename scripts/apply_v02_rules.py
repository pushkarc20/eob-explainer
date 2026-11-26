"""Apply the pre-registered v0.2 decision rules to the saved runs and write docs/v0.2_decisions.md.

No AI and no cost. Usage: python scripts/apply_v02_rules.py
"""
from eob.ai_eval import RUNS_DIR
from eob.decisions import build_decisions
from eob.evaluation import ROOT

HELDOUT_RUNS = ROOT / "docs" / "eval" / "runs_heldout"
OUT = ROOT / "docs" / "v0.2_decisions.md"


def main() -> None:
    text = build_decisions(RUNS_DIR, HELDOUT_RUNS)
    print(text)
    OUT.write_text(text + "\n", encoding="utf-8")
    print(f"Saved to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()