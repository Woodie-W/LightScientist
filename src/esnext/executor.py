"""Execution layer for the current LightScientist skeleton."""

from __future__ import annotations

from typing import Callable

from .minimal_agent import run_agent
from .models import ExecutionResult, RuntimeTask

StatusCallback = Callable[[str, str], None]


class ExecutionRuntime:
    """Third-layer execution runtime with command-line capability only."""

    def __init__(self, agent_query_fn=None) -> None:
        self.agent_query_fn = agent_query_fn

    def execute(self, task: RuntimeTask, status_cb: StatusCallback | None = None) -> ExecutionResult:
        task.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._emit(status_cb, "running", "Execution runtime received the task.")
        if not task.use_agent:
            text = "Only the agent path is implemented in the current skeleton."
            self._emit(status_cb, "failed", text)
            return ExecutionResult(task.task_id, "failed", text, task.output_path)
        return self._agent_goal(task, status_cb)

    def _agent_goal(self, task: RuntimeTask, status_cb: StatusCallback | None = None) -> ExecutionResult:
        self._emit(status_cb, "running", "Minimal agent loop started.")
        log_path = task.workspace_root / "agent-debug.log"
        try:
            r = run_agent(task.objective, cwd=task.workspace_root, query_fn=self.agent_query_fn, status_cb=status_cb, log_path=log_path)
        except Exception as e:
            self._emit(status_cb, "failed", f"Minimal agent failed: {e}")
            return ExecutionResult(task.task_id, "failed", f"Minimal agent failed: {e}", task.output_path)
        status = self._agent_status(r.status)
        text = [
            "# Agent Goal Run", "", f"- Stage: `{task.stage_name}`", f"- Status: `{status}`", f"- Steps: {r.step_count}",
            f"- Last action: `{r.last_action or '(none)'}`", f"- Log: `{log_path}`", "", "## Final Output", "", r.final_output or "(empty)",
        ]
        if status != r.status:
            text[7:7] = [f"- Raw agent status: `{r.status}`"]
        if r.error:
            text += ["", "## Error", "", r.error]
        task.output_path.write_text("\n".join(text) + "\n", encoding="utf-8")
        self._emit(status_cb, status, f"Minimal agent finished after {r.step_count} steps.")
        return ExecutionResult(
            task.task_id, status, f"Minimal agent run finished with status {status}.", task.output_path,
            artifacts=[task.output_path, log_path], notes=[f"Minimal agent steps: {r.step_count}", f"Log: {log_path}"],
        )

    def _agent_status(self, status: str) -> str:
        if status in {"completed", "terminated"}:
            return "completed"
        if status == "max_steps_reached":
            return "failed"
        return "failed"

    def _emit(self, status_cb: StatusCallback | None, status: str, text: str) -> None:
        if status_cb:
            status_cb(status, text)


# Backward-compatible alias for the earlier two-layer skeleton.
ExecutionAgent = ExecutionRuntime
