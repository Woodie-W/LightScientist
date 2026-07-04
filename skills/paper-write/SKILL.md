---
name: paper-write
description: Write the paper in LaTeX following the paper plan. Produces a compilable manuscript with proper structure, citations, and formatting for the target venue.
---

# Paper Write

Write the full paper in LaTeX based on the paper plan, experiment results, and figures.

## Inputs

- `phase3-paper/PAPER_PLAN.md`
- `phase2-experiment/EXPERIMENT_RESULTS.md`
- `phase1-idea/IDEA_REPORT.md`
- `phase1-idea/LITERATURE_SURVEY.md`
- `phase3-paper/figures/`

## Prerequisites

- `phase3-paper/PAPER_PLAN.md` must exist
- figures should be generated first when needed

## Procedure

### 1. Initialize LaTeX Project

```bash
mkdir -p phase3-paper/paper/sections
```

Set up from a venue template if one exists; otherwise use a generic format.

### 2. Write Each Section

Write sections in order:

- `introduction.tex`
- `background.tex`
- `design.tex`
- `implementation.tex`
- `evaluation.tex`
- `related.tex`
- `conclusion.tex`

### 3. Build References

Create `phase3-paper/paper/references.bib` with real BibTeX entries.

### 4. Quality Checks

Before compiling, verify:

- all claims are supported
- all planned figures and tables are present
- no unresolved references
- terminology is consistent
- all numbers match the experiment data

### 5. Compile

```bash
cd phase3-paper/paper
latexmk -pdf main.tex
```

If compilation is unavailable, still produce complete source files.

### 6. Anti-AI Writing Patterns

Avoid repetitive, generic, obviously machine-written prose patterns.

## Output

- `phase3-paper/paper/main.tex`
- `phase3-paper/paper/sections/*.tex`
- `phase3-paper/paper/references.bib`
- `phase3-paper/paper/main.pdf`
