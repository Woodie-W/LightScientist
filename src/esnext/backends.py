from __future__ import annotations

import os, re, signal, subprocess, threading, time
from pathlib import Path
from typing import Any

from deepagents.backends import LocalShellBackend
from deepagents.backends.protocol import ExecuteResponse
from langchain.tools import tool
from langgraph.types import interrupt

from .events import EventBus

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
# 官方工作区后端，增强loger等
# ---------------------------------------------------------------
class CommandProcessRegistry:
    """Tracks running shell processes so cancellation can terminate them."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._processes: set[subprocess.Popen[str]] = set()

    def add(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            self._processes.add(process)

    def remove(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            self._processes.discard(process)

    def running_count(self) -> int:
        with self._lock:
            return sum(1 for process in self._processes if process.poll() is None)

    def kill_all(self, grace_seconds: float = 1.0) -> int:
        with self._lock:
            processes = [process for process in self._processes if process.poll() is None]
        for process in processes:
            self._signal_process(process, signal.SIGTERM)
        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline and any(process.poll() is None for process in processes):
            time.sleep(0.05)
        for process in processes:
            if process.poll() is None:
                self._signal_process(process, signal.SIGKILL)
        return len(processes)

    def _signal_process(self, process: subprocess.Popen[str], sig: int) -> None:
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return
        except Exception:
            try:
                process.send_signal(sig)
            except Exception:
                return


class WorkspaceBackend(LocalShellBackend):
    """Workspace-rooted backend with EvoScientist-style virtual path handling."""

    def __init__(
        self, *, root_dir: str | Path, timeout: int = 30, env: dict[str, str] | None = None,
        inherit_env: bool = False, process_registry: CommandProcessRegistry | None = None,
    ) -> None:
        super().__init__(root_dir=str(Path(root_dir).resolve()), virtual_mode=True, timeout=timeout, env=env, inherit_env=inherit_env)
        self._workspace_name = self.cwd.name
        self.process_registry = process_registry or CommandProcessRegistry()

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
        if not command or not isinstance(command, str):
            return ExecuteResponse(output="Error: Command must be a non-empty string.", exit_code=1, truncated=False)
        effective_timeout = timeout if timeout is not None else self._default_timeout
        if effective_timeout <= 0:
            raise ValueError(f"timeout must be positive, got {effective_timeout}")
        process: subprocess.Popen[str] | None = None
        try:
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=self._env,
                cwd=str(self.cwd),
                start_new_session=True,
            )
            self.process_registry.add(process)
            stdout, stderr = process.communicate(timeout=effective_timeout)
            return _execute_response(stdout, stderr, process.returncode, self._max_output_bytes)
        except subprocess.TimeoutExpired:
            if process:
                self.process_registry.kill_all()
            return ExecuteResponse(output=_timeout_message(effective_timeout, timeout is not None), exit_code=124, truncated=False)
        except Exception as e:
            return ExecuteResponse(output=f"Error executing command ({type(e).__name__}): {e}", exit_code=1, truncated=False)
        finally:
            if process:
                self.process_registry.remove(process)


def _execute_response(stdout: str, stderr: str, returncode: int | None, max_output_bytes: int) -> ExecuteResponse:
    output_parts = []
    if stdout:
        output_parts.append(stdout)
    if stderr:
        output_parts.extend(f"[stderr] {line}" for line in stderr.strip().split("\n"))
    output = "\n".join(output_parts) if output_parts else "<no output>"
    truncated = False
    if len(output) > max_output_bytes:
        output = output[:max_output_bytes] + f"\n\n... Output truncated at {max_output_bytes} bytes."
        truncated = True
    if returncode:
        output = f"{output.rstrip()}\n\nExit code: {returncode}"
    return ExecuteResponse(output=output, exit_code=returncode, truncated=truncated)


def _timeout_message(seconds: int, custom: bool) -> str:
    if custom:
        return f"Error: Command timed out after {seconds} seconds (custom timeout). The command may be stuck or require more time."
    return f"Error: Command timed out after {seconds} seconds. For long-running commands, re-run using the timeout parameter."


class LoggingWorkspaceBackend(WorkspaceBackend):
    def __init__(
        self, *, trace: Any, log_path: Path, root_dir: Path, timeout: int = 30,
        process_registry: CommandProcessRegistry | None = None,
        event_bus: EventBus | None = None,
        event_layer: str = "L3",
        event_context: dict[str, object] | None = None,
    ) -> None:
        super().__init__(root_dir=root_dir, timeout=timeout, env=ENV, inherit_env=False, process_registry=process_registry)
        self.trace, self.log_path = trace, log_path
        self.event_bus, self.event_layer = event_bus, event_layer
        self.event_context = dict(event_context or {})

    def _log_backend_output(self, name: str, output: Any) -> None:
        body = output if isinstance(output, str) else str(output)
        self.trace.action_count += 1
        self.trace.command_outputs.append(f"[{name}]\n{body}")
        log_step(self.log_path, f"step-{self.trace.step_count}-{name}-output", body)
        self._emit("tool_result", body, tool=name)

    def _emit_tool_call(self, name: str, **data: object) -> None:
        detail = ", ".join(f"{key}={value}" for key, value in data.items() if value not in {None, ""})
        self._emit("tool_call", f"{name}({detail})" if detail else name, tool=name, **data)

    def _emit(self, kind: str, message: str, **data: object) -> None:
        if not self.event_bus: return
        context = dict(self.event_context)
        self.event_bus.emit(
            self.event_layer,
            kind,
            message,
            task_id=str(context.pop("task_id", "")),
            agent_id=str(context.pop("agent_id", "")),
            stage=str(context.pop("stage", "")),
            step_count=self.trace.step_count,
            action_count=self.trace.action_count,
            **context,
            **data,
        )

    def ls(self, path: str):
        self._emit_tool_call("ls", path=path)
        result = super().ls(path)
        self._log_backend_output("ls", result)
        return result

    def read(self, file_path: str, offset: int = 0, limit: int = 2000):
        self._emit_tool_call("read_file", file_path=file_path, offset=offset, limit=limit)
        result = super().read(file_path, offset=offset, limit=limit)
        self._log_backend_output("read_file", result)
        return result

    def write(self, file_path: str, content: str):
        self._emit_tool_call("write_file", file_path=file_path, bytes=len(content.encode("utf-8")))
        result = super().write(file_path, content)
        self._log_backend_output("write_file", result)
        return result

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False):
        self._emit_tool_call("edit_file", file_path=file_path, replace_all=replace_all)
        result = super().edit(file_path, old_string, new_string, replace_all=replace_all)
        self._log_backend_output("edit_file", result)
        return result

    def glob(self, pattern: str, path: str = "/"):
        self._emit_tool_call("glob", pattern=pattern, path=path)
        result = super().glob(pattern, path=path)
        self._log_backend_output("glob", result)
        return result

    def grep(self, pattern: str, path: str | None = None, glob: str | None = None):
        self._emit_tool_call("grep", pattern=pattern, path=path or "", glob=glob or "")
        result = super().grep(pattern, path=path, glob=glob)
        self._log_backend_output("grep", result)
        return result

    def execute(self, command: str, *, timeout: int | None = None):
        self._emit_tool_call("execute", command=command, timeout=timeout)
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
