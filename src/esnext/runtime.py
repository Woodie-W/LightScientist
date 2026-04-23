"""Middle layer that tracks third-layer worker records."""

from __future__ import annotations

from .executor import ExecutionRuntime
from .models import AgentRecord, ExecutionResult, RuntimeTask


class RuntimeSupervisor:
    """Middle layer that stores lightweight records for third-layer workers."""

    def __init__(self, executor: ExecutionRuntime | None = None) -> None:
        self.executor = executor or ExecutionRuntime()
        self._agents: dict[str, AgentRecord] = {}

    def start(self, task: RuntimeTask) -> ExecutionResult:
        agent_id = f"agent-{task.task_id}"
        record = AgentRecord(agent_id, task.task_id, task.objective, "running", progress_text="Worker created.", output_path=task.output_path)
        self._agents[agent_id] = record
        result = self.executor.start(agent_id, task, status_cb=lambda s, t="": self._update_agent(agent_id, s, t))
        if session := self.executor.get_session(agent_id):
            record.thread_id = session.thread_id
        self._update_agent(agent_id, result.status, result.summary, result)
        result.notes.extend([f"Agent ID: {agent_id}", f"Final status: {result.status}"])
        return result

    def resume(self, agent_id: str, user_input: str) -> ExecutionResult:
        result = self.executor.resume(agent_id, user_input, status_cb=lambda s, t="": self._update_agent(agent_id, s, t))
        if agent_id not in self._agents:
            return result
        self._update_agent(agent_id, result.status, result.summary, result)
        result.notes.extend([f"Agent ID: {agent_id}", f"Final status: {result.status}"])
        return result

    def get_agent(self, agent_id: str) -> AgentRecord | None:
        return self._agents.get(agent_id)

    def list_agents(self) -> list[AgentRecord]:
        return list(self._agents.values())

    def _update_agent(
        self, agent_id: str, status: str, progress_text: str = "", result: ExecutionResult | None = None
    ) -> None:
        record = self._agents[agent_id]
        record.status = status
        record.resume_mode = "interrupt" if status == "waiting" else "message"
        record.progress_text = progress_text
        record.pending_text = progress_text if status in {"waiting", "background"} else ""
        if result:
            record.result = result
