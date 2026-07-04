---
name: paper-plan
description: Create a structured paper outline with claim-evidence alignment. Maps experiment results to paper sections and figures.
---

# Paper Plan

Create a detailed paper outline that maps experimental evidence to claims.

## Inputs

- `phase2-experiment/EXPERIMENT_RESULTS.md`
- `phase1-idea/IDEA_REPORT.md`
- `phase1-idea/LITERATURE_SURVEY.md`
- **Venue**: target venue

## Prerequisites

`phase2-experiment/EXPERIMENT_RESULTS.md` must exist with meaningful results or a clearly framed negative result.

## Procedure

### 1. Extract Claims from Results

Identify:

- primary claim
- secondary claims
- negative results

For each claim, identify supporting evidence and candidate figures/tables.

### 2. Design Paper Structure

Use a standard research paper structure:

1. Introduction
2. Background & Motivation
3. Approach / Design
4. Implementation
5. Evaluation
6. Related Work
7. Conclusion

### 3. Plan Figures and Tables

Map each claim to visual evidence.

### 4. Research Questions

Formulate 3-4 research questions:

- main metric improvement
- component contribution
- practicality or overhead
- optional generalization

### 5. Write Plan Document

Create `phase3-paper/PAPER_PLAN.md` with:

- target venue
- title
- abstract draft
- claims and evidence
- section outline
- figures and tables plan
- key references
- writing notes

## Output

- `phase3-paper/PAPER_PLAN.md`
