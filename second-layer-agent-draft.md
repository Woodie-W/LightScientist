# Second-Layer Agent Draft

## Goal

The second-layer agent is a supervisor agent.

Its job is not to execute concrete shell/file tasks by itself, but to supervise whether one task has been completed, and decide how third-layer worker agents should continue.

It should:

- watch third-layer worker status changes
- decide whether the overall task is completed
- decide whether to wait, resume a worker, or start another worker
- inspect worker artifacts, logs, and workspace files when needed

It should not replace the third layer as the main execution layer.

## Core Idea

Reuse the same deepagent runtime used by the third-layer agent.

Do not build a separate agent runtime for the second layer.

The second-layer agent should inherit:

- deepagent session/runtime
- thread/checkpointer mechanism
- waiting/background semantics
- the built-in deepagents workspace tools:
  - `execute`
  - `read_file`
  - `write_file`
  - `edit_file`
  - `grep`
  - `glob`
  - `ls`
  - `write_todos`
  - `read_todos`
  - `task`

Only change:

- the system prompt
- the tool set exposed to the agent

## Role Split

### First Layer

- manages overall stage-level goals
- stays minimal for now

### Second-Layer Agent

- supervises one task
- observes third-layer worker events
- decides how the task should continue

### Third-Layer Agent

- executes concrete work
- uses the built-in workspace tools
- produces artifacts and status updates

## Why Reuse the Third-Layer Runtime

The third layer already has:

- agent session
- start/resume
- waiting via interrupt
- background via persistent session
- the built-in workspace tools

So the second-layer agent does not need a new runtime.

It can use the same runtime skeleton, but with a different prompt and different tool exposure.

## Second-Layer Agent Inputs

The supervisor agent should be event-driven.

It should receive:

- the overall task objective
- one new event from the second-layer controller

It should not receive the full worker state every time by default.

If it needs more context, it should query it through tools.

This keeps the interface simple:

- incremental event input
- on-demand state lookup

## Second-Layer Agent Abilities

### Inherited From Third Layer

The second-layer agent inherits the same built-in workspace tools used by the third-layer workers.

This is useful for:

- reading worker output files
- reading logs
- inspecting workspace files
- editing files when supervision requires it

### Exposed Runtime Control Functions

The second-layer agent should be given access to existing `RuntimeSupervisor` functions through deepagents tools instead of a new action system.

Minimal exposed functions:

- `get_task()`
- `list_workers()`
- `get_worker(agent_id)`
- `start_worker(objective)`
- `resume_worker(agent_id, text)`

If later needed:

- `cancel(agent_id)`

No new action class hierarchy is needed.

## Control Model

The second-layer controller remains responsible for:

- receiving worker events
- updating shared records
- enqueueing worker events
- forwarding events to the supervisor agent only when the supervisor is idle

The second-layer agent is responsible for:

- deciding what to do next based on the new event and the current task objective

So the flow becomes:

1. third-layer worker emits an event
2. second-layer controller receives the event
3. second-layer controller updates records
4. second-layer controller appends the event into its deque
5. if the supervisor agent is idle, the controller pops one event and forwards it
6. if the supervisor agent is busy, events remain queued
7. supervisor agent queries status if needed
8. supervisor agent calls `resume_worker(...)`, `start_worker(...)`, or does nothing

## Prompt Direction

The supervisor agent prompt should emphasize:

- you are a supervisor, not the main executor
- on each event, inspect current task/worker state first
- prefer reusing existing workers before starting new ones
- only start a new worker when no existing worker is suitable, or parallel exploration is clearly useful
- only cancel a worker when it is no longer useful
- inspect state before making decisions
- inspect artifacts/logs/files when needed with the built-in workspace tools
- only declare completion when the overall task objective is satisfied
- answer with exactly one line starting with `TASK_COMPLETED:`, `TASK_FAILED:`, or `TASK_CONTINUE:`

## Minimal First Version

The first supervisor-agent version should stay small.

It only needs to support:

- reading task and worker state
- reading artifacts/logs/files with the built-in workspace tools
- resuming a worker
- starting a new worker if needed
- deciding whether the task is complete

It does not need:

- a separate planner
- a complex action schema
- its own storage system
- a new runtime implementation

## Worker Status Flow

Worker status values remain in code, but the transition relationship is documented here instead of hard-coded as a separate table.

Current expected flow:

- `running -> waiting`
- `running -> background`
- `running -> completed`
- `running -> failed`
- `running -> cancelled`
- `waiting -> running`
- `waiting -> cancelled`
- `background -> running`
- `background -> cancelled`

Terminal worker states:

- `completed`
- `failed`
- `cancelled`

The second layer uses these statuses for supervision and resume behavior:

- `waiting` resumes through interrupt resume
- `background` resumes through normal message resume

Worker prompt constraints:

- use `ask_input` only when progress truly depends on missing external input
- keep `ask_input` questions short and concrete
- use `suspend_background(note)` only after work has already been launched and the next useful step depends on a future external result
- do not use `suspend_background` for ordinary work that can continue immediately

## Summary

The second-layer agent should reuse the third-layer deepagent runtime and keep the architecture simple.

The design is:

- same agent runtime foundation as the third layer
- different supervisor prompt
- inherited built-in workspace tools
- additional access to `RuntimeSupervisor` query/control tools
- event-driven invocation by the second-layer controller

This makes the second-layer agent a supervisor over third-layer workers, without introducing a second independent agent framework.
