---
name: experiment-analyze
description: Statistical and qualitative analysis of experiment results. Describes the principles, methods, and standards the agent should follow when analyzing results and preparing Phase 2 outputs.
---

# Experiment Analyze

Analyze experiment results with rigor. You write the analysis code yourself when needed.

## When to Use

- After a full experiment run completes
- When comparing multiple experiment runs
- When generating figures or summaries for the paper phase

## Available Data

Each run may produce different artifacts. Read whatever raw data is useful:

- per-trial metrics
- logs
- config snapshots
- generated outputs
- error reports
- derived tables or plots

Parse the available data however makes sense for the project.

## Statistical Principles

Use statistical methods that fit the actual data regime.

### Non-Parametric Tests

If trial counts are small or distributions are not normal, prefer non-parametric methods:

- Mann-Whitney U test
- Wilcoxon signed-rank test when paired data is appropriate

### Effect Size

P-values alone are insufficient. Report an effect size whenever meaningful:

- Vargha-Delaney A12
- Cohen's d
- rank-biserial correlation

Choose the one that matches the data and comparison design.

### Minimum Trial Count

- sanity checks: 1 trial
- full experiments: 3 or more recommended
- if the count is too small for strong claims, say so explicitly

## What to Analyze

At minimum, report:

1. per-trial raw values when they exist
2. summary statistics
3. relative improvement vs baseline
4. statistical test results when appropriate
5. verdict: keep, discard, inconclusive, or blocked

Beyond the minimum, explain any interesting pattern that matters scientifically.

If the loop mixed different optimization categories, such as parameter tuning
and algorithm-flow changes, make that distinction explicit in the analysis.

## Visualization

Generate whatever plots help understand the results. Common useful visualizations:

- progress-over-time curves
- box plots or violin plots
- ablation comparison tables
- sensitivity curves
- scatter plots between metrics
- case-study figures

Save figures in `phase2-experiment/plots/`.

## Output

Typical outputs:

- `phase2-experiment/results/run-<N>/analysis.json`
- `phase2-experiment/plots/`
- `phase2-experiment/EXPERIMENT_RESULTS.md`
- inline notes in `phase2-experiment/worklog.md`

What matters is that the analysis is rigorous, the conclusions are supported by the data, and later stages can reuse the result.
