"""Middle layer that tracks third-layer worker records."""

from __future__ import annotations

import json, threading, time, uuid
from collections import deque
from pathlib import Path

from .executor import ExecutionRuntime
from .minimal_agent import resume_agent_session, start_agent_session
from .data_models import AgentRecord, AgentSession, ExecutionResult, RuntimeEnvelope, RuntimeTask, RuntimeUpdate, ScheduledResume
from .prompts import load_prompt


def supervisor_event_input(task_objective: str, event: str) -> str:
    parts = [f"Task objective: {task_objective}", f"Event: {event}"]
    for line in event.splitlines():
        if line.strip().lower() == "status: background":
            parts += ["", load_prompt("supervisor_background")]
            break
        if line.strip().lower() == "status: waiting":
            parts += ["", load_prompt("supervisor_waiting")]
            break
    else:
        if "worker stalled" in event.lower():
            parts += ["", load_prompt("supervisor_stalled")]
    return "\n".join(parts)


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
        self._scheduled_resumes: list[ScheduledResume] = []
        self._queue_ready = threading.Condition(self._lock)
        self._controller = threading.Thread(target=self._control_loop, daemon=True, name="runtime-controller")
        self._controller.start()

    # ---------------------------------------------------------------
    # 提供接口
    # ---------------------------------------------------------------
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

    # ---------------------------------------------------------------
    # Worker 运行控制
    # ---------------------------------------------------------------
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
                    self._resume_due_workers_locked()
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

    # ---------------------------------------------------------------
    # Supervisor Agent
    # ---------------------------------------------------------------
    def _run_supervisor(self, text: str) -> None:
        try:
            task = self._task
            if not task: return
            session = self._supervisor
            user_input = supervisor_event_input(str(task["objective"]), text)
            if session is None:
                session = start_agent_session(
                    user_input,
                    cwd=self._workspace_root or Path.cwd(),
                    system_prompt=load_prompt("supervisor"),
                    log_path=(self._workspace_root or Path.cwd()) / f"supervisor-{task['task_id']}.log",
                    tools=self._runtime_tools(),
                )
                self._supervisor = session
                result = session.last_result
            else: result = resume_agent_session(session, user_input)
            if result: self._apply_supervisor_result(result.final_output or "")
        finally:
            with self._queue_ready:
                self._supervisor_busy = False
                self._queue_ready.notify()

    # Supervisor tools
    def _runtime_tools(self) -> list[object]:
        from langchain.tools import tool

        def agent_dict(agent_id: str) -> dict[str, object]:
            agent = self._agents.get(agent_id)
            return agent.to_dict() if agent else {}

        @tool("get_task", parse_docstring=True)
        def get_task_tool() -> str:
            """Get the current supervised task state.

            Use this before making supervisor decisions to understand the
            overall task objective, status, and latest summary.

            Returns:
                JSON object with task_id, objective, status, and summary. Empty
                JSON object if no task is active.
            """
            if not self._task:
                return json.dumps({}, ensure_ascii=False)
            return json.dumps(self.get_task(str(self._task["task_id"])) or {}, ensure_ascii=False)

        @tool("list_workers", parse_docstring=True)
        def list_workers_tool() -> str:
            """List all worker records under the current task.

            Use this to see every worker managed by this supervisor, including
            their status, progress, workspace path, output path, and pending text.

            Returns:
                JSON list of worker records for the active task.
            """
            task = self._task or {}
            workers = [agent_dict(agent_id) for agent_id in task.get("worker_ids", [])]
            return json.dumps(workers, ensure_ascii=False)

        @tool("get_worker", parse_docstring=True)
        def get_worker_tool(agent_id: str) -> str:
            """Get one worker record by agent id.

            Use this when an event names a specific worker and you need its
            current status, progress, workspace path, output path, or pending text.

            Args:
                agent_id: Worker id such as "agent-task1".

            Returns:
                JSON object for the worker, or empty JSON object if not found.
            """
            return json.dumps(agent_dict(agent_id), ensure_ascii=False)

        @tool("resume_worker", parse_docstring=True)
        def resume_worker_tool(agent_id: str, text: str) -> str:
            """Resume a worker immediately with new input.

            Use this when a waiting or background worker can continue now. For a
            background worker, include concrete new information from files, logs,
            or external results when available.

            Args:
                agent_id: Worker id to resume.
                text: Message to send to the worker as resume input.

            Returns:
                JSON object with the worker run status and summary.
            """
            result = self.resume(agent_id, text)
            return json.dumps({"status": result.status, "summary": result.summary}, ensure_ascii=False)

        @tool("start_worker", parse_docstring=True)
        def start_worker_tool(objective: str) -> str:
            """Start a new worker under the current task.

            Use this only when the existing workers cannot reasonably be resumed
            to make progress or when parallel investigation is needed.

            Args:
                objective: Concrete objective for the new worker.

            Returns:
                JSON object with the worker start status, summary, and task_id.
            """
            if not self._task: return json.dumps({"status": "failed", "summary": "No active task."}, ensure_ascii=False)
            task_id = str(self._task["task_id"])
            result = self.start_worker(task_id, objective)
            return json.dumps({"status": result.status, "summary": result.summary, "task_id": result.task_id}, ensure_ascii=False)

        @tool("cancel_worker", parse_docstring=True)
        def cancel_worker_tool(agent_id: str) -> str:
            """Cancel one worker by agent id.

            Use this when the worker is no longer useful, is superseded by
            another worker, or should not be resumed.

            Args:
                agent_id: Worker id to cancel.

            Returns:
                JSON object with cancellation status and summary.
            """
            result = self.cancel_worker(agent_id)
            return json.dumps({"status": result.status, "summary": result.summary}, ensure_ascii=False)

        @tool("schedule_worker_resume", parse_docstring=True)
        def schedule_worker_resume_tool(agent_id: str, seconds: float, message: str) -> str:
            """Schedule a future direct resume for one worker.

            Use this after a background worker event when the supervisor wants
            the runtime to wake the same worker later without another supervisor
            decision. At the scheduled time, message is sent directly to the
            worker as resume input.

            Args:
                agent_id: Worker id to resume later.
                seconds: Delay in seconds before resuming the worker.
                message: Exact text to send to the worker when the delay expires.

            Returns:
                JSON object showing whether the future resume was scheduled.
            """
            return self._schedule_worker_resume(agent_id, seconds, message)

        return [
            get_task_tool,
            list_workers_tool,
            get_worker_tool,
            resume_worker_tool,
            start_worker_tool,
            cancel_worker_tool,
            schedule_worker_resume_tool,
        ]

    # ---------------------------------------------------------------
    # Supervisor 辅助函数
    # ---------------------------------------------------------------
	# Supervisor 结果
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

    # Worker 状态
    def _update_agent(self, agent_id: str, update: RuntimeUpdate) -> None:
        record = self._agents[agent_id]
        record.status = update.status
        record.resume_mode = "interrupt" if update.status == "waiting" else "message"
        record.progress_text = update.text
        if update.progress: record.progress = update.progress.snapshot()
        if update.status != "running": record.stall_reported, record.stalled_action_count = False, -1
        if update.thread_id: record.thread_id = update.thread_id
        if update.result: record.result = update.result

    # 卡死检测
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

    # 定时恢复
    def _schedule_worker_resume(self, agent_id: str, seconds: float, message: str) -> str:
        with self._queue_ready:
            if agent_id not in self._agents:
                return json.dumps({"status": "failed", "summary": f"Unknown agent session: {agent_id}."}, ensure_ascii=False)
            delay = max(0.0, float(seconds))
            self._scheduled_resumes.append(ScheduledResume(agent_id, time.monotonic() + delay, message))
            self._queue_ready.notify()
            return json.dumps({"status": "scheduled", "agent_id": agent_id, "seconds": delay, "message": message}, ensure_ascii=False)

    def _resume_due_workers_locked(self) -> None:
        if not self._scheduled_resumes: return
        now = time.monotonic()
        pending: list[ScheduledResume] = []
        for item in self._scheduled_resumes:
            if item.due_at > now:
                pending.append(item)
                continue
            record = self._agents.get(item.agent_id)
            if not record or record.status in {"completed", "failed", "cancelled"}:
                continue
            self._waiters[item.agent_id] = threading.Event()
            threading.Thread(target=self._run, args=("resume", item.agent_id, item.message), daemon=True, name=f"runtime-scheduled-resume-{item.agent_id}").start()
        self._scheduled_resumes = pending


    # 结果封装
    def _final_result(self, agent_id: str) -> ExecutionResult:
        record = self._agents[agent_id]
        result = record.result or ExecutionResult(record.task_id, record.status, record.progress_text or "No result.", record.output_path or (Path.cwd() / "agent-run.md"))
        result.notes.extend([f"Agent ID: {agent_id}", f"Final status: {result.status}"])
        return result
