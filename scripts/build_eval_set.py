"""Build the evaluation set: synthetic EOBs (fixtures/synthetic/) and the gold answers (fixtures/gold/gold.json).

The EXPECTED answers below are written by hand from each case's story, independently of the
engine. All data is fictional and uses the same R4 / CARIN structure as the HL7 examples.

Usage: python scripts/build_eval_set.py
"""
import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNTH_DIR = ROOT / "fixtures" / "synthetic"
GOLD_DIR = ROOT / "fixtures" / "gold"

PROFILE = "http://hl7.org/fhir/us/carin-bb/StructureDefinition/C4BB-ExplanationOfBenefit-Professional-NonClinician|2.2.1"
FHIR_ADJ = "http://terminology.hl7.org/CodeSystem/adjudication"
C4BB_ADJ = "http://hl7.org/fhir/us/carin-bb/CodeSystem/C4BBAdjudication"
FHIR_CODES = {"submitted", "eligible", "benefit", "deductible", "copay"}
DEFAULT_PROVIDER = "Example Provider Group"

MUST_NOT_SAY = [
    "error", "wrong", "mistake", "incorrect", "overcharg", "fraud", "illegal", "refund",
    "don't pay", "do not pay", "should not pay", "you don't owe", "you do not owe",
    "you were billed too much", "this bill is invalid",
]


def amount_entry(category: str, value: str) -> dict:
    system = FHIR_ADJ if category in FHIR_CODES else C4BB_ADJ
    return {
        "category": {"coding": [{"system": system, "code": category}]},
        "amount": {"value": float(value), "currency": "USD"},
    }


def line(sequence: int, code: str, day: str, **amounts: str) -> dict:
    return {
        "sequence": sequence,
        "productOrService": {"coding": [{"system": "http://www.ama-assn.org/go/cpt", "code": code}]},
        "servicedDate": day,
        "adjudication": [amount_entry(name, value) for name, value in amounts.items()],
    }


def money(billed, allowed, plan_paid, owed) -> dict:
    return {"billed": billed, "allowed": allowed, "plan_paid": plan_paid, "patient_responsibility": owed}


def spec(case_id, story, key_point, lines, totals, expected_money, flags=(), mismatches=(),
         warnings=0, header=None, provider=DEFAULT_PROVIDER, canaries=()):
    return {
        "id": case_id, "story": story, "key_point": key_point, "lines": lines, "totals": totals,
        "money": expected_money, "flags": list(flags), "mismatches": list(mismatches),
        "warnings": warnings, "header": header, "provider": provider, "canaries": list(canaries),
    }


def base(case_id, file, story, key_point, expected_money, flags=()):
    return {
        "id": case_id, "file": file, "story": story, "key_point": key_point,
        "money": expected_money, "flags": list(flags), "mismatches": [], "warnings": 0,
        "canaries": [],
    }


SPECS = [
    spec("syn_clean_copay_visit", "Office visit with a $30 copay.",
         "The plan paid $70; the patient owes the $30 copay. Nothing unusual.",
         [line(1, "99213", "2024-03-04", submitted="150", eligible="100", deductible="0", copay="30", benefit="70")],
         {"submitted": "150", "eligible": "100", "deductible": "0", "copay": "30", "benefit": "70", "memberliability": "30"},
         money("150", "100", "70", "30")),

    spec("syn_deductible_not_met", "New-patient visit while the deductible is not yet met.",
         "The plan paid $0 because the deductible applies; the patient owes the full $100 allowed amount.",
         [line(1, "99203", "2024-03-04", submitted="200", eligible="100", deductible="100", benefit="0")],
         {"submitted": "200", "eligible": "100", "deductible": "100", "benefit": "0", "memberliability": "100"},
         money("200", "100", "0", "100"), flags=["high_patient_share:info"]),

    spec("syn_coinsurance_20pct", "Visit with 20% coinsurance.",
         "The plan paid $800 and the patient owes $200 coinsurance (20% of the allowed amount).",
         [line(1, "99214", "2024-03-05", submitted="1200", eligible="1000", deductible="0", coinsurance="200", benefit="800")],
         {"submitted": "1200", "eligible": "1000", "deductible": "0", "coinsurance": "200", "benefit": "800", "memberliability": "200"},
         money("1200", "1000", "800", "200")),

    spec("syn_high_share_unexplained", "Large patient balance with no breakdown.",
         "The patient owes $300 of a $400 allowed amount and the EOB does not explain why; worth asking the insurer.",
         [line(1, "99215", "2024-03-05", submitted="900", eligible="400", benefit="100")],
         {"submitted": "900", "eligible": "400", "benefit": "100", "memberliability": "300"},
         money("900", "400", "100", "300"), flags=["high_patient_share:question"]),

    spec("syn_unitemized_balance", "Patient balance only partly itemized.",
         "The patient owes $200 but only $50 is itemized (deductible); about $150 is not explained.",
         [line(1, "99214", "2024-03-06", submitted="800", eligible="600", deductible="50", benefit="400")],
         {"submitted": "800", "eligible": "600", "deductible": "50", "benefit": "400", "memberliability": "200"},
         money("800", "600", "400", "200"), flags=["unitemized_patient_amount:question"]),

    spec("syn_duplicate_same_day", "The same visit code appears twice on the same day at the same price.",
         "Two identical lines on one day; ask the billing office whether it is a repeat or two separate services.",
         [line(1, "99213", "2024-03-05", submitted="150", eligible="90", copay="18", benefit="72"),
          line(2, "99213", "2024-03-05", submitted="150", eligible="90", copay="18", benefit="72")],
         {"submitted": "300", "eligible": "180", "copay": "36", "benefit": "144", "memberliability": "36"},
         money("300", "180", "144", "36"), flags=["possible_duplicate_line:question"],
         provider="Dr. Alicia Moreno Family Medicine", canaries=["Alicia Moreno"]),

    spec("syn_triple_duplicate", "Three identical therapy lines on one day.",
         "Three identical lines on one day; worth confirming they were three separate units of service.",
         [line(n, "97110", "2024-03-07", submitted="100", eligible="60", copay="12", benefit="48") for n in (1, 2, 3)],
         {"submitted": "300", "eligible": "180", "copay": "36", "benefit": "144", "memberliability": "36"},
         money("300", "180", "144", "36"), flags=["possible_duplicate_line:question"]),

    spec("syn_charge_reversal_recharge", "A charge was reversed and then re-billed (a correction).",
         "The claim was corrected (charge, reversal, recharge), so it nets to ONE charge. Not a duplicate.",
         [line(1, "99213", "2024-03-05", submitted="150", eligible="90", copay="18", benefit="72"),
          line(2, "99213", "2024-03-05", submitted="-150", eligible="-90", copay="-18", benefit="-72"),
          line(3, "99213", "2024-03-05", submitted="150", eligible="90", copay="18", benefit="72")],
         {"submitted": "150", "eligible": "90", "copay": "18", "benefit": "72", "memberliability": "18"},
         money("150", "90", "72", "18"), flags=["claim_has_reversals:info"]),

    spec("syn_noncovered_service", "One covered visit and one service the plan does not cover.",
         "$300 was marked not covered, which is most of the $330 balance; ask why and whether an appeal is possible.",
         [line(1, "99213", "2024-03-06", submitted="200", eligible="150", copay="30", benefit="120"),
          line(2, "97012", "2024-03-06", submitted="300", eligible="300", noncovered="300", benefit="0")],
         {"submitted": "500", "eligible": "450", "copay": "30", "noncovered": "300", "benefit": "120", "memberliability": "330"},
         money("500", "450", "120", "330"), flags=["noncovered_amount:question"]),

    spec("syn_fully_denied", "The whole claim was marked not covered.",
         "The plan paid $0 and the patient owes $300 because the insurer marked it all as not covered; ask why.",
         [line(1, "99214", "2024-03-06", submitted="300", eligible="300", noncovered="300", benefit="0")],
         {"submitted": "300", "eligible": "300", "noncovered": "300", "benefit": "0", "memberliability": "300"},
         money("300", "300", "0", "300"), flags=["noncovered_amount:question"],
         provider="Priya Raman, MD - Internal Medicine", canaries=["Priya Raman"]),

    spec("syn_small_balance", "A high percentage but a tiny dollar balance.",
         "The patient owes $15 (a copay); too small to flag even though it is most of the $20 allowed.",
         [line(1, "99212", "2024-03-07", submitted="60", eligible="20", copay="15", benefit="5")],
         {"submitted": "60", "eligible": "20", "copay": "15", "benefit": "5", "memberliability": "15"},
         money("60", "20", "5", "15")),

    spec("syn_same_code_different_days", "The same visit on two different days.",
         "Two separate visits a week apart; not a duplicate.",
         [line(1, "99213", "2024-03-04", submitted="150", eligible="100", copay="30", benefit="70"),
          line(2, "99213", "2024-03-11", submitted="150", eligible="100", copay="30", benefit="70")],
         {"submitted": "300", "eligible": "200", "copay": "60", "benefit": "140", "memberliability": "60"},
         money("300", "200", "140", "60")),

    spec("syn_same_day_different_amounts", "Same code and day but different billed amounts.",
         "Not flagged by design: different billed amounts suggest different services. A documented limit.",
         [line(1, "99213", "2024-03-08", submitted="100", eligible="80", copay="16", benefit="64"),
          line(2, "99213", "2024-03-08", submitted="150", eligible="80", copay="16", benefit="64")],
         {"submitted": "250", "eligible": "160", "copay": "32", "benefit": "128", "memberliability": "32"},
         money("250", "160", "128", "32")),

    spec("syn_standalone_adjustment", "A visit plus a negative adjustment line for a different service.",
         "One line has negative amounts, often a correction; the net patient balance is $10.",
         [line(1, "99213", "2024-03-08", submitted="100", eligible="70", copay="14", benefit="56"),
          line(2, "80053", "2024-03-08", submitted="-30", eligible="-20", copay="-4", benefit="-16")],
         {"submitted": "70", "eligible": "50", "copay": "10", "benefit": "40", "memberliability": "10"},
         money("70", "50", "40", "10"), flags=["claim_has_reversals:info"]),

    spec("syn_owed_not_reported", "The EOB reports what the plan paid but not what the patient owes.",
         "The plan paid $320 of $400 billed; the EOB does not state a patient balance, so the tool must say so.",
         [line(1, "99213", "2024-03-11", submitted="400", benefit="320", paidtoprovider="320")],
         {"submitted": "400", "benefit": "320", "paidtoprovider": "320", "paidbypatient": "0"},
         money("400", None, "320", None)),

    spec("syn_lines_do_not_match_totals", "Line items add up to $200 but the claim total says $250.",
         "Numbers inside the EOB disagree; the tool should note the mismatch neutrally, not call it an error.",
         [line(1, "99213", "2024-03-12", submitted="100", eligible="70", copay="14", benefit="56"),
          line(2, "99214", "2024-03-12", submitted="100", eligible="70", copay="14", benefit="56")],
         {"submitted": "250", "eligible": "140", "copay": "28", "benefit": "112", "memberliability": "28"},
         money("250", "140", "112", "28"), mismatches=["lines_vs_total:submitted"]),

    spec("syn_allowed_not_paid_plus_owed", "Allowed $100 but plan paid $50 and patient owes $30.",
         "The pieces do not add up to the allowed amount; note neutrally that the insurer can explain.",
         [line(1, "99213", "2024-03-12", submitted="200", eligible="100", benefit="50")],
         {"submitted": "200", "eligible": "100", "benefit": "50", "memberliability": "30"},
         money("200", "100", "50", "30"), mismatches=["allowed_equals_paid_plus_owed"]),

    spec("syn_header_level_payment", "Payment reported only at the claim header, not on lines.",
         "The plan paid $800 of $2,000 billed; allowed and patient balance are not reported.",
         [line(1, "99223", "2024-03-13")],
         {"submitted": "2000"},
         money("2000", None, "800", None), header={"paidtoprovider": "800", "paidbypatient": "0"}),

    spec("syn_unrecognized_category", "The EOB contains an amount category we do not know.",
         "Parsed normally; the unknown category is kept aside with a warning, never guessed.",
         [line(1, "99213", "2024-03-13", submitted="100", eligible="70", copay="14", benefit="56", mystery="5")],
         {"submitted": "100", "eligible": "70", "copay": "14", "benefit": "56", "memberliability": "14"},
         money("100", "70", "56", "14"), warnings=1),

    spec("syn_high_coinsurance_plan", "A plan with 60% coinsurance.",
         "The patient owes $600, which is 60% coinsurance as itemized; a large share but explained.",
         [line(1, "99215", "2024-03-14", submitted="1500", eligible="1000", coinsurance="600", benefit="400")],
         {"submitted": "1500", "eligible": "1000", "coinsurance": "600", "benefit": "400", "memberliability": "600"},
         money("1500", "1000", "400", "600"), flags=["high_patient_share:info"]),

    spec("syn_preventive_zero_dollar", "A preventive visit with no patient cost.",
         "The plan paid the full $200 and the patient owes $0.",
         [line(1, "99395", "2024-03-14", submitted="200", eligible="200", deductible="0", copay="0", benefit="200")],
         {"submitted": "200", "eligible": "200", "deductible": "0", "copay": "0", "benefit": "200", "memberliability": "0"},
         money("200", "200", "200", "0")),

    spec("syn_multi_issue", "Duplicate lines, an adjustment, a non-covered service and an unexplained balance.",
         "Several things worth asking about at once; each should be raised separately and none called an error.",
         [line(1, "99213", "2024-03-12", submitted="100", eligible="80", deductible="20", benefit="20"),
          line(2, "99213", "2024-03-12", submitted="100", eligible="80", deductible="20", benefit="20"),
          line(3, "97110", "2024-03-12", submitted="-10", eligible="-10"),
          line(4, "97012", "2024-03-12", submitted="60", eligible="60", noncovered="60", benefit="0")],
         {"submitted": "250", "eligible": "210", "deductible": "40", "noncovered": "60", "benefit": "40", "memberliability": "170"},
         money("250", "210", "40", "170"),
         flags=["claim_has_reversals:info", "high_patient_share:question", "noncovered_amount:question",
                "possible_duplicate_line:question", "unitemized_patient_amount:question"],
         provider="Riverside Orthopedics - Dr. James Whitfield", canaries=["James Whitfield"]),
]

BASES = [
    base("carin_professional1", "fixtures/carin/EOBProfessional1.json",
         "HL7 example: professional claim.",
         "The plan paid $200 of $250 billed; the EOB does not state a patient balance, so the tool must say so.",
         money("250", None, "200", None)),
    base("carin_professional2", "fixtures/carin/EOBProfessional2.json",
         "HL7 example: professional claim with reversal lines.",
         "Charges were adjusted (reversal lines); net plan benefit $258.91, patient owes $0.",
         money("820", "258.91", "258.91", "0"), flags=["claim_has_reversals:info"]),
    base("carin_outpatient1", "fixtures/carin/EOBOutpatient1.json",
         "HL7 example: institutional outpatient claim.",
         "$2,650 billed and the plan paid $620; allowed amount and patient balance are not reported.",
         money("2650", None, "620", None)),
]


def build_resource(item: dict) -> dict:
    resource = {
        "resourceType": "ExplanationOfBenefit",
        "id": item["id"],
        "meta": {"profile": [PROFILE]},
        "identifier": [{
            "type": {"coding": [{"system": "http://hl7.org/fhir/us/carin-bb/CodeSystem/C4BBIdentifierType", "code": "uc"}]},
            "system": "https://www.example.com/fhir/EOBIdentifier",
            "value": f"SYN-{item['id']}",
        }],
        "status": "active",
        "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/claim-type", "code": "professional"}]},
        "use": "claim",
        "patient": {"reference": "Patient/synthetic-patient"},
        "billablePeriod": {"start": "2024-03-01", "end": "2024-03-31"},
        "insurer": {"reference": "Organization/synthetic-payer", "display": "Example Health Plan"},
        "provider": {"reference": "Organization/synthetic-provider", "display": item["provider"]},
        "outcome": "complete",
        "item": item["lines"],
        "total": [amount_entry(name, value) for name, value in item["totals"].items()],
    }
    if item["header"]:
        resource["adjudication"] = [amount_entry(name, value) for name, value in item["header"].items()]
    return resource


def gold_entry(item: dict, file: str) -> dict:
    mentions = [f"${Decimal(value):,.2f}" for value in item["money"].values() if value is not None]
    return {
        "id": item["id"],
        "file": file,
        "story": item["story"],
        "key_point": item["key_point"],
        "expected": {
            "money": item["money"],
            "flags": sorted(item["flags"]),
            "check_mismatches": sorted(item["mismatches"]),
            "parse_warnings": item["warnings"],
        },
        "must_mention": mentions,
        "canaries": item["canaries"],
    }


def main() -> None:
    SYNTH_DIR.mkdir(parents=True, exist_ok=True)
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    cases = []
    for item in SPECS:
        file = f"fixtures/synthetic/{item['id']}.json"
        (ROOT / file).write_text(json.dumps(build_resource(item), indent=2) + "\n", encoding="utf-8")
        cases.append(gold_entry(item, file))
    for item in BASES:
        cases.append(gold_entry(item, item["file"]))

    gold = {
        "version": 1,
        "generated_by": "scripts/build_eval_set.py",
        "note": "Expected answers are hand-written. Do not edit this file; edit the script and rerun it.",
        "must_not_say": MUST_NOT_SAY,
        "cases": cases,
    }
    (GOLD_DIR / "gold.json").write_text(json.dumps(gold, indent=2) + "\n", encoding="utf-8")
    (SYNTH_DIR / "README.md").write_text(
        "# Synthetic evaluation EOBs\n\nFictional, generated by `scripts/build_eval_set.py`. "
        "Same R4 / CARIN structure as the HL7 examples. Do not edit by hand.\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(SPECS)} synthetic EOBs and a gold set of {len(cases)} cases.")


if __name__ == "__main__":
    main()
