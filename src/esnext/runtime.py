"""Middle layer that tracks third-layer worker records."""

from __future__ import annotations

import threading, time
from collections import deque
from dataclasses import dataclass

from .executor import ExecutionRuntime
from .models import AgentRecord, ExecutionResult, ExecutionState, RuntimeTask

STATE_TRANSITIONS: dict[ExecutionState, tuple[ExecutionState, ...]] = {
    "running": ("waiting", "background", "completed", "failed", "cancelled"),
    "waiting": ("running", "cancelled"),
    "background": ("running", "cancelled"),
    "completed": (),
    "failed": (),
    "cancelled": (),
}


@dataclass(slots=True)
class RuntimeUpdate:
    status: str
    text: str = ""
    result: ExecutionResult | None = None
    thread_id: str = ""


@dataclass(slots=True)
class RuntimeEnvelope:
    agent_id: str
    update: RuntimeUpdate


class RuntimeSupervisor:
    """Middle layer that stores lightweight records for third-layer workers."""

    def __init__(self, executor: ExecutionRuntime | None = None) -> None:
        self.executor = executor or ExecutionRuntime()
        self._agents: dict[str, AgentRecord] = {}
        self._tasks: dict[str, dict[str, object]] = {}
        self._waiters: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._queue: deque[RuntimeEnvelope] = deque()
        self._queue_ready = threading.Condition(self._lock)
        self._controller = threading.Thread(target=self._control_loop, daemon=True, name="runtime-controller")
        self._controller.start()

    def start(self, task: RuntimeTask) -> ExecutionResult:
        agent_id = f"agent-{task.task_id}"
        with self._lock:
            self._agents[agent_id] = AgentRecord(agent_id, task.task_id, task.objective, "running", progress_text="Worker created.", output_path=task.output_path)
            self._tasks[task.task_id] = {
                "task_id": task.task_id,
                "objective": task.objective,
                "worker_ids": [agent_id],
                "status": "running",
                "summary": "Worker created.",
            }
            self._waiters[agent_id] = threading.Event()
        self._push_update(agent_id, "running", "Worker created.")
        threading.Thread(target=self._run, args=("start", agent_id, task), daemon=True, name=f"runtime-start-{agent_id}").start()
        self._waiters[agent_id].wait()
        return self._final_result(agent_id)

    def resume(self, agent_id: str, user_input: str) -> ExecutionResult:
        with self._lock:
            if agent_id not in self._agents:
                return ExecutionResult(agent_id.removeprefix("agent-"), "failed", f"Unknown agent session: {agent_id}.", taskless_output())
            self._waiters[agent_id] = threading.Event()
        threading.Thread(target=self._run, args=("resume", agent_id, user_input), daemon=True, name=f"runtime-resume-{agent_id}").start()
        self._waiters[agent_id].wait()
        return self._final_result(agent_id)

    def get_agent(self, agent_id: str) -> AgentRecord | None:
        return self._agents.get(agent_id)

    def list_agents(self) -> list[AgentRecord]:
        return list(self._agents.values())

    def get_task(self, task_id: str) -> dict[str, object] | None:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[dict[str, object]]:
        return list(self._tasks.values())

    def _run(self, mode: str, agent_id: str, arg: RuntimeTask | str) -> None:
        try:
            if mode == "start":
                task = arg
                result = self.executor.start(agent_id, task, status_cb=lambda s, t="": self._push_update(agent_id, s, t))
            else:
                result = self.executor.resume(agent_id, str(arg), status_cb=lambda s, t="": self._push_update(agent_id, s, t))
            session = self.executor.get_session(agent_id)
            self._push_update(agent_id, result.status, result.summary, result=result, thread_id=session.thread_id if session else "")
        except Exception as e:
            if mode == "start":
                task = arg
                self._push_update(agent_id, "failed", str(e), result=ExecutionResult(task.task_id, "failed", str(e), task.output_path))
            else:
                task_id = agent_id.removeprefix("agent-")
                output = self._agents[agent_id].output_path or taskless_output()
                self._push_update(agent_id, "failed", str(e), result=ExecutionResult(task_id, "failed", str(e), output))

    def _push_update(
        self, agent_id: str, status: str, text: str = "", result: ExecutionResult | None = None, thread_id: str = ""
    ) -> None:
        with self._queue_ready:
            self._queue.append(RuntimeEnvelope(agent_id, RuntimeUpdate(status, text, result, thread_id)))
            self._queue_ready.notify()

    def _control_loop(self) -> None:
        while True:
            with self._queue_ready:
                while not self._queue:
                    self._queue_ready.wait()
                item = self._queue.popleft()
            self._handle_update(item.agent_id, item.update)
            time.sleep(1)

    def _handle_update(self, agent_id: str, update: RuntimeUpdate) -> None:
        if agent_id not in self._agents:
            return
        old_status = self._agents[agent_id].status
        self._update_agent(agent_id, update.status, update.text, update.result, update.thread_id)
        self._handle_status_change(agent_id, old_status, update.status)
        self._supervise_task(self._agents[agent_id].task_id)
        if update.result and agent_id in self._waiters:
            self._waiters[agent_id].set()

    def _handle_status_change(self, agent_id: str, old: str, new: str) -> None:
        if old == new:
            return

    def _supervise_task(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if not task:
            return
        workers = [self._agents[agent_id] for agent_id in task["worker_ids"] if agent_id in self._agents]
        if not workers:
            task["status"], task["summary"] = "failed", "No active workers."
            return
        if any(worker.status == "completed" for worker in workers):
            worker = next(worker for worker in workers if worker.status == "completed")
            task["status"] = "completed"
            task["summary"] = worker.result.summary if worker.result else worker.progress_text
            return
        if any(worker.status == "running" for worker in workers):
            worker = next(worker for worker in workers if worker.status == "running")
            task["status"], task["summary"] = "running", worker.progress_text
            return
        if any(worker.status == "waiting" for worker in workers):
            worker = next(worker for worker in workers if worker.status == "waiting")
            task["status"], task["summary"] = "waiting", worker.pending_text or worker.progress_text
            return
        if any(worker.status == "background" for worker in workers):
            worker = next(worker for worker in workers if worker.status == "background")
            task["status"], task["summary"] = "background", worker.pending_text or worker.progress_text
            return
        if all(worker.status == "cancelled" for worker in workers):
            task["status"], task["summary"] = "cancelled", "All workers cancelled."
            return
        task["status"] = "failed"
        task["summary"] = next((worker.progress_text for worker in workers if worker.progress_text), "All workers failed.")

    def _update_agent(
        self, agent_id: str, status: str, progress_text: str = "", result: ExecutionResult | None = None,
        thread_id: str = "",
    ) -> None:
        record = self._agents[agent_id]
        record.status = status
        record.resume_mode = "interrupt" if status == "waiting" else "message"
        record.progress_text = progress_text
        record.pending_text = progress_text if status in {"waiting", "background"} else ""
        if thread_id:
            record.thread_id = thread_id
        if result:
            record.result = result

    def _final_result(self, agent_id: str) -> ExecutionResult:
        record = self._agents[agent_id]
        result = record.result or ExecutionResult(record.task_id, record.status, record.progress_text or "No result.", record.output_path or taskless_output())
        result.notes.extend([f"Agent ID: {agent_id}", f"Final status: {result.status}"])
        return result


def taskless_output():
    from pathlib import Path
    return Path.cwd() / "agent-run.md"
