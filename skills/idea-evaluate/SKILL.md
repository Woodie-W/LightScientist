---
name: idea-evaluate
description: Deep evaluation of top research ideas. Downloads and reads related papers for novelty verification, performs feasibility analysis via local project inspection, and produces a final recommendation with experiment plan and references.
---

# Idea Evaluate

Deep evaluation of candidate research ideas. **Download and read full papers** that might overlap with the proposed ideas.

## Inputs

- `phase1-idea/IDEAS_CANDIDATES.md`
- `phase1-idea/LITERATURE_SURVEY.md`
- `phase1-idea/papers/`

## Prerequisites

`phase1-idea/IDEAS_CANDIDATES.md` must exist.

## Procedure

### 1. Novelty Verification (Read Full Papers!)

For each top-3 candidate, perform a thorough novelty check:

```bash
python tools/arxiv_search.py --query "<specific technique and problem>" --max-results 15 --source both
python tools/arxiv_search.py download --id "<arxiv-id>" --output-dir phase1-idea/papers/
```

Then read each potentially overlapping paper in full. Look for:

- direct matches
- partial overlaps
- complementary work

Record the overlap findings and update novelty scores.

### 2. Feasibility Deep Dive

For each remaining candidate:

- inspect the local code/data/workflow surface
- check dependency availability
- estimate prototype effort
- confirm evaluation setup

### 3. Impact Assessment

Estimate:

- best case
- expected case
- worst case
- comparable prior results

### 4. Risk Matrix

Build a risk table with probability, impact, and mitigation.

### 5. Final Ranking and Selection

Re-rank all candidates. The ideal idea has:

- strong novelty
- feasible implementation
- meaningful expected impact
- clear evaluation path

### 6. Write Final Report

Create `phase1-idea/IDEA_REPORT.md` with:

- selected idea
- summary
- research question
- hypothesis
- technical approach
- implementation plan
- experiment plan
- expected outcomes
- risks and mitigations
- novelty verification
- references
- runner-up ideas
- decision rationale

## Output

- `phase1-idea/IDEA_REPORT.md`
