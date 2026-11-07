"""Print a compact structural outline of a FHIR ExplanationOfBenefit file.

Handles a single resource, a bare list, a Bundle, or a Bundle-entry wrapper.
Only the FIRST EOB is outlined. Synthetic data only.

Usage:
    python scripts/inspect_eob.py data/raw/sample/sample-eob-entry.json
"""
import json
import sys
from pathlib import Path

MAX_STR = 70
MAX_DEPTH = 3
MAX_ITEMS_SHOWN = 5


def short(value) -> str:
    text = value if isinstance(value, str) else json.dumps(value)
    return text if len(text) <= MAX_STR else text[: MAX_STR - 3] + "..."


def unwrap(doc) -> list:
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict) and doc.get("resourceType") == "Bundle":
        return [entry.get("resource", {}) for entry in doc.get("entry", [])]
    if isinstance(doc, dict) and "resource" in doc and "resourceType" not in doc:
        return [doc["resource"]]
    return [doc]


def outline(node: dict, indent: int = 0, depth: int = 0) -> None:
    pad = "  " * indent
    for key, val in node.items():
        if isinstance(val, dict):
            print(f"{pad}{key}: {{object, {len(val)} keys}}")
            if depth < MAX_DEPTH:
                outline(val, indent + 1, depth + 1)
        elif isinstance(val, list):
            print(f"{pad}{key}: [list of {len(val)}]")
            if val and depth < MAX_DEPTH:
                first = val[0]
                if isinstance(first, dict):
                    print(f"{pad}  [0]:")
                    outline(first, indent + 2, depth + 1)
                else:
                    print(f"{pad}  [0]: {short(first)}")
        else:
            print(f"{pad}{key}: {short(val)}")


def first_coding(concept: dict) -> dict:
    codings = (concept or {}).get("coding") or [{}]
    return codings[0]


def money(entry: dict) -> str:
    amount = entry.get("amount")
    if isinstance(amount, dict):
        return f"{amount.get('value')} {amount.get('currency', '')}".strip()
    return "-"


def show_adjudications(adjs: list, label: str) -> None:
    for adj in adjs or []:
        coding = first_coding(adj.get("category", {}))
        print(f"    {label}: code={short(coding.get('code'))} | display={short(coding.get('display'))} | amount={money(adj)}")


def summarize_money(eob: dict) -> None:
    print("\n=== MONEY SUMMARY (what the amounts are called) ===")
    print("Header-level adjudication:")
    show_adjudications(eob.get("adjudication"), "adj")
    print("Totals:")
    for total in eob.get("total") or []:
        coding = first_coding(total.get("category", {}))
        print(f"    total: code={short(coding.get('code'))} | display={short(coding.get('display'))} | amount={money(total)}")
    payment = eob.get("payment")
    if payment:
        print(f"Payment: amount={money(payment)}")
    items = eob.get("item") or []
    print(f"\nLine items: {len(items)} (showing up to {MAX_ITEMS_SHOWN})")
    for item in items[:MAX_ITEMS_SHOWN]:
        service = first_coding(item.get("productOrService", {}))
        when = item.get("servicedDate") or item.get("servicedPeriod")
        print(f"  item sequence={item.get('sequence')} | service={short(service.get('code'))} {short(service.get('display'))}"
              f" | serviced={short(when)} | quantity={short(item.get('quantity'))}")
        show_adjudications(item.get("adjudication"), "adj")


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python scripts/inspect_eob.py path/to/file.json")
    resources = unwrap(json.loads(Path(sys.argv[1]).read_text()))
    eobs = [r for r in resources if r.get("resourceType") == "ExplanationOfBenefit"]
    print(f"Resources in file: {len(resources)} | ExplanationOfBenefit resources: {len(eobs)}")
    if not eobs:
        sys.exit("No ExplanationOfBenefit found.")
    print("\n=== STRUCTURE OF THE FIRST EOB ===")
    outline(eobs[0])
    summarize_money(eobs[0])


if __name__ == "__main__":
    main()
