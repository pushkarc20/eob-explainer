"""Build the HELD-OUT evaluation set: 15 synthetic EOBs and their expected answers.

The expected answers were derived by hand from docs/rules.md, before the rules engine or any model was run on
these claims. They must not be used to tune prompts or rules (see docs/v0.2_plan.md). This generator also checks
the arithmetic of the data it writes, without using the engine, to catch typos in the hand-derived numbers.

Usage: python scripts/build_heldout_set.py
"""
import hashlib
import json
from datetime import date, timedelta
from decimal import Decimal

from build_eval_set import (
    MUST_NOT_SAY,
    ROOT,
    build_resource,
    gold_entry,
    line,
    money,
    spec,
)

HELDOUT_DIR = ROOT / "fixtures" / "heldout"
WEEKLY_DATES = [(date(2024, 1, 8) + timedelta(weeks=n)).isoformat() for n in range(12)]

HELDOUT = [
    spec("ho_01_er_itemized", "Emergency room visit with a deductible and coinsurance, fully itemized.",
         "The plan paid $1,120 of the $1,900 allowed. The $780 you owe is $500 deductible plus $280 coinsurance.",
         [line(1, "99285", "2024-02-10", submitted="3800", eligible="1500", deductible="500", coinsurance="200", benefit="800"),
          line(2, "85025", "2024-02-10", submitted="1000", eligible="400", coinsurance="80", benefit="320")],
         {"submitted": "4800", "eligible": "1900", "deductible": "500", "coinsurance": "280", "benefit": "1120", "memberliability": "780"},
         money("4800", "1900", "1120", "780"),
         provider="Mehta Emergency Medicine Group - Dr. Rohan Mehta", canaries=["Rohan Mehta"]),

    spec("ho_02_specialist_40pct", "Specialist consultation where the plan paid 40% and only part of the balance is itemized.",
         "You owe $600 of the $1,000 allowed, but the EOB itemizes only $100 of it as coinsurance; worth asking about the rest.",
         [line(1, "99244", "2024-05-14", submitted="1500", eligible="1000", coinsurance="100", benefit="400")],
         {"submitted": "1500", "eligible": "1000", "coinsurance": "100", "benefit": "400", "memberliability": "600"},
         money("1500", "1000", "400", "600"),
         flags=["high_patient_share:question", "unitemized_patient_amount:question"]),

    spec("ho_03_secondary_payer", "A prior payer paid part of the claim before this plan.",
         "Another payer paid $300 first, this plan paid $140, and you owe $60; together they equal the $500 allowed amount.",
         [line(1, "99214", "2024-06-18", submitted="800", eligible="500", priorpayerpaid="300", copay="60", benefit="140")],
         {"submitted": "800", "eligible": "500", "priorpayerpaid": "300", "copay": "60", "benefit": "140", "memberliability": "60"},
         money("800", "500", "140", "60")),

    spec("ho_04_labs_deductible", "Three lab tests on one day, all applied to the deductible.",
         "The plan paid $0 because the full $90 allowed amount went to your deductible.",
         [line(1, "80053", "2024-07-23", submitted="70", eligible="30", deductible="30", benefit="0"),
          line(2, "85025", "2024-07-23", submitted="45", eligible="25", deductible="25", benefit="0"),
          line(3, "80061", "2024-07-23", submitted="60", eligible="35", deductible="35", benefit="0")],
         {"submitted": "175", "eligible": "90", "deductible": "90", "benefit": "0", "memberliability": "90"},
         money("175", "90", "0", "90"), flags=["high_patient_share:info"]),

    spec("ho_05_preventive_vaccine", "A preventive visit and a vaccine, both covered in full.",
         "The plan paid the full $320 and you owe $0.",
         [line(1, "99395", "2024-08-06", submitted="220", eligible="220", deductible="0", copay="0", benefit="220"),
          line(2, "90686", "2024-08-06", submitted="100", eligible="100", deductible="0", copay="0", benefit="100")],
         {"submitted": "320", "eligible": "320", "deductible": "0", "copay": "0", "benefit": "320", "memberliability": "0"},
         money("320", "320", "320", "0")),

    spec("ho_06_uneven_cents", "Three therapy lines whose cents do not divide evenly.",
         "The plan paid $88.89 and you owe $22.22 of the $111.11 allowed.",
         [line(1, "97110", "2024-09-03", submitted="111.11", eligible="37.04", copay="7.41", benefit="29.63"),
          line(2, "97112", "2024-09-03", submitted="111.11", eligible="37.04", copay="7.41", benefit="29.63"),
          line(3, "97140", "2024-09-03", submitted="111.11", eligible="37.03", copay="7.40", benefit="29.63")],
         {"submitted": "333.33", "eligible": "111.11", "copay": "22.22", "benefit": "88.89", "memberliability": "22.22"},
         money("333.33", "111.11", "88.89", "22.22")),

    spec("ho_07_twelve_weekly_visits", "Twelve weekly physical therapy visits on one claim.",
         "Twelve separate weekly visits; the plan paid $540 and you owe $180 in copays.",
         [line(n + 1, "97110", day, submitted="90", eligible="60", copay="15", benefit="45") for n, day in enumerate(WEEKLY_DATES)],
         {"submitted": "1080", "eligible": "720", "copay": "180", "benefit": "540", "memberliability": "180"},
         money("1080", "720", "540", "180"),
         provider="Rao Physical Therapy - Sunita Rao, DPT", canaries=["Sunita Rao"]),

    spec("ho_08_header_only_amounts", "Amounts reported only at the claim header, not on the line.",
         "The plan paid $1,450 of $3,200 billed; the allowed amount and what you owe are not stated.",
         [line(1, "99223", "2024-10-01")],
         {"submitted": "3200"},
         money("3200", None, "1450", None), header={"paidtoprovider": "1450"}),

    spec("ho_09_two_unknown_categories", "The EOB includes two amount categories this tool does not recognize.",
         "Read normally: the plan paid $184 and you owe $46; the two unknown categories are set aside with warnings.",
         [line(1, "99213", "2024-10-15", submitted="300", eligible="230", copay="46", benefit="184", mystery_a="5", mystery_b="9")],
         {"submitted": "300", "eligible": "230", "copay": "46", "benefit": "184", "memberliability": "46"},
         money("300", "230", "184", "46"), warnings=2),

    spec("ho_10_share_at_threshold", "A balance of exactly 50% of the allowed amount and exactly $50.",
         "You owe $50 of the $100 allowed with no breakdown; worth asking how it was calculated.",
         [line(1, "99213", "2024-11-05", submitted="150", eligible="100", benefit="50")],
         {"submitted": "150", "eligible": "100", "benefit": "50", "memberliability": "50"},
         money("150", "100", "50", "50"), flags=["high_patient_share:question"]),

    spec("ho_11_unitemized_gap_exactly_one_dollar", "The balance is exactly $1.00 more than the itemized copay.",
         "You owe $41 and $40 is itemized as a copay; a $1.00 difference is below the point worth asking about.",
         [line(1, "99213", "2024-11-12", submitted="160", eligible="120", copay="40", benefit="79")],
         {"submitted": "160", "eligible": "120", "copay": "40", "benefit": "79", "memberliability": "41"},
         money("160", "120", "79", "41")),

    spec("ho_12_unitemized_gap_over_one_dollar", "The balance is $1.01 more than the itemized copay.",
         "You owe $41.01 and only $40 is itemized as a copay; the $1.01 difference is worth asking about.",
         [line(1, "99213", "2024-11-19", submitted="160", eligible="120", copay="40", benefit="78.99")],
         {"submitted": "160", "eligible": "120", "copay": "40", "benefit": "78.99", "memberliability": "41.01"},
         money("160", "120", "78.99", "41.01"), flags=["unitemized_patient_amount:question"]),

    spec("ho_13_reversal_with_deductible", "A charge, its reversal, and the charge again, all applied to the deductible.",
         "The claim was corrected and nets to one charge; the plan paid $0 and the $120 allowed went to your deductible.",
         [line(1, "99213", "2024-12-03", submitted="180", eligible="120", deductible="120", benefit="0"),
          line(2, "99213", "2024-12-03", submitted="-180", eligible="-120", deductible="-120", benefit="0"),
          line(3, "99213", "2024-12-03", submitted="180", eligible="120", deductible="120", benefit="0")],
         {"submitted": "180", "eligible": "120", "deductible": "120", "benefit": "0", "memberliability": "120"},
         money("180", "120", "0", "120"), flags=["claim_has_reversals:info", "high_patient_share:info"]),

    spec("ho_14_noncovered_twice", "The same non-covered service appears twice on one day.",
         "Both lines were marked not covered, so the plan paid $0 and you owe $200; ask whether the service was entered twice.",
         [line(1, "97012", "2024-12-10", submitted="100", eligible="100", noncovered="100", benefit="0"),
          line(2, "97012", "2024-12-10", submitted="100", eligible="100", noncovered="100", benefit="0")],
         {"submitted": "200", "eligible": "200", "noncovered": "200", "benefit": "0", "memberliability": "200"},
         money("200", "200", "0", "200"),
         flags=["noncovered_amount:question", "possible_duplicate_line:question"],
         provider="Joshi Wellness Clinic - Dr. Kavita Joshi", canaries=["Kavita Joshi"]),

    spec("ho_15_totals_disagree", "The copay total disagrees with the lines, and the figures do not add up to the allowed amount.",
         "Numbers inside the EOB disagree; the tool should say so neutrally and not call it an error.",
         [line(1, "99213", "2024-12-17", submitted="150", eligible="100", copay="20", benefit="80"),
          line(2, "99214", "2024-12-17", submitted="200", eligible="100", copay="20", benefit="80")],
         {"submitted": "350", "eligible": "200", "copay": "50", "benefit": "160", "memberliability": "50"},
         money("350", "200", "160", "50"),
         mismatches=["allowed_equals_paid_plus_owed", "lines_vs_total:copay"]),
]


def declared_paid(item: dict, totals: dict) -> Decimal | None:
    header = {key: Decimal(value) for key, value in (item["header"] or {}).items()}
    for source in (totals, header):
        if "paidtoprovider" in source:
            return source["paidtoprovider"]
    return totals.get("benefit")


def check_arithmetic(item: dict) -> None:
    """Arithmetic sanity of the data I wrote, independent of the rules engine."""
    case = item["id"]
    totals = {key: Decimal(value) for key, value in item["totals"].items()}
    sums: dict[str, Decimal] = {}
    for entry in item["lines"]:
        for adjudication in entry["adjudication"]:
            code = adjudication["category"]["coding"][0]["code"]
            sums[code] = sums.get(code, Decimal(0)) + Decimal(str(adjudication["amount"]["value"]))
    for code, total in totals.items():
        if code in sums and f"lines_vs_total:{code}" not in item["mismatches"]:
            assert sums[code] == total, f"{case}: lines add up to {sums[code]} but the total for {code} is {total}"

    expected = {key: None if value is None else Decimal(value) for key, value in item["money"].items()}
    paid = declared_paid(item, totals)
    assert expected["billed"] == totals.get("submitted"), f"{case}: expected billed does not match the data"
    assert expected["allowed"] == totals.get("eligible"), f"{case}: expected allowed does not match the data"
    assert expected["plan_paid"] == paid, f"{case}: expected plan paid does not match the data"
    assert expected["patient_responsibility"] == totals.get("memberliability"), f"{case}: expected owed does not match the data"

    allowed, owed = totals.get("eligible"), totals.get("memberliability")
    if None not in (allowed, paid, owed) and "allowed_equals_paid_plus_owed" not in item["mismatches"]:
        prior = totals.get("priorpayerpaid", Decimal(0))
        assert allowed == prior + paid + owed, f"{case}: allowed {allowed} != prior {prior} + paid {paid} + owed {owed}"


def main() -> None:
    ids = [item["id"] for item in HELDOUT]
    assert len(ids) == 15 and len(set(ids)) == 15, "expected 15 unique held-out cases"
    for item in HELDOUT:
        check_arithmetic(item)

    HELDOUT_DIR.mkdir(parents=True, exist_ok=True)
    cases = []
    for item in HELDOUT:
        file = f"fixtures/heldout/{item['id']}.json"
        (ROOT / file).write_text(json.dumps(build_resource(item), indent=2) + "\n", encoding="utf-8")
        cases.append(gold_entry(item, file))

    gold = {
        "version": 1,
        "generated_by": "scripts/build_heldout_set.py",
        "note": (
            "HELD-OUT set. Expected answers were derived by hand before any model or the rules engine ran on these "
            "claims. Do not tune against it. Do not edit this file; edit the generator and re-run it, which changes "
            "the recorded hash visibly."
        ),
        "must_not_say": MUST_NOT_SAY,
        "cases": cases,
    }
    text = json.dumps(gold, indent=2) + "\n"
    (HELDOUT_DIR / "gold.json").write_text(text, encoding="utf-8")
    (HELDOUT_DIR / "gold.sha256").write_text(hashlib.sha256(text.encode("utf-8")).hexdigest() + "\n", encoding="utf-8")
    (HELDOUT_DIR / "README.md").write_text(
        "# Held-out evaluation set\n\nFictional claims generated by `scripts/build_heldout_set.py`, with expected answers "
        "derived by hand before any model or the rules engine ran on them. Not used for tuning. See `docs/v0.2_plan.md`.\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(HELDOUT)} held-out EOBs, the gold answers, and their recorded hash.")


if __name__ == "__main__":
    main()