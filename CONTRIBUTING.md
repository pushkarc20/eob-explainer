# Contributing

Thanks for looking. This is a portfolio project on synthetic data. Feedback and small fixes are welcome.

## Ground rules

- **Never include real health, insurance, or personal information, API keys, or tokens** in code, issues, or pull requests (see [SECURITY.md](SECURITY.md)). Use the synthetic files under `fixtures/`.
- Be kind. This is a learning project.

## Set up

```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m spacy download en_core_web_sm
scripts/dev.sh hooks     # installs the commit guard
scripts/dev.sh check     # lint and tests
```

Built-in mode needs no API key. Cloud mode needs your own (see the README).

## Before opening a pull request

- `scripts/dev.sh check` passes.
- New behavior has a test, and any privacy or safety claim has a test too.
- If your change affects a figure, a flag, the prompt, or the validator, re-run the evaluation (`python scripts/run_eval.py`, then `python scripts/run_ai_eval.py`, which asks before spending) and update the README tables. Say what changed in the pull request.

## Design rules this project keeps

- Code computes the facts; the model only rewrites verified facts, and code checks its answer.
- Flags are questions for the insurer or billing office, never conclusions that a bill is wrong.
- Missing data is "not stated", never $0.
- The user approves exactly what is sent to a model.