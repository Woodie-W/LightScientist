---
name: experiment-setup
description: Set up a generic experiment environment. Prepares code, data, commands, evaluation scripts, and validates with a smoke test when execution is required.
---

# Experiment Setup

Prepare everything needed to run repeated experiments: the local code or artifact surface, runnable commands, evaluation path, data inputs, and smoke test.

## Inputs

The caller provides:

- **System under study**: source code path, project name, model, workflow, or artifact set
- **Baseline**: the reference implementation, command, or configuration
- **Idea description**: what modification or hypothesis is being tested
- **Base config**: optional path to an existing config or experiment manifest

If any of these are missing, infer them from the workspace when possible; otherwise ask the user.

## Procedure

### 1. Inspect the Local Project

Read the local repository or workspace deeply before preparing experiments:

- identify the main code paths or artifact paths
- identify available run commands
- identify where outputs naturally belong
- identify whether the task is execution-heavy or analysis-only

Understanding the local system is essential for meaningful experimentation.

### 2. Identify the Editable Surface

Determine which files, configs, scripts, prompts, or parameters are in scope for experimentation.

Examples:

| Surface | Purpose |
|------|---------|
| source files | implementation changes |
| config files | parameter or pipeline variations |
| prompts / templates | LLM workflow changes |
| evaluation scripts | derived metrics and reporting |
| existing results folders | analysis-only comparison |

### 3. Prepare Workspace Structure

```bash
mkdir -p phase2-experiment
mkdir -p phase2-experiment/results
mkdir -p phase2-experiment/plots
```

If helper scripts are needed for repeatable execution, place them under `phase2-experiment/`.

### 4. Define How the Experiment Runs

Write down:

- the baseline command
- the modified run command
- the primary metric
- important secondary metrics
- where raw outputs will be stored
- how summary numbers will be extracted

If a reusable wrapper script helps consistency, create one in `phase2-experiment/`.

### 5. Prepare Inputs

If the task needs data or fixed artifacts:

- verify paths exist
- verify formats are understood
- create small smoke-test inputs if none exist
- avoid moving or duplicating huge data unless necessary

### 6. Smoke Test

If execution is required, run the smallest valid sanity check:

```bash
# example pattern only — adapt to the real project
bash phase2-experiment/run_experiment.sh --duration short --output-dir phase2-experiment/results/smoke-test --trial-id 0
```

Verify:

- the command exits successfully, or fails in a well-understood way
- the expected outputs are produced
- the primary metric can be extracted
- runtime assumptions are valid

If the smoke test fails, diagnose and fix before proceeding.

### 7. Write Setup Artifacts

Create or update `research.md` with:

- objective
- system under study
- baseline
- metrics
- how to run
- editable surface
- off-limits surface
- constraints

Create or update `phase2-experiment/SETUP_COMPLETE.md`:

```markdown
# Experiment Setup

- **System**: <name or path>
- **Baseline**: <command or artifact>
- **Primary metric**: <name>
- **Secondary metrics**: <list>
- **Inputs**: <key data or artifact paths>
- **Smoke test**: PASSED / SKIPPED / NOT REQUIRED
- **Run entry**: <main command or script>
- **Timestamp**: <ISO timestamp>
```

Initialize `phase2-experiment/worklog.md` if it does not exist.

## Output

- `research.md`
- `phase2-experiment/worklog.md`
- `phase2-experiment/SETUP_COMPLETE.md`
- any helper runner script placed in `phase2-experiment/`

The experiment is now ready for `experiment-reproduce`.
