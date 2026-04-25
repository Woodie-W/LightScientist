---
name: research-pipeline
description: Reference document for the full end-to-end research flow. In LightScientist, the first-layer controller owns orchestration and state; this file describes the intended pipeline only.
---

# Research Pipeline

Reference end-to-end flow: take a fuzzing research topic and produce a paper.

This file is not the active orchestrator in LightScientist. The first-layer
controller owns state, gates, and stage transitions. Use this file as a high-
level map for how Phase 1, Phase 2, and Phase 3 connect.

## Inputs

- **Research topic**: a fuzzing research direction (e.g., "improve seed scheduling for greybox fuzzing")
- **Venue** (optional): target publication venue (default: usenix-security)

## Flow

```
Topic
  │
  ▼
Phase 1: Idea Engine ──── idea-pipeline
  │                       (survey → generate → evaluate)
  │ IDEA_REPORT.md
  ▼
Gate 1: User confirms idea
  │
  ▼
Phase 2: Experiment Engine ── fuzz-pipeline
  │                           (setup → loop → analyze)
  │ EXPERIMENT_RESULTS.md
  ▼
Gate 2: Significant results exist
  │
  ▼
Phase 3: Paper Engine ──── paper-pipeline
  │                        (plan → figure → write → review)
  │ main.pdf
  ▼
Done: Paper ready for submission
```

## Procedure

### Phase 1: Idea Generation

Run the Phase 1 stages under first-layer control with the research topic.

**Inputs**: research topic from user
**Outputs**: `phase1-idea/IDEA_REPORT.md`

**Gate 1**: After the idea pipeline completes, present the selected idea to the user:

```
═══ Phase 1 Complete: Idea Selected ═══

Research Direction: <topic>
Selected Idea: <idea name>
Summary: <1-2 sentences>
Expected improvement: <metric and range>

Proceed to Phase 2 (experiments)? [yes/no/modify]
```

Wait for user confirmation. If the user wants modifications, update the idea and re-evaluate. If the user rejects all ideas, return to idea generation with a different direction.

### Phase 2: Experiment Loop

Run the Phase 2 stages under first-layer control with:
- Goal from `IDEA_REPORT.md`
- Target and fuzzer from the experiment plan in `IDEA_REPORT.md`

**Inputs**: `phase1-idea/IDEA_REPORT.md`
**Outputs**: `phase2-experiment/EXPERIMENT_RESULTS.md`

This phase runs autonomously and may take hours or days. The agent loops continuously, implementing variations and running experiments.

**Gate 2**: After the experiment loop ends (user stop, idea exhaustion, or context limit), verify:

1. At least one statistically significant improvement was found
2. `phase2-experiment/EXPERIMENT_RESULTS.md` exists with results
3. The improvement is publishable (> 5% on primary metric, p < 0.05, A12 > 0.56)

If no significant results:
- Check `research.ideas.md` for untried ideas
- Consider pivoting to a runner-up idea from `IDEA_REPORT.md`
- If all avenues exhausted, produce a negative results report and stop

```
═══ Phase 2 Complete: Experiments Done ═══

Best Result: <metric> = <value> (+X.X% vs baseline)
Statistical Significance: p=<value>, A12=<value>
Total Experiments: <N runs>, <M kept>

Proceed to Phase 3 (paper writing)? [yes/no/more experiments]
```

### Phase 3: Paper Writing

Run the Phase 3 stages under first-layer control with:
- Venue from user (or default)
- All Phase 1 and Phase 2 outputs

**Inputs**: all prior phase outputs
**Outputs**: `phase3-paper/paper/main.pdf`

```
═══ Phase 3 Complete: Paper Ready ═══

Title: <paper title>
Venue: <target venue>
PDF: phase3-paper/paper/main.pdf
Review Score: <X.X/5>

The paper is ready for author review before submission.
```

## State Management

The original pipeline encoded state implicitly in the filesystem. In
LightScientist, `.lightscientist/project_state.json` is the first-layer source
of truth, while filesystem artifacts remain the execution outputs:

| State Indicator | Meaning |
|----------------|---------|
| No `phase1-idea/` | Not started |
| `phase1-idea/` exists, no `IDEA_REPORT.md` | Phase 1 in progress |
| `IDEA_REPORT.md` exists, no `research.jsonl` | Phase 1 complete, Phase 2 not started |
| `research.jsonl` exists, no `EXPERIMENT_RESULTS.md` | Phase 2 in progress |
| `EXPERIMENT_RESULTS.md` exists, no `phase3-paper/` | Phase 2 complete, Phase 3 not started |
| `phase3-paper/` exists, no `main.pdf` | Phase 3 in progress |
| `main.pdf` exists | Phase 3 complete |

On resume, detect the current state and continue from the appropriate point.

## Error Handling

- **Phase 1 fails** (no good ideas): try a different research direction or broaden the scope
- **Phase 2 fails** (no significant results): try runner-up ideas, or write a negative results paper
- **Phase 3 fails** (paper doesn't compile): fix LaTeX errors, simplify figures
- **Any phase interrupted**: resume from the last checkpoint (all phases support resume)

## Time Expectations

| Phase | Typical Duration | Agent-Hours |
|-------|-----------------|-------------|
| Phase 1: Ideas | 30-60 minutes | 1-2 |
| Phase 2: Experiments | 1-7 days | 10-50+ (mostly fuzzer wall clock) |
| Phase 3: Paper | 2-4 hours | 2-4 |

Phase 2 dominates the timeline because fuzzing experiments require wall-clock time (24h per full run × multiple runs).
