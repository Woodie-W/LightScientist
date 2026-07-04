---
name: idea-survey
description: Survey the research landscape for a given topic. Searches arXiv and DBLP, downloads and reads key papers in full, identifies research gaps and trends.
---

# Idea Survey

Conduct a systematic literature survey for a given topic. **Read full papers, not just titles and abstracts.**

## Inputs

- **Research direction**: the current research topic or problem statement
- **Scope**: optional constraints such as time range, venue, or domain

## Procedure

### 1. Search for Papers

Use the arXiv/DBLP search tool:

```bash
python tools/arxiv_search.py --query "<research direction>" --max-results 30 --source both --output phase1-idea/search_results.md
```

Also search with related terms and synonyms:
- the technique name
- broader task category
- baseline method names
- domain-specific terminology

### 2. Download and Read Key Papers (Critical!)

From the search results, identify the 5-8 most important papers and download their full PDFs:

```bash
python tools/arxiv_search.py download-top --query "<research direction>" --top 5 --output-dir phase1-idea/papers/
python tools/arxiv_search.py download --id "<arxiv-id>" --output-dir phase1-idea/papers/
```

Then read each downloaded PDF in full. For each paper, understand:
- the exact method proposed
- implementation details
- evaluation methodology
- actual numbers reported
- limitations
- related work worth following

### 3. Identify Key Papers

Create a ranked list of 10-15 important papers:

1. seminal papers
2. recent state of the art
3. top venue papers
4. highly influential papers

### 4. Analyze the Landscape

For each key paper, extract:
- **Problem**
- **Approach**
- **Evaluation**
- **Limitations**
- **Key numbers**

### 5. Identify Research Gaps

Based on deep reading, identify:

1. unsolved problems
2. evaluation gaps
3. combination opportunities
4. scalability limitations
5. reproducibility issues
6. methodology weaknesses

### 6. Write Survey Report

Create `phase1-idea/LITERATURE_SURVEY.md` with:

- search summary
- landscape summary
- key techniques table
- research gaps
- trends
- papers read in full
- recommended reading

## Output

- `phase1-idea/search_results.md`
- `phase1-idea/papers/`
- `phase1-idea/papers/index.json`
- `phase1-idea/LITERATURE_SURVEY.md`
