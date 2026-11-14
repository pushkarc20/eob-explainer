# Rules catalog

The rules engine is deterministic (no AI). It computes the numbers and the flags; an LLM later only
rephrases them. Flag text is templated, so the product still works if the LLM is unavailable.

## Definitions

| Figure | Definition | Source order |
|---|---|---|
| Billed | `submitted` amount | claim totals, claim header, sum of lines |
| Allowed | `eligible` amount | same |
| Plan paid | `paidtoprovider`, else `benefit`, else `payment.amount` | same, then claim payment |
| Patient responsibility | `memberliability` if reported; else deductible + copay + coinsurance, labelled "computed" | same |
| Patient has already paid | `paidbypatient` (not the same as what is owed) | same |

A missing figure is "not reported", never $0. Non-covered amounts are not added to computed patient
responsibility, because whether the patient owes them depends on the contract.

## Consistency checks (neutral wording)

- Line items vs claim total, per category, within $0.01.
- Allowed amount = plan paid + patient responsibility, when all three are reported.

A mismatch means "double-check", not "error": insurers report amounts differently.

## Flags

| Code | Severity | Fires when | Why it's worth asking | Deliberately does NOT claim |
|---|---|---|---|---|
| `possible_duplicate_line` | question | Same code + same day + same billed amount nets to 2 or more after reversals | A repeated entry would be worth confirming | That it is a billing error. Two units or modifiers can look identical. |
| `high_patient_share` | info or question | Patient share of the covered allowed amount (any non-covered amount is excluded, since it has its own flag) >= 50% and responsibility (same basis) >= $50. Info if itemized deductible/copay/coinsurance covers >= 90% of it | A large share is often legitimate (deductible) but worth understanding | That the share is wrong |
| `unitemized_patient_amount` | question | Reported responsibility exceeds itemized parts (deductible, copay, coinsurance, non-covered) by more than $1, and at least one part is itemized | The EOB does not explain all of the balance | That the balance is wrong |
| `noncovered_amount` | question | Non-covered amount > 0 | Patients can ask why, and whether appeal or recoding is possible | That the denial was wrong |
| `claim_has_reversals` | info | Any line has a negative billed amount | Explains why lines look odd; helps compare with earlier statements | What changed |

## Assumptions and known limits

- Duplicates are checked within one claim only. Cross-claim duplicates need a claim history (cut for the MVP).
- Modifiers are not compared in duplicate detection.
- Thresholds (50%, $50, 90%, $1) are product judgments, configurable in `Thresholds`, and will be
  tuned against the evaluation set.
- Network status (in/out of network) is not flagged yet.
- Only amount categories seen in CARIN examples or verified in the CARIN code system are interpreted;
  anything else is kept under `other` with a warning.

## Changelog

- Step 4: `high_patient_share` now excludes non-covered amounts from the share calculation. Found while
  writing the gold set: a claim with $300 not covered raised both the non-covered flag and the
  large-share flag, which was redundant and gave misleading advice.
- Step 9b: the duplicate-line question no longer says "two" (the AI judge noticed a three-line case); the
  large-share note names coinsurance; the fallback explanation opens with an "In short:" sentence and no longer
  says "paid or payable". Judge-input placeholders now resolve consistently when provider and insurer share a name.
