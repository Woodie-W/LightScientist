---
name: paper-write
description: Write the paper in LaTeX following the paper plan. Produces a compilable manuscript with proper structure, citations, and formatting for the target venue. Use after paper-plan has produced PAPER_PLAN.md.
---

# Paper Write

Write the full paper in LaTeX based on the paper plan, experiment results, and figures.

## Inputs

- `phase3-paper/PAPER_PLAN.md` — paper structure and claim-evidence mapping
- `phase2-experiment/EXPERIMENT_RESULTS.md` — data for tables and discussion
- `phase1-idea/IDEA_REPORT.md` — approach description
- `phase1-idea/LITERATURE_SURVEY.md` — related work references
- `phase3-paper/figures/` — generated figures (from `paper-figure`)

## Prerequisites

- `phase3-paper/PAPER_PLAN.md` must exist
- Figures should be generated first (invoke `paper-figure` if `phase3-paper/figures/` is empty)

## Procedure

### 1. Initialize LaTeX Project

```bash
mkdir -p phase3-paper/paper/sections
```

Set up based on venue template from `templates/paper/<venue>/`:

- Copy the venue's style files (.cls, .sty) to `phase3-paper/paper/`
- Create `main.tex` with the proper document class and structure
- Create section files in `phase3-paper/paper/sections/`

If no template exists for the venue, use a generic two-column format.

### 2. Write Each Section

Write sections in order, each in its own file under `phase3-paper/paper/sections/`:

**`introduction.tex`**:
- Start with a compelling hook about fuzzing's importance
- Present the limitation clearly with a concrete example
- State the key insight concisely
- List contributions (3-4 bullets, each with a forward reference)
- Last paragraph: "The rest of this paper is organized as..."
- NO implementation details here — save for Section 3

**`background.tex`**:
- Only include background necessary to understand the approach
- Use a running example if applicable
- Define notation consistently
- Avoid repeating textbook material — cite instead

**`design.tex`**:
- Start with a high-level overview (architecture diagram reference)
- Present the main algorithm with pseudocode in an `algorithm` environment
- Use `\lstlisting` for code snippets if needed
- Explain design decisions and trade-offs
- Each subsection should map to a component

**`implementation.tex`**:
- Lines of code changed/added
- Base fuzzer version
- Language and key libraries
- Engineering challenges and solutions

**`evaluation.tex`**:
- Begin with experimental setup: targets (with table), baseline, hardware, duration, trials
- Present each RQ in its own subsection:
  - State the question
  - Describe the experiment
  - Present the results (reference specific tables and figures)
  - Discuss the findings
- Include a "Threats to Validity" subsection
- ALL numbers must match `phase2-experiment/EXPERIMENT_RESULTS.md` exactly

**`related.tex`**:
- Organize by category, not chronologically
- Compare and contrast, don't just list
- Highlight how our work differs from the closest approaches
- Use `phase1-idea/LITERATURE_SURVEY.md` as the source

**`conclusion.tex`**:
- Summarize contributions (don't just repeat the abstract)
- State the main takeaway
- Briefly mention future work
- No new information

### 3. Build References

Create `phase3-paper/paper/references.bib`:

- Use real BibTeX entries (search DBLP for correct entries)
- Verify every citation exists and is correct
- Use consistent key format: `AuthorYYYY` (e.g., `Bohme2016`)
- Include DOI when available
- Mark any citation that needs verification with `% TODO: verify`

### 4. Quality Checks

Before compiling, verify:

- [ ] All claims in the plan have supporting evidence in the evaluation
- [ ] All figures and tables referenced in the plan are included
- [ ] No unresolved `\ref{}` or `\cite{}` warnings
- [ ] Page count within venue limits
- [ ] No first-person pronouns except in acknowledgments
- [ ] Consistent terminology throughout
- [ ] All numbers match the experiment data

### 5. Compile

```bash
cd phase3-paper/paper
latexmk -pdf main.tex
```

If compilation fails, fix LaTeX errors iteratively. Common issues:
- Missing packages → add `\usepackage{}`
- Undefined references → check label names
- Figure not found → verify paths

### 6. Anti-AI Writing Patterns

Avoid patterns that mark text as AI-generated:
- Don't start paragraphs with "In this paper" or "We propose"
- Vary sentence length and structure
- Use field-specific terminology naturally
- Don't over-hedge ("might", "could potentially") — be direct
- Don't use "delve", "utilize", "leverage", "harness", "myriad"
- Prefer active voice for contributions, passive for methodology

## Output

- `phase3-paper/paper/main.tex` — main LaTeX file
- `phase3-paper/paper/sections/*.tex` — individual sections
- `phase3-paper/paper/references.bib` — bibliography
- `phase3-paper/paper/main.pdf` — compiled PDF
