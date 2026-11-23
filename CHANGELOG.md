# Changelog

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
