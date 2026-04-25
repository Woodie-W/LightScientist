---
name: paper-figure
description: Generate publication-quality figures and tables for the fuzzing research paper. Describes what kinds of figures a good fuzzing paper needs and the quality standards they must meet. The agent decides how to create them. Use after experiment results are available and paper plan exists.
---

# Paper Figure

Generate all figures and tables needed for the paper. You write the code yourself — use matplotlib, tikz, raw SVG, LaTeX tabular, or whatever best suits each figure.

## Inputs

- `phase3-paper/PAPER_PLAN.md` — which figures/tables are planned and what they should show
- `phase2-experiment/results/` — raw experiment data
- `phase2-experiment/EXPERIMENT_RESULTS.md` — summary statistics (if generated during analysis)

## What a Good Fuzzing Paper Needs

### Essential Figures

1. **Coverage-over-time curves** — the single most important figure in a fuzzing paper
   - Median line with shaded confidence region (IQR or CI)
   - One per target, or a combined multi-panel figure
   - Baseline vs. your approach (and optionally other baselines)
   - X-axis: time, Y-axis: edge/branch coverage

2. **Comparison box plots or violin plots** — distribution of final metric values across trials
   - Shows variance, not just means
   - One per primary metric

3. **Architecture/overview diagram** — how your approach works
   - Highlight what's novel (the part you modified)
   - Show the feedback loop

### Common Additional Figures (use judgment)

- Crash discovery timeline (cumulative unique crashes over time)
- Ablation study results (if you tested component contributions)
- Sensitivity analysis (parameter tuning effects)
- Case study: specific bug found, with code/trace
- Heatmap of performance across different targets

### Essential Tables

1. **Main comparison table** — coverage/crashes across all targets
   - Baseline, your approach, and any other compared methods
   - Mean ± std, with best in bold
   - Statistical significance markers (* or †)

2. **Statistical significance table** — p-values and effect sizes
   - Mann-Whitney U p-value, Vargha-Delaney A12
   - Effect size classification

3. **Bug table** (if applicable) — unique bugs found
   - Bug type, target, which tool found it, time to discovery

## Quality Standards

These are non-negotiable for a good paper:

- **Font size**: all text ≥ 8pt when printed at final size (two-column papers use ~3.3" column width)
- **Grayscale readability**: figures must be interpretable in grayscale — use different line styles (solid, dashed, dotted), markers (circle, square, triangle), and patterns in addition to color
- **Vector format**: PDF for all plots and diagrams (not raster PNG/JPG)
- **Consistent style**: same fonts, colors, and line widths across all figures
- **Axis labels**: descriptive, with units (e.g., "Edge Coverage (count)", "Time (hours)")
- **No chart junk**: no unnecessary grid lines, 3D effects, or decorations
- **Captions**: every figure and table gets a substantive caption that explains what the reader should see

## LaTeX Integration

- Place figures in `phase3-paper/figures/`
- Tables can be `.tex` files (for `\input{}`) or inline in the paper
- Use `\label{}` and `\ref{}` for cross-references
- Use booktabs (`\toprule`, `\midrule`, `\bottomrule`) for tables, not `\hline`

## Approach

Read the paper plan, look at the data, and create the figures that best tell the paper's story. Don't mechanically generate a fixed set — think about what visualizations will be most convincing to reviewers and most informative to readers.

If a standard figure type doesn't fit the data, invent a better one. If additional figures would strengthen the paper, create them. If a planned figure turns out to be uninformative, skip it and explain why.

## Output

- `phase3-paper/figures/` — all generated figures (PDF) and tables (.tex)
