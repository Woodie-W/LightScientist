# First-Layer Research Controller

## Role

The first layer is `ResearchController`.

It is a deterministic controller, not a long-lived LLM agent. Its job is to:

- keep the project state machine
- build the stage prompt for the second layer
- validate stage delivery
- write project-level state and history files
- decide stage transitions
- expose the minimal project-control tools to the second layer

The first layer does not directly run experiments and does not directly modify worker state.

## Position In The Stack

```text
CLI / user
  -> ResearchController
       -> RuntimeSupervisor
            -> ExecutionRuntime
                 -> DeepAgent worker
```

For the first layer, the second and third layers are one controllable stage runtime.

## Persistent Files

First-layer persistent state lives in the workspace root:

```text
.lightscientist/project_state.json
.lightscientist/events.jsonl
PROCESS.md
```

`project_state.json` is the current project truth. It stores:

- `project_id`
- `topic`
- `mode`
- `phase`
- `stage`
- `status`
- `workspace_root`
- `current_task_id`
- `output_path`
- `pending_question`
- `pending_next_stage`
- `user_feedback`

`events.jsonl` is append-only and records stage start, finish, transition, gate waiting, and user replies.

`PROCESS.md` is the lightweight long-term project memory. The first layer appends one concise entry after each successful stage delivery so later stages can quickly read project history without replaying all logs.

## Stage Table

The first layer owns the research state table in `research_stages.py`.

Each stage defines:

- `phase`
- `skill_path`
- `output_path`
- `default_next`
- `allowed_next`
- `human_gate`

Current stages:

```text
idea.survey
idea.generate
idea.evaluate
idea.probe_batch
idea.probe_collect
idea.gate

experiment.setup
experiment.loop
experiment.analyze
experiment.gate

paper.plan
paper.figure
paper.write
paper.review

done
```

Cross-phase movement is constrained by the stage table. The second layer may suggest `next_stage`, but the first layer validates and applies it.

## Run Model

The public first-layer entry is `run()`.

Its behavior is:

1. Load or create `project_state.json`.
2. Read the current stage spec.
3. If the stage is a human gate:
   manual mode returns `waiting_user`; auto mode transitions immediately.
4. Build the current stage prompt.
5. Start one `RuntimeSupervisor` with one `RuntimeTask`.
6. Wait for the second layer to return a stage result.
7. Read the stage decision from `finish_stage(...)` or fallback summary parsing.
8. Validate required output existence.
9. Append `PROCESS.md` and `events.jsonl`.
10. Transition to the next stage.
11. Loop until `done`, `failed`, or `waiting_user`.

The first layer no longer exposes the old `run_once()` public flow.

## Prompt Strategy

The first layer does not inline every skill into the prompt.

For the current stage, it sends the second layer:

- the global pipeline map: `idea -> experiment -> paper -> done`
- the project topic
- latest user feedback, when present
- current phase and stage
- the current phase stage list
- the current stage skill path
- the required output path
- the allowed next stages
- standard phase files to inspect directly

This keeps the prompt small and lets the second layer read the current `SKILL.md` on demand.

For experiment stages, the first layer also injects a compact Phase 2 status summary derived from:

- `research.jsonl`
- `research.md`
- `phase2-experiment/worklog.md`
- `phase2-experiment/EXPERIMENT_RESULTS.md`

## Phase 2 State Source

`experiment.loop` is special.

The first layer reads `research.jsonl` and related files to summarize:

- run count
- kept vs discarded runs
- crash count
- sanity failures
- best metric summary
- whether `research.md`, `worklog.md`, and results files exist

This summary is added to the stage prompt so the second layer can decide whether to keep looping, analyze, or gate.

The first layer still validates only a small set of conditions itself. It does not replace the second layer's scientific judgment.

## Project-Control Tools Exposed Downward

The first layer exposes two tools to the second layer:

```text
finish_stage(status, summary, output_path="", next_stage="")
request_user_decision(question, options="")
```

Rules:

- `finish_stage` is the normal delivery path.
- Allowed `status` values are `completed`, `failed`, and `blocked`.
- `next_stage` is only a suggestion; the first layer validates it.
- `request_user_decision` is only for project-level judgment.

Meaning:

- `finish_stage` submits the current stage result upward.
- `request_user_decision` asks the CLI user a project-level question.

The first layer does not expose a direct `set_stage` tool.

## Manual And Auto Modes

Two project modes exist:

- `auto`
- `manual`

In `auto` mode:

- gate stages auto-approve
- `request_user_decision(...)` is rejected
- the second layer should decide from files, workers, and artifacts

In `manual` mode:

- gate stages return `waiting_user`
- the CLI can send `--reply`
- reply format is `y <optional reason>` or `n <optional reason>`

`y` accepts `pending_next_stage`.

`n` rejects the gate and moves to another allowed same-phase stage chosen by first-layer logic.

The optional reason is stored in `user_feedback` and injected into the next stage prompt.

## First-Layer Statuses

Project-level statuses are:

- `idle`
- `running`
- `waiting_user`
- `completed`
- `failed`
- `paused`

These are not worker statuses. They describe the whole research controller state.

## Delivery Rules

A stage is considered successfully delivered only when:

- the second layer reports completion
- the declared or default output path exists

If the required output is missing, the first layer marks the stage as failed even if the second layer claimed completion.

On successful delivery, the first layer:

- updates `state.output_path`
- appends one summary block to `PROCESS.md`
- appends a `stage_finished` event
- transitions to the validated next stage

## Boundaries

The first layer owns:

- project stage machine
- human gate handling
- project-level memory files
- stage transition validation

The first layer does not own:

- worker lifecycle
- worker cancellation mechanics
- experiment shell execution
- direct model tool use

That separation keeps the project controller small and stable.
