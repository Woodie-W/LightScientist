---
name: research-pipeline
description: Reference document for the full end-to-end research flow. In LightScientist, the first-layer controller owns orchestration and state; this file describes the intended pipeline only.
---

# Research Pipeline

Reference end-to-end flow: take a research topic and produce a paper or report.

This file is not the active orchestrator in LightScientist. The first-layer
controller owns state, gates, and stage transitions. Use this file as a high-level map for how Phase 1, Phase 2, and Phase 3 connect.

## Inputs

- **Research topic**: a concrete research direction, reproduction goal, or analysis target
- **Venue** (optional): target publication venue or report style

## Flow

```text
Topic
  |
  v
Phase 1: Idea Engine ---- idea-pipeline
  |                       (survey -> generate -> evaluate)
  | IDEA_REPORT.md
  v
Gate 1: User confirms idea
  |
  v
Phase 2: Experiment Engine ---- experiment-pipeline
  |                              (setup -> loop -> analyze)
  | EXPERIMENT_RESULTS.md
  v
Gate 2: Results are strong enough to write up
  |
  v
Phase 3: Paper Engine ---- paper-pipeline
  |                         (plan -> figure -> write -> review)
  | main.pdf
  v
Done
```

## Procedure

### Phase 1: Idea Generation

Run the Phase 1 stages under first-layer control with the research topic.

**Inputs**: research topic from user
**Outputs**: `phase1-idea/IDEA_REPORT.md`

**Gate 1**: after the idea pipeline completes, present the selected idea to the user.

### Phase 2: Experiment Loop

Run the Phase 2 stages under first-layer control with:

- goal from `IDEA_REPORT.md`
- system under study from the experiment plan
- baseline and metrics from the experiment plan

**Inputs**: `phase1-idea/IDEA_REPORT.md`
**Outputs**: `phase2-experiment/EXPERIMENT_RESULTS.md`

This phase runs autonomously and may take hours or days.

**Gate 2**: after the loop ends, verify:

1. meaningful evidence was produced
2. `phase2-experiment/EXPERIMENT_RESULTS.md` exists
3. the results justify writing or clearly justify a negative-results report

If no useful result exists:

- check `research.ideas.md`
- consider pivoting to a runner-up idea
- if exhausted, stop with a negative-results summary

### Phase 3: Paper Writing

Run the Phase 3 stages under first-layer control with:

- venue from user
- all Phase 1 and Phase 2 outputs

**Inputs**: all prior phase outputs
**Outputs**: `phase3-paper/paper/main.pdf`

## State Management

`.lightscientist/project_state.json` is the first-layer source of truth, while filesystem artifacts remain the execution outputs.

| State Indicator | Meaning |
|----------------|---------|
| No `phase1-idea/` | Not started |
| `phase1-idea/` exists, no `IDEA_REPORT.md` | Phase 1 in progress |
| `IDEA_REPORT.md` exists, no `research.jsonl` | Phase 1 complete, Phase 2 not started |
| `research.jsonl` exists, no `EXPERIMENT_RESULTS.md` | Phase 2 in progress |
| `EXPERIMENT_RESULTS.md` exists, no `phase3-paper/` | Phase 2 complete, Phase 3 not started |
| `phase3-paper/` exists, no `main.pdf` | Phase 3 in progress |
| `main.pdf` exists | Phase 3 complete |

## Error Handling

- **Phase 1 fails**: try a different direction or broaden scope
- **Phase 2 fails**: try runner-up ideas or produce a negative-results report
- **Phase 3 fails**: fix writing, figure, or compilation issues
- **Any phase interrupted**: resume from the last checkpoint
