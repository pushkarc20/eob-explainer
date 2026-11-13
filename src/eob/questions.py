"""Fixed, first-person questions for each flag.

Deterministic, so the message to the insurer never depends on AI wording. Wording rules (enforced by
tests): every question asks and none concludes; none says a charge is wrong, and none makes a legal claim.
"""

QUESTIONS = {
    "possible_duplicate_line": (
        "Can you tell me whether these were two separate services or one entry that was repeated, "
        "and how each line was processed?"
    ),
    "high_patient_share": (
        "Can you explain how this amount was calculated, and how much of it is deductible, copay or coinsurance?"
    ),
    "unitemized_patient_amount": (
        "Can you tell me what makes up the part of my responsibility that is not broken down on the EOB?"
    ),
    "noncovered_amount": (
        "Can you tell me why this amount was marked as not covered, and whether I can ask for it to be reviewed?"
    ),
    "claim_has_reversals": (
        "Can you confirm which version of this claim is current, and whether my balance changed after the adjustment?"
    ),
}

GENERIC_QUESTION = "Can you explain this item?"
