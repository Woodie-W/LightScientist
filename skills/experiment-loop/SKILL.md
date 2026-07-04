---
name: experiment-loop
description: Core autonomous experiment loop for generic research. Implements ideas, runs evaluations with two-tier validation when needed, applies analysis, keeps improvements, discards failures, and resumes from structured state.
---

# Experiment Loop

Autonomous experiment loop: optimize around an already reproduced baseline, validate with rigor, keep what works, discard what does not, and continue until the current direction is exhausted or paused.

## Prerequisites

- `research.md` exists
- `phase2-experiment/SETUP_COMPLETE.md` exists
- `phase2-experiment/REPRODUCE_COMPLETE.md` exists
- the baseline and evaluation path are understood

## Setup

1. Ask or infer:
   - **Goal**
   - **Scope**
   - **Constraints**
2. Create or switch to a working branch if code edits are part of the task.
3. Read the core local files deeply before making changes.
4. Create `research.md`, `phase2-experiment/worklog.md`, and `research.jsonl` if missing.
5. Initialize state -> read the reproduced baseline -> start looping.

### `research.md`

A fresh agent with no context should be able to read this file and continue the loop effectively.

```markdown
# Research: <goal>

## Objective
<What improvement or validation is being explored and why.>

## System Under Study
- **System**: <name or path>
- **Baseline**: <reference command / config / artifact>
- **Entry point**: <main run path>
- **Current best**: <summary if known>

## Metrics
- **Primary**: <name> (<unit>, higher/lower is better)
- **Secondary**: <metric1>, <metric2>, ...

## How to Run
1. Modify code/config/prompt in scope
2. Rebuild or refresh if needed
3. Run sanity
4. Run full evaluation
5. Analyze and log

## Files in Scope
- <editable paths>

## Off Limits
- <paths or assets that should not be changed>

## Constraints
- <resource, dependency, or correctness constraints>

## What's Been Tried
<Update as experiments accumulate.>
```

### Experiment Parameters

Record these in `research.md` or the config row:

```yaml
sanity_duration: "short"
sanity_trials: 1
full_duration: "full"
full_trials: 3
significance_level: 0.05
improvement_threshold: 0.03
```

## JSONL State Protocol

All experiment state lives in `research.jsonl`.

### Config Header

First line or re-initialization line:

```json
{"type":"config","name":"<session>","goal":"<description>","system":"<name>","metrics":{"primary":{"name":"primary_metric","unit":"score","direction":"higher"},"secondary":["metric2","metric3"]},"experiment":{"sanity_duration":"short","sanity_trials":1,"full_duration":"full","full_trials":3,"significance_level":0.05}}
```

### Result Lines

Each experiment appends a JSON line:

```json
{"run":1,"phase":"sanity","commit":"abc1234","status":"keep","description":"baseline","trials":1,"results":{"primary_metric":{"mean":0.64,"median":0.64,"std":0.0}},"stat_tests":{},"vs_baseline":{},"timestamp":1234567890,"segment":0,"duration_sec":60}
```

Fields:

- `run`: sequential number
- `phase`: `"sanity"` | `"full"` | `"analysis"`
- `commit`: commit hash or other stable revision marker when relevant
- `status`: `"keep"` | `"discard"` | `"failed"` | `"blocked"`
- `description`: what this experiment tried
- `trials`: number of evaluations
- `results`: metric dict
- `stat_tests`: comparison results when applicable
- `vs_baseline`: relative deltas
- `timestamp`: Unix epoch seconds
- `segment`: segment index
- `duration_sec`: total wall clock time

## Two-Tier Experiment Protocol

### Before Each Experiment

After modifying the system:

```bash
# example pattern only — adapt to the project
<rebuild or refresh command if needed>
```

If compilation, setup, or validation fails:

- log the failure
- revert the bad experiment state when appropriate
- move on

### Tier 1: Sanity Check

Run a quick, cheap verification step before spending large compute:

```bash
<sanity command>
```

**Pass criteria**:

- command succeeds
- expected outputs exist
- primary metric is extractable and plausible

If sanity fails -> status `"failed"` or `"blocked"` depending on cause.

### Tier 2: Full Experiment

If sanity passes and the idea is worth a full evaluation:

```bash
<full evaluation command or loop>
```

Run trials in parallel if resources allow; otherwise sequentially.

After trials complete:

1. load per-trial metrics
2. compare against baseline
3. determine whether to keep or discard

## Logging Results

After each experiment, follow this protocol:

### 1. Determine Status

- **keep**: meaningful improvement or useful retained result
- **discard**: no meaningful gain
- **failed**: experiment execution failed
- **blocked**: external condition prevented progress

### 2. Git Operations

If code changed and the result should be retained, commit it. If the result should be discarded, revert the experimental changes when appropriate.

### 3. Append Result to JSONL

```bash
echo '<result JSON>' >> research.jsonl
```

### 4. Update Dashboard

Regenerate `research-dashboard.md`:

```markdown
# Research Dashboard: <name>

**Runs:** 12 | **Kept:** 3 | **Discarded:** 7 | **Failed:** 1 | **Blocked:** 1
**Baseline:** primary_metric: 0.42 (#1)
**Best:** primary_metric: 0.57 (#8, +35.7%)

| # | phase | commit | primary_metric | status | description |
|---|-------|--------|----------------|--------|-------------|
| 1 | sanity | abc1234 | 0.42 | keep | baseline |
| 2 | full | def5678 | 0.57 | keep | feature set v2 |
...
```

### 5. Append to Worklog

After every experiment, append to `phase2-experiment/worklog.md`:

```markdown
### Run N: <short description> — primary_metric=<mean> (<STATUS>)
- Timestamp: YYYY-MM-DD HH:MM
- Phase: sanity | full | analysis
- What changed: <1-2 sentences>
- Result: <metric values>
- Delta vs baseline: <+/-X.X%>
- Insight: <what was learned>
- Next: <what to try next>
```

### 6. Update research.md

Every few experiments, update the "What's Been Tried" section with accumulated insights.

## Loop Rules

- Keep looping unless the current direction is exhausted or the runtime pauses/cancels it.
- Treat the reproduced baseline as fixed reference; do not keep redefining baseline mid-loop.
- Prefer cheap sanity checks before expensive full evaluations.
- Understand the local system deeply before changing it.
- Do not thrash on the same failing idea category.
- Treat failures as data; log them and move on.
- Parallelize when the project and hardware allow it.

## Resuming

If `research.md` exists, this is a resume:

1. Read `research.md`
2. Read `research.jsonl`
3. Read `phase2-experiment/worklog.md`
4. Read `phase2-experiment/REPRODUCE_COMPLETE.md`
5. Read recent git history if code changes are involved
6. Continue from where the loop left off

## Ideas Backlog

When you discover promising but deferred ideas:

- append them to `research.ideas.md`
- use them on resume
- prune ideas that were tried or are clearly bad

## User Steers

User messages during an experiment are incorporated into the next experiment step unless the runtime explicitly interrupts the current one.

## Procedure

1. Read `research.md` and identify the next highest-value experiment.
2. If a long-running job is needed, launch it cleanly, record what was started, then use background suspension.
3. When evidence is available, append a structured row to `research.jsonl`.
4. Update `phase2-experiment/worklog.md` with:
   - what changed
   - what was measured
   - what was learned
   - what to try next
5. Stay in this stage while more iterations are justified.
6. Move naturally toward `experiment.analyze` once there is enough evidence or a stable stopping point.

## Rules

- Keep the JSONL schema simple and consistent.
- Prefer small, interpretable steps over large bundles of changes.
- If the task is analysis-only, you may log evaluations of existing artifacts instead of launching new runs.
- Do not rewrite history in `research.jsonl`; append new rows.

## Output

- `research.jsonl`
