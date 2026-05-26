# MOEW Example

This example shows how to use `LightScientist` to produce a report for the
CORAL `meow` benchmark without running new long experiments.

The target is not a traditional paper reproduction. The target is:

- audit the benchmark task
- inspect the seed code
- inspect existing CORAL attempts, logs, and notes
- organize the material into a report

It uses the first-layer `paper` phase only:

```text
paper.plan -> paper.figure -> paper.write -> paper.review
```

## Source Material

The example is designed around these existing paths:

- task root: `/data/moew/CORAL/examples/meow`
- seed code: `/data/moew/CORAL/examples/meow/seed`
- existing results: `/data/moew/CORAL/results/meow-lob-deep-alpha`

Important files the agent should inspect:

- `task.yaml`
- `seed/AGENTS.md`
- `seed/DATA.md`
- `seed/REFERENCES.md`
- `seed/solution.py`
- `seed/run_benchmark.py`
- `eval/grader.py`
- `results/.../.coral/public/attempts/*.json`
- `results/.../.coral/public/logs/*.log`
- `results/.../.coral/public/notes/*.md`

## Recommended Workflow

1. Prepare a dedicated workspace under `examples/moew/workspace` with symlinks to the source task and result history.
2. Start `LightScientist` from `paper.plan`.
3. Let the agent build:
   - a report outline
   - attempt/result summary tables
   - a report draft
   - a final review note

The example is designed to avoid modifying the CORAL source tree. The agent should read from `source_task`, `source_seed`, and `source_results`, then write only inside its own workspace.

## Files In This Example

- `prepare_workspace.sh`
  creates a dedicated workspace for the MOEW report task
- `task_prompt.md`
  the exact prompt text recommended for the report-writing run
- `run_paper_report.sh`
  a one-command launcher for the `paper` phase report flow

## Expected Outputs

Inside the prepared workspace, `LightScientist` should generate:

- `.lightscientist/project_state.json`
- `.lightscientist/events.jsonl`
- `PROCESS.md`
- `phase3-paper/PAPER_PLAN.md`
- `phase3-paper/figures/`
- `phase3-paper/paper/main.pdf` or draft-equivalent artifact
- `phase3-paper/PAPER_SUMMARY.md`

The main value of this example is to demonstrate:

- first-layer `paper` stage control
- second-layer supervision over a report task
- third-layer file inspection and report generation
- visible agent behavior through `--watch`
