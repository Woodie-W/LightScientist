---
name: paper-review
description: Automated review and improvement loop for the paper. Simulates reviewer feedback, identifies weaknesses, and iteratively improves the manuscript. Use after paper-write has produced a compilable PDF.
---

# Paper Review

Simulate rigorous review for a reproduction-and-optimization manuscript and iteratively improve it.

## Inputs

- `phase3-paper/paper/main.pdf` — compiled paper
- `phase3-paper/paper/sections/*.tex` — LaTeX source files
- `phase3-paper/PAPER_PLAN.md` — original plan for reference
- `phase2-experiment/REPRODUCE_COMPLETE.md` — reproduction baseline reference

## Prerequisites

A compilable paper must exist. If `main.pdf` is missing, invoke `paper-write` first.

## Procedure

### 1. Self-Review Pass

Read the entire paper (all `.tex` files) and evaluate against these criteria:

**Technical Soundness** (1-5):
- Are claims supported by evidence?
- Is the reproduced baseline stated clearly and compared correctly?
- Is the statistical methodology correct?
- Are there logical gaps in the argument?
- Are threats to validity adequately discussed?

**Novelty** (1-5):
- Is the optimization contribution clearly separated from the original paper's contribution?
- Does the manuscript avoid pretending this is a broader novelty claim than was actually tested?

**Presentation** (1-5):
- Is the paper well-organized and easy to follow?
- Are figures and tables clear and informative?
- Is the writing concise and precise?
- Are there grammatical errors?

**Evaluation** (1-5):
- Are the benchmarks appropriate and sufficient?
- Is the experimental methodology sound (enough trials, proper baselines)?
- Are the results reproducible from the description?
- Are failure cases and scope limits stated honestly?

### 2. Simulate Reviewer Feedback

Generate 3 simulated reviews, each from a different perspective:

**Reviewer 1 — Domain Expert** (focuses on technical depth):
- Does the approach make sense theoretically?
- Are there edge cases or failure modes not discussed?
- How does this compare to the most recent related work?

**Reviewer 2 — Systems Researcher** (focuses on evaluation):
- Is the evaluation comprehensive enough?
- Are the baselines fair?
- Is the statistical analysis correct?
- Are there missing experiments?

**Reviewer 3 — Skeptic** (focuses on weaknesses):
- What would make you reject this paper?
- What claims are overclaimed?
- What is the weakest part of the paper?

### 3. Compile Review Summary

Write `phase3-paper/reviews/review-round-<N>.md`:

```markdown
# Review Round <N>

## Overall Assessment
- Technical Soundness: X/5
- Novelty: X/5
- Presentation: X/5
- Evaluation: X/5
- Overall: X/5

## Critical Issues (must fix)
1. <issue + suggested fix>
2. ...

## Major Issues (should fix)
1. <issue + suggested fix>
2. ...

## Minor Issues (nice to fix)
1. <issue + suggested fix>
2. ...

## Strengths
1. <strength>
2. ...
```

### 4. Address Issues

For each critical and major issue, make the corresponding fix:

- **Missing evidence**: add data from `EXPERIMENT_RESULTS.md` or note that additional experiments are needed
- **Overclaimed results**: tone down language, add caveats
- **Reproduction mismatch**: explain the gap against the reference paper instead of hiding it
- **Presentation issues**: rewrite sections, improve figure clarity
- **Missing related work**: add references from `LITERATURE_SURVEY.md`
- **Statistical concerns**: verify numbers, add confidence intervals

After each fix, mark the issue as resolved in the review document.

### 5. Recompile and Verify

```bash
cd phase3-paper/paper
latexmk -pdf main.tex
```

Verify the PDF is within page limits and all references resolve.

### 6. Iterate

Repeat the review-fix cycle up to 3 rounds. Stop when:
- All critical issues are resolved
- Overall score is ≥ 3.5/5 on all dimensions
- No new critical issues are found

### 7. Final Checklist

Before declaring the paper ready:

- [ ] Title is specific and informative
- [ ] Abstract is self-contained (250 words max)
- [ ] All contributions listed in intro are supported in evaluation
- [ ] Reproduced baseline and optimized result are both explicitly reported
- [ ] All tables and figures are referenced in text
- [ ] References are complete and correctly formatted
- [ ] Page count is within venue limits
- [ ] No TODO markers remain in the text
- [ ] Author information is placeholder (for blind review)

## Output

- `phase3-paper/reviews/review-round-*.md` — review documents
- Updated `phase3-paper/paper/sections/*.tex` — improved sections
- Updated `phase3-paper/paper/main.pdf` — improved PDF
