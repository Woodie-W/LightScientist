---
name: idea-probe-collect
description: Summarize and compare probe results, then recommend the next idea-phase transition.
---

# Idea Probe Collect

Use this skill after one or more idea probes have completed.

## Inputs

- `phase1-idea/probes/*/PROBE_REPORT.md`
- `phase1-idea/IDEA_REPORT.md` when present
- Prior artifact summaries from `list_artifacts`

## Goals

- Read all available probe reports.
- Compare feasibility, risk, signal strength, and expected payoff.
- Produce one concise selection summary for the first layer.

## Required Output

- `phase1-idea/PROBE_SUMMARY.md`

The summary should include:

- probe list
- strongest idea
- rejected or weak ideas
- recommended next stage: `idea.generate`, `idea.evaluate`, or `idea.gate`

## Rules

- Do not rerun large experiments here unless clearly necessary.
- Prefer synthesizing existing probe evidence.
- When complete, call `finish_stage`.
