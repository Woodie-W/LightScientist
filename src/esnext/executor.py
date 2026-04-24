"""Execution layer for the current LightScientist skeleton."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from .minimal_agent import create_agent_session, resume_agent_session
from .data_models import AgentHandle, AgentRunResult, AgentSession, ExecutionResult, RuntimeTask, RuntimeUpdate

StatusCallback = Callable[[RuntimeUpdate], None]


class ExecutionRuntime:
    """Third-layer execution runtime with command-line capability only."""

    def __init__(self, cancel_timeout: float = 30.0) -> None:
        self.cancel_timeout = cancel_timeout
        self._agents: dict[str, AgentHandle] = {}
        self._running: set[str] = set()
        self._cancelled: dict[str, ExecutionResult] = {}

    def start(self, agent_id: str, task: RuntimeTask, status_cb: StatusCallback | None = None) -> ExecutionResult:
        task.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._emit(status_cb, "running", "Execution runtime received the task.")
        if not task.use_agent:
            text = "Only the agent path is implemented in the current skeleton."
            self._emit(status_cb, "failed", text)
            return ExecutionResult(task.task_id, "failed", text, task.output_path)
        return self._agent_goal(agent_id, task, status_cb)

    def resume(
        self, agent_id: str, user_input: str, status_cb: StatusCallback | None = None
    ) -> ExecutionResult:
        handle = self._agents.get(agent_id)
        if not handle:
            return self._cancelled.get(agent_id) or ExecutionResult(agent_id.removeprefix("agent-"), "failed", f"Unknown agent session: {agent_id}.", Path.cwd() / "agent-run.md")
        self._emit(status_cb, "running", "Resuming persistent agent session.")
        self._running.add(agent_id)
        try:
            r = resume_agent_session(handle.session, user_input, status_cb=status_cb)
        finally:
            self._running.discard(agent_id)
        if agent_id in self._cancelled:
            return self._cancelled[agent_id]
        return self._write_result(handle.task_id, handle.stage_name, handle.output_path, handle.session.log_path, r, status_cb)

    def cancel(self, agent_id: str, status_cb: StatusCallback | None = None) -> ExecutionResult:
        handle = self._agents.get(agent_id)
        if not handle:
            return self._cancelled.get(agent_id) or ExecutionResult(agent_id.removeprefix("agent-"), "failed", f"Unknown agent session: {agent_id}.", Path.cwd() / "agent-run.md")
        if agent_id in self._running:
            killed = handle.session.process_registry.kill_all() if handle.session.process_registry else 0
            result = self._cancel_result(agent_id, handle, f"Worker cancelled. Terminated {killed} running subprocess(es).", status_cb)
            self._agents.pop(agent_id, None)
            return result
        handle = self._agents.pop(agent_id)
        self._emit(status_cb, "running", "Cancelling persistent agent session.")
        message = (
            "The upper layer cancelled this worker. Stop normal task progress now. "
            "Inspect current workspace files if needed, preserve deliverables, write or update delivery "
            "documentation when useful, summarize completed work, unfinished work, preserved artifact paths, "
            "and next steps, then call finish_cancelled(summary)."
        )
        r = self._finalize_cancel(handle, message, status_cb)
        if r.status != "cancelled":
            r.status = "cancelled"  # type: ignore[assignment]
            if not r.final_output:
                r.final_output = "Worker cancelled before producing a cancellation summary."
        result = self._write_result(handle.task_id, handle.stage_name, handle.output_path, handle.session.log_path, r, status_cb)
        self._cancelled[agent_id] = result
        return result

    def _finalize_cancel(self, handle: AgentHandle, message: str, status_cb: StatusCallback | None) -> AgentRunResult:
        box: dict[str, AgentRunResult | Exception] = {}

        def run() -> None:
            try:
                box["result"] = resume_agent_session(handle.session, message, status_cb=status_cb)
            except Exception as e:
                box["error"] = e

        thread = threading.Thread(target=run, daemon=True, name=f"executor-cancel-{handle.task_id}")
        thread.start()
        thread.join(timeout=self.cancel_timeout)
        if thread.is_alive():
            killed = handle.session.process_registry.kill_all() if handle.session.process_registry else 0
            return self._cancel_run_result(handle, f"Worker cancelled. Cancellation finalization timed out. Terminated {killed} running subprocess(es).")
        if error := box.get("error"):
            return self._cancel_run_result(handle, f"Worker cancelled. Finalization failed: {error}", str(error))
        return box.get("result") or self._cancel_run_result(handle, "Worker cancelled before producing a cancellation summary.")

    def _cancel_result(self, agent_id: str, handle: AgentHandle, summary: str, status_cb: StatusCallback | None) -> ExecutionResult:
        result = self._write_result(handle.task_id, handle.stage_name, handle.output_path, handle.session.log_path, self._cancel_run_result(handle, summary), status_cb)
        self._cancelled[agent_id] = result
        return result

    def _cancel_run_result(self, handle: AgentHandle, summary: str, error: str = "") -> AgentRunResult:
        return AgentRunResult("cancelled", handle.session.info.snapshot(), [], final_output=summary, error=error)

    def get_session(self, agent_id: str) -> AgentSession | None:
        handle = self._agents.get(agent_id)
        return handle.session if handle else None

    def _agent_goal(self, agent_id: str, task: RuntimeTask, status_cb: StatusCallback | None = None) -> ExecutionResult:
        self._emit(status_cb, "running", "Minimal agent loop started.")
        log_path = task.workspace_root / "agent-debug.log"
        try:
            session = create_agent_session(cwd=task.workspace_root, log_path=log_path)
            self._agents[agent_id] = AgentHandle(session, task.task_id, task.stage_name, task.output_path)
            self._running.add(agent_id)
            session.last_result = resume_agent_session(session, task.objective, status_cb=status_cb, start=True)
        except Exception as e:
            self._emit(status_cb, "failed", f"Minimal agent failed: {e}")
            return ExecutionResult(task.task_id, "failed", f"Minimal agent failed: {e}", task.output_path)
        finally:
            self._running.discard(agent_id)
        if agent_id in self._cancelled:
            return self._cancelled[agent_id]
        r = session.last_result or AgentRunResult("failed", session.info.snapshot(), [], error="Agent session did not return a result.")
        return self._write_result(task.task_id, task.stage_name, task.output_path, log_path, r, status_cb)

    def _write_result(
        self, task_id: str, stage_name: str, output_path: Path, log_path: Path, r: AgentRunResult,
        status_cb: StatusCallback | None = None,
    ) -> ExecutionResult:
        status = self._agent_status(r.status)
        resume_mode = self._resume_mode(status)
        notes = [f"Minimal agent steps: {r.step_count}", f"Minimal agent actions: {r.action_count}", f"Session ID: {r.session_id}", f"Thread ID: {r.thread_id}", f"Resume mode: {resume_mode}", f"Log: {log_path}"]
        pending = status in {"waiting", "background"} and r.final_output
        if pending:
            notes.insert(-1, f"Pending text: {r.final_output}")
        header = [
            "# Agent Goal Run", "", f"- Stage: `{stage_name}`", f"- Status: `{status}`", f"- Steps: {r.step_count}", f"- Actions: {r.action_count}",
            f"- Session ID: `{r.session_id}`", f"- Thread ID: `{r.thread_id}`",
            f"- Resume mode: `{resume_mode}`",
        ]
        if pending:
            header.append(f"- Pending text: `{r.final_output}`")
        if status != r.status:
            header.append(f"- Raw agent status: `{r.status}`")
        text = header + [
            f"- Last action: `{r.last_action or '(none)'}`", f"- Log: `{log_path}`", "", "## Final Output", "", r.final_output or "(empty)",
        ]
        if r.error:
            text += ["", "## Error", "", r.error]
        output_path.write_text("\n".join(text) + "\n", encoding="utf-8")
        self._emit(status_cb, status, f"Minimal agent finished after {r.step_count} steps.")
        summary = r.final_output if status in {"waiting", "background", "cancelled"} and r.final_output else f"Minimal agent run finished with status {status}."
        return ExecutionResult(task_id, status, summary, output_path, artifacts=[output_path, log_path], notes=notes)

    def _agent_status(self, status: str) -> str:
        return status if status in {"completed", "waiting", "background", "cancelled"} else "failed"

    def _resume_mode(self, status: str) -> str:
        return "interrupt" if status == "waiting" else "message"

    def _emit(self, status_cb: StatusCallback | None, status: str, text: str) -> None:
        if status_cb:
            status_cb(RuntimeUpdate(status, text))


# Backward-compatible alias for the earlier two-layer skeleton.
ExecutionAgent = ExecutionRuntime
