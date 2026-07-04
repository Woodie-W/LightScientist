---
name: idea-generate
description: Generate research improvement ideas based on the literature survey and full paper reading. Brainstorms multiple approaches, analyzes feasibility, and produces ranked candidates.
---

# Idea Generate

Generate concrete, implementable research ideas based on identified gaps and deep understanding of existing work.

## Inputs

- `phase1-idea/LITERATURE_SURVEY.md`
- `phase1-idea/papers/`
- research direction from the caller

## Prerequisites

`phase1-idea/LITERATURE_SURVEY.md` must exist.

## Procedure

### 1. Read the Landscape and Papers

Read the survey thoroughly. Then re-read the most relevant downloaded papers, focusing on:

- implementation details
- evaluation gaps
- limitations sections
- algorithm descriptions

### 2. Brainstorm Ideas

Generate 8-12 diverse ideas. For each idea, think about:

- which gap it addresses
- the core technical insight
- how it would be implemented
- what evidence supports it
- what metric it should improve
- what could go wrong

Use diversity strategies:

- vary the intervention surface
- vary the technical approach
- vary the evaluation setting
- consider orthogonal improvements

### 3. Initial Screening

For each idea, assign preliminary scores:

- **Novelty**
- **Feasibility**
- **Impact**
- **Evaluability**

### 4. Devil's Advocate

For the top 5 ideas, apply critical thinking:

- check prior work overlap
- test theoretical soundness
- inspect practical concerns
- inspect evaluation risk

```bash
python tools/arxiv_search.py --query "<specific idea technique>" --max-results 15
python tools/arxiv_search.py download --id "<arxiv-id>" --output-dir phase1-idea/papers/
```

### 5. Refine Top Ideas

For the top 3-4 ideas, flesh out:

- gap addressed
- core insight
- supporting evidence
- approach
- implementation scope
- expected outcome
- risks
- evaluation plan
- weighted score

### 6. Write Ideas Report

Create `phase1-idea/IDEAS_CANDIDATES.md` with:

- generation summary
- ranked ideas
- eliminated ideas

## Output

- `phase1-idea/IDEAS_CANDIDATES.md`
