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
