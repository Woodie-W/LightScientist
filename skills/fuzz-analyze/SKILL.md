---
name: fuzz-analyze
description: Statistical analysis of fuzzing experiment results. Describes the principles, methods, and standards the agent should follow when analyzing results. The agent writes its own analysis code. Use after completing a full experiment run.
---

# Fuzz Analyze

Analyze fuzzing experiment results with statistical rigor. You write the analysis code yourself — there are no pre-built analysis tools. Use Python with `numpy`, `scipy`, `matplotlib` (all pre-installed) or any approach you judge appropriate.

## When to Use

- After a full experiment run completes (all trials finished)
- When comparing multiple experiment runs
- When generating figures for the paper phase

## Available Data

Each trial produces a results directory (`phase2-experiment/results/run-<N>/trial-<M>/`) containing:

- `stats.json` — per-trial metrics (branch_cov, unique_crashes, throughput, etc.)
- `coverage.json` — coverage data (edges, branches, timeline if available)
- `crash_analysis.json` — crash information (if crashes occurred)
- `fuzz.log` — raw fuzzer output
- AFL++ native files: `fuzzer_stats`, `plot_data`, `queue/`, `crashes/`

Read whatever raw data you need. Parse it however makes sense for the analysis.

## Statistical Principles

Follow the fuzzing evaluation standards from Klees et al., "Evaluating Fuzz Testing" (CCS 2018):

### Non-Parametric Tests (Required)

Fuzzing results are rarely normally distributed. Use non-parametric methods:

- **Mann-Whitney U test**: compares two independent samples. The standard for fuzzing comparisons. Use `scipy.stats.mannwhitneyu`.
- **Significance threshold**: p < 0.05 (configurable in `configs/defaults.yaml`)

### Effect Size (Required)

P-values alone are insufficient. Always report effect size:

- **Vargha-Delaney A12**: probability that a random value from X is greater than a random value from Y. This is the standard effect size measure for fuzzing.
  - A12 = 0.50 → no difference
  - A12 ∈ [0.56, 0.64) → small effect
  - A12 ∈ [0.64, 0.71) → medium effect
  - A12 ≥ 0.71 → large effect
  
### Keep/Discard Decision

Both conditions must hold for the primary metric:
- p < significance_level (default 0.05)
- A12 > a12_threshold (default 0.56)

### Minimum Trial Count

- Sanity checks: 1 trial (just verifying the fuzzer works)
- Full experiments: ≥ 5 trials recommended, 10 is standard
- With < 5 trials, statistical tests have low power — note this limitation

## What to Analyze

At minimum, report these for each comparison:

1. **Per-trial raw values** — don't hide the data behind averages
2. **Summary statistics** — mean, median, std, min, max for each metric
3. **Relative improvement** — percentage change vs baseline
4. **Statistical test results** — U statistic, p-value, A12, effect size classification
5. **Verdict** — keep or discard, with reasoning

Beyond the minimum, use your judgment. If the data tells an interesting story (e.g., coverage plateaus at different points, bimodal distribution, one outlier trial), analyze and explain it.

## Visualization

Generate whatever plots help understand the results. Common useful visualizations in fuzzing research:

- **Coverage-over-time curves** with median line and IQR shading
- **Box plots** comparing metric distributions across configurations
- **Crash discovery timelines** (cumulative unique crashes over time)
- **Scatter plots** of one metric vs another
- **Histograms** of trial-level metric distributions

But don't limit yourself to these — if a different visualization better tells the story, create it. Use matplotlib, or write raw SVG, or whatever works. Save figures in `phase2-experiment/plots/`.

### Style Guidelines for Figures

- Readable at the size they'll appear in a paper (≥ 8pt font)
- Distinguishable in grayscale (use patterns/markers, not just color)
- PDF vector output for paper use; PNG for dashboards
- Clear axis labels with units
- Legends that explain what each line/bar represents

## Output

Write your analysis results wherever makes sense. Typical outputs:

- `phase2-experiment/results/run-<N>/analysis.json` — structured analysis for a single run
- `phase2-experiment/plots/` — any generated figures
- `phase2-experiment/EXPERIMENT_RESULTS.md` — comprehensive summary when all experiments are done
- Inline in `phase2-experiment/worklog.md` — narrative interpretation

The format is up to you. What matters is that the analysis is rigorous, the conclusions are supported by the data, and another researcher could reproduce your findings.
