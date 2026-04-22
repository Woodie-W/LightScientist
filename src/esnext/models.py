"""Shared data models for the current LightScientist skeleton."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

ExecutionState = Literal["running", "waiting", "background", "completed", "failed", "cancelled"]


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
class AgentRecord:
    """Runtime-facing record for one third-layer execution worker."""

    agent_id: str
    task_id: str
    objective: str
    status: ExecutionState
    thread_id: str = ""
    progress_text: str = ""
    output_path: Path | None = None
    result: ExecutionResult | None = None


# Backward-compatible aliases from the earlier two-layer skeleton.
WorkRequest = StageRequest
ExecutionTask = RuntimeTask
