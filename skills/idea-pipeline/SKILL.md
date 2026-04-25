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

- **Research direction**: a fuzzing research topic or area of interest

If no direction is provided, ask the user. Suggest areas if they're unsure:
- Seed scheduling and power schedules
- Mutation strategies (grammar-aware, learning-based)
- Hybrid fuzzing (with symbolic execution, taint analysis)
- Directed fuzzing (patch testing, bug reproduction)
- Fuzzing for specific domains (OS kernels, network protocols, smart contracts)
- Fuzzing infrastructure (benchmarks, evaluation methodology)

## Procedure

### Stage 1: Literature Survey

Invoke the `idea-survey` skill with the research direction.

**Gate**: Verify `phase1-idea/LITERATURE_SURVEY.md` exists and contains:
- At least 5 key papers analyzed
- At least 3 research gaps identified
- A clear picture of the state of the art

If the survey is too shallow, ask the agent to expand with additional search queries.

### Stage 2: Idea Generation

Invoke the `idea-generate` skill.

**Gate**: Verify `phase1-idea/IDEAS_CANDIDATES.md` exists and contains:
- At least 5 ideas generated
- At least 3 ideas with full descriptions (approach, evaluation plan, scores)
- Diverse ideas (not all variations of the same approach)

### Stage 3: Idea Evaluation

Invoke the `idea-evaluate` skill.

**Gate**: Verify `phase1-idea/IDEA_REPORT.md` exists and contains:
- A selected idea with clear research question and hypothesis
- An implementation plan with time estimates
- An experiment plan with specific targets, metrics, and trial counts
- Risk assessment with mitigations
- At least one runner-up idea as backup

### Stage 4: User Checkpoint

Present the selected idea to the user for approval:

```
Phase 1 complete. Selected idea: <name>

Summary: <1-2 sentences>
Expected improvement: <metric and range>
Implementation time: <estimate>

Options:
1. Proceed to Phase 2 (experiments)
2. Select a different idea from the candidates
3. Generate more ideas
4. Modify the selected idea
```

Wait for user confirmation before proceeding to Phase 2.

## Recovery

If interrupted at any stage:
- Check which output files exist
- Resume from the last incomplete stage
- Don't repeat completed stages unless the user requests it

## Output

- `phase1-idea/search_results.md` — raw paper search results
- `phase1-idea/LITERATURE_SURVEY.md` — landscape analysis
- `phase1-idea/IDEAS_CANDIDATES.md` — ranked idea candidates
- `phase1-idea/IDEA_REPORT.md` — final selection with experiment plan
