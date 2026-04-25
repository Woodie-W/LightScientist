---
name: idea-evaluate
description: Deep evaluation of top fuzzing research ideas. Downloads and reads related papers for novelty verification, performs feasibility analysis via source code inspection, and produces a final recommendation with experiment plan and references. Use after idea-generate has produced IDEAS_CANDIDATES.md.
---

# Idea Evaluate

Deep evaluation of candidate research ideas. **Download and read full papers** that might overlap with the proposed ideas. Produce a final selection with proper references and an actionable experiment plan.

## Inputs

- `phase1-idea/IDEAS_CANDIDATES.md` — ranked idea candidates from `idea-generate`
- `phase1-idea/LITERATURE_SURVEY.md` — for reference
- `phase1-idea/papers/` — previously downloaded papers

## Prerequisites

`phase1-idea/IDEAS_CANDIDATES.md` must exist. If not, invoke `idea-generate` first.

## Procedure

### 1. Novelty Verification (Read Full Papers!)

For each top-3 candidate, perform a **thorough** novelty check:

```bash
# Search for closely related work
python tools/arxiv_search.py --query "<specific technique applied to fuzzing>" --max-results 15 --source both

# Download any paper whose title/abstract suggests potential overlap
python tools/arxiv_search.py download --id "<arxiv-id>" --output-dir phase1-idea/papers/
```

**Then read each potentially overlapping paper in full.** Look for:
- **Direct matches**: the exact same technique applied to the same problem (deal-breaker)
- **Partial overlaps**: same technique in a different context, or same problem with a different technique (need clear differentiation)
- **Complementary work**: results that support the feasibility of the proposed approach

> **Do not skip this step.** Abstracts can be misleading. A paper might appear unrelated from its abstract but propose the exact same idea in Section 4. Read the method sections.

For each paper checked, record:

```markdown
| Paper | Year | Overlap? | Details |
|-------|------|----------|---------|
| <title> | <year> | None / Partial / Direct | <what's similar, what's different> |
```

Update the novelty score based on findings. If a candidate turns out to be not novel, drop it and promote the next one.

### 2. Feasibility Deep Dive

For each remaining candidate:

- **Code inspection**: look at the target fuzzer's source code. Can the modification be made cleanly? Read the specific files that would be modified.
- **Dependency check**: are all required tools/libraries available?
- **Prototype estimate**: how long would a minimal prototype take?
- **Evaluation setup**: can we use existing benchmarks, or do we need custom targets?

### 3. Impact Assessment

For each candidate, estimate the realistic impact using evidence from papers you've read:

- **Best case**: what improvement is possible if everything works?
- **Expected case**: what's the likely improvement given practical constraints?
- **Worst case**: what's the minimum improvement that would still be publishable?
- **Comparable prior results**: what did similar approaches achieve? (cite specific numbers from papers)

### 4. Risk Matrix

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Improvement is not statistically significant | Medium | High | Use enough trials (N=10+), test on diverse targets |
| Implementation is harder than expected | Medium | Medium | Start with simplest version, iterate |
| Overhead is too high | Low-Medium | High | Profile early, set performance budget |
| Not novel (similar concurrent work) | Low | Critical | Read full papers, check thoroughly, move fast |

### 5. Final Ranking and Selection

Re-rank all candidates with updated scores. The ideal idea has:
- Novelty ≥ 4/5 (verified by reading full related papers)
- Feasibility ≥ 3/5 (implementable in reasonable time)
- Impact ≥ 3/5 (publishable improvement expected)
- Evaluability ≥ 4/5 (standard benchmarks work)

### 6. Write Final Report

Create `phase1-idea/IDEA_REPORT.md`:

```markdown
# Fuzzing Research Idea Report

## Selected Idea: <name>

### Summary
<2-3 sentence description of the idea and why it's the best choice>

### Research Question
<Crisp statement of what we're investigating>

### Hypothesis
<If we do X, then Y will improve because Z>

### Technical Approach
<Detailed description of the technique>

### Implementation Plan
1. <Step 1 with estimated time>
2. <Step 2 with estimated time>
3. ...
Total estimated time: <X days/weeks>

### Experiment Plan
- **Fuzzer**: <which fuzzer to modify>
- **Targets**: <which programs to fuzz>
- **Baseline**: <what to compare against>
- **Metrics**: primary=<metric>, secondary=<metrics>
- **Duration**: <per-trial duration>
- **Trials**: <number of independent trials>
- **Statistical test**: Mann-Whitney U, α=0.05, A12>0.56

### Expected Outcomes
- Best case: <metric improvement>
- Expected: <metric improvement>
- Minimum publishable: <metric improvement>

### Risks and Mitigations
<From risk matrix>

### Novelty Verification
Papers read and checked for overlap:
| Paper | Year | Local Path | Overlap | Differentiation |
|-------|------|------------|---------|-----------------|
| <title> | <year> | phase1-idea/papers/... | None/Partial | <how our approach differs> |

**Conclusion**: <why we believe this is novel, with evidence>

### References
Key papers that inform this research (all read in full):
1. <Author et al., "Title", Venue Year> — <relevance to our work>
2. <Author et al., "Title", Venue Year> — <relevance>
3. ...

## Runner-Up Ideas
<Brief summary of alternatives in case the selected idea doesn't pan out>

## Decision Rationale
<Why this idea over the others, with references to specific findings from papers>
```

## Output

- `phase1-idea/IDEA_REPORT.md` — final idea selection with experiment plan, references, and novelty verification

This is the key handoff document for Phase 2 (experiment engine).
