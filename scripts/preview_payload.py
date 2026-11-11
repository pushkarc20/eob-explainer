"""Show exactly what would leave the device for one EOB in cloud mode. NOTHING is sent.

Usage:
    python scripts/preview_payload.py fixtures/synthetic/syn_duplicate_same_day.json
"""
import json
import sys

from eob.engine import analyze
from eob.parser import parse_eob
from eob.privacy import collect_blocked_values, prepare_cloud_payload
from healthcore.fhir.helpers import load_resource
from healthcore.privacy.guard import LeakError
from healthcore.privacy.pseudonymizer import Pseudonymizer


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python scripts/preview_payload.py path/to/eob.json")
    raw = load_resource(sys.argv[1])
    eob = parse_eob(raw)
    try:
        prepared = prepare_cloud_payload(
            eob, analyze(eob), Pseudonymizer(), blocked_values=collect_blocked_values(raw)
        )
    except LeakError as error:
        print(f"LEAK GUARD: {error}")
        sys.exit(1)

    print("=== EXACTLY WHAT WOULD BE SENT (cloud + redaction mode) ===")
    print(json.dumps(json.loads(prepared.json_text), indent=2))
    print("\n=== REPLACED LOCALLY BY PLACEHOLDERS (counts only; real values stay on this machine) ===")
    for kind, count in sorted(prepared.replaced.items()):
        print(f"  {kind}: {count}")
    if not prepared.replaced:
        print("  (none)")
    print("\n=== PRESIDIO FINDINGS IN FREE TEXT (entity types only) ===")
    for entity, count in sorted(prepared.scrub_counts.items()):
        print(f"  {entity}: {count}")
    if not prepared.scrub_counts:
        print("  (none)")
    print("\nNever parsed, so never sent: patient name/ID/address/birth date, member IDs, claim number,")
    print("provider IDs (NPI), diagnoses, supporting info, notes.")
    print("Leak guard: PASSED")


if __name__ == "__main__":
    main()
