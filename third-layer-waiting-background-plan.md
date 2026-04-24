# Third Layer Waiting / Background Plan

## Goal

Refine the persistent third-layer agent with a simple split:

- `waiting`: use LangGraph `interrupt()`
- `background`: finish the current round normally, but keep the session in memory

Keep the design minimal:

- no disk persistence
- no job registry
- no top-layer resume command
- no complex pending payload system

## Waiting

`waiting` is for immediate external input.

Implementation:

1. The third-layer agent calls a small `ask_input(question)` tool.
2. That tool calls `interrupt({"type": "waiting", "question": question})`.
3. The current graph run pauses.
4. The second layer stores the session as `waiting`.
5. Later, the second layer resumes the same session with `Command(resume=<text>)`.

## Background

`background` is for "stop this round, continue later".

Implementation:

1. The third-layer agent calls `suspend_background(note)`.
2. The current graph run ends normally.
3. The second layer stores the session as `background`.
4. Later, the second layer resumes the same session by sending a new normal input on the same `thread_id`.

## Remove

Delete the old `WAITING:` text protocol:

- remove it from the system prompt
- stop parsing it in `_status_from_output()`
- replace waiting tests with interrupt-based tests

## Keep

- `thread_id`
- in-memory checkpointer
- `start_agent_session(...)`
- `resume_agent_session(...)`
- `suspend_background(note)`
- current status set:
  - `running`
  - `waiting`
  - `background`
  - `completed`
  - `failed`
  - `cancelled`
