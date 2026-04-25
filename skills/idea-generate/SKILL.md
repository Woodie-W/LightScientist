---
name: idea-generate
description: Generate fuzzing research improvement ideas based on the literature survey and full paper reading. Brainstorms multiple approaches, analyzes feasibility, and produces ranked candidates. Use after idea-survey has produced a LITERATURE_SURVEY.md.
---

# Idea Generate

Generate concrete, implementable fuzzing improvement ideas based on identified research gaps and deep understanding of existing work.

## Inputs

- `phase1-idea/LITERATURE_SURVEY.md` — landscape analysis from `idea-survey`
- `phase1-idea/papers/` — downloaded paper PDFs (read these for implementation details)
- Research direction from the caller

## Prerequisites

`phase1-idea/LITERATURE_SURVEY.md` must exist. If not, invoke `idea-survey` first.

## Procedure

### 1. Read the Landscape and Papers

Read `phase1-idea/LITERATURE_SURVEY.md` thoroughly. Then **re-read the most relevant downloaded papers** in `phase1-idea/papers/`, focusing on:

- Implementation details that might inspire new approaches
- Evaluation gaps that suggest untested improvements
- Limitations sections where authors acknowledge weaknesses
- Algorithm descriptions that reveal combination opportunities

### 2. Brainstorm Ideas

Generate 8-12 diverse ideas. For each idea, think about:

- **Which gap does it address?** Map directly to a gap from the survey.
- **What is the core technical insight?** What makes this different from prior work?
- **How would it be implemented?** Which fuzzer components need modification?
- **What evidence supports it?** Cite specific findings from papers you read.
- **What is the expected improvement?** Coverage? Crash finding? Throughput?
- **What is the risk?** What could go wrong? What assumptions might not hold?

**Diversity strategies** to avoid converging on similar ideas:
- Vary the fuzzer component: seed selection, mutation, scheduling, feedback, triage
- Vary the technique: static analysis, machine learning, program analysis, heuristics
- Vary the target type: binaries, protocols, kernels, firmware
- Consider orthogonal improvements: performance, usability, evaluation methodology

### 3. Initial Screening

For each idea, assign preliminary scores (1-5):

| Criterion | Weight | Description |
|-----------|--------|-------------|
| **Novelty** | 30% | Has this been tried before? Is the angle genuinely new? |
| **Feasibility** | 25% | Can it be implemented in weeks, not months? |
| **Impact** | 25% | If it works, how significant is the improvement? |
| **Evaluability** | 20% | Can we convincingly demonstrate it works with standard benchmarks? |

### 4. Devil's Advocate

For the top 5 ideas, apply critical thinking:

- **Prior work check**: has someone already done this? Search arXiv/DBLP for the specific approach. **Download and skim any suspicious matches.**
- **Theoretical soundness**: does the underlying assumption hold? Can we prove or argue it?
- **Practical concerns**: does it add too much overhead? Does it require unrealistic inputs?
- **Evaluation risk**: can the improvement be shown statistically? Or is it marginal?

```bash
# Search for potential overlaps
python tools/arxiv_search.py --query "<specific idea technique>" --max-results 15

# If any results look like they might overlap, download and read them
python tools/arxiv_search.py download --id "<arxiv-id>" --output-dir phase1-idea/papers/
```

### 5. Refine Top Ideas

For the top 3-4 ideas after screening, flesh out:

```markdown
### Idea: <short name>

**Gap addressed**: <which research gap from the survey>

**Core insight**: <1-2 sentences on the key technical contribution>

**Supporting evidence**: <cite specific findings from papers you read that support this idea>

**Approach**:
1. <Step 1>
2. <Step 2>
3. ...

**Implementation scope**:
- Fuzzer to modify: <AFL++, libFuzzer, etc.>
- Components affected: <mutation engine, scheduler, feedback loop, etc.>
- Estimated LOC: <rough estimate>
- Dependencies: <any special tools or libraries needed>

**Expected outcome**:
- Primary metric: <expected improvement range>
- Secondary: <other expected effects>

**Risks**:
- <Risk 1 and mitigation>
- <Risk 2 and mitigation>

**Evaluation plan**:
- Targets: <which programs to fuzz>
- Baseline: <what to compare against>
- Duration: <how long per trial>
- Trials: <how many independent runs>

**Novelty score**: X/5
**Feasibility score**: X/5
**Impact score**: X/5
**Evaluability score**: X/5
**Weighted total**: X.X/5
```

### 6. Write Ideas Report

Create `phase1-idea/IDEAS_CANDIDATES.md`:

```markdown
# Fuzzing Research Ideas: <direction>

## Generation Summary
- Based on: LITERATURE_SURVEY.md
- Papers read in full: <N>
- Ideas generated: <N total>
- After screening: <M candidates>
- Date: <ISO date>

## Ranked Ideas

### 1. <Top idea> (Score: X.X/5)
<Full description from step 5>

### 2. <Second idea> (Score: X.X/5)
<Full description>

...

## Eliminated Ideas
| Idea | Reason for elimination |
|------|----------------------|
| ... | ... |
```

## Output

- `phase1-idea/IDEAS_CANDIDATES.md` — ranked and detailed idea list

This feeds into `idea-evaluate` for deeper evaluation, or into the experiment phase if the project is ready to proceed.
