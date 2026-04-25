---
name: idea-survey
description: Survey the fuzzing research landscape for a given topic. Searches arXiv and DBLP, downloads and reads key papers in full, identifies research gaps and trends. Use when starting a new research direction or when the current stage is literature survey.
---

# Idea Survey

Conduct a systematic literature survey of the fuzzing research landscape for a given topic. **Read full papers, not just titles and abstracts.**

## Inputs

- **Research direction**: a fuzzing topic (e.g., "seed scheduling for greybox fuzzing")
- **Scope**: optional constraints (e.g., "last 3 years", "top security venues only")

## Procedure

### 1. Search for Papers

Use the arXiv/DBLP search tool to find relevant papers:

```bash
python tools/arxiv_search.py --query "<research direction>" --max-results 30 --source both --output phase1-idea/search_results.md
```

Also search with related terms and synonyms. For fuzzing topics, consider:
- The technique name + "fuzzing" (e.g., "seed scheduling fuzzing")
- Related concepts (e.g., "power schedule", "energy assignment")
- The broader category (e.g., "greybox fuzzing", "mutation-based fuzzing")

### 2. Download and Read Key Papers (Critical!)

From the search results, identify the 5-8 most important papers and **download their full PDFs**:

```bash
# Download top papers for your main query
python tools/arxiv_search.py download-top --query "<research direction>" --top 5 --output-dir phase1-idea/papers/

# Download specific papers you identified as important
python tools/arxiv_search.py download --id "<arxiv-id>" --output-dir phase1-idea/papers/
```

**Then read each downloaded PDF in full.** For each paper, understand:
- The exact algorithm/technique proposed (not just the abstract summary)
- Implementation details: what code was changed, how many LOC, what fuzzer
- Evaluation methodology: which targets, how many trials, what duration
- Actual numbers: exact coverage improvements, crash counts, p-values reported
- Limitations the authors acknowledge
- Related work the authors cite (follow important citations)

Papers are saved to `phase1-idea/papers/` and indexed in `phase1-idea/papers/index.json`.

> **Why full papers?** Abstracts are marketing. The real contribution, limitations, and gaps are in the method sections, evaluation details, and discussion. You cannot reliably assess novelty or generate meaningful ideas from abstracts alone.

### 3. Identify Key Papers

From both search results and full-text reading, create a ranked list of 10-15 most important papers:

1. **Seminal papers**: foundational work that established the area
2. **State-of-the-art**: most recent advances (last 1-2 years)
3. **Top venue papers**: work published at S&P, USENIX Security, CCS, NDSS, ISSTA, ICSE, ASE, FSE
4. **High-citation papers**: widely cited and influential

### 4. Analyze the Landscape

For each key paper, extract (from full-text reading, not abstracts):
- **Problem**: what specific fuzzing limitation does it address?
- **Approach**: what technique does it propose? (describe the actual algorithm)
- **Evaluation**: what benchmarks and metrics were used? How much improvement? How many trials?
- **Limitations**: what are the acknowledged or evident weaknesses?
- **Key numbers**: exact improvement percentages, statistical significance results

### 5. Identify Research Gaps

Based on deep reading, identify:

1. **Unsolved problems**: issues raised but not adequately addressed
2. **Evaluation gaps**: approaches not tested on certain target types or benchmarks
3. **Combination opportunities**: techniques that haven't been combined
4. **Scalability limitations**: approaches that work in small settings but not at scale
5. **Reproducibility issues**: claims not independently verified
6. **Methodology weaknesses**: papers with insufficient trials, missing statistical tests, or cherry-picked targets

### 6. Write Survey Report

Create `phase1-idea/LITERATURE_SURVEY.md`:

```markdown
# Literature Survey: <research direction>

## Search Summary
- Sources: arXiv, DBLP
- Queries: <list of queries used>
- Papers found: <N total>, <M key papers analyzed>
- **Papers read in full**: <K papers with local paths>
- Date: <ISO date>

## Research Landscape

### Foundational Work
<2-3 seminal papers with key contributions>

### State of the Art
<3-5 most recent and relevant papers, with specific numbers from full-text reading>

### Key Techniques
| Technique | Paper | Year | Improvement | Benchmark | Trials | Stat. Test |
|-----------|-------|------|-------------|-----------|--------|------------|
| ... | ... | ... | ... | ... | ... | ... |

## Research Gaps
1. <Gap 1: description and why it matters, citing specific evidence from papers>
2. <Gap 2: description and why it matters>
3. ...

## Trends
<Emerging directions in the field>

## Papers Read in Full
| # | Title | Authors | Year | Local Path | Key Finding |
|---|-------|---------|------|------------|-------------|
| 1 | ... | ... | ... | phase1-idea/papers/... | ... |
| 2 | ... | ... | ... | phase1-idea/papers/... | ... |

## Recommended Reading
<Ordered list of papers to read for deep understanding>
```

## Output

- `phase1-idea/search_results.md` — raw search results
- `phase1-idea/papers/` — downloaded paper PDFs
- `phase1-idea/papers/index.json` — index of downloaded papers
- `phase1-idea/LITERATURE_SURVEY.md` — structured landscape analysis with full-paper insights

This output feeds into `idea-generate` for generating specific improvement ideas.
