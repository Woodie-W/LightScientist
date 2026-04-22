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
        output_path = self._build_output_path(request, workspace_root)
        return RuntimeTask(
            task_id=task_id,
            stage_name="stage-2-three-layer-skeleton",
            target=request.target,
            output_path=output_path,
            workspace_root=workspace_root,
            objective=request.target,
            use_agent=request.use_agent,
        )

    def _build_output_path(self, request: StageRequest, workspace_root: Path) -> Path:
        if request.output_path:
            out = Path(request.output_path)
            return out if out.is_absolute() else (workspace_root / out)
        return workspace_root / ("agent-run.md" if request.use_agent else "result.md")


# Backward-compatible alias for the earlier two-layer skeleton.
ManagingAgent = StageManager
