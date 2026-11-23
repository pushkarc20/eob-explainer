# EOB Explainer

![tests](https://github.com/pushkarc20/eob-explainer/actions/workflows/tests.yml/badge.svg)

**A patient-facing tool that turns a FHIR `ExplanationOfBenefit` into a plain-language explanation, points out questions worth asking, and drafts a message to the insurer. Built privacy-first, on synthetic data only.**

> Portfolio project. Not medical, legal, or billing advice. It never says a bill is wrong; it helps you ask good questions.

![Explanation tab](docs/images/app-explanation.png)
![What will be sent to the cloud model](docs/images/app-payload.png)

## Independence and data statement

- This is a personal learning project, built on personal time and personal equipment.
- It uses no employer code, data, documents, or confidential knowledge, and is not affiliated with or derived from any employer's product.
- **Synthetic or public data only.** No real patient data is used, ever. All names in the test data (providers, members) are fictional.
- Not affiliated with HL7, CMS, or Anthropic. It uses HL7's public CARIN Blue Button example resources and Anthropic's Claude API.

## 1. The problem

An Explanation of Benefits (EOB) is what a health plan sends after it processes a claim. It is dense, full of codes, and easy to misread. People cannot tell what they owe, why, or whether anything deserves a question. Some pay without asking; others call the insurer without knowing what to ask.

The data is increasingly available in machine-readable form. The CMS Interoperability and Prior Authorization rule (CMS-0057-F, published February 2024) requires Medicare Advantage organizations, state Medicaid and CHIP programs and their managed care plans, and Qualified Health Plan issuers on the federal exchanges to maintain FHIR-based APIs. It builds on the 2020 Patient Access rule and adds prior authorization information to the Patient Access API by January 1, 2027. Original Medicare is outside that rule; its separate Blue Button 2.0 API serves a similar purpose. Raw FHIR is unreadable to a patient, so the gap is explanation.

This project works with the payer-neutral FHIR R4 format used by claims APIs (the CARIN Blue Button profile), so it models what a consumer app built on a payer's Patient Access API would receive.

## 2. Who it is for

**Primary user:** a health plan member who has just received an EOB and is not a billing expert.

Jobs to be done:
1. "Tell me what I owe, and why."
2. "Tell me whether anything is worth asking about."
3. "Help me ask, without starting from a blank page."

Not built: caregivers or advocates acting for someone else; providers (that is the planned Project B).

## 3. Product principles

1. **Facts from code, words from the model.** A rules engine computes every number and flag. A language model may only rephrase verified facts, and code checks its answer.
2. **Questions, never conclusions.** Flags are phrased as questions for the insurer or the provider's billing office. The tool never says a charge is wrong, an error, or an overcharge, and gives no medical or legal advice.
3. **Privacy by structure.** The parser is an allow-list, so a patient name cannot reach the explainer because the schema cannot carry it. Redaction is a second layer, not the first.
4. **The AI is optional.** Without it (or when its answer fails verification), the user still gets a correct, plainer explanation.
5. **Honest about uncertainty.** "The EOB does not state this" is never shown as $0.

## 4. MVP and user stories

One FHIR R4 `ExplanationOfBenefit` in (a sample or an uploaded file); on screen only:

- **What happened:** a plain-language summary and the money: billed, allowed, plan paid, what you owe.
- **Questions to ask:** up to five rule-based flags (repeated service on one day, large share of the allowed amount, part of the balance not itemized, non-covered amount, adjustment lines).
- **Draft message:** a short written question to the insurer, assembled locally from fixed, tested templates.
- **Two modes:** built-in (nothing leaves the computer) or Claude with redaction (you approve the exact payload first).

User stories:
- As a member, I want to know what I owe and why, so I can decide whether to pay.
- As a member, I want unusual items pointed out as questions, so I know what to ask.
- As a member, I want a draft message I can edit, so I do not start from a blank page.
- As a privacy-conscious member, I want to see exactly what leaves my device before anything is sent.
- As a member, I want the tool to say when to ask my insurer or provider, because it cannot say a bill is wrong.

## 5. What I cut, and why

| Cut | Why |
|---|---|
| Live OAuth / Patient Access connection | Plumbing, not the learning goal. Claims are loaded from a file. |
| Medicare Blue Button sandbox data | The sandbox API refused command-line requests at the network edge from my network, and the sample file was an older FHIR version (STU3). The CARIN R4 examples are closer to what payers expose under CMS-0057-F anyway. |
| PDF or scanned EOBs (OCR) | Real EOBs are mostly PDFs, but that is a different problem. Top next step. |
| Cross-claim duplicate detection | Needs claim history. Duplicates are detected within one claim only. |
| In-network / out-of-network flag | I had not verified the exact code values. |
| Service code descriptions | CPT descriptions are licensed by the AMA, so a description is shown only if the EOB provides one. |
| Formal appeal letters, phone scripts, rights and deadlines | Depends on plan type, state, and deadlines; that is legal advice. The draft points to the denial notice instead. |
| AI-polished messages | The deterministic version is safer, testable, and keeps member details away from any model. |
| Accounts, database, history, hosting | Contradicts "nothing stored". The app is local-only by design. |
| Local model mode (Ollama) | Built with safety guards and tests, but even a 4B model strained an 8 GB laptop. Not evaluated; I would use 16 GB or more. |
| Multilingual | Stretch goal. |

## 6. How it works

```mermaid
flowchart LR
  subgraph Device["Your computer"]
    A["EOB (FHIR R4 JSON)"] --> B["Parser: allow-list model"]
    B --> C["Rules engine: figures, checks, flags"]
    C --> D["Built-in explanation, questions, draft message"]
    C --> E["Placeholders + Presidio scan"]
    E --> F["Leak guard + your approval"]
    K["Validator: numbers, flags, wording"] --> L["Restore real names and dates"]
    L --> M["Screen only; nothing stored"]
  end
  F -->|"placeholders and amounts only"| G["Claude API"]
  G -->|"JSON with placeholders"| K
  K -.->|"fails twice, or API error"| D
```

1. **Parse** (`eob/parser.py`): copies only declared fields into a typed model. Amounts are `Decimal`, never floats; "not reported" stays `None`, never 0.
2. **Rules engine** (`eob/money.py`, `eob/flags.py`): a money waterfall (billed, allowed, plan paid, patient responsibility), each figure labelled with where it came from; consistency checks worded neutrally; five flags with stated assumptions and thresholds (`docs/rules.md`). Repeated lines are netted against reversals, so a corrected claim is not flagged as a duplicate.
3. **Explain** (`eob/explainer.py`): in cloud mode, a payload of placeholders and amounts goes to Claude with a versioned prompt. The reply must be a JSON object that passes the validator, with one retry that sends back a list of problems. Otherwise the built-in explanation is used.
4. **Validate** (`eob/validate.py`): every dollar amount and percentage must appear in the data; no banned phrases; no invented placeholders or flags; each flag covered; the next step must point to the insurer or billing office; no identifier-like content.
5. **Draft** (`eob/drafter.py`): fixed first-person questions per flag; your name and member ID are typed locally and never sent.

## 7. Safety guardrails

- Flag wording is templated and tested against a banned-phrase list (error, wrong, overcharge, fraud, and so on); the same list is enforced on model output.
- Every explanation shows a fixed disclaimer. Every draft carries notes: review before sending, use the secure portal, no SSN or bank details, and for denials, a pointer to the denial notice for the review process and deadlines.
- Only "question" flags become questions in the message; "info" flags are noted, not asked.
- The tool states what it does not know rather than guessing ("not stated on this EOB").

## 8. Privacy design

Full detail: [`docs/privacy.md`](docs/privacy.md) and [`docs/stateless.md`](docs/stateless.md).

| Category | Examples | Handling |
|---|---|---|
| Never parsed, so never sent | Patient name, ID, address, birth date; member IDs; claim number; provider IDs; diagnoses; notes | Dropped by the allow-list parser |
| Replaced, then restored locally | Provider and insurer names, service dates | `[PROVIDER_1]`, `[DATE_1]`, ... (map lives in memory only) |
| Sent in cloud mode | Dollar amounts and their source, service codes, line numbers, flag text | Shown to you first; you must approve the exact payload |

- **Layers:** allow-list schema, known-value placeholders, a Presidio scan of free text, and a fail-closed leak guard that scans the exact outbound text.
- **Consent is enforced in code:** the send path compares the payload built at send time with the one you reviewed and cancels on any difference.
- **Stateless, tested:** across all 25 test claims, a patched filesystem shows no file writes, a blocked socket shows no network connections outside the model client, and a log capture finds none of the planted identifiers.
- **Provider data handling:** I chose a model that is not subject to mandatory retention, and the project does not use API features that store data. HIPAA readiness and zero data retention are organization-level arrangements that I did not enable because the data is synthetic.
- **This is risk reduction, not HIPAA compliance.** A real deployment needs a business associate agreement, security review, and legal sign-off.

## 9. Evaluation

Two evaluations, both on a 25-case gold set (3 HL7 example EOBs plus 22 synthetic scenarios, expected answers written independently of the code). Full reports: [`docs/eval_results.md`](docs/eval_results.md) and [`docs/eval_ai_results.md`](docs/eval_ai_results.md).

**The deterministic rules engine**

| Metric | Result |
|---|---|
| Cases fully correct | 25 of 25 |
| Money figures correct | 100 of 100 |
| Flag precision / recall | 100% / 100% (16 flags) |
| False alarms on clean claims | 0 of 13 |

**The explanation systems** (Claude Sonnet 5.5 at medium effort; an LLM judge with a fixed rubric, scoring 1 to 5)

| Metric | Built-in | Claude, prompt v1 | Claude, prompt v2 (default) |
|---|---|---|---|
| Answer passed all code checks on the first try | n/a | 25 of 25 | 24 of 25 (1 retry, 0 fallbacks) |
| Expected money figures shown | 92 of 92 | 92 of 92 | 92 of 92 |
| Cases with overclaiming phrases | 0 | 0 | 0 |
| Reading grade (lower is easier) | 6.7 | 5.5 | 5.8 |
| Judge: faithfulness | 4.52 | 4.20 | 4.32 |
| Judge: key point | 3.20 | 4.20 | 4.08 |
| Judge: clarity | 3.92 | 4.24 | 4.28 |
| Judge: tone and safety | 4.72 | 4.80 | 4.84 |
| Judge: concision | 3.88 | 3.16 | 4.00 |
| Unsupported claims the judge found | 11 | 38 | 26 |
| Mean cost per explanation | n/a | $0.0099 | $0.0088 |
| Mean seconds per explanation | under 0.1 | 6.4 | 4.2 |

Privacy audit: 0 planted-name leaks across all 126 requests to a model in the final run, including the judge's. Every request is scanned independently for the planted provider names and every identifier the pipeline knows.

**Reading it.** The AI's advantage is the *key point*: it says what the claim means (about 4.1 against 3.2). The built-in version is slightly more faithful. Prompt v2 was adopted under a decision rule written and committed before the run (see [`docs/prompt_notes.md`](docs/prompt_notes.md)); all five criteria passed, with the first-try criterion exactly at its threshold.

**Caveats, stated plainly**
- The judge is a model too (the same family as the writer), so it may favor similar writing. Its scores are a screening signal, not a substitute for human review.
- 25 cases and one run per configuration. v1 ran twice and its judge means differed by 0.08 or less, which suggests the larger changes (concision, unsupported claims) are real and the smaller ones (faithfulness, key point) are not clearly so.
- The gold set was both my development set and my test set. I wrote prompt v2's rules after reading v1's failures on it, so some of the gain may be fit to those cases. A held-out set is the right next check.
- The test claims are idealized or synthetic. Real payer EOBs vary far more.

## 10. Decisions, and what building it taught me

- **R4 and CARIN, not the Medicare sample.** The sample EOB I had was an older FHIR version (STU3). Reading its structure before writing a parser changed the plan.
- **Deterministic first, AI second.** The AI scored higher on clarity but also produced more unsupported claims, which is why code verification stays in the loop.
- **An AI judge found a bug in my own template.** A fixed question said "two separate services" on a three-line claim. Evaluating the "boring" deterministic layer paid off.
- **A bug in my own evaluation report** capped the "cases to review" list so the newest prompt's cases were hidden. Found, fixed, and noted.
- **Pre-registered decision rule.** The pass/fail criteria for the new prompt were committed before the results existed.
- **Safety and privacy as tests.** "Nothing stored", "no network", "no identifiers in logs", and "you approve exactly what is sent" are automated checks, not just statements.
- **The commit guard worked under human error:** it blocked a real API key I had accidentally placed in the project folder before it reached git history.
- **Shelving local mode** on an 8 GB laptop was a product call, kept honestly in the cut list rather than hidden.

## 11. Limitations and risks

- Not validated on real EOBs; commercial plan variety is unknown. Only professional and outpatient example claims were tested.
- One claim at a time; no history, so repeats across claims are not detected.
- Name and place detection (Presidio, small English model) is statistical with imperfect recall. That is why it is a second layer behind the allow-list, and why a pattern-based leak guard backs it up.
- Amounts, service codes, and claim structure can in principle be quasi-identifiers; they are needed to explain the claim.
- Streamlit keeps an uploaded file in server memory until it is replaced, cleared, or the tab closes; the operating system may swap memory to disk. Neither can be controlled from this project.
- Cloud mode sends the approved payload to Anthropic.
- Thresholds (for example "a large share is 50% of the allowed amount and at least $50") are product judgments, configurable, and not medical or legal facts.

### Known issues (planned for v0.2)

- The fixed question for a large patient share ("how much is deductible, copay or coinsurance?") reads oddly when the EOB already itemizes the amount. The judge flagged it; fixing it would change the published evaluation numbers, so it waits for a re-run.
- The judge flags one-sentence definitions of standard terms as "unsupported", because it does not see the glossary the prompt allows.
- Prompt v2 passed its first-try criterion exactly at the threshold (24 of 25), and every result is a single run.
- Local mode (Ollama) has guards and tests but was never evaluated.

## 12. Run it

Requires Python 3.10 to 3.13.

```bash
git clone https://github.com/pushkarc20/eob-explainer.git
cd eob-explainer
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m spacy download en_core_web_sm
cp scripts/pre-commit-guard.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
streamlit run app.py
```

- **Built-in mode needs no key and sends nothing.** Choose a sample claim in the sidebar.
- **Cloud mode:** copy `.env.example` to `.env` and add an Anthropic API key. Use a dedicated key in its own workspace with a spend limit; an explanation costs about a cent. Never commit `.env`.
- **Tests (about 200):** `pytest -q` (no key or network needed; cloud paths use a fake model).
- **Evaluation:** `python scripts/run_eval.py` (rules engine, free) and `python scripts/run_ai_eval.py` (calls Claude and asks before spending).
- Other scripts: `scripts/preview_payload.py` (show exactly what would be sent), `scripts/explain_eob.py`, `scripts/draft_message.py`.

## 13. Repository map

```
app.py                 Streamlit app (thin; logic is in src/eob/app_logic.py)
src/eob/               EOB-specific: parser, money view, flags, templates, drafter, prompts, validator, explainer, evaluation
src/healthcore/        Reusable for other healthcare projects: FHIR helpers, privacy layer (placeholders, Presidio, leak guard), LLM clients
fixtures/              HL7 CARIN examples (CC0), synthetic claims, and the gold answers
docs/                  Rule catalog, privacy design, stateless checks, drafter, prompt log, evaluation reports
scripts/               Evaluation, previews, command-line tools, commit guard
tests/                 Unit, privacy, stateless, and headless UI tests
```

## 14. What is next

- **Project B: a provider-side prior authorization assistant** that reuses `healthcore` (FHIR helpers, the privacy layer, the verify-then-fall-back pattern, the evaluation harness). CMS-0057-F's Prior Authorization API requirements take effect around January 2027.
- **A held-out evaluation set,** then cross-claim duplicates, PDF EOBs, and an in-network flag.
- **A separate idea:** a "nothing leaves the device" tool for personal finance or health data, run entirely on a local model. It needs more memory than an 8 GB laptop.

## 15. How this was built

I built this to learn AI-assisted development and FHIR hands-on. I worked step by step with an AI assistant (Claude), which proposed designs and wrote most of the code and tests. I made the product decisions (scope, the default message type, shelving local mode, the model and privacy choices), ran every command and test myself, and reviewed the outputs. The prompt log and decision records are in [`docs/prompt_notes.md`](docs/prompt_notes.md).

## 16. Data sources, licenses, attribution

- HL7 CARIN Consumer Directed Payer Data Exchange (Blue Button) example EOBs, under `fixtures/carin/`. The source pages carry the CC0 mark; see `fixtures/carin/SOURCE.md`.
- Synthetic claims generated by `scripts/build_eval_set.py`: fictional, not derived from any real person or claim.
- No CMS data files are included in this repository.
- Code: MIT license. Libraries include Presidio, spaCy, Pydantic, and Streamlit, each under its own license.
