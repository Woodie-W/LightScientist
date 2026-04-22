"""Stage management layer for the current LightScientist skeleton."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from .executor import ExecutionResult
from .models import RuntimeTask, StageRequest
from .runtime import RuntimeSupervisor


class StageManager:
    """Top layer that converts a user request into a runtime task."""

    def __init__(self, runtime_supervisor: RuntimeSupervisor | None = None) -> None:
        self.runtime_supervisor = runtime_supervisor or RuntimeSupervisor()

    def handle(self, request: StageRequest) -> ExecutionResult:
        task = self._build_runtime_task(request)
        return self.runtime_supervisor.run(task)

    def _build_runtime_task(self, request: StageRequest) -> RuntimeTask:
        task_id = uuid4().hex[:8]
        workspace_root = request.workspace_root.resolve()
        return RuntimeTask(
            task_id=task_id,
            stage_name="stage-2-three-layer-skeleton",
            target=request.target,
            output_path=Path(request.output_path),
            workspace_root=workspace_root,
            objective=self._build_objective(request.target, workspace_root, request.use_agent),
            use_agent=request.use_agent,
        )

    def _build_objective(self, target: str, workspace_root: Path, use_agent: bool) -> str:
        if use_agent:
            return target
        path = self._resolve_target(target, workspace_root)
        if path.is_file():
            return f"Summarize the file at {target} into a compact markdown artifact."
        if path.is_dir():
            return f"Inspect the workspace path at {target} and write a structured inventory."
        return "Write the provided note text into a markdown artifact."

    def _resolve_target(self, target: str, workspace_root: Path) -> Path:
        candidate = Path(target)
        return candidate if candidate.is_absolute() else (workspace_root / candidate).resolve()


# Backward-compatible alias for the earlier two-layer skeleton.
ManagingAgent = StageManager
