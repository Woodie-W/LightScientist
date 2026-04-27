"""Shared data models for the current LightScientist skeleton."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from langgraph.checkpoint.memory import MemorySaver

ExecutionState = Literal["running", "waiting", "background", "completed", "failed", "cancelled"]
ResumeMode = Literal["message", "interrupt"]
AgentRunState = Literal["completed", "failed", "max_steps_reached", "running", "waiting", "background", "cancelled"]
ResearchMode = Literal["auto", "manual"]
ResearchStatus = Literal["idle", "running", "waiting_user", "completed", "failed", "paused"]


# ---------------------------------------------------------------
# manager / runtime
# ---------------------------------------------------------------


@dataclass(slots=True)
class StageRequest:
    """Incoming request handled by the stage management layer."""

    target: str
    output_path: Path | None
    workspace_root: Path
    use_agent: bool = False


@dataclass(slots=True)
class RuntimeTask:
    """Task passed from stage management into the runtime state layer."""

    task_id: str
    stage_name: str
    target: str
    output_path: Path
    workspace_root: Path
    objective: str
    use_agent: bool = False
    isolate_workspace: bool = True


@dataclass(slots=True)
class ResearchState:
    """Persistent first-layer research controller state."""

    project_id: str
    topic: str
    mode: ResearchMode
    phase: str
    stage: str
    status: ResearchStatus
    workspace_root: Path
    current_task_id: str = ""
    output_path: str = ""
    pending_question: str = ""
    pending_next_stage: str = ""
    user_feedback: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "topic": self.topic,
            "mode": self.mode,
            "phase": self.phase,
            "stage": self.stage,
            "status": self.status,
            "workspace_root": str(self.workspace_root),
            "current_task_id": self.current_task_id,
            "output_path": self.output_path,
            "pending_question": self.pending_question,
            "pending_next_stage": self.pending_next_stage,
            "user_feedback": self.user_feedback,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ResearchState":
        return cls(
            project_id=str(data["project_id"]),
            topic=str(data.get("topic", "")),
            mode=str(data.get("mode", "manual")),  # type: ignore[arg-type]
            phase=str(data.get("phase", "idea")),
            stage=str(data.get("stage", "idea.survey")),
            status=str(data.get("status", "idle")),  # type: ignore[arg-type]
            workspace_root=Path(str(data.get("workspace_root", "."))),
            current_task_id=str(data.get("current_task_id", "")),
            output_path=str(data.get("output_path", data.get("last_output_path", ""))),
            pending_question=str(data.get("pending_question", "")),
            pending_next_stage=str(data.get("pending_next_stage", "")),
            user_feedback=str(data.get("user_feedback", "")),
        )


@dataclass(slots=True)
class ExecutionResult:
    """Structured result returned by the execution layer."""

    task_id: str
    status: ExecutionState
    summary: str
    output_path: Path
    artifacts: list[Path] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------
# minimal_agent / runtime
# ---------------------------------------------------------------
@dataclass(slots=True)
class AgentProgress:
    """Lightweight third-layer progress shared with the runtime layer."""

    step_count: int = 0
    action_count: int = 0
    last_activity_at: float = field(default_factory=time.monotonic)

    def snapshot(self) -> "AgentProgress":
        return AgentProgress(self.step_count, self.action_count, self.last_activity_at)

    def to_dict(self) -> dict[str, float | int]:
        return {
            "step_count": self.step_count,
            "action_count": self.action_count,
            "last_activity_at": self.last_activity_at,
        }


@dataclass(slots=True)
class AgentSessionInfo:
    """Value object for third-layer session metadata."""

    session_id: str
    thread_id: str
    cwd: Path
    log_path: Path
    model: str
    max_steps: int

    def snapshot(self) -> "AgentSessionInfo":
        return AgentSessionInfo(self.session_id, self.thread_id, self.cwd, self.log_path, self.model, self.max_steps)


class HasAgentSessionInfo:
    info: AgentSessionInfo

    def __getattr__(self, name: str) -> object:
        if name in {"session_id", "thread_id", "cwd", "log_path", "model", "max_steps"}:
            return getattr(self.info, name)
        return super().__getattr__(name)  # type: ignore[misc]


class HasAgentProgress:
    progress: AgentProgress

    def __getattr__(self, name: str) -> object:
        if name in {"step_count", "action_count", "last_activity_at"}:
            return getattr(self.progress, name)
        raise AttributeError(name)

    def __setattr__(self, name: str, value: object) -> None:
        if name in {"step_count", "action_count", "last_activity_at"}:
            try:
                progress = object.__getattribute__(self, "progress")
            except AttributeError:
                progress = None
            if progress is not None:
                setattr(progress, name, value)
                if name == "action_count": progress.last_activity_at = time.monotonic()
                return
        super().__setattr__(name, value)


# ---------------------------------------------------------------
# runtime - worker
# ---------------------------------------------------------------
@dataclass(slots=True)
class RuntimeUpdate:
    """Unified status update passed from lower layers into RuntimeSupervisor."""

    status: ExecutionState
    text: str = ""
    progress: AgentProgress | None = None
    result: ExecutionResult | None = None
    thread_id: str = ""


@dataclass(slots=True)
class AgentRecord:
    """Runtime-facing record for one third-layer execution worker."""

    agent_id: str
    task_id: str
    objective: str
    status: ExecutionState
    thread_id: str = ""
    resume_mode: ResumeMode = "message"
    progress: AgentProgress = field(default_factory=AgentProgress)
    progress_text: str = ""  # Latest status text from the worker.
    stall_reported: bool = False
    stalled_action_count: int = -1
    workspace_root: Path | None = None
    output_path: Path | None = None

    @property
    def pending_text(self) -> str:
        return self.progress_text if self.status in {"waiting", "background"} else ""

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "objective": self.objective,
            "status": self.status,
            "thread_id": self.thread_id,
            "resume_mode": self.resume_mode,
            "progress": self.progress.to_dict(),
            "progress_text": self.progress_text,
            "pending_text": self.pending_text,
            "stall_reported": self.stall_reported,
            "workspace_root": str(self.workspace_root) if self.workspace_root else "",
            "output_path": str(self.output_path) if self.output_path else "",
        }
        return data


# ---------------------------------------------------------------
# runtime 内部队列
# ---------------------------------------------------------------
@dataclass(slots=True)
class RuntimeEnvelope:
    agent_id: str
    update: RuntimeUpdate


@dataclass(slots=True)
class ScheduledResume:
    agent_id: str
    due_at: float
    message: str


@dataclass(slots=True)
class SupervisorEvent:
    agent_id: str
    status: ExecutionState
    text: str = ""
    summary: str = ""
    output_path: Path | None = None
    kind: str = "worker"

    @property
    def prompt_key(self) -> str:
        if self.kind == "stall":
            return "stalled"
        return self.status

    def to_prompt_text(self) -> str:
        parts = [f"Worker: {self.agent_id}", f"Status: {self.status}"]
        if self.text: parts.append(f"Text: {self.text}")
        if self.summary: parts.append(f"Summary: {self.summary}")
        if self.output_path: parts.append(f"Output: {self.output_path}")
        return "\n".join(parts)


# ---------------------------------------------------------------
# executor
# ---------------------------------------------------------------
@dataclass(slots=True)
class AgentHandle:
    session: AgentSession
    task_id: str
    stage_name: str
    output_path: Path



# ---------------------------------------------------------------
# minimal_agent
# ---------------------------------------------------------------
@dataclass(slots=True)
class AgentRunResult(HasAgentSessionInfo, HasAgentProgress):
    """Final result for one start/resume cycle of a third-layer session."""

    status: AgentRunState
    info: AgentSessionInfo
    messages: list[dict[str, str]]
    last_model_output: str = ""  # Raw last assistant output before result normalization.
    last_action: str = ""  # Normalized last tool/action summary, such as execute or ask_input.
    final_output: str = ""  # User-facing final text, waiting question, or background note.
    progress: AgentProgress = field(default_factory=AgentProgress)
    error: str = ""
    command_outputs: list[str] = field(default_factory=list)  # Logged workspace-tool outputs.

    @classmethod
    def from_trace(cls, trace: "RunTrace", status: str, final_output: str | None = None) -> "AgentRunResult":
        return cls(
            status,  # type: ignore[arg-type]
            trace.info.snapshot(),
            trace.messages,
            trace.last_model_output,
            trace.last_action,
            trace.final_output if final_output is None else final_output,
            trace.progress.snapshot(),
            trace.error,
            trace.command_outputs,
        )


@dataclass(slots=True)
class RunTrace(HasAgentSessionInfo, HasAgentProgress):
    """Mutable trace collected during one start/resume cycle."""

    info: AgentSessionInfo
    status: Literal["running", "waiting", "background", "completed", "failed", "cancelled"] = "running"
    progress: AgentProgress = field(default_factory=AgentProgress)
    last_model_output: str = ""
    last_action: str = ""
    final_output: str = ""
    error: str = ""
    max_steps_reached: bool = False
    command_outputs: list[str] = field(default_factory=list)
    messages: list[dict[str, str]] = field(default_factory=list)


@dataclass(slots=True)
class AgentSession(HasAgentSessionInfo):
    info: AgentSessionInfo
    system_prompt: str
    checkpointer: MemorySaver
    tools: list[Any] = field(default_factory=list)
    include_lifecycle_tools: bool = True
    resume_mode: ResumeMode = "message"
    last_result: AgentRunResult | None = None
    process_registry: Any | None = None




# Backward-compatible aliases from the earlier two-layer skeleton.
WorkRequest = StageRequest
ExecutionTask = RuntimeTask
