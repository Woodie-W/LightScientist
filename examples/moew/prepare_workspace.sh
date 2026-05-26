#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${1:-/data/auto-research/LightScientist/examples/moew/workspace}"

mkdir -p "$WORKSPACE"
mkdir -p "$WORKSPACE/phase3-paper/figures"
mkdir -p "$WORKSPACE/phase3-paper/paper"

ln -sfn /data/moew/CORAL/examples/meow "$WORKSPACE/source_task"
ln -sfn /data/moew/CORAL/examples/meow/seed "$WORKSPACE/source_seed"
ln -sfn /data/moew/CORAL/results/meow-lob-deep-alpha "$WORKSPACE/source_results"

printf '%s\n' "$WORKSPACE"
