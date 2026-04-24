from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from deepagents.backends import LocalShellBackend
from langchain.tools import tool
from langgraph.types import interrupt

# ---------------------------------------------------------------
# 基础配置
# ---------------------------------------------------------------
_SYSTEM_PATH_PREFIXES = (
    "/Users/",
    "/home/",
    "/tmp/",
    "/var/",
    "/etc/",
    "/opt/",
    "/usr/",
    "/bin/",
    "/sbin/",
    "/dev/",
    "/proc/",
    "/sys/",
    "/root/",
)

ENV = {"PAGER": "cat", "MANPAGER": "cat", "LESS": "-R", "PIP_PROGRESS_BAR": "off", "TQDM_DISABLE": "1"}


# ---------------------------------------------------------------
# 日志记录
# ---------------------------------------------------------------
def log_step(path: Path | None, title: str, body: str = "") -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"[{title}]\n")
        if body:
            f.write(body.rstrip() + "\n")
        f.write("\n")


def _convert_virtual_paths(command: str, workspace_name: str) -> str:
    def replace(match: re.Match[str]) -> str:
        path = match.group(0)
        if path == "/":
            return "."
        if path.startswith(f"/{workspace_name}/"):
            return "./" + path[len(workspace_name) + 2 :]
        return "." + path

    return re.sub(r'(?<=\s)/[^\s;|&<>\'"`]*|^/[^\s;|&<>\'"`]*', replace, command)


# ---------------------------------------------------------------
# 官方工作区后端，增强
# ---------------------------------------------------------------
class WorkspaceBackend(LocalShellBackend):
    """Workspace-rooted backend with EvoScientist-style virtual path handling."""

    def __init__(self, *, root_dir: str | Path, timeout: int = 30, env: dict[str, str] | None = None, inherit_env: bool = False) -> None:
        super().__init__(root_dir=str(Path(root_dir).resolve()), virtual_mode=True, timeout=timeout, env=env, inherit_env=inherit_env)
        self._workspace_name = self.cwd.name

    def _resolve_path(self, key: str) -> Path:
        if key == f"/{self._workspace_name}":
            key = "/"
        elif key.startswith(f"/{self._workspace_name}/"):
            key = key[len(self._workspace_name) + 1 :]
        for prefix in _SYSTEM_PATH_PREFIXES:
            if key.startswith(prefix):
                marker = f"/{self._workspace_name}/"
                idx = key.find(marker)
                if idx != -1:
                    key = "/" + key[idx + len(marker) :]
                else:
                    key = "/" + Path(key).name
                break
        return super()._resolve_path(key)

    def execute(self, command: str, *, timeout: int | None = None):
        command = _convert_virtual_paths(command, self._workspace_name)
        return super().execute(command, timeout=timeout)


class LoggingWorkspaceBackend(WorkspaceBackend):
    def __init__(self, *, trace: Any, log_path: Path, root_dir: Path, timeout: int = 30) -> None:
        super().__init__(root_dir=root_dir, timeout=timeout, env=ENV, inherit_env=False)
        self.trace, self.log_path = trace, log_path

    def _log_backend_output(self, name: str, output: Any) -> None:
        body = output if isinstance(output, str) else str(output)
        self.trace.action_count += 1
        self.trace.command_outputs.append(f"[{name}]\n{body}")
        log_step(self.log_path, f"step-{self.trace.step_count}-{name}-output", body)

    def ls(self, path: str):
        result = super().ls(path)
        self._log_backend_output("ls", result)
        return result

    def read(self, file_path: str, offset: int = 0, limit: int = 2000):
        result = super().read(file_path, offset=offset, limit=limit)
        self._log_backend_output("read_file", result)
        return result

    def write(self, file_path: str, content: str):
        result = super().write(file_path, content)
        self._log_backend_output("write_file", result)
        return result

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False):
        result = super().edit(file_path, old_string, new_string, replace_all=replace_all)
        self._log_backend_output("edit_file", result)
        return result

    def glob(self, pattern: str, path: str = "/"):
        result = super().glob(pattern, path=path)
        self._log_backend_output("glob", result)
        return result

    def grep(self, pattern: str, path: str | None = None, glob: str | None = None):
        result = super().grep(pattern, path=path, glob=glob)
        self._log_backend_output("grep", result)
        return result

    def execute(self, command: str, *, timeout: int | None = None):
        result = super().execute(command, timeout=timeout)
        self._log_backend_output("execute", result.output)
        return result



# ---------------------------------------------------------------
# 自定义工具
# ---------------------------------------------------------------
@tool(parse_docstring=True)
def ask_input(question: str) -> str:
    """Ask the upper layer for required input and pause this worker.

    Use this only when the task cannot continue without a specific external
    answer that is not available from the workspace or tools. The question
    should be short and concrete.

    Args:
        question: The exact question to send to the upper layer.

    Returns:
        The answer provided when the worker is resumed.
    """
    response = interrupt({"type": "waiting", "question": question})
    return str(response or "")


@tool(parse_docstring=True)
def suspend_background(note: str) -> str:
    """Suspend this worker because progress depends on future external work.

    Use this after starting or handing off work that must continue outside the
    current model turn, such as a long-running experiment. Do not use it for
    normal work that can continue immediately.

    Args:
        note: A concise status note explaining what is running or pending and
            what should be checked later.

    Returns:
        The background status note.
    """
    return note


@tool(parse_docstring=True)
def finish_cancelled(summary: str) -> str:
    """Finish cancellation after preserving the worker's current deliverables.

    Use this only after the upper layer asks this worker to cancel. Before
    calling it, inspect the workspace if needed, write or update delivery
    documentation when useful, and make sure the summary explains completed
    work, unfinished work, preserved artifact paths, and useful next steps.

    Args:
        summary: Concise cancellation handoff summary for the upper layers.

    Returns:
        The cancellation handoff summary.
    """
    return summary
