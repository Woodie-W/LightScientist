# Cancel Lifecycle Plan

## Goal

Cancellation should preserve deliverables and let the worker agent summarize its own work whenever possible.

The second layer should not write third-layer delivery content. It should only request cancellation, store the returned result, and notify the supervisor agent.

## Layer Responsibilities

First layer:

- Owns future task-level cancellation.
- Not implemented yet.

Second layer, `RuntimeSupervisor`:

- Owns worker records.
- Owns supervisor event queue.
- Owns worker result records.
- Decides which worker should be cancelled.
- Calls `ExecutionRuntime.cancel(agent_id)`.
- Stores the returned `ExecutionResult`.
- Emits one supervisor event for the cancellation result.

Second layer should not:

- Write cancellation delivery files.
- Summarize third-layer work itself.
- Clean third-layer sessions directly.
- Kill subprocesses directly.

Third layer, `ExecutionRuntime`:

- Owns third-layer `AgentSession` lifecycle.
- Owns `start`, `resume`, and `cancel`.
- Asks the worker agent to finalize cancellation.
- Writes or updates `agent-run.md`.
- Returns `ExecutionResult(status="cancelled", ...)`.
- Removes the in-memory session after cancellation.
- Provides fallback delivery if agent finalization fails.

Third-layer worker agent:

- Inspects current workspace when asked to cancel.
- Summarizes completed work, unfinished work, preserved artifacts, and next steps.
- Calls `finish_cancelled(summary)` when cancellation handoff is ready.

## Phase 1

Implement cooperative cancellation:

1. Add `finish_cancelled(summary)` worker tool.
2. Add `ExecutionRuntime.cancel(agent_id)`.
3. Make `RuntimeSupervisor.cancel_worker(agent_id)` call executor cancel.
4. Add a second-layer result store:

```python
self._results: dict[str, ExecutionResult] = {}
```

5. Store every terminal `ExecutionResult` by `agent_id`.
6. Keep `AgentRecord.result` as a cached pointer for now.

## Phase 2

Implement real subprocess cancellation:

1. Make workspace `execute` keep process handles or process groups.
2. Attach running processes to the worker/session.
3. On force cancel, terminate then kill remaining processes.
4. Preserve files, logs, and `agent-run.md`.

## Current Scope

Do phase 1 only.

Real subprocess kill is intentionally left for phase 2 because the current backend does not keep subprocess handles.
