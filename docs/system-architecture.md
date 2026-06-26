# LightScientist System Architecture

## Goal

`LightScientist` uses a simple three-layer architecture for long-running research work:

- Layer 1 keeps the project state machine small and deterministic.
- Layer 2 supervises one active research stage.
- Layer 3 runs concrete worker sessions with DeepAgents.

The main design goal is to keep project control small while still allowing persistent worker sessions, background work, cancellation, and stage-based research flow.

## Top-Level Structure

```text
CLI / user
  -> Layer 1: ResearchController
       -> Layer 2: RuntimeSupervisor
            -> Layer 3: ExecutionRuntime
                 -> DeepAgent worker session
                      -> workspace tools / shell / files / experiments
```

Two agent layers use the model API:

- the second-layer supervisor agent
- third-layer worker agents

The first layer is deterministic code.

The default model endpoint is DeepSeek's OpenAI-compatible API:

```text
BASE_URL=https://api.deepseek.com
MODEL=deepseek-v4-pro
API_KEY from DEEPSEEK_API_KEY or LIGHTSCIENTIST_API_KEY
thinking=enabled
reasoning_effort=high
```

Other OpenAI-compatible services can still be selected with `LIGHTSCIENTIST_BASE_URL`, `LIGHTSCIENTIST_MODEL`, and `LIGHTSCIENTIST_API_KEY`.

## Responsibilities By Layer

### Layer 1

Owns:

- project phase and stage
- stage prompt construction
- manual vs auto gate policy
- project-level files
- stage transition validation

Exposes only project-control tools:

- `finish_stage(...)`
- `request_user_decision(...)`

### Layer 2

Owns:

- worker records
- worker event queue
- supervisor event queue
- scheduled resume queue
- one persistent supervisor session for the current task

Exposes runtime tools to the supervisor agent:

- `get_task`
- `list_workers`
- `get_worker`
- `start_worker`
- `resume_worker`
- `cancel_worker`
- `schedule_worker_resume`

Plus first-layer project-control tools:

- `finish_stage`
- `request_user_decision`

### Layer 3

Owns:

- persistent DeepAgent sessions
- worker start / resume / cancel
- workspace tool execution
- lifecycle states
- per-run delivery file and debug log

Worker tools include:

- DeepAgents workspace tools such as `execute`, `read_file`, `write_file`, `edit_file`, `grep`, `glob`, `ls`, `write_todos`, `read_todos`, `task`
- custom lifecycle tools `ask_input`, `suspend_background`, `finish_cancelled`

## Research State Machine

The project-level pipeline is:

```text
idea -> experiment -> paper -> done
```

Current stage table:

```text
idea.survey -> idea.generate -> idea.evaluate -> idea.gate
idea.generate -> idea.probe_batch -> idea.probe_collect -> idea.gate

experiment.setup -> experiment.loop -> experiment.analyze -> experiment.gate

paper.plan -> paper.figure -> paper.write -> paper.review -> done
```

Cross-phase transitions go through gate stages:

- `idea.gate -> experiment.setup`
- `experiment.gate -> paper.plan`
- `paper.review -> done`

The second layer may suggest the next stage, but the first layer validates it.

## State And Memory Files

Project-level files:

```text
.lightscientist/project_state.json
.lightscientist/events.jsonl
PROCESS.md
```

Phase outputs:

```text
phase1-idea/LITERATURE_SURVEY.md
phase1-idea/IDEAS_CANDIDATES.md
phase1-idea/IDEA_REPORT.md
phase1-idea/PROBE_SUMMARY.md

research.md
research.jsonl
phase2-experiment/worklog.md
phase2-experiment/EXPERIMENT_RESULTS.md

phase3-paper/PAPER_PLAN.md
phase3-paper/figures/
phase3-paper/paper/main.pdf
phase3-paper/PAPER_SUMMARY.md
```

`PROCESS.md` is the compact long-term project memory. It stores one concise stage summary instead of replaying full logs into future prompts.

## Main Control Flow

The normal project flow is:

1. CLI starts `ResearchController`.
2. Layer 1 loads project state.
3. Layer 1 builds the stage prompt.
4. Layer 1 starts one `RuntimeSupervisor` for that stage.
5. Layer 2 starts or resumes third-layer workers.
6. Layer 3 reads files, runs commands, writes artifacts, and reports status.
7. Layer 2 supervises worker events and decides whether the stage should continue, block, fail, or complete.
8. Layer 2 calls `finish_stage(...)` or `request_user_decision(...)`.
9. Layer 1 validates outputs, updates project state, and either transitions or waits for user reply.

## Worker Lifecycle

Third-layer worker states are:

- `running`
- `waiting`
- `background`
- `completed`
- `failed`
- `cancelled`

Meaning:

- `waiting`: worker needs explicit new input; resume goes through LangGraph interrupt resume
- `background`: worker intentionally pauses after launching or delegating future work; resume uses a normal message on the same session
- `cancelled`: upper layer stopped the worker; cancellation handoff is preserved

The second layer records these states in `AgentRecord`.

## Event Flow

The third layer sends `RuntimeUpdate` upward:

- `status`
- `text`
- `progress`
- `result`
- `thread_id`

The second layer updates worker records, and only meaningful changes become `SupervisorEvent` inputs for the supervisor agent.

Ordinary `running -> running` progress updates do not go into the supervisor decision queue.

Supervisor-relevant events are:

- status transitions
- final results
- cancellations
- stall detection events

## Observable Agent Events

The runtime also has a side-channel event stream for watching Agent behavior.

This stream is observational only. It does not drive control flow.

Core pieces:

- `AgentEvent`
- `EventBus`
- `JsonlEventSink`
- `ConsoleEventSink`

Events are written to:

```text
.lightscientist/events.jsonl
```

When CLI `--watch` is enabled, the same events are printed live.

Example:

```text
[L1 stage_started] idea.survey stage-idea-survey
[L2 worker_created] stage-idea-survey agent-stage-idea-survey Worker created.
[L3 model_call] stage-idea-survey agent-stage-idea-survey Step 1: querying model.
[L3 tool_call] stage-idea-survey agent-stage-idea-survey execute(command=...)
[L3 tool_result] stage-idea-survey agent-stage-idea-survey ...
[L2 supervisor_decision] stage-idea-survey supervisor TASK_COMPLETED: ...
```

Current observed event families:

- Layer 1: stage lifecycle and user-decision events
- Layer 2: worker records, supervisor queue, decisions, stall and scheduled resume events
- Layer 3: session lifecycle, model calls, model outputs, tool calls, tool results, waiting/background/cancelled events

The detailed third-layer debug log remains `agent-debug.log`.

## Background And Waiting

The two pause modes are intentionally different.

`waiting`:

- triggered by `ask_input(question)`
- used when progress truly depends on missing external input
- resumes through interrupt resume

`background`:

- triggered by `suspend_background(note)`
- used when useful work must continue outside the current turn, such as a running experiment
- can be resumed later by `schedule_worker_resume(agent_id, seconds, message)`

This keeps “need an answer now” separate from “check again later”.

## Cancellation

Cancellation flows downward through the second layer into the third layer:

1. Layer 2 calls `ExecutionRuntime.cancel(agent_id)`.
2. Layer 3 asks the worker session to finalize cancellation when possible.
3. The worker preserves useful outputs and can call `finish_cancelled(summary)`.
4. If finalization times out, the runtime returns a fallback cancelled result.
5. Registered shell subprocesses are terminated through the process registry.
6. Layer 2 stores the cancelled result and emits a cancellation event to the supervisor.

The worker session is then removed from executor state and cannot be resumed again.

## Prompt Strategy

Prompt size is controlled by layer.

Layer 1 gives the second layer:

- current stage context
- current `SKILL.md` path
- required output
- allowed next stages
- compact project memory and Phase 2 summary

Layer 2 gives the supervisor agent:

- task objective
- one incremental `SupervisorEvent`
- optional condition prompt for `waiting`, `background`, or `stalled`

Layer 3 worker prompt stays focused on concrete execution.

This keeps long-term project context in files and small summaries instead of endlessly growing chat history.

## Current Limits

The current implementation intentionally stays small:

- third-layer sessions are in-memory only
- top-level CLI does not expose general session resume management
- first layer is deterministic code, not a LangGraph controller
- project memory is document-based, not vector-memory based

Those limits are deliberate. The current system prioritizes clear layer boundaries over more features.

## Related Documents

- [`first-layer-research-controller.md`](first-layer-research-controller.md): first layer
- [`second-layer-runtime-supervisor.md`](second-layer-runtime-supervisor.md): second layer
- [`third-layer-execution-runtime.md`](third-layer-execution-runtime.md): third layer
- [`lightscientist-architecture.svg`](lightscientist-architecture.svg): architecture diagram
