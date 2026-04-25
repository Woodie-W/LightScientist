---
name: paper-pipeline
description: Reference document for the full Phase 3 flow. In LightScientist, first-layer stage control owns orchestration; use the fine-grained stage skills for actual execution.
---

# Paper Pipeline

Reference flow for Phase 3: plan the paper, generate figures, write the manuscript, review and improve.

This file is not the active orchestrator in LightScientist. The first-layer
controller owns stage transitions. Use `paper-plan`, `paper-figure`,
`paper-write`, and `paper-review` as the execution skills for real work.

## Inputs

From prior artifacts or the first-layer controller:

- **Venue**: target venue (default: usenix-security)
- `phase2-experiment/EXPERIMENT_RESULTS.md` — experiment results (required)
- `phase1-idea/IDEA_REPORT.md` — research idea (required)
- `phase1-idea/LITERATURE_SURVEY.md` — related work (required)

## Prerequisites

Phase 2 must be complete with statistically significant results. Check:
1. `phase2-experiment/EXPERIMENT_RESULTS.md` exists
2. At least one "keep" result in `research.jsonl` (if it exists)

If prerequisites are not met, warn the user and suggest completing Phase 2 first.

## Procedure

### Stage 1: Paper Plan

Invoke the `paper-plan` skill.

**Gate**: Verify `phase3-paper/PAPER_PLAN.md` exists with:
- Clear title and abstract draft
- Claim-evidence mapping
- Section outline with page budget
- Figure and table plan

### Stage 2: Figures and Tables

Invoke the `paper-figure` skill.

**Gate**: Verify `phase3-paper/figures/` contains:
- At least 2 PDF figures (coverage plot + comparison)
- At least 1 LaTeX table file

### Stage 3: Paper Writing

Invoke the `paper-write` skill.

**Gate**: Verify:
- `phase3-paper/paper/main.tex` exists
- All section files in `phase3-paper/paper/sections/` are non-empty
- `phase3-paper/paper/references.bib` has entries
- `phase3-paper/paper/main.pdf` compiles successfully

### Stage 4: Review and Improvement

Invoke the `paper-review` skill.

Run up to 3 review rounds. **Gate** for completion:
- All critical issues from the latest review are resolved
- Overall score ≥ 3.5/5
- Paper compiles cleanly with no warnings

### Stage 5: Final Summary

Create `phase3-paper/PAPER_SUMMARY.md`:

```markdown
# Paper Summary

## Title
<final title>

## Venue
<target venue>

## Key Results
- <primary finding with numbers>
- <secondary findings>

## Review History
- Round 1: <score>, <N critical issues>, <M major issues>
- Round 2: <score>, <N critical issues>, <M major issues>
- Round 3: <score>, <final assessment>

## Files
- PDF: phase3-paper/paper/main.pdf
- LaTeX source: phase3-paper/paper/
- Figures: phase3-paper/figures/
- Reviews: phase3-paper/reviews/

## Status
<Ready for submission / Needs attention on X>
```

## Recovery

If interrupted:
- Check which output files exist
- Resume from the last incomplete stage
- Don't regenerate figures or rewrite completed sections unless review requires it

## Output

- `phase3-paper/PAPER_PLAN.md` — paper plan
- `phase3-paper/figures/` — figures and tables
- `phase3-paper/paper/` — complete LaTeX project with compiled PDF
- `phase3-paper/reviews/` — review history
- `phase3-paper/PAPER_SUMMARY.md` — final summary
