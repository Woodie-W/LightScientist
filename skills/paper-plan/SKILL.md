---
name: paper-plan
description: Create a structured paper outline with claim-evidence alignment. Maps experiment results to paper sections and figures. Use when starting the paper writing phase or when the current stage is paper planning.
---

# Paper Plan

Create a detailed paper outline that maps experimental evidence to claims, designed for top security venues.

## Inputs

- `phase2-experiment/EXPERIMENT_RESULTS.md` — comprehensive experiment results
- `phase1-idea/IDEA_REPORT.md` — research idea and approach description
- `phase1-idea/LITERATURE_SURVEY.md` — related work context
- **Venue**: target venue (e.g., usenix-security, ieee-sp, acm-ccs, ndss)

## Prerequisites

`phase2-experiment/EXPERIMENT_RESULTS.md` must exist with statistically significant results. If not, warn that Phase 2 should complete first.

## Procedure

### 1. Extract Claims from Results

Read `phase2-experiment/EXPERIMENT_RESULTS.md` and identify all supportable claims:

- **Primary claim**: the main result (e.g., "Our approach improves branch coverage by X% on average across Y targets")
- **Secondary claims**: additional findings (e.g., "Our approach finds Z more unique crashes", "Overhead is less than W%")
- **Negative results**: things that didn't work (important for honesty)

For each claim, identify the specific evidence:
- Which runs support it?
- What are the exact numbers (mean, std, p-value, A12)?
- Which figures/tables would illustrate it?

### 2. Design Paper Structure

Standard fuzzing paper structure for top security venues:

```
1. Introduction (1-1.5 pages)
   - Problem motivation
   - Limitation of existing approaches
   - Key insight / contribution
   - Summary of results
   - Paper organization

2. Background & Motivation (1-1.5 pages)
   - Fuzzing fundamentals relevant to our approach
   - Running example showing the limitation
   - Problem formalization (if applicable)

3. Approach / Design (2-3 pages)
   - Overview / architecture
   - Key algorithm(s) with pseudocode
   - Implementation details

4. Implementation (0.5-1 page)
   - Lines of code, base fuzzer, language
   - Engineering decisions

5. Evaluation (3-4 pages)
   - Research questions (RQ1, RQ2, RQ3...)
   - Experimental setup (targets, baseline, duration, trials, hardware)
   - RQ1: Coverage comparison (table + coverage-over-time plots)
   - RQ2: Bug finding (crash table + discovery timeline)
   - RQ3: Ablation study / overhead analysis
   - Threats to validity

6. Related Work (1-1.5 pages)
   - Coverage-guided fuzzing
   - Specific sub-area of our contribution
   - Comparison with closest work

7. Conclusion (0.5 page)
```

### 3. Plan Figures and Tables

Map each claim to visual evidence:

| Figure/Table | Type | Data Source | Supports Claim |
|-------------|------|-------------|----------------|
| Table 1 | Comparison table | All runs, primary metric | Primary |
| Figure 1 | Coverage-over-time | Baseline vs best run | Primary |
| Table 2 | Crash comparison | Crash analysis | Secondary |
| Figure 2 | Box plot | All runs, per-target | Primary |
| Table 3 | Ablation | Ablation runs | Component contribution |
| Figure 3 | Architecture | Design diagram | N/A (explanatory) |

### 4. Research Questions

Formulate 3-4 research questions:

- **RQ1** (main): Does our approach improve coverage/bug-finding compared to the baseline?
- **RQ2** (depth): How does each component contribute? (ablation study)
- **RQ3** (practicality): What is the runtime overhead?
- **RQ4** (optional): Does our approach generalize across different targets/fuzzers?

### 5. Write Plan Document

Create `phase3-paper/PAPER_PLAN.md`:

```markdown
# Paper Plan: <title>

## Target Venue
<venue name, page limit, format>

## Title
<working title>

## Abstract Draft
<150-250 word abstract>

## Claims and Evidence

### Claim 1 (Primary): <statement>
- Evidence: <specific numbers from EXPERIMENT_RESULTS.md>
- Figures: <Figure X, Table Y>
- Significance: p=<value>, A12=<value>

### Claim 2: <statement>
...

## Section Outline

### 1. Introduction
- Hook: <opening sentence>
- Problem: <1 paragraph>
- Limitation: <1 paragraph>
- Our insight: <1 paragraph>
- Contributions: <bullet list>

### 2. Background
- <subsection topics>

### 3. Design
- <subsection topics with key algorithms>

### 4. Implementation
- <key details>

### 5. Evaluation
- RQ1: <question, expected answer, supporting data>
- RQ2: <question, expected answer, supporting data>
- RQ3: <question, expected answer, supporting data>

### 6. Related Work
- <categories of related work>

### 7. Conclusion
- <key takeaway>

## Figures and Tables Plan
<table from step 3>

## References (Key)
<10-15 most important references to cite>

## Writing Notes
- Page budget per section
- Specific style notes for the venue
```

## Output

- `phase3-paper/PAPER_PLAN.md` — detailed paper plan with claim-evidence mapping
