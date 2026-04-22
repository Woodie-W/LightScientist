"""Middle layer that tracks third-layer worker records."""

from __future__ import annotations

from .executor import ExecutionRuntime
from .models import AgentRecord, ExecutionResult, RuntimeTask


class RuntimeSupervisor:
    """Middle layer that stores lightweight records for third-layer workers."""

    def __init__(self, executor: ExecutionRuntime | None = None) -> None:
        self.executor = executor or ExecutionRuntime()
        self._agents: dict[str, AgentRecord] = {}

    def run(self, task: RuntimeTask) -> ExecutionResult:
        agent_id = f"agent-{task.task_id}"
        record = AgentRecord(agent_id, task.task_id, task.objective, "running", "Worker created.")
        self._agents[agent_id] = record
        result = self.executor.execute(task, status_cb=lambda s, t="": self._update_agent(agent_id, s, t))
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
        record.progress_text = progress_text
        if result:
            record.result = result
