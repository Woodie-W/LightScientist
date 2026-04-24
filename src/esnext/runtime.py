"""Middle layer that tracks third-layer worker records."""

from __future__ import annotations

import json, threading, time, uuid
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from .executor import ExecutionRuntime
from .minimal_agent import AgentSession, resume_agent_session, start_agent_session
from .data_models import AgentRecord, ExecutionResult, RuntimeTask, RuntimeUpdate


@dataclass(slots=True)
class RuntimeEnvelope:
    agent_id: str
    update: RuntimeUpdate

SUPERVISOR_SYS = (
    "You are the second-layer supervisor. Supervise one task and its worker agents. "
    "Use the built-in workspace tools when you need to inspect files, outputs, logs, or edit working files. "
    "Use the runtime tools to inspect task state, inspect worker state, start workers, resume workers, and cancel workers when needed. "
    "On each new event, first inspect the current task and worker states before making a decision. "
    "Do not start a new worker if an existing worker can be resumed to make progress. "
    "Use cancel_worker only when a worker is no longer useful for the task. "
    "Reply with exactly one line starting with TASK_COMPLETED:, TASK_FAILED:, or TASK_CONTINUE:. "
    "When the overall task is complete, answer with 'TASK_COMPLETED: <summary>'. "
    "When the task cannot continue, answer with 'TASK_FAILED: <summary>'. "
    "Otherwise answer with 'TASK_CONTINUE: <summary>'."
)


class RuntimeSupervisor:
    """Middle layer that stores lightweight records for third-layer workers."""

    def __init__(self, executor: ExecutionRuntime | None = None, stall_timeout: float | None = 300.0) -> None:
        self.executor = executor or ExecutionRuntime()
        self.stall_timeout = stall_timeout
        self._agents: dict[str, AgentRecord] = {}
        self._task: dict[str, object] | None = None
        self._workspace_root: Path | None = None
        self._supervisor: AgentSession | None = None
        self._supervisor_busy = False
        self._waiters: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._queue: deque[RuntimeEnvelope] = deque()
        self._supervisor_queue: deque[str] = deque()
        self._queue_ready = threading.Condition(self._lock)
        self._controller = threading.Thread(target=self._control_loop, daemon=True, name="runtime-controller")
        self._controller.start()

    def start(self, task: RuntimeTask) -> ExecutionResult:
        with self._lock:
            if self._task and self._task["task_id"] != task.task_id: 
                return ExecutionResult(task.task_id, "failed", "RuntimeSupervisor already manages another task.", task.output_path)
        agent_id = f"agent-{task.task_id}"
        worker_root = task.workspace_root / agent_id
        output_path = worker_root / "agent-run.md"
        runtime_task = RuntimeTask(task.task_id, task.stage_name, task.target, output_path, worker_root, task.objective, task.use_agent)
        with self._lock:
            self._agents[agent_id] = AgentRecord(agent_id, task.task_id, task.objective, "running", progress_text="Worker created.", workspace_root=worker_root, output_path=output_path)
            self._task = {
                "task_id": task.task_id,
                "objective": task.objective,
                "worker_ids": [agent_id],
                "status": "running",
                "summary": "",
            }
            self._workspace_root = task.workspace_root
            self._waiters[agent_id] = threading.Event()
        self._push_update(agent_id, RuntimeUpdate("running", "Worker created."))
        threading.Thread(target=self._run, args=("start", agent_id, runtime_task), daemon=True, name=f"runtime-start-{agent_id}").start()
        self._waiters[agent_id].wait()
        return self._final_result(agent_id)

    def start_worker(self, task_id: str, objective: str) -> ExecutionResult:
        task = self.get_task(task_id)
        if not task: return ExecutionResult(task_id, "failed", f"Unknown task: {task_id}.", Path.cwd() / "agent-run.md")
        if task["status"] in {"completed", "failed", "cancelled"}: 
            return ExecutionResult(task_id, "failed", f"Cannot start worker for {task['status']} task.", Path.cwd() / "agent-run.md")
        worker_task_id = f"{task_id}-{uuid.uuid4().hex[:4]}"
        agent_id = f"agent-{worker_task_id}"
        worker_root = (self._workspace_root or Path.cwd()) / agent_id
        output_path = worker_root / "agent-run.md"
        runtime_task = RuntimeTask(worker_task_id, "supervised", objective, output_path, worker_root, objective, True)
        with self._lock:
            self._agents[agent_id] = AgentRecord(agent_id, worker_task_id, objective, "running", progress_text="Worker created.", workspace_root=worker_root, output_path=output_path)
            self._task["worker_ids"].append(agent_id)
            self._waiters[agent_id] = threading.Event()
        self._push_update(agent_id, RuntimeUpdate("running", "Worker created."))
        threading.Thread(target=self._run, args=("start", agent_id, runtime_task), daemon=True, name=f"runtime-start-{agent_id}").start()
        self._waiters[agent_id].wait()
        return self._final_result(agent_id)

    def resume(self, agent_id: str, user_input: str) -> ExecutionResult:
        with self._lock:
            if agent_id not in self._agents: return ExecutionResult(agent_id.removeprefix("agent-"), "failed", f"Unknown agent session: {agent_id}.", Path.cwd() / "agent-run.md")
            record = self._agents[agent_id]
            if record.status == "cancelled": return record.result or ExecutionResult(record.task_id, "cancelled", "Worker cancelled.", record.output_path or (Path.cwd() / "agent-run.md"))
            self._waiters[agent_id] = threading.Event()
        threading.Thread(target=self._run, args=("resume", agent_id, user_input), daemon=True, name=f"runtime-resume-{agent_id}").start()
        self._waiters[agent_id].wait()
        return self._final_result(agent_id)

    def cancel_worker(self, agent_id: str) -> ExecutionResult:
        with self._lock:
            record = self._agents.get(agent_id)
            if not record: return ExecutionResult(agent_id.removeprefix("agent-"), "failed", f"Unknown agent session: {agent_id}.", Path.cwd() / "agent-run.md")
            if record.status == "cancelled": return record.result or ExecutionResult(record.task_id, "cancelled", "Worker cancelled.", record.output_path or (Path.cwd() / "agent-run.md"))
            result = ExecutionResult(record.task_id, "cancelled", "Worker cancelled.", record.output_path or (Path.cwd() / "agent-run.md"))
            self._update_agent(agent_id, RuntimeUpdate("cancelled", "Worker cancelled.", result=result))
            if agent_id in self._waiters: self._waiters[agent_id].set()
            self._supervisor_queue.append(f"Worker: {agent_id}\nStatus: cancelled\nText: Worker cancelled.\nSummary: Worker cancelled.")
            self._queue_ready.notify()
            return result

    def get_task(self, task_id: str) -> dict[str, object] | None:
        if not self._task or self._task["task_id"] != task_id: return None
        return {
            "task_id": self._task["task_id"],
            "objective": self._task["objective"],
            "status": self._task["status"],
            "summary": self._task["summary"],
        }

    def _run(self, mode: str, agent_id: str, arg: RuntimeTask | str) -> None:
        try:
            if mode == "start":
                task = arg
                result = self.executor.start(agent_id, task, status_cb=lambda update: self._push_update(agent_id, update))
            else:
                result = self.executor.resume(agent_id, str(arg), status_cb=lambda update: self._push_update(agent_id, update))
            session = self.executor.get_session(agent_id)
            self._push_update(agent_id, RuntimeUpdate(result.status, result.summary, result=result, thread_id=session.thread_id if session else ""))
        except Exception as e:
            if mode == "start":
                task = arg
                self._push_update(agent_id, RuntimeUpdate("failed", str(e), result=ExecutionResult(task.task_id, "failed", str(e), task.output_path)))
            else:
                task_id = agent_id.removeprefix("agent-")
                output = self._agents[agent_id].output_path or (Path.cwd() / "agent-run.md")
                self._push_update(agent_id, RuntimeUpdate("failed", str(e), result=ExecutionResult(task_id, "failed", str(e), output)))

    def _push_update(self, agent_id: str, update: RuntimeUpdate) -> None:
        with self._queue_ready:
            self._queue.append(RuntimeEnvelope(agent_id, update))
            self._queue_ready.notify()

    def _control_loop(self) -> None:
        while True:
            with self._queue_ready:
                while not self._queue and not (self._supervisor_queue and not self._supervisor_busy):
                    self._queue_ready.wait(timeout=0.5)
                    self._check_worker_stalls_locked()
                item = self._queue.popleft() if self._queue else None
                supervisor = None if item or self._supervisor_busy or not self._supervisor_queue else self._supervisor_queue.popleft()
            if item:
                self._handle_update(item.agent_id, item.update)
            elif supervisor:
                with self._queue_ready:
                    self._supervisor_busy = True
                task_id = self._task["task_id"] if self._task else "supervisor"
                threading.Thread(target=self._run_supervisor, args=(supervisor,), daemon=True, name=f"runtime-supervisor-{task_id}").start()
            time.sleep(0.1)

    def _handle_update(self, agent_id: str, update: RuntimeUpdate) -> None:
        if agent_id not in self._agents: return
        old_status = self._agents[agent_id].status
        if old_status == "cancelled" and update.status != "cancelled":
            if update.result and agent_id in self._waiters: self._waiters[agent_id].set()
            return
        self._update_agent(agent_id, update)
        should_notify_supervisor = old_status != update.status or update.result is not None
        parts = [f"Worker: {agent_id}", f"Status: {update.status}"]
        if update.text: parts.append(f"Text: {update.text}")
        if update.result: parts.append(f"Summary: {update.result.summary}")
        if should_notify_supervisor:
            with self._queue_ready:
                self._supervisor_queue.append("\n".join(parts))
                self._queue_ready.notify()
        if update.result and agent_id in self._waiters: self._waiters[agent_id].set()

    def _run_supervisor(self, text: str) -> None:
        try:
            task = self._task
            if not task: return
            session = self._supervisor
            if session is None:
                session = start_agent_session(
                    f"Task objective: {task['objective']}\nEvent: {text}",
                    cwd=self._workspace_root or Path.cwd(),
                    system_prompt=SUPERVISOR_SYS,
                    log_path=(self._workspace_root or Path.cwd()) / f"supervisor-{task['task_id']}.log",
                    tools=self._runtime_tools(),
                )
                self._supervisor = session
                result = session.last_result
            else: result = resume_agent_session(session, text)
            if result: self._apply_supervisor_result(result.final_output or "")
        finally:
            with self._queue_ready:
                self._supervisor_busy = False
                self._queue_ready.notify()

    def _runtime_tools(self) -> list[object]:
        from langchain.tools import tool

        def agent_dict(agent_id: str) -> dict[str, object]:
            agent = self._agents.get(agent_id)
            return agent.to_dict() if agent else {}

        @tool("get_task")
        def get_task_tool() -> str:
            """Get current task state."""
            if not self._task:
                return json.dumps({}, ensure_ascii=False)
            return json.dumps(self.get_task(str(self._task["task_id"])) or {}, ensure_ascii=False)

        @tool("list_workers")
        def list_workers_tool() -> str:
            """List worker records for the current task."""
            task = self._task or {}
            workers = [agent_dict(agent_id) for agent_id in task.get("worker_ids", [])]
            return json.dumps(workers, ensure_ascii=False)

        @tool("get_worker")
        def get_worker_tool(agent_id: str) -> str:
            """Get one worker record by agent id."""
            return json.dumps(agent_dict(agent_id), ensure_ascii=False)

        @tool("resume_worker")
        def resume_worker_tool(agent_id: str, text: str) -> str:
            """Resume a worker agent with new input."""
            result = self.resume(agent_id, text)
            return json.dumps({"status": result.status, "summary": result.summary}, ensure_ascii=False)

        @tool("start_worker")
        def start_worker_tool(objective: str) -> str:
            """Start a new worker under the current task."""
            if not self._task: return json.dumps({"status": "failed", "summary": "No active task."}, ensure_ascii=False)
            task_id = str(self._task["task_id"])
            result = self.start_worker(task_id, objective)
            return json.dumps({"status": result.status, "summary": result.summary, "task_id": result.task_id}, ensure_ascii=False)

        @tool("cancel_worker")
        def cancel_worker_tool(agent_id: str) -> str:
            """Cancel one worker by agent id."""
            result = self.cancel_worker(agent_id)
            return json.dumps({"status": result.status, "summary": result.summary}, ensure_ascii=False)

        return [get_task_tool, list_workers_tool, get_worker_tool, resume_worker_tool, start_worker_tool, cancel_worker_tool]

    def _apply_supervisor_result(self, text: str) -> None:
        task = self._task
        if not task: return
        raw = text.strip()
        if raw.upper().startswith("TASK_COMPLETED:"):
            task["status"] = "completed"
            task["summary"] = raw[len("TASK_COMPLETED:"):].strip()
            return
        if raw.upper().startswith("TASK_FAILED:"):
            task["status"] = "failed"
            task["summary"] = raw[len("TASK_FAILED:"):].strip()
            return
        if raw.upper().startswith("TASK_CONTINUE:"):
            if task["status"] in {"completed", "failed", "cancelled"}:
                return
            task["summary"] = raw[len("TASK_CONTINUE:"):].strip()
            return
        if raw and task["status"] not in {"completed", "failed", "cancelled"}:
            task["summary"] = raw

    def _update_agent(self, agent_id: str, update: RuntimeUpdate) -> None:
        record = self._agents[agent_id]
        record.status = update.status
        record.resume_mode = "interrupt" if update.status == "waiting" else "message"
        record.progress_text = update.text
        if update.progress: record.progress = update.progress.snapshot()
        if update.status != "running": record.stall_reported, record.stalled_action_count = False, -1
        if update.thread_id: record.thread_id = update.thread_id
        if update.result: record.result = update.result

    def _check_worker_stalls_locked(self) -> None:
        if self.stall_timeout is None: return
        now = time.monotonic()
        for agent_id, record in self._agents.items():
            if record.status != "running":
                record.stall_reported, record.stalled_action_count = False, -1
                continue
            if record.stall_reported and record.progress.action_count != record.stalled_action_count:
                record.stall_reported, record.stalled_action_count = False, -1
                continue
            if record.stall_reported or now - record.progress.last_activity_at < self.stall_timeout:
                continue
            record.stall_reported = True
            record.stalled_action_count = record.progress.action_count
            self._supervisor_queue.append(
                f"Worker: {agent_id}\nStatus: running\nText: Worker stalled.\n"
                f"Progress: step_count={record.progress.step_count}, action_count={record.progress.action_count}"
            )
        if self._supervisor_queue: self._queue_ready.notify()

    def _final_result(self, agent_id: str) -> ExecutionResult:
        record = self._agents[agent_id]
        result = record.result or ExecutionResult(record.task_id, record.status, record.progress_text or "No result.", record.output_path or (Path.cwd() / "agent-run.md"))
        result.notes.extend([f"Agent ID: {agent_id}", f"Final status: {result.status}"])
        return result
