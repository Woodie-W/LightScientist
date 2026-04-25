---
name: idea-probe
description: Run small, cheap feasibility probes for one or more shortlisted ideas before entering the full experiment phase.
---

# Idea Probe

Use this skill when the current goal is to validate whether a candidate idea is worth a full experiment campaign.

## Inputs

- `phase1-idea/IDEA_REPORT.md` or `phase1-idea/IDEAS_CANDIDATES.md`
- Any relevant prior artifacts from `list_artifacts`

## Goals

- Pick one concrete idea or probe objective.
- Design the smallest experiment that can falsify or de-risk the idea.
- Run only short, cheap validation steps.
- Write probe outputs under `phase1-idea/probes/`.

## Required Outputs

- One subdirectory per probe under `phase1-idea/probes/`
- A `PROBE_REPORT.md` in each probe directory with:
  - objective
  - setup
  - observations
  - recommendation: keep / revise / drop

## Rules

- Do not start a long full experiment campaign here.
- Prefer reusing an existing worker over creating many parallel workers.
- If more time is needed for a background run, use the worker background flow and report clearly why.
- When the probe batch is sufficient, call `finish_stage`.
