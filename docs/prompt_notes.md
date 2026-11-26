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

## Outcome of the v1 vs v2 evaluation (25 gold cases, one run each, judge j1)

| Criterion | v1 | v2 | Result |
|---|---|---|---|
| 1. Passed code checks on first try (need 24 or more of 25) | 25 | 24 (1 retry, 0 fallbacks) | Pass, exactly at the threshold |
| 2. Faithfulness no lower than v1 | 4.20 | 4.32 | Pass |
| 3. Concision improves by 0.4 or more | 3.16 | 4.00 | Pass (+0.84) |
| 4. Key point drops by 0.2 or less | 4.20 | 4.08 | Pass (-0.12) |
| 5. No leaks, no overclaiming | 0 and 0 | 0 leaks in 51 requests, 0 | Pass |

Decision: v2 is now the default prompt (DEFAULT_PROMPT_VERSION = "v2"). v1 is kept for comparison.

Other measurements
- Unsupported claims found by the judge: 38 (v1) to 26 (v2). Reading grade 5.5 to 5.8. Mean tokens in/out 1417/706 to 1866/505.
- v2 is cheaper and faster: $0.0099 to $0.0088 per explanation, 6.4 s to 4.2 s on average.
- Template baseline (after the 9b fixes): faithfulness 4.52, key point 3.20, concision 3.88, reading grade 6.7, unsupported claims 11.
  Claude's advantage is the key point (about 4.1 against 3.2); the template is slightly more faithful.
- Noise estimate: v1 ran in both 9a and 9b. Judge means differed by 0.08 or less, so the concision gain and the drop in
  unsupported claims are well outside the noise; the faithfulness gain (+0.12) and key-point dip (-0.12) are not clearly so.
- The hypothesis that the template's "In short:" sentence would raise its key-point score was not supported
  (3.16 to 3.20, within noise).

Limitations and follow-ups
- The 25 gold cases were both my development set and my test set. I wrote v2's rules after reading v1's failures on
  them, so part of the gain may be fit to those cases. A held-out set of new cases is the right check.
- Criterion 1 passed with no margin (24 of 25), so it is weak evidence on its own.
- Harness bug found and fixed: the "Cases to review" list was capped at 30 notes overall, so the last configuration (v2)
  was hidden. It is now worst-first, up to 10 per configuration.
- Backlog for a possible v3 or template fix: for a large-share flag that the EOB already explains as deductible or
  coinsurance, the fixed question ("how much is deductible, copay or coinsurance?") reads oddly; the judge flagged it.

## Judge j2 (v0.2)

j1 flagged one-sentence definitions of standard billing terms as unsupported, because it never saw that prompt v2 allows
them. j2 is j1 plus one rule: a short, general definition of a standard billing term is allowed, provided it states no
fact about the claim that the data does not support. j1's text is kept in the code (`JUDGE_SYSTEM_J1`). The j1 results
are archived (docs/eval/archive/9b/) before the v0.2 runs. Every v0.2 score is a j2 score, and j1 and j2 numbers are not comparable.

## v0.2 human spot-check

The author read the Sonnet (medium, v2) and Haiku (v2) answers side by side for three claims (syn_duplicate_same_day,
syn_noncovered_service, carin_professional2). Both read fine; Sonnet seemed slightly better. This is informal: three
claims and one reader, so it supports "Haiku is acceptable" without being a quality measurement. It is consistent with the
judge, which scored Haiku's key point lower (3.88 against 4.03, both sets pooled).
