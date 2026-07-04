---
name: idea-pipeline
description: Reference document for the full Phase 1 flow. In LightScientist, first-layer stage control owns orchestration; use the fine-grained stage skills for actual execution.
---

# Idea Pipeline

Reference flow for Phase 1: survey the literature, generate ideas, evaluate and select the best one.

This file is not the active orchestrator in LightScientist. The first-layer
controller owns stage transitions. Use `idea-survey`, `idea-generate`,
`idea-evaluate`, `idea-probe`, and `idea-probe-collect` as the execution
skills for real work.

## Inputs

From the project goal or first-layer controller:

- **Research direction**: a research topic or area of interest

If no direction is provided, ask the user. Suggest areas if they are unsure:

- modeling or algorithm changes
- training or optimization changes
- evaluation or benchmark improvements
- workflow or tooling improvements
- domain-specific adaptations

## Procedure

### Stage 1: Literature Survey

Invoke the `idea-survey` skill.

**Gate**: verify `phase1-idea/LITERATURE_SURVEY.md` exists and is substantive.

### Stage 2: Idea Generation

Invoke the `idea-generate` skill.

**Gate**: verify `phase1-idea/IDEAS_CANDIDATES.md` exists and contains multiple serious candidates.

### Stage 3: Idea Evaluation

Invoke the `idea-evaluate` skill.

**Gate**: verify `phase1-idea/IDEA_REPORT.md` exists and contains:

- selected idea
- research question and hypothesis
- implementation plan
- experiment plan
- risk assessment
- at least one runner-up idea

### Stage 4: User Checkpoint

Present the selected idea to the user for approval before proceeding to experiments.

## Recovery

If interrupted:

- check which output files exist
- resume from the last incomplete stage
- do not repeat completed stages unless requested

## Output

- `phase1-idea/search_results.md`
- `phase1-idea/LITERATURE_SURVEY.md`
- `phase1-idea/IDEAS_CANDIDATES.md`
- `phase1-idea/IDEA_REPORT.md`
