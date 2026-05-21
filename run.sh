#!/usr/bin/env bash
# Run Nations at War with Python 3.13 venv (system Python 3.14 breaks pygame fonts).
set -e
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
  echo "Creating virtual environment..."
  # Prefer 3.12/3.13 over 3.14 for pygame compatibility
  if command -v python3.13 >/dev/null 2>&1; then
    python3.13 -m venv .venv
  elif command -v python3.12 >/dev/null 2>&1; then
    python3.12 -m venv .venv
  else
    python3 -m venv .venv
  fi
  .venv/bin/pip install -q -r requirements.txt
fi
exec .venv/bin/python main.py "$@"
