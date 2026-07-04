---
name: experiment-reproduce
description: Reproduce the fixed baseline experiment before any optimization. Confirms the target paper/task/dataset/metric scope, runs the baseline once, records the result, and writes a reproducible handoff for later optimization.
---

# Experiment Reproduce

This stage is strictly for reproducing the fixed baseline experiment in scope.
Do not start broader optimization work here.

## Inputs

- `research.md`
- `phase2-experiment/SETUP_COMPLETE.md`
- the fixed paper, task, dataset, and evaluation target already chosen for this project

## Goal

Produce one trustworthy baseline reproduction result that later optimization runs
can compare against.

## Hard Rules

- Stay on the fixed paper/task/dataset already selected.
- Reproduce one concrete experiment first.
- Do not broaden scope to new datasets, new benchmark suites, or unrelated ideas.
- If reproduction fails, document the failure clearly instead of silently moving to optimization.

## Procedure

### 1. Lock the Reproduction Target

Read the setup artifacts and identify:

- target paper or implementation
- target experiment
- dataset or split
- baseline command
- primary metric
- expected output location

Write the chosen target clearly in `research.md` if it is not already explicit.

### 2. Run the Baseline Reproduction

Execute the smallest full baseline run that still counts as a meaningful
reproduction for this task.

If the project already contains valid baseline outputs, verify they match the
current target before reusing them.

### 3. Record the Result

Update or create:

- `research.jsonl`
- `phase2-experiment/worklog.md`

The recorded baseline should include:

- command or artifact source
- metric value(s)
- whether the result matches, approximately matches, or fails to match the paper
- any important deviations from the paper or official code

### 4. Write the Reproduction Handoff

Create `phase2-experiment/REPRODUCE_COMPLETE.md` with:

```markdown
# Reproduction Complete

- **Target paper**: <name>
- **Target experiment**: <which experiment>
- **Dataset / split**: <name>
- **Baseline command or artifact**: <command or path>
- **Primary metric**: <name>
- **Reproduced value**: <number or explicit failure>
- **Reference paper value**: <number if known>
- **Comparison**: <matched / close / lower / failed>
- **Notes**: <important caveats and deviations>
```

This file should let a later agent continue directly into optimization.

## Completion Standard

This stage is complete only when `phase2-experiment/REPRODUCE_COMPLETE.md`
exists and the baseline reproduction status is clearly stated.

## Output

- `phase2-experiment/REPRODUCE_COMPLETE.md`
- updated `research.jsonl`
- updated `phase2-experiment/worklog.md`
