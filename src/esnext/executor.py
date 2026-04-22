"""Execution layer for the current LightScientist skeleton."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .minimal_agent import AgentRunResult, AgentSession, resume_agent_session, start_agent_session
from .models import ExecutionResult, RuntimeTask

StatusCallback = Callable[[str, str], None]


@dataclass(slots=True)
class AgentHandle:
    session: AgentSession
    task_id: str
    stage_name: str
    output_path: Path


class ExecutionRuntime:
    """Third-layer execution runtime with command-line capability only."""

    def __init__(self, agent_query_fn=None) -> None:
        self.agent_query_fn = agent_query_fn
        self._agents: dict[str, AgentHandle] = {}

    def execute(self, task: RuntimeTask, status_cb: StatusCallback | None = None) -> ExecutionResult:
        return self.start(f"agent-{task.task_id}", task, status_cb)

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
            return ExecutionResult(agent_id.removeprefix("agent-"), "failed", f"Unknown agent session: {agent_id}.", Path.cwd() / "agent-run.md")
        self._emit(status_cb, "running", "Resuming persistent agent session.")
        r = resume_agent_session(handle.session, user_input, query_fn=self.agent_query_fn, status_cb=status_cb)
        return self._write_result(handle.task_id, handle.stage_name, handle.output_path, handle.session.log_path, r, status_cb)

    def get_session(self, agent_id: str) -> AgentSession | None:
        handle = self._agents.get(agent_id)
        return handle.session if handle else None

    def _agent_goal(self, agent_id: str, task: RuntimeTask, status_cb: StatusCallback | None = None) -> ExecutionResult:
        self._emit(status_cb, "running", "Minimal agent loop started.")
        log_path = task.workspace_root / "agent-debug.log"
        try:
            session = start_agent_session(task.objective, cwd=task.workspace_root, query_fn=self.agent_query_fn, status_cb=status_cb, log_path=log_path)
        except Exception as e:
            self._emit(status_cb, "failed", f"Minimal agent failed: {e}")
            return ExecutionResult(task.task_id, "failed", f"Minimal agent failed: {e}", task.output_path)
        self._agents[agent_id] = AgentHandle(session, task.task_id, task.stage_name, task.output_path)
        r = session.last_result or AgentRunResult("failed", session.session_id, session.thread_id, [], error="Agent session did not return a result.")
        return self._write_result(task.task_id, task.stage_name, task.output_path, log_path, r, status_cb)

    def _write_result(
        self, task_id: str, stage_name: str, output_path: Path, log_path: Path, r: AgentRunResult,
        status_cb: StatusCallback | None = None,
    ) -> ExecutionResult:
        status = self._agent_status(r.status)
        text = [
            "# Agent Goal Run", "", f"- Stage: `{stage_name}`", f"- Status: `{status}`", f"- Steps: {r.step_count}",
            f"- Session ID: `{r.session_id}`", f"- Thread ID: `{r.thread_id}`",
            f"- Last action: `{r.last_action or '(none)'}`", f"- Log: `{log_path}`", "", "## Final Output", "", r.final_output or "(empty)",
        ]
        if status != r.status:
            text[9:9] = [f"- Raw agent status: `{r.status}`"]
        if r.error:
            text += ["", "## Error", "", r.error]
        output_path.write_text("\n".join(text) + "\n", encoding="utf-8")
        self._emit(status_cb, status, f"Minimal agent finished after {r.step_count} steps.")
        summary = r.final_output if status in {"waiting", "background"} and r.final_output else f"Minimal agent run finished with status {status}."
        return ExecutionResult(
            task_id, status, summary, output_path,
            artifacts=[output_path, log_path], notes=[f"Minimal agent steps: {r.step_count}", f"Session ID: {r.session_id}", f"Thread ID: {r.thread_id}", f"Log: {log_path}"],
        )

    def _agent_status(self, status: str) -> str:
        if status in {"completed", "waiting", "background", "cancelled"}:
            return status
        if status == "max_steps_reached":
            return "failed"
        return "failed"

    def _emit(self, status_cb: StatusCallback | None, status: str, text: str) -> None:
        if status_cb:
            status_cb(status, text)


# Backward-compatible alias for the earlier two-layer skeleton.
ExecutionAgent = ExecutionRuntime
