---
name: paper-figure
description: Generate publication-quality figures and tables for the research paper. Describes what kinds of figures a good paper needs and the quality standards they must meet.
---

# Paper Figure

Generate all figures and tables needed for the paper.

## Inputs

- `phase3-paper/PAPER_PLAN.md`
- `phase2-experiment/results/`
- `phase2-experiment/EXPERIMENT_RESULTS.md`

## What a Good Paper Needs

### Essential Figures

1. main metric comparison figure
2. distribution figure across trials or settings
3. architecture or workflow overview diagram

### Common Additional Figures

- progress-over-time plots
- ablation study results
- sensitivity analysis
- case study
- heatmap across settings

### Essential Tables

1. main comparison table
2. statistical significance table
3. artifact-specific table when useful

## Quality Standards

- readable at paper scale
- distinguishable in grayscale
- vector output where possible
- consistent style
- clear axis labels
- no chart junk
- substantive captions

## LaTeX Integration

- place figures in `phase3-paper/figures/`
- tables may be `.tex` files
- use `\\label{}` and `\\ref{}`
- use `booktabs`

## Approach

Read the paper plan, inspect the data, and create the figures that best tell the paper's story.

## Output

- `phase3-paper/figures/`
