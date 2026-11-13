# Message drafter

Default output: a short written question (email or secure-portal message) to the insurer.
Built locally from a template: no AI and no network, so there is no privacy exposure and the wording is fully tested.

## What goes in

| Field | Source | Notes |
|---|---|---|
| Claim number, provider, service dates, amounts | The EOB | Used locally only; the cloud payload never includes the claim number |
| Member name, member ID | Typed by the member at run time | Used only to fill in the draft; never stored or sent |
| Questions | One fixed, first-person question per flag | Only "question" flags; "info" flags are noted, not asked |
| Closing question | Confirm the balance owed, or ask for it if the EOB does not state it | Always included |

## Wording rules (enforced by tests)

- Every question asks; none concludes. No "error", "wrong", "overcharge", "fraud", and no legal claims.
- Missing details appear as visible `[FILL IN]` fields, never guessed.
- Guidance shown with the draft: review before sending, use the secure portal, no SSN or bank details,
  and for denials, a pointer to the denial notice for the review process and deadlines.

## Deliberately not included (and why)

- Phone-call script and formal appeal letter: the chosen default was a short written question.
  A formal appeal depends on plan type, state and deadlines, which this tool cannot advise on.
- Rights and deadline guidance: legal advice; the draft points to the denial notice instead.
- AI polishing of the message: possible later, but the deterministic version is safer and testable.
- Cross-claim context ("this repeats my March 5 visit on another EOB"): needs claim history.
