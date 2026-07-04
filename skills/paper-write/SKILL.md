---
name: paper-write
description: Write the paper/report in LaTeX following the paper plan. Produces a compilable manuscript with proper structure, citations, and formatting for the target venue or report style.
---

# Paper Write

Write the full manuscript in LaTeX based on the paper plan, reproduced baseline, experiment results, and figures.

## Inputs

- `phase3-paper/PAPER_PLAN.md`
- `phase2-experiment/EXPERIMENT_RESULTS.md`
- `phase2-experiment/REPRODUCE_COMPLETE.md`
- `phase1-idea/IDEA_REPORT.md` (optional)
- `phase1-idea/LITERATURE_SURVEY.md` (optional)
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
Do not reshape the task into a broad novelty paper if the project is really a
single-task reproduction-and-optimization report.

### 2. Write Each Section

Write sections in order:

- `introduction.tex`
- `task_definition.tex`
- `reproduction_setup.tex`
- `optimization_method.tex`
- `evaluation.tex`
- `limitations.tex`
- `conclusion.tex`

### 3. Build References

Create `phase3-paper/paper/references.bib` with real BibTeX entries.

### 4. Quality Checks

Before compiling, verify:

- all claims are supported
- the reproduced baseline result is stated exactly
- optimized results are compared directly against that baseline
- all planned figures and tables are present
- no unresolved references
- terminology is consistent
- all numbers match the experiment data
- failures and limitations are explicitly documented

### 5. Compile

```bash
cd phase3-paper/paper
latexmk -pdf main.tex
```

If compilation is unavailable, still produce complete source files.

### 6. Anti-AI Writing Patterns

Avoid repetitive, generic, obviously machine-written prose patterns.

### 7. Hard Constraints

- Do not invent missing metrics, citations, or experiments.
- Do not claim general superiority beyond the reproduced task and tested setup.
- If the optimization failed, write the failure honestly and explain the likely reason.

## Output

- `phase3-paper/paper/main.tex`
- `phase3-paper/paper/sections/*.tex`
- `phase3-paper/paper/references.bib`
- `phase3-paper/paper/main.pdf`
