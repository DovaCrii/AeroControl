#!/usr/bin/env bash
set -euo pipefail

python -m pip install --upgrade pip uv
uv sync --locked --all-groups
uv run python scripts/compile_translations.py
uv run python manage.py collectstatic --noinput
