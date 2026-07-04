---
name: paper-plan
description: Create a structured paper outline with claim-evidence alignment. Maps experiment results to paper sections and figures.
---

# Paper Plan

Create a detailed outline for a reproduction-and-optimization manuscript that maps experimental evidence to claims.

## Inputs

- `phase2-experiment/EXPERIMENT_RESULTS.md`
- `phase2-experiment/REPRODUCE_COMPLETE.md`
- `phase1-idea/IDEA_REPORT.md` (optional)
- `phase1-idea/LITERATURE_SURVEY.md` (optional)
- **Venue**: target venue or report style

## Prerequisites

`phase2-experiment/EXPERIMENT_RESULTS.md` must exist with meaningful results or a clearly framed negative result.

`phase2-experiment/REPRODUCE_COMPLETE.md` must exist so the plan is anchored to
one fixed reproduced experiment.

## Procedure

### 1. Extract Claims from Results

Identify:

- primary claim about the reproduced task
- secondary claims about the tested optimization
- negative results

For each claim, identify supporting evidence and candidate figures/tables.

### 2. Design Paper Structure

Use a report/manuscript structure that stays tied to the fixed reproduced task:

1. Introduction
2. Task and Reproduction Target
3. Reproduction Setup
4. Optimization Method
5. Results and Analysis
6. Limitations and Failure Cases
7. Conclusion

### 3. Plan Figures and Tables

Map each claim to visual evidence.

### 4. Research Questions

Formulate 3-4 research questions:

- whether the baseline reproduction matches the reference paper
- whether the optimization improves the reproduced baseline
- what trade-offs, overheads, or failures appear
- what conclusions are valid only inside the tested scope

### 5. Write Plan Document

Create `phase3-paper/PAPER_PLAN.md` with:

- target venue
- title
- abstract draft
- claims and evidence
- explicit baseline vs optimized comparison plan
- section outline
- figures and tables plan
- key references
- writing notes

## Output

- `phase3-paper/PAPER_PLAN.md`
