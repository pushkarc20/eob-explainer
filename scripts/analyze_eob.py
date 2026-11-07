"""Print the deterministic analysis of an EOB file (no AI involved).

Usage:
    python scripts/analyze_eob.py fixtures/carin/EOBProfessional2.json
"""
import sys

from eob.engine import analyze
from eob.money import Figure, fmt_money
from eob.parser import parse_eob
from healthcore.fhir.helpers import load_resource


def show(label: str, figure: Figure) -> None:
    text = "not reported" if figure.value is None else fmt_money(figure.value)
    print(f"  {label:<28}{text:>14}   ({figure.source})")


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python scripts/analyze_eob.py path/to/eob.json")
    analysis = analyze(parse_eob(load_resource(sys.argv[1])))
    money = analysis.money

    print("MONEY")
    show("Billed", money.billed)
    show("Allowed", money.allowed)
    show("Plan paid", money.plan_paid)
    show("Patient responsibility", money.patient_responsibility)
    show("  deductible", money.deductible)
    show("  copay", money.copay)
    show("  coinsurance", money.coinsurance)
    show("  non-covered", money.noncovered)
    show("Patient has already paid", money.patient_paid)

    print("\nCHECKS")
    for check in analysis.checks:
        print(f"  [{check.status}] {check.message}")
    if not analysis.checks:
        print("  (nothing to compare)")

    print("\nFLAGS")
    for flag in analysis.flags:
        print(f"  [{flag.severity}] {flag.title}\n      {flag.detail}\n      Ask: {flag.ask}")
    if not analysis.flags:
        print("  (none)")

    if analysis.parse_warnings:
        print("\nPARSE WARNINGS")
        for warning in analysis.parse_warnings:
            print(f"  {warning}")


if __name__ == "__main__":
    main()
