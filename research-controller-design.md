# First-Layer Research Controller Design

## Goal

Implement the `auto-fuzzing-research` idea with a simple three-layer split:

- Layer 1: deterministic research controller.
- Layer 2: persistent LLM supervisor for one research stage.
- Layer 3: worker agents that read/write files, run experiments, and produce artifacts.

Layer 1 is not an LLM agent. It only controls stage state, prepares prompts, starts the second layer, checks simple gates, and records events.

## Core Model

```text
ResearchController
  -> RuntimeSupervisor
       -> ExecutionRuntime
            -> DeepAgent worker
```

Layer 1 treats Layer 2 + Layer 3 as one controllable subtask runtime.

The user can start from any stage. Full pipeline starts from `idea.survey`; a
paper reproduction or baseline-only task can start from `experiment.setup` with
the user's task description as the project topic.

## State Files

All first-layer state lives under:

```text
.lightscientist/project_state.json
.lightscientist/events.jsonl
```

`project_state.json` stores the current stage:

```json
{
  "project_id": "fuzz-seed-scheduling",
  "topic": "improve AFL++ seed scheduling",
  "mode": "manual",
  "phase": "idea",
  "stage": "idea.survey",
  "status": "running",
  "workspace_root": "/work",
  "current_task_id": "stage-idea-survey",
  "last_summary": "",
  "last_output_path": "",
  "pending_question": ""
}
```

`events.jsonl` is append-only:

```json
{"type":"stage_started","stage":"idea.survey","task_id":"stage-idea-survey"}
{"type":"stage_finished","stage":"idea.survey","status":"completed","output_path":"phase1-idea/LITERATURE_SURVEY.md"}
{"type":"stage_transition","from":"idea.survey","to":"idea.generate"}
```

## Stage Table

Layer 1 owns a fixed stage table. Each stage defines:

- phase
- skill path
- required output path
- default next stage
- allowed next stages
- whether human confirmation is required

The second layer may suggest an allowed next stage, but Layer 1 applies the transition.

## Prompt Strategy

Do not inline all skills into the supervisor prompt.

For the current stage, Layer 1 tells the second layer:

- current phase and stage
- current skill path to read first
- required output path
- allowed next stages
- short global pipeline map
- short current-phase stage list

The second layer must read the current `SKILL.md` by path before acting.

## Tool Visibility

Tools are separated by layer.

Layer 1 is deterministic code and owns project control tools:

```text
finish_stage
request_user_decision
get_project_state (planned)
```

Layer 2 supervisor can see runtime and project-control tools:

```text
get_task
list_workers
get_worker
start_worker
resume_worker
cancel_worker
schedule_worker_resume
finish_stage
request_user_decision
```

Layer 2 must not see worker lifecycle tools:

```text
ask_input
suspend_background
finish_cancelled
```

Layer 3 workers keep worker lifecycle tools:

```text
ask_input
suspend_background
finish_cancelled
```

Meaning:

```text
ask_input = worker execution detail is missing
request_user_decision = supervisor needs project-level human judgment
finish_stage = supervisor submits a stage result to Layer 1
```

## Stage Transition

First implementation:

```text
RuntimeSupervisor completes
Layer 1 checks output path exists when possible
Layer 1 reads the supervisor stage summary
Layer 1 applies NEXT_STAGE if it is allowed
Otherwise Layer 1 moves to default_next
manual mode stops at human gate
auto mode passes human gate automatically
```

Tool-based implementation:

```text
Layer 1 exposes finish_stage(status, summary, output_path, next_stage)
RuntimeSupervisor calls finish_stage
Layer 1 validates next_stage and gate policy
```

Do not expose direct `set_stage` to the second layer.

Layer 1 also exposes:

```text
request_user_decision(question, options)
```

Manual mode:

```text
request_user_decision -> Layer 1 returns waiting to CLI
CLI/user can answer in a later resume flow
```

Auto mode:

```text
request_user_decision is rejected
Supervisor should decide from available evidence or finish as failed
```

Both modes should minimize user interruption. The supervisor should inspect
workspace files, worker states, and artifacts before requesting human input.

### Current Lightweight Protocol

`finish_stage(...)` is the preferred protocol. A temporary text fallback is kept
for debugging: the second-layer supervisor can put a transition suggestion in
its normal completion summary:

```text
TASK_COMPLETED: <summary>
NEXT_STAGE: idea.probe_batch
```

Layer 1 parses `NEXT_STAGE`, validates it against the current stage's
`allowed_next`, and only then applies it. Invalid suggestions are ignored and
recorded as events.

## Phase Jump Rules

The second layer can suggest jumps inside the current phase:

```text
idea.evaluate -> idea.generate
experiment.analyze -> experiment.loop
paper.review -> paper.write
```

Cross-phase transition must go through gate stages:

```text
idea.gate -> experiment.setup
experiment.gate -> paper.plan
paper.review -> done
```

## Initial Stages

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
failed
paused
waiting_user
```

`idea.probe_batch` is reserved for later fan-out/fan-in. First implementation can keep it in the table but does not need parallel execution yet.

## Minimal Implementation Order

1. Add stage table.
2. Add research state load/save.
3. Add stage prompt builder.
4. Add `ResearchController.run_once()`.
5. Add CLI entry for one stage run.
6. Later: add `finish_stage` tool and parallel idea probes.
