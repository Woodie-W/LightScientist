"""Execution layer for the current LightScientist skeleton."""

from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess, run
from typing import Callable

from .minimal_agent import run_agent
from .models import ExecutionResult, RuntimeTask

StatusCallback = Callable[[str, str], None]


class CommandLineTool:
    """Minimal command-line capability exposed to the execution layer."""

    def run(self, args: list[str], cwd: Path) -> CompletedProcess[str]:
        return run(
            args,
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
        )


class ExecutionRuntime:
    """Third-layer execution runtime with command-line capability only."""

    def __init__(self, command_line: CommandLineTool | None = None, agent_query_fn=None) -> None:
        self.command_line = command_line or CommandLineTool()
        self.agent_query_fn = agent_query_fn

    def execute(self, task: RuntimeTask, status_cb: StatusCallback | None = None) -> ExecutionResult:
        task.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._emit(status_cb, "running", "Execution runtime received the task.")
        if task.use_agent:
            return self._agent_goal(task, status_cb)
        target_path = self._resolve_path(task)
        if target_path.is_file():
            return self._summarize_file(task, status_cb)
        if target_path.is_dir():
            return self._inspect_path(task, status_cb)
        return self._write_note(task, status_cb)

    def _agent_goal(self, task: RuntimeTask, status_cb: StatusCallback | None = None) -> ExecutionResult:
        self._emit(status_cb, "running", "Minimal agent loop started.")
        try:
            r = run_agent(task.objective, cwd=task.workspace_root, query_fn=self.agent_query_fn, status_cb=status_cb)
        except Exception as e:
            self._emit(status_cb, "failed", f"Minimal agent failed: {e}")
            return ExecutionResult(task.task_id, "failed", f"Minimal agent failed: {e}", task.output_path)
        status = self._agent_status(r.status)
        text = [
            "# Agent Goal Run", "", f"- Stage: `{task.stage_name}`", f"- Status: `{status}`", f"- Steps: {r.step_count}",
            f"- Last action: `{r.last_action or '(none)'}`", "", "## Final Output", "", r.final_output or "(empty)",
        ]
        if status != r.status:
            text[6:6] = [f"- Raw agent status: `{r.status}`"]
        if r.error:
            text += ["", "## Error", "", r.error]
        task.output_path.write_text("\n".join(text) + "\n", encoding="utf-8")
        self._emit(status_cb, status, f"Minimal agent finished after {r.step_count} steps.")
        return ExecutionResult(
            task.task_id, status, f"Minimal agent run finished with status {status}.", task.output_path,
            artifacts=[task.output_path], notes=[f"Minimal agent steps: {r.step_count}"],
        )

    def _summarize_file(self, task: RuntimeTask, status_cb: StatusCallback | None = None) -> ExecutionResult:
        source_path = self._resolve_path(task)
        self._emit(status_cb, "running", f"Summarizing file {source_path.name}.")
        if not source_path.is_file():
            self._emit(status_cb, "failed", f"Source file not found: {source_path}")
            return ExecutionResult(
                task_id=task.task_id,
                status="failed",
                summary=f"Source file not found: {source_path}",
                output_path=task.output_path,
                notes=["The execution runtime received a file summary task with an invalid path."],
            )

        line_info = self.command_line.run(["wc", "-l", str(source_path)], cwd=task.workspace_root)
        word_info = self.command_line.run(["wc", "-w", str(source_path)], cwd=task.workspace_root)
        preview_info = self.command_line.run(
            ["sed", "-n", "1,3p", str(source_path)],
            cwd=task.workspace_root,
        )

        line_count = self._extract_first_int(line_info.stdout)
        word_count = self._extract_first_int(word_info.stdout)
        preview = [
            line.strip()
            for line in preview_info.stdout.splitlines()
            if line.strip()
        ]

        report = [
            "# File Summary",
            "",
            f"- Source: `{source_path}`",
            f"- Stage: `{task.stage_name}`",
            f"- Total lines: {line_count}",
            f"- Approximate word count: {word_count}",
            "",
            "## Leading Highlights",
        ]

        if preview:
            report.extend(f"- {line[:120]}" for line in preview)
        else:
            report.append("- The file is empty.")

        task.output_path.write_text("\n".join(report) + "\n", encoding="utf-8")
        self._emit(status_cb, "completed", f"File summary written to {task.output_path.name}.")
        return ExecutionResult(
            task_id=task.task_id,
            status="completed",
            summary=f"Summarized file {source_path.name}.",
            output_path=task.output_path,
            artifacts=[task.output_path],
        )

    def _inspect_path(self, task: RuntimeTask, status_cb: StatusCallback | None = None) -> ExecutionResult:
        target_path = self._resolve_path(task)
        self._emit(status_cb, "running", f"Inspecting path {target_path}.")
        if not target_path.exists():
            self._emit(status_cb, "failed", f"Target path not found: {target_path}")
            return ExecutionResult(
                task_id=task.task_id,
                status="failed",
                summary=f"Target path not found: {target_path}",
                output_path=task.output_path,
                notes=["The execution runtime could not locate the requested path."],
            )

        if target_path.is_dir():
            listing = self.command_line.run(
                ["find", str(target_path), "-maxdepth", "1", "-mindepth", "1"],
                cwd=task.workspace_root,
            )
            entries = sorted(
                Path(line).name
                for line in listing.stdout.splitlines()
                if line.strip()
            )[:20]
            lines = [
                "# Path Inspection",
                "",
                f"- Target: `{target_path}`",
                f"- Stage: `{task.stage_name}`",
                "- Type: directory",
                f"- Listed entries: {len(entries)}",
                "",
                "## Entries",
            ]
            if entries:
                for entry_name in entries:
                    suffix = "/" if (target_path / entry_name).is_dir() else ""
                    lines.append(f"- `{entry_name}{suffix}`")
            else:
                lines.append("- Directory is empty.")
        else:
            size_info = self.command_line.run(
                ["wc", "-c", str(target_path)],
                cwd=task.workspace_root,
            )
            lines = [
                "# Path Inspection",
                "",
                f"- Target: `{target_path}`",
                f"- Stage: `{task.stage_name}`",
                "- Type: file",
                f"- Size: {self._extract_first_int(size_info.stdout)} bytes",
            ]

        task.output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self._emit(status_cb, "completed", f"Path inspection written to {task.output_path.name}.")
        return ExecutionResult(
            task_id=task.task_id,
            status="completed",
            summary=f"Inspected path {target_path}.",
            output_path=task.output_path,
            artifacts=[task.output_path],
        )

    def _write_note(self, task: RuntimeTask, status_cb: StatusCallback | None = None) -> ExecutionResult:
        self._emit(status_cb, "running", "Writing note artifact.")
        lines = [
            "# Note",
            "",
            task.target.strip() or "(empty note)",
            "",
            "## Execution Context",
            "",
            f"- Stage: `{task.stage_name}`",
            f"- Workspace: `{task.workspace_root}`",
            f"- Task ID: `{task.task_id}`",
            "- Execution capability: local command line only",
        ]
        task.output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self._emit(status_cb, "completed", f"Note written to {task.output_path.name}.")
        return ExecutionResult(
            task_id=task.task_id,
            status="completed",
            summary="Wrote note artifact.",
            output_path=task.output_path,
            artifacts=[task.output_path],
        )

    def _resolve_path(self, task: RuntimeTask) -> Path:
        candidate = Path(task.target)
        if candidate.is_absolute():
            return candidate
        return (task.workspace_root / candidate).resolve()

    def _extract_first_int(self, text: str) -> int:
        for part in text.split():
            if part.isdigit():
                return int(part)
        return 0

    def _agent_status(self, status: str) -> str:
        if status in {"completed", "terminated"}:
            return "completed"
        if status == "max_steps_reached":
            return "failed"
        return "failed"

    def _emit(self, status_cb: StatusCallback | None, status: str, text: str) -> None:
        if status_cb:
            status_cb(status, text)


# Backward-compatible alias for the earlier two-layer skeleton.
ExecutionAgent = ExecutionRuntime
