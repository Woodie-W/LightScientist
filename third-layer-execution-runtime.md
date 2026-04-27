# Third-Layer Execution Runtime

## Role

The third layer is the concrete execution layer.

It is composed of:

- `ExecutionRuntime`
- `minimal_agent.py` session wrapper
- `backends.py` workspace backend and custom lifecycle tools

This layer owns persistent DeepAgent worker sessions and is responsible for concrete work such as reading files, editing files, running shell commands, and writing artifacts.

## Core Structure

```text
ExecutionRuntime
  -> AgentSession
       -> DeepAgent
            -> LoggingWorkspaceBackend
            -> workspace tools
            -> lifecycle tools
            -> model API
```

The third layer is session-based. It is no longer a one-shot function.

## Session Model

The persistent object is `AgentSession`.

It stores:

- `session_id`
- `thread_id`
- `cwd`
- `log_path`
- `model`
- `max_steps`
- `checkpointer`
- custom tool list
- `resume_mode`
- `last_result`
- `process_registry`

`checkpointer` is LangGraph `MemorySaver`, so the same thread can continue across resumes while the process stays alive.

## Main Entry Points

Current execution APIs are:

- `ExecutionRuntime.start(agent_id, task, status_cb=None)`
- `ExecutionRuntime.resume(agent_id, user_input, status_cb=None)`
- `ExecutionRuntime.cancel(agent_id, status_cb=None)`

Inside `minimal_agent.py`, the session helpers are:

- `create_agent_session(...)`
- `start_agent_session(...)`
- `resume_agent_session(...)`

`start(...)` creates a session and runs the initial objective.

`resume(...)` continues the same session on the same `thread_id`.

`cancel(...)` tries to let the worker finalize its own handoff before the runtime falls back to a forced cancelled result.

## DeepAgent Composition

Each worker run builds a DeepAgent with:

- the configured chat model from `model_config.py`
- the worker system prompt
- DeepAgents workspace tools
- custom lifecycle tools when enabled
- `LoggingWorkspaceBackend`
- `MemorySaver` checkpointer

No custom multi-action text protocol is used anymore. Tool use is native DeepAgents tool calling.

## Worker Tools

The worker sees standard workspace tools through the backend, including:

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

The worker also gets these custom lifecycle tools:

- `ask_input(question)`
- `suspend_background(note)`
- `finish_cancelled(summary)`

These tools are worker-only. They are not exposed to the second-layer supervisor.

## Status Model

Worker-facing statuses are:

- `running`
- `waiting`
- `background`
- `completed`
- `failed`
- `cancelled`

Meaning:

- `waiting`
  the worker cannot continue without specific external input
- `background`
  the worker intentionally pauses because useful progress depends on future external work
- `cancelled`
  the upper layer stopped the worker and the worker produced or attempted a cancellation handoff

`ExecutionRuntime` maps DeepAgent run results into these external statuses.

## Waiting And Background

`waiting` and `background` are implemented differently on purpose.

`ask_input(question)`:

- calls LangGraph `interrupt(...)`
- ends the current turn in `waiting`
- next resume uses `Command(resume=...)`

`suspend_background(note)`:

- returns a normal tool result
- the current turn ends normally
- the wrapper interprets the last action as `background`
- next resume uses a normal message on the same session

This keeps “I need an answer” separate from “wake me later”.

## Runtime Updates

The third layer reports upward through `RuntimeUpdate`:

- `status`
- `text`
- `progress`
- `result`
- `thread_id`

`progress` is:

- `step_count`
- `action_count`
- `last_activity_at`

The current design is:

- model activity increments progress
- backend tool activity increments progress
- the second layer receives a lightweight structured progress snapshot instead of reconstructing progress from logs

## Logging And Output Files

Each worker keeps:

- `agent-debug.log`
- `agent-run.md`

`agent-debug.log` is the detailed execution trace.

`agent-run.md` is the delivery-oriented run summary written by `ExecutionRuntime._write_result(...)`. It records:

- stage
- status
- steps
- actions
- session id
- thread id
- resume mode
- pending text when applicable
- last action
- log path
- final output
- error section when present

These files are preserved on normal completion and on cancellation.

## Workspace Backend

`LoggingWorkspaceBackend` extends the DeepAgents local shell backend.

It adds:

- workspace-rooted path handling
- output logging for workspace tools
- command execution logging
- process registration for later cancellation

`CommandProcessRegistry` tracks active subprocesses started by `execute(...)`.

If cancellation happens, the runtime can terminate the registered process group.

## Cancellation

Third-layer cancellation tries to preserve as much useful state as possible.

Flow:

1. the upper layer asks `ExecutionRuntime.cancel(agent_id)`
2. if the worker is currently inside a running shell workload, subprocess groups are terminated
3. otherwise the runtime resumes the worker with a cancellation instruction
4. the worker is expected to inspect the workspace if needed, preserve outputs, and call `finish_cancelled(summary)`
5. if finalization times out or errors, the runtime returns a fallback cancelled result
6. the session is removed from the executor registry and can no longer be resumed

This keeps cancellation practical without pretending Python threads can be forcibly killed safely.

## Boundaries

The third layer owns:

- concrete execution
- per-session memory while the process lives
- tool calls
- logs
- subprocess cleanup

The third layer does not own:

- project stage transitions
- worker supervision policy
- project-level user decisions

That separation is what allows the upper layers to stay small.
