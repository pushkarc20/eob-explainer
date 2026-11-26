#!/usr/bin/env bash
# Common developer commands. Usage: scripts/dev.sh {test|lint|check|app|eval|hooks}
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

case "${1:-}" in
  test)  pytest -q ;;
  lint)  ruff check . ;;
  check) ruff check . && pytest -q ;;
  app)   streamlit run app.py ;;
  eval)  python scripts/run_eval.py ;;
  hooks) cp scripts/pre-commit-guard.sh .git/hooks/pre-commit \
           && chmod +x .git/hooks/pre-commit \
           && echo "Commit guard installed (blocks data/, .env and key-shaped strings)." ;;
  *)     echo "usage: scripts/dev.sh {test|lint|check|app|eval|hooks}"; exit 1 ;;
esac