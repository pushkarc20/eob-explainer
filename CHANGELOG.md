# Changelog

## v0.2.0 (2026-11-26)

Evaluation release: a held-out set, a judge fix, and a cost-versus-quality comparison. No prompt changed.

- Held-out evaluation set: 15 synthetic claims with expected answers derived by hand, frozen by hash before the rules engine or any model ran on them (`fixtures/heldout/`, `scripts/build_heldout_set.py`).
- Rules engine: the allowed-amount check now counts another payer's payment. Found by the held-out set (14 of 15 before the fix, 15 of 15 after; the development set stayed at 25 of 25).
- Questions: when the EOB already itemizes a large patient share, the fixed question asks about the deductible and out-of-pocket limit instead of asking what makes up the amount.
- Judge j2: one-sentence definitions of standard billing terms are no longer scored as unsupported. The j1 text is kept. Scores from v0.1.0 came from j1 and are not comparable with j2 scores.
- Cost versus quality: Claude Haiku 5.5 and low-effort Sonnet 5.5 evaluated on both sets. Under the decision rule, Haiku is recommended (about 91% cheaper per explanation) and low effort is not (about 2% cheaper). The default stays Sonnet 5.5 with prompt v2.
- Decision rules as code (`src/eob/decisions.py`, `scripts/apply_v02_rules.py`). Prompt v2 stays the default: four of five criteria passed, and key point fell by 0.33 on the held-out set. See `docs/v0.2_decisions.md` and `docs/v0.2_plan.md`.
- `EOB_CLOUD_EFFORT=default` leaves the effort parameter out, as in the Haiku evaluation.
- Repository: issue and pull request templates, CONTRIBUTING.md, `scripts/dev.sh`, and tests that keep the docs index and links in sync.

## v0.1.0 (2026-11-23)

First public version.

- Parser for FHIR R4 `ExplanationOfBenefit` (CARIN Blue Button style) into an allow-list model; money kept as `Decimal`, "not reported" kept distinct from zero.
- Rules engine: money waterfall with sources, consistency checks, five "worth asking" flags, netting of reversals.
- Explanation: a built-in deterministic version, and Claude (Sonnet 5.5) with prompt v2 behind a code validator, one retry, and a fallback.
- Privacy layer: placeholders, Presidio scan, fail-closed leak guard, and a consent step that sends only the exact payload you reviewed.
- Local message drafter with fixed, tested questions.
- Streamlit app (local only; Deploy button hidden; getting-started guidance) and command-line scripts.
- Evaluation: 25-case gold set; rules engine 25 of 25; explanation systems compared with an LLM judge, under a pre-registered decision rule.
- 209 automated tests, including checks that a run writes no files, opens no connections, and logs no identifiers.

Known issues and limits: see the README ("Known issues", "Limitations and risks").
