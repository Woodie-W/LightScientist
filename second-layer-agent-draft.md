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
- basic bash capability

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
- uses bash/tools
- produces artifacts and status updates

## Why Reuse the Third-Layer Runtime

The third layer already has:

- agent session
- start/resume
- waiting via interrupt
- background via persistent session
- bash capability

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

The second-layer agent may keep the basic bash capability.

This is useful for:

- reading worker output files
- reading logs
- inspecting workspace files

### Exposed Runtime Control Functions

The second-layer agent should be given access to existing `RuntimeSupervisor` functions instead of a new action system.

Minimal exposed functions:

- `get_task(task_id)`
- `list_tasks()`
- `get_agent(agent_id)`
- `list_agents()`
- `start(task)`
- `resume(agent_id, text)`

If later needed:

- `cancel(agent_id)`

No new action class hierarchy is needed.

## Control Model

The second-layer controller remains responsible for:

- receiving worker events
- updating shared records
- invoking the supervisor agent

The second-layer agent is responsible for:

- deciding what to do next based on the new event and the current task objective

So the flow becomes:

1. third-layer worker emits an event
2. second-layer controller receives the event
3. second-layer controller updates records
4. second-layer controller invokes the supervisor agent
5. supervisor agent queries status if needed
6. supervisor agent calls `resume(...)`, `start(...)`, or does nothing

## Prompt Direction

The supervisor agent prompt should emphasize:

- you are a supervisor, not the main executor
- prefer reusing existing workers before starting new ones
- inspect state before making decisions
- inspect artifacts/logs/files when needed
- only declare completion when the overall task objective is satisfied

## Minimal First Version

The first supervisor-agent version should stay small.

It only needs to support:

- reading task and worker state
- reading artifacts/logs/files with bash
- resuming a worker
- starting a new worker if needed
- deciding whether the task is complete

It does not need:

- a separate planner
- a complex action schema
- its own storage system
- a new runtime implementation

## Summary

The second-layer agent should reuse the third-layer deepagent runtime and keep the architecture simple.

The design is:

- same agent runtime foundation as the third layer
- different supervisor prompt
- inherited bash capability
- additional access to `RuntimeSupervisor` query/control functions
- event-driven invocation by the second-layer controller

This makes the second-layer agent a supervisor over third-layer workers, without introducing a second independent agent framework.
