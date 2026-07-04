---
name: experiment-pipeline
description: Reference document for the full Phase 2 flow. In LightScientist, first-layer stage control owns orchestration; use the stage skills for actual execution.
---

# Experiment Pipeline

Reference flow for Phase 2: set up the experiment environment, reproduce the fixed baseline experiment, then enter the autonomous optimization loop.

This file is not the active orchestrator in LightScientist. The first-layer
controller owns stage transitions. Use `experiment-setup`, `experiment-reproduce`,
`experiment-loop`, and `experiment-analyze` as the execution skills for real work.

## Inputs

From the project goal, prior artifacts, or first-layer controller:

- **Goal**: what improvement, reproduction, or analysis objective to explore
- **System under study**: which codebase, model, dataset, workflow, or artifact is being evaluated
- **Baseline**: what the new idea should be compared against
- **Idea source**: optional `phase1-idea/IDEA_REPORT.md` for idea context

If invoked after Phase 1, read `phase1-idea/IDEA_REPORT.md` to select the top-ranked idea as the starting point.

## Procedure

### Stage 1: Setup

Invoke the `experiment-setup` skill:

1. Inspect the system under study and baseline
2. Confirm commands, data paths, and output locations
3. Prepare `research.md` and workspace structure
4. Create any helper scripts or manifests needed for repeated evaluation
5. Run a smoke test if execution is required

**Gate**: proceed only if `phase2-experiment/SETUP_COMPLETE.md` exists and the setup is valid.

### Stage 2: Reproduction

Invoke the `experiment-reproduce` skill:

1. lock the fixed paper/task/dataset/metric scope
2. run the baseline reproduction
3. record the reproduced value and any deviation from the reference paper
4. create `phase2-experiment/REPRODUCE_COMPLETE.md`

**Gate**: proceed only if `phase2-experiment/REPRODUCE_COMPLETE.md` exists and the baseline reproduction status is explicit.

### Stage 3: Experiment Loop

Invoke the `experiment-loop` skill:

1. Create or resume `research.md`, `research.jsonl`, and `phase2-experiment/worklog.md`
2. Read the reproduced baseline result first
3. Enter the autonomous loop: choose the highest-value scoped optimization -> sanity -> full evaluation -> analyze -> keep or discard -> repeat

Within the loop, the optimization may be:

- parameter tuning
- model modification
- algorithm-flow modification
- preprocessing change
- feature-selection change
- other project-specific scoped improvement

The choice should be adaptive and evidence-driven, not fixed in advance.

The loop runs autonomously until:
- The first-layer controller or runtime pauses/cancels it
- The idea space is exhausted
- Context or resource limits are reached

### Stage 4: Final Analysis

When the loop ends:

1. Invoke `experiment-analyze` for a comprehensive comparison
2. Generate `phase2-experiment/EXPERIMENT_RESULTS.md` with:
   - summary of all runs and evaluations
   - best configuration or finding
   - key insights and failed approaches
   - recommended next steps
3. Generate final plots or tables if they help later writing

### Stage 5: Handoff to Paper Phase

If the research pipeline is running end-to-end:

1. Verify `phase2-experiment/EXPERIMENT_RESULTS.md` exists and is complete
2. Summarize key findings for the paper phase
3. Signal readiness for Phase 3

## Recovery

If the pipeline is interrupted at any point:

- **During setup**: re-run `experiment-setup` (should be idempotent)
- **During reproduction**: re-run `experiment-reproduce` and refresh the baseline handoff
- **During loop**: `experiment-loop` resumes from `research.jsonl`, `research.md`, and `worklog.md`
- **During analysis**: re-run `experiment-analyze` on existing results

## Output

- All `experiment-setup` outputs
- `phase2-experiment/REPRODUCE_COMPLETE.md`
- All `experiment-loop` outputs (`research.jsonl`, dashboard, worklog)
- `phase2-experiment/EXPERIMENT_RESULTS.md`
- `phase2-experiment/plots/`
