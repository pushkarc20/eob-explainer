# Prompt log

## v1 (PROMPT_VERSION = "v1")

First live run: `syn_duplicate_same_day`, `claude-sonnet-5-5`, effort `medium`.
Result: verified on the first attempt. 1 request, 1,491 input / 675 output tokens, about $0.01.

What worked
- Placeholders round-tripped: the model saw only [PROVIDER_1], [INSURER_1], [DATE_1]; real values were restored locally.
- All amounts grounded in the data; the flag was phrased as a question; next steps pointed to the insurer or billing office.
- The model did not invent a description for a service code that the EOB did not describe.

Candidates for v2 (not applied; a change is made only when the evaluation set shows it helps)
1. The "not_reported" list is padded with routine fields (deductible, coinsurance, non-covered, prior payer)
   that do not matter when the balance is fully explained. Ask for only items a patient would need.
2. Relational statements ("matches the copay total") are not covered by the number validator.
   Step 9 adds a judge-based faithfulness score.
3. Rendering: AI flag questions are phrased as questions, the template's are instructions.
   Step 7 adds a deterministic question to every flag and a consistent "Question to ask" label.
4. Code meanings: CPT descriptions are licensed by the AMA, so the tool shows a description only if the EOB provides one.
5. Effort sweep in Step 9: compare low, medium and high on quality, latency and cost.

## 9a baseline (prompt v1, judge j1, 25 gold cases, one run each)

Claude Sonnet 5.5 (medium) vs the built-in template: passed the code checks 25 of 25 on the first try; every expected
figure shown; no overclaiming; reading grade 5.5 vs 7.4; judge key point 4.16 vs 3.16; faithfulness 4.20 vs 4.32; tone
4.72 vs 4.64; concision 3.12 vs 3.92; unsupported claims 36 vs 14; 0 planted-name leaks across 75 requests; about
$0.0096 and 6.3 seconds per explanation. Results are archived in docs/eval/archive/9a/.

What the judge's flags turned out to be
- A bug in my template: the fixed duplicate question said "two separate services" on a three-line case. Fixed.
- A measurement artifact: provider and insurer share one display name in the HL7 Professional 1 example, so my judge
  input swapped placeholders and produced the two lowest faithfulness scores. Fixed (judge the verified answer in
  placeholder form; first-registered placeholder wins on ambiguous names).
- Wording that did not fit every claim: the large-share note omitted coinsurance. Fixed.
- Prompt and model issues, addressed in v2: describing code 99213 as an "office visit" with no description in the data;
  "paid to the provider"; pairing specific lines as reversals; dropping the basis of a flag's figure; a padded
  "not stated" list.
- Judge limits, NOT changed so the comparison stays fair: the judge never sees my glossary, so it flags standard
  one-sentence definitions as unsupported.

## Decision rule for adopting prompt v2 (written BEFORE the v2 run)

Adopt v2 only if, against v1 on the same 25 cases and the fixed harness:
1. at least 24 of 25 answers pass the code checks on the first try;
2. judge faithfulness is no lower than v1;
3. judge concision improves by at least 0.4;
4. judge key point drops by no more than 0.2;
5. there are no planted-name leaks and no overclaiming phrases.
One run per configuration is noisy, so a result close to a threshold is inconclusive and not a pass.
