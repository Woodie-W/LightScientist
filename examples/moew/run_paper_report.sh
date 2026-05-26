#!/usr/bin/env bash
set -euo pipefail

ROOT="/data/auto-research/LightScientist"
WORKSPACE="${1:-/data/auto-research/LightScientist/examples/moew/workspace}"

"$ROOT/examples/moew/prepare_workspace.sh" "$WORKSPACE" >/dev/null

cd "$ROOT"
set -a
source .env
set +a

PROMPT="$(cat "$ROOT/examples/moew/task_prompt.md")"

PYTHONPATH=src python -m esnext research \
  "$PROMPT" \
  --workspace "$WORKSPACE" \
  --mode auto \
  --stage paper.plan \
  --watch
