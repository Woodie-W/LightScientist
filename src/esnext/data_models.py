"""Shared data models for the current LightScientist skeleton."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

ExecutionState = Literal["running", "waiting", "background", "completed", "failed", "cancelled"]
ResumeMode = Literal["message", "interrupt"]


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


@dataclass(slots=True)
class ExecutionResult:
    """Structured result returned by the execution layer."""

    task_id: str
    status: ExecutionState
    summary: str
    output_path: Path
    artifacts: list[Path] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


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
    pending_text: str = ""  # Waiting question or background note when the worker is suspended.
    stall_reported: bool = False
    stalled_action_count: int = -1
    workspace_root: Path | None = None
    output_path: Path | None = None
    result: ExecutionResult | None = None  # Final execution result once a worker round finishes.

    def to_dict(self) -> dict[str, object]:
        return {
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


# Backward-compatible aliases from the earlier two-layer skeleton.
WorkRequest = StageRequest
ExecutionTask = RuntimeTask
