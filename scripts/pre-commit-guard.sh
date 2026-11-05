#!/usr/bin/env bash
# Blocks commits that include downloaded data, env files, or anything that looks like an Anthropic API key.
set -u

staged=$(git diff --cached --name-only --diff-filter=ACM)
[ -z "$staged" ] && exit 0
fail=0

bad=$(echo "$staged" | grep -E '^(data/|\.env($|\.))' | grep -v '^\.env\.example$' || true)
if [ -n "$bad" ]; then
  echo "BLOCKED: data/ and .env files must never be committed:"
  echo "$bad"
  fail=1
fi

leak=$(git diff --cached -U0 | grep -E '^\+' | grep -E 'sk-ant-[A-Za-z0-9_-]{10,}' || true)
if [ -n "$leak" ]; then
  echo "BLOCKED: staged content looks like an Anthropic API key."
  echo "If this was a real key, rotate it in the Claude Console."
  fail=1
fi

exit $fail
