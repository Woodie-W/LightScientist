---
name: fuzz-pipeline
description: Reference document for the full Phase 2 flow. In LightScientist, first-layer stage control owns orchestration; use the stage skills for actual execution.
---

# Fuzz Pipeline

Reference flow for Phase 2: set up the experiment environment, then enter the autonomous experiment loop.

This file is not the active orchestrator in LightScientist. The first-layer
controller owns stage transitions. Use `fuzz-setup`, `fuzz-loop`, and
`fuzz-analyze` as the execution skills for real work.

## Inputs

From the project goal, prior artifacts, or first-layer controller:

- **Goal**: what fuzzing improvement to explore
- **Target**: which program(s) to fuzz
- **Fuzzer**: which fuzzer to use (default: from `configs/defaults.yaml`)
- **Idea source**: optional `phase1-idea/IDEA_REPORT.md` for idea context

If invoked after Phase 1 (idea engine), read `phase1-idea/IDEA_REPORT.md` to select the top-ranked idea as the starting point.

## Procedure

### Stage 1: Setup

Invoke the `fuzz-setup` skill:

1. Clone and build fuzzer source
2. Compile target with instrumentation
3. Prepare seed corpus
4. Create experiment script
5. Run smoke test

**Gate**: proceed only if `phase2-experiment/SETUP_COMPLETE.md` exists and smoke test passed.

### Stage 2: Experiment Loop

Invoke the `fuzz-loop` skill:

1. Create `research.md` and `research.jsonl`
2. Run baseline experiment
3. Enter the autonomous loop: implement → sanity → full → analyze → keep/discard → repeat

The loop runs autonomously until:
- The first-layer controller or runtime pauses/cancels it
- All ideas are exhausted (no `research.ideas.md` and agent has no new ideas)
- Context limit is reached (agent should update `research.md` and `worklog.md` before stopping)

### Stage 3: Final Analysis

When the loop ends (user intervention or idea exhaustion):

1. Invoke `fuzz-analyze` for a comprehensive multi-run comparison
2. Generate `phase2-experiment/EXPERIMENT_RESULTS.md` with:
   - Summary of all runs and their statistical results
   - Best configuration and its parameters
   - Key insights and failed approaches
   - Recommended next steps
3. Generate final plots (coverage curves, comparison box plots)

### Stage 4: Handoff to Paper Phase

If the research pipeline is running end-to-end:

1. Verify `phase2-experiment/EXPERIMENT_RESULTS.md` exists and is complete
2. Summarize key findings for the paper phase
3. Signal readiness for Phase 3

## Recovery

If the pipeline is interrupted at any point:

- **During setup**: re-run `fuzz-setup` (idempotent)
- **During loop**: `fuzz-loop` handles its own resume via `research.jsonl` and `research.md`
- **During analysis**: re-run `fuzz-analyze` on existing results

## Output

- All `fuzz-setup` outputs (targets, seeds, experiment script)
- All `fuzz-loop` outputs (research.jsonl, dashboard, worklog)
- `phase2-experiment/EXPERIMENT_RESULTS.md` — comprehensive results for Phase 3
- `phase2-experiment/plots/` — publication-ready figures
