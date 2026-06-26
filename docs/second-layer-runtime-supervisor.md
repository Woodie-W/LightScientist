# Second-Layer RuntimeSupervisor

## Role

The second layer is `RuntimeSupervisor`.

It supervises one active stage task and manages a set of third-layer workers under that task.

It is an LLM-assisted control layer, but its control loop is deterministic code:

- worker state updates are handled in Python
- worker events are queued in Python
- the supervisor agent is invoked only when a meaningful event needs a decision

This layer is the bridge between project control and concrete execution.

## Core Structure

```text
RuntimeSupervisor
  -> worker records
  -> result store
  -> runtime update queue
  -> supervisor event queue
  -> scheduled resume queue
  -> one supervisor agent session
  -> ExecutionRuntime
```

The second layer itself is not a separate runtime framework. Its supervisor agent reuses the same DeepAgent session mechanism as the third layer.

## Main Responsibilities

The second layer owns:

- the current supervised task record
- all worker `AgentRecord`s under that task
- routing of third-layer status updates
- deciding which worker events should reach the supervisor agent
- scheduled future resumes for background workers
- exposing query/control tools to the supervisor agent

The second layer does not own:

- project phase transitions
- project-level state files
- direct shell execution logic
- DeepAgent worker internals

## Runtime Model

One `RuntimeSupervisor` manages one task at a time.

That task may have multiple workers, but they are scoped to this supervisor only. Workers are not intended to be globally visible across unrelated supervisors.

The startup path is:

1. Layer 1 calls `RuntimeSupervisor.start(RuntimeTask)`.
2. The second layer creates the first worker record.
3. It starts a background thread for the worker through `ExecutionRuntime`.
4. It waits for the first terminal-or-paused result.
5. While running, updates flow through the control loop and can trigger supervisor decisions.

## Data Model

The main worker record is `AgentRecord`.

It stores:

- `agent_id`
- `task_id`
- `objective`
- `status`
- `thread_id`
- `resume_mode`
- `progress`
- `progress_text`
- `stall_reported`
- `workspace_root`
- `output_path`

`progress` is `AgentProgress`:

- `step_count`
- `action_count`
- `last_activity_at`

The second layer also stores final `ExecutionResult`s in `_results`.

## Event Flow

The third layer sends `RuntimeUpdate`.

The second layer handles it in two steps:

1. `_update_agent(...)` updates the worker record and cached result.
2. `_handle_update(...)` decides whether the supervisor agent should be notified.

Current rule:

- ordinary `running -> running` progress only updates the record
- status changes or final results create `SupervisorEvent`

That keeps the supervisor from being spammed by every minor step.

In addition to control events, the second layer also emits observable `AgentEvent`s through `EventBus`.

Current second-layer watch events include:

- `task_started`
- `worker_created`
- `worker_progress`
- `worker_status`
- `supervisor_event_queued`
- `supervisor_started`
- `supervisor_decision`
- `worker_resume_dispatched`
- `worker_resume_scheduled`
- `scheduled_resume_due`
- `worker_stalled`

These events are for logs and CLI watch output only. They do not change the supervisor control rules.

## Supervisor Queue Model

The second layer uses two queues:

- `_queue`
  receives raw `RuntimeUpdate`s from workers
- `_supervisor_queue`
  stores higher-level `SupervisorEvent`s for the supervisor agent

The control loop does this:

1. drain worker updates
2. update worker records
3. convert meaningful updates into supervisor events
4. if the supervisor agent is idle, pop exactly one event and forward it
5. while the supervisor agent is busy, keep accumulating events
6. periodically check stalls and due scheduled resumes

This is intentionally simple and keeps supervisor decisions serialized.

## Supervisor Agent

The supervisor agent is a persistent DeepAgent session with:

- the supervisor prompt
- normal workspace tools
- second-layer runtime tools
- first-layer project-control tools

It does not get worker lifecycle tools like `ask_input`, `suspend_background`, or `finish_cancelled`.

Its input is incremental:

- the task objective
- one `SupervisorEvent`
- an optional condition prompt for `waiting`, `background`, or `stalled`

If it needs more context, it should query it through tools instead of receiving everything in every prompt.

## Tools Exposed To The Supervisor

Current runtime tools are:

- `get_task()`
- `list_workers()`
- `get_worker(agent_id)`
- `start_worker(objective)`
- `resume_worker(agent_id, text)`
- `cancel_worker(agent_id)`
- `schedule_worker_resume(agent_id, seconds, message)`

These are standard DeepAgent tools, not a custom action protocol.

Semantics:

- `start_worker` and `resume_worker` are non-blocking dispatch tools
- their results come back later as worker events
- `schedule_worker_resume` lets the supervisor decide now and wake the same worker later without another supervisor decision

The second layer may also expose first-layer tools through `supervisor_tools`, currently:

- `finish_stage(...)`
- `request_user_decision(...)`

## Supervisor Output Contract

The supervisor prompt expects exactly one line:

- `TASK_COMPLETED: <summary>`
- `TASK_FAILED: <summary>`
- `TASK_CONTINUE: <summary>`

`RuntimeSupervisor` parses that line in `_apply_supervisor_result(...)` and updates the task summary/status.

This keeps the second-layer supervisor contract minimal.

## Waiting, Background, And Resume

The second layer distinguishes the two pause modes by `resume_mode`.

If a worker is `waiting`:

- `resume_mode = interrupt`
- resume should provide the missing answer

If a worker is `background`:

- `resume_mode = message`
- resume is a normal follow-up message on the same session

The second layer can also schedule a direct future resume for a background worker:

```text
schedule_worker_resume(agent_id, seconds, message)
```

When the delay expires, the control loop resumes that worker directly without first asking the supervisor again.

## Stall Detection

Only `running` workers participate in stall detection.

The second layer checks:

- current time
- `last_activity_at`
- `action_count`

If a worker stays `running` without activity longer than `stall_timeout`, the second layer emits a `SupervisorEvent` with `kind="stall"`.

`waiting` and `background` are intentional pause states and are not treated as stalls.

## Cancellation

Second-layer cancellation is simple by design.

`cancel_worker(agent_id)`:

1. calls `ExecutionRuntime.cancel(agent_id)`
2. stores the returned `ExecutionResult`
3. updates the worker state to `cancelled`
4. wakes any waiter for that worker
5. emits a cancellation event for the supervisor agent

The second layer does not write cancellation handoff content itself. That content should come from the worker when possible.

## Boundaries

The second layer should make supervision decisions, not do the main scientific work itself.

It may inspect files and logs when needed, but its default behavior should be:

- inspect state
- reuse a useful worker
- start a new worker only when necessary
- avoid excessive parallel workers
- prefer delayed resume over unnecessary cancellation
- finish the stage only when the stage objective is really satisfied

This keeps the second layer small and focused.
