---
name: fuzz-loop
description: Core autonomous experiment loop for fuzzing research. Implements ideas, runs experiments with two-tier validation (sanity → full), applies statistical tests, keeps improvements, discards failures, loops forever. Use when asked to "run experiments", "start fuzzing loop", or "optimize fuzzer".
---

# Fuzz Loop

Autonomous fuzzing experiment loop: implement ideas, validate with statistical rigor, keep what works, discard what doesn't, never stop.

## Prerequisites

- `phase2-experiment/fuzz_experiment.sh` exists and passes smoke test (run `fuzz-setup` first)
- `configs/defaults.yaml` is readable for experiment parameters
- Fuzzer source built: `fuzzers/aflpp/afl-fuzz` exists

## Setup

1. Ask (or infer): **Goal** (what fuzzing improvement to explore), **Scope** (which fuzzer source files may be modified), **Constraints** (time budget, resource limits).
2. `git checkout -b fuzz-research/<goal>-<date>`
3. **Read the fuzzer source code deeply** — understand the algorithms you intend to improve. For AFL++, start with `fuzzers/aflpp/src/afl-fuzz-one.c` (mutations), `afl-fuzz-queue.c` (scheduling), and `include/afl-fuzz.h` (data structures).
4. Create `research.md`, `phase2-experiment/worklog.md`. Commit both.
5. Initialize state (write config header to `research.jsonl`) → run baseline → log result → start looping.

### `research.md`

A fresh agent with no context should be able to read this file and run the loop effectively.

```markdown
# Fuzzing Research: <goal>

## Objective
<What fuzzing improvement we're exploring and why.>

## Target & Fuzzer
- **Target**: <name> (binary at <path>)
- **Fuzzer**: AFL++ (source at `fuzzers/aflpp/`)
- **Fuzzer binary**: `fuzzers/aflpp/afl-fuzz`
- **Compiler**: `fuzzers/aflpp/afl-clang-fast`
- **Baseline coverage**: <N edges from smoke test>

## Metrics
- **Primary**: <name> (<unit>, higher/lower is better)
- **Secondary**: <metric1>, <metric2>, ...

## How to Run
1. Modify fuzzer source: edit files in `fuzzers/aflpp/src/`
2. Rebuild fuzzer: `cd fuzzers/aflpp && make -j$(nproc) source-only`
3. Recompile target: `CC=fuzzers/aflpp/afl-clang-fast <build command>`
4. Run sanity: `bash phase2-experiment/fuzz_experiment.sh --duration 10m --output-dir results/run-<N> --trial-id 1`
5. Analyze results: write Python code with numpy/scipy/matplotlib

## Fuzzer Files in Scope (agent may modify these)
- `fuzzers/aflpp/src/afl-fuzz-one.c` — mutation strategies
- `fuzzers/aflpp/src/afl-fuzz-queue.c` — seed scheduling
- `fuzzers/aflpp/include/afl-fuzz.h` — data structures (if new fields needed)
<Add/remove files based on the research direction.>

## Off Limits
- Target program source code (we're improving the fuzzer, not the target)
- `fuzzers/aflpp/instrumentation/` (compiler passes — unless research is about instrumentation)
- Benchmark harnesses and build scripts
- The experiment script's METRIC output format

## Constraints
- Fuzzer must compile cleanly (`make source-only` succeeds)
- No new external dependencies without user approval
- Modified fuzzer must still produce valid AFL++ output format (queue/, crashes/, fuzzer_stats)

## What's Been Tried
<Update as experiments accumulate. Note wins, dead ends, and insights.>
```

### Experiment Parameters

Read from `configs/defaults.yaml` (can be overridden in `research.md`):

```yaml
sanity_duration: "10m"
sanity_trials: 1
full_duration: "24h"
full_trials: 10
significance_level: 0.05
a12_threshold: 0.56
improvement_threshold: 0.03  # 3% minimum for short run promotion
```

---

## JSONL State Protocol

All experiment state lives in `research.jsonl`. This is the source of truth.

### Config Header

First line (and any re-initialization):

```json
{"type":"config","name":"<session>","goal":"<description>","fuzzer":"<name>","targets":["<target1>"],"metrics":{"primary":{"name":"branch_cov","unit":"edges","direction":"higher"},"secondary":["unique_crashes","throughput_execs_per_sec"]},"experiment":{"sanity_duration":"10m","sanity_trials":1,"full_duration":"24h","full_trials":10,"significance_level":0.05}}
```

### Result Lines

Each experiment appends a JSON line:

```json
{"run":1,"phase":"sanity","commit":"abc1234","status":"keep","description":"baseline","trials":1,"results":{"branch_cov":{"mean":3200,"median":3200,"std":0},"unique_crashes":{"mean":0,"median":0,"std":0}},"stat_tests":{},"vs_baseline":{},"timestamp":1234567890,"segment":0,"duration_sec":600}
```

Fields:
- `run`: sequential number (1-indexed, across segments)
- `phase`: `"sanity"` | `"full"`
- `commit`: 7-char git short hash (after commit for keeps, HEAD for discard/crash)
- `status`: `"keep"` | `"discard"` | `"crash"` | `"sanity_fail"`
- `description`: what this experiment tried
- `trials`: number of independent fuzzing trials
- `results`: dict of metric name → `{mean, median, std}` across trials
- `stat_tests`: dict of metric name → `{mann_whitney_p, a12, significant}` (empty for sanity/baseline)
- `vs_baseline`: dict of metric name → delta string (e.g., `"+8.2%"`)
- `timestamp`: Unix epoch seconds
- `segment`: segment index (increments with each config header)
- `duration_sec`: total wall clock time for this experiment

---

## Two-Tier Experiment Protocol

### Before Each Experiment: Rebuild

After modifying fuzzer source code:

```bash
# 1. Rebuild the modified fuzzer
cd fuzzers/aflpp && make -j$(nproc) source-only
if [ $? -ne 0 ]; then
    echo "COMPILE FAILED — revert and try a different approach"
    git checkout -- fuzzers/aflpp/
fi

# 2. Recompile the target with the modified fuzzer's compiler
cd phase2-experiment
CC=../../fuzzers/aflpp/afl-clang-fast CXX=../../fuzzers/aflpp/afl-clang-fast++ <build command>
```

### Tier 1: Sanity Check

```bash
cd phase2-experiment
bash fuzz_experiment.sh --duration 10m --output-dir results/run-<N>/trial-01 --trial-id 1
```

**Pass criteria**: exit code 0, METRIC lines present, primary metric is nonzero.

If sanity fails → status `"sanity_fail"`, revert fuzzer source (`git checkout -- fuzzers/`), log, move on.

### Tier 2: Full Experiment

If sanity passes AND the idea is worth a full evaluation:

```bash
for TRIAL in $(seq 1 $FULL_TRIALS); do
    bash fuzz_experiment.sh --duration 24h --output-dir results/run-<N>/trial-$(printf '%02d' $TRIAL) --trial-id $TRIAL &
done
wait
```

Run all trials in parallel if resources allow, otherwise sequentially.

After all trials complete, analyze the results. Write your own Python code to:
1. Load per-trial metrics from `phase2-experiment/results/run-<N>/trial-*/stats.json`
2. Compare against baseline using Mann-Whitney U test and Vargha-Delaney A12 effect size
3. Determine whether to keep or discard

See `skills/fuzz-analyze/SKILL.md` for detailed statistical principles.

**Keep criteria**:
- Mann-Whitney U test: p < significance_level (default 0.05)
- Vargha-Delaney A12 > a12_threshold (default 0.56)
- Both conditions must hold for the primary metric

---

## Logging Results

After each experiment, follow this exact protocol:

### 1. Determine Status

- **keep**: full experiment shows statistically significant improvement on primary metric
- **discard**: not significant, or sanity passed but full experiment showed no gain
- **crash**: fuzzer or target crashed during the run
- **sanity_fail**: sanity check failed (compilation error, runtime crash, no coverage)

### 2. Git Operations

**If keep:**
```bash
git add -A
git diff --cached --quiet && echo "nothing to commit" || git commit -m "<description>

Result: {\"status\":\"keep\",\"<primary_metric>\":<mean_value>,\"p_value\":<p>,\"a12\":<a12>}"
```

Then: `git rev-parse --short=7 HEAD`

**If discard, crash, or sanity_fail:**
```bash
git checkout -- .
git clean -fd
# Rebuild the reverted fuzzer
cd fuzzers/aflpp && make -j$(nproc) source-only
```

Use current HEAD hash as the commit field.

### 3. Append Result to JSONL

```bash
echo '<result JSON>' >> research.jsonl
```

### 4. Update Dashboard

Regenerate `research-dashboard.md`:

```markdown
# Fuzzing Research Dashboard: <name>

**Runs:** 12 | **Kept:** 3 | **Discarded:** 7 | **Crashed:** 1 | **Sanity Fail:** 1
**Baseline:** branch_cov: 3200 edges (#1)
**Best:** branch_cov: 4521 edges (#8, +41.3%, p=0.003, A12=0.78)

| # | phase | commit | branch_cov | unique_crashes | status | description |
|---|-------|--------|------------|----------------|--------|-------------|
| 1 | sanity | abc1234 | 3200 | 0 | keep | baseline |
| 2 | sanity | abc1234 | 3100 (-3.1%) | 0 | sanity_fail | broken mutation |
| 3 | full | def5678 | 4521 (+41.3%) | 12 | keep | energy schedule v2 |
...
```

### 5. Append to Worklog

After every experiment, append to `phase2-experiment/worklog.md`:

```markdown
### Run N: <short description> — branch_cov=<mean> (<STATUS>)
- Timestamp: YYYY-MM-DD HH:MM
- Phase: sanity | full (N trials, duration)
- What changed: <1-2 sentences about the code/config change>
- Result: <metric values>, p=<p_value>, A12=<a12> (if full run)
- Delta vs baseline: <+/-X.X%>
- Delta vs best: <+/-X.X%>
- Insight: <what was learned>
- Next: <what to try based on this result>
```

### 6. Update research.md

Every 3-5 experiments, update the "What's Been Tried" section of `research.md` with accumulated insights.

---

## Loop Rules

**LOOP FOREVER.** Never ask "should I continue?" — the user expects autonomous work.

- **Statistical significance is king.** Only `keep` when both p-value and A12 pass thresholds on the primary metric.
- **Sanity first.** Always run a quick sanity check before committing to a full experiment. Don't waste hours on broken code.
- **Understand the fuzzer deeply.** Before making changes, read the relevant source files in `fuzzers/aflpp/src/`. Understand the data structures in `include/afl-fuzz.h`. Reason about *why* a change should improve coverage or crash discovery.
- **Rebuild after every change.** Always `make source-only` after modifying fuzzer source, and recompile the target if the instrumentation changed.
- **Don't thrash.** If the same category of ideas keeps failing, try something structurally different.
- **Crashes are data.** Log them, note what caused them, move on. Don't over-invest in fixing obscure crashes.
- **Parallelize when possible.** Run trials in parallel with `&` and `wait` if CPU cores are available.
- **Monitor resource usage.** Watch for disk space (crash corpora can grow fast) and memory (ASAN overhead).

## Resuming

If `research.md` exists, this is a resume:

1. Read `research.md` for objective and scope
2. Read `research.jsonl` to reconstruct state (total runs, best result, current segment)
3. Read `phase2-experiment/worklog.md` for the full narrative
4. Read recent `git log --oneline -20`
5. If `research.ideas.md` exists, use it for inspiration
6. Continue from where the loop left off

## Ideas Backlog

When you discover promising but complex optimizations to defer:

- Append to `research.ideas.md` as bullet points
- On resume, read and use as inspiration
- Prune ideas that were already tried or are clearly bad
- Delete the file when all ideas are exhausted

## User Steers

User messages during an experiment are incorporated into the NEXT experiment. Finish the current experiment first. Never stop or ask for confirmation mid-experiment.
