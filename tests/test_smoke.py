from __future__ import annotations

import time
from collections import deque
from pathlib import Path

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ConfigDict, Field

from esnext.cli import main, repl
from esnext.manager import StageManager
from esnext.minimal_agent import _status_from_output, resume_agent_session, run_agent, start_agent_session
from esnext.models import RuntimeTask, StageRequest
from esnext.runtime import RuntimeSupervisor, RuntimeUpdate


class ScriptedChatModel(BaseChatModel):
    role: str = "worker"
    worker_replies: object = Field(exclude=True)
    supervisor_replies: object = Field(exclude=True)
    trace: object = Field(exclude=True)
    status_cb: object = Field(default=None, exclude=True)
    log_path: object = Field(default=None, exclude=True)
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs):
        trace = self.trace
        trace.step_count += 1
        step = trace.step_count
        trace.messages = [m for msg in messages if (m := self._to_msg(msg))]
        if self.status_cb:
            self.status_cb("running", f"Step {step}: querying model.")
        is_supervisor = self.role == "supervisor" or any(
            isinstance(msg, SystemMessage) and "second-layer supervisor" in str(msg.content).lower() for msg in messages
        )
        queue = self.supervisor_replies if is_supervisor else self.worker_replies
        raw = queue.popleft() if queue else ("answer: TASK_CONTINUE: No action." if is_supervisor else "")
        trace.last_model_output = raw
        from esnext.minimal_agent import log_step

        log_step(self.log_path, f"step-{step}-model-output", raw)
        if not raw:
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=""))])
        if raw.startswith("tool:"):
            spec = raw.split(":", 1)[1].strip()
            name, sep, arg = spec.partition("|")
            name = name.strip() or "execute"
            arg = arg.strip() if sep else name
            if name == "ask_input":
                trace.last_action = f"ask_input: {arg}"
                log_step(self.log_path, f"step-{step}-tool-call", trace.last_action)
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[{"name": "ask_input", "args": {"question": arg}, "id": f"call_{step}", "type": "tool_call"}]))])
            cmd = spec if not sep else arg
            trace.last_action = f"execute: {cmd}"
            log_step(self.log_path, f"step-{step}-tool-call", trace.last_action)
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[{"name": "execute", "args": {"command": cmd}, "id": f"call_{step}", "type": "tool_call"}]))])
        trace.status, trace.final_output = _status_from_output(raw.removeprefix("answer:").strip())
        log_step(self.log_path, f"step-{step}-final-answer", trace.final_output)
        if self.status_cb:
            self.status_cb(trace.status, f"Step {step}: {trace.final_output or trace.status}.")
        log_step(self.log_path, "run-end", f"status: {trace.status}\nstep: {step}\nmessage: {trace.final_output}")
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=trace.final_output))])

    def _to_msg(self, msg: BaseMessage):
        if isinstance(msg, SystemMessage):
            return {"role": "system", "content": str(msg.content)}
        if isinstance(msg, HumanMessage):
            return {"role": "user", "content": str(msg.content)}
        if isinstance(msg, ToolMessage):
            return {"role": "tool", "content": str(msg.content)}
        if isinstance(msg, AIMessage):
            return {"role": "assistant", "content": str(msg.content or "")}
        return None


def patch_scripted_model(monkeypatch, *replies: str, supervisor_replies: tuple[str, ...] = (), scope_root: Path | None = None) -> None:
    worker_queue = deque(replies)
    supervisor_queue = deque(supervisor_replies)
    monkeypatch.setattr(
        "esnext.minimal_agent.build_chat_model",
        lambda *, trace, status_cb, log_path, model, max_steps, **_: ScriptedChatModel(
            role="supervisor" if Path(log_path).name.startswith("supervisor-") else "worker",
            worker_replies=worker_queue if scope_root is None or str(Path(log_path)).startswith(str(scope_root)) else deque(),
            supervisor_replies=supervisor_queue if scope_root is None or str(Path(log_path)).startswith(str(scope_root)) else deque(),
            trace=trace,
            status_cb=status_cb,
            log_path=log_path,
        ),
    )


def make_agent_manager(monkeypatch, scope_root: Path, *replies: str) -> StageManager:
    patch_scripted_model(monkeypatch, *replies, scope_root=scope_root)
    manager = StageManager(runtime_supervisor=RuntimeSupervisor(executor=None))
    return manager


def test_stage_manager_non_agent_flow_is_not_implemented(tmp_path: Path) -> None:
    manager = StageManager()
    result = manager.handle(StageRequest(target="plain text", output_path=tmp_path / "result.md", workspace_root=tmp_path))
    assert result.status == "failed"
    assert "Only the agent path is implemented" in result.summary


def test_runtime_supervisor_tracks_agent_records(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "agent.md"
    manager = make_agent_manager(monkeypatch, tmp_path, "answer: Done.")
    supervisor = manager.runtime_supervisor
    result = manager.handle(
        StageRequest(
            target="Stage 2 three-layer skeleton is running.",
            output_path=output,
            workspace_root=tmp_path,
            use_agent=True,
        )
    )

    assert result.status == "completed"
    agents = list(supervisor._agents.values())
    assert len(agents) == 1
    assert agents[0].status == "completed"
    assert agents[0].thread_id
    assert agents[0].result is result
    assert agents[0].progress_text == result.summary
    assert any("Agent ID:" in note for note in result.notes)


def test_stage_manager_builds_default_output_path(tmp_path: Path, monkeypatch) -> None:
    manager = make_agent_manager(monkeypatch, tmp_path, "answer: Done.")
    result = manager.handle(StageRequest(target="Try and stop cleanly.", output_path=None, workspace_root=tmp_path, use_agent=True))
    assert result.output_path == tmp_path / "agent-run.md"


def test_cli_run_uses_default_output_path(tmp_path: Path, capsys, monkeypatch) -> None:
    manager = make_agent_manager(monkeypatch, tmp_path, "answer: Done.")
    monkeypatch.setattr("esnext.cli.StageManager", lambda: manager)
    exit_code = main(["run", "Try and stop cleanly.", "--workspace", str(tmp_path), "--agent"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "output:" in captured.out
    assert (tmp_path / "agent-run.md").exists()


def test_repl_runs_until_quit(tmp_path: Path, capsys, monkeypatch) -> None:
    manager = make_agent_manager(monkeypatch, tmp_path, "answer: Done.")
    inputs = iter(["Try and stop cleanly.", "quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    exit_code = repl(manager=manager, workspace=tmp_path)
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "LightScientist REPL" in captured.out
    assert "status: completed" in captured.out
    assert (tmp_path / "agent-run.md").exists()


def test_minimal_agent_run_handles_command_and_final_answer(tmp_path: Path) -> None:
    from unittest.mock import patch
    from collections import deque

    with patch("esnext.minimal_agent.build_chat_model") as build:
        build.side_effect = lambda **kw: ScriptedChatModel(
            worker_replies=deque(["tool: printf 'hello from agent'", "answer: Done."]),
            supervisor_replies=deque(),
            trace=kw["trace"],
            status_cb=kw["status_cb"],
            log_path=kw["log_path"],
        )
        result = run_agent("Say hello", cwd=tmp_path, max_steps=4)
    assert result.status == "completed"
    assert result.step_count == 2
    assert "hello from agent" in "".join(result.command_outputs)
    log_text = (tmp_path / "agent-debug.log").read_text(encoding="utf-8")
    assert "[step-1-model-output]" in log_text
    assert "execute: printf 'hello from agent'" in log_text
    assert "[run-end]" in log_text


def test_minimal_agent_run_handles_final_answer(tmp_path: Path) -> None:
    from unittest.mock import patch
    from collections import deque

    with patch("esnext.minimal_agent.build_chat_model") as build:
        build.side_effect = lambda **kw: ScriptedChatModel(
            worker_replies=deque(["tool: pwd", "answer: 当前工作目录是 /tmp/example"]),
            supervisor_replies=deque(),
            trace=kw["trace"],
            status_cb=kw["status_cb"],
            log_path=kw["log_path"],
        )
        result = run_agent("Where am I?", cwd=tmp_path, max_steps=4)
    assert result.status == "completed"
    assert result.final_output == "当前工作目录是 /tmp/example"


def test_persistent_agent_session_can_resume(tmp_path: Path, monkeypatch) -> None:
    patch_scripted_model(monkeypatch, "answer: First answer.", "answer: Second answer.")
    session = start_agent_session("First turn", cwd=tmp_path)
    first = session.last_result
    second = resume_agent_session(session, "Second turn")
    assert first is not None
    assert first.thread_id == second.thread_id
    assert first.session_id == second.session_id
    assert second.final_output == "Second answer."
    log_text = (tmp_path / "agent-debug.log").read_text(encoding="utf-8")
    assert "[run-start]" in log_text
    assert "[resume-start]" in log_text


def test_runtime_supervisor_can_resume_agent(tmp_path: Path, monkeypatch) -> None:
    patch_scripted_model(monkeypatch, "answer: First answer.", "answer: Second answer.")
    supervisor = RuntimeSupervisor()
    start = supervisor.start(
        RuntimeTask("task1234", "interactive", "First turn", tmp_path / "agent.md", tmp_path, "First turn", True)
    )
    agent_id = next(iter(supervisor._agents.values())).agent_id
    resumed = supervisor.resume(agent_id, "Second turn")
    assert start.status == "completed"
    assert resumed.status == "completed"
    assert supervisor._agents[agent_id].thread_id


def test_minimal_agent_run_can_suspend_waiting(tmp_path: Path) -> None:
    from unittest.mock import patch
    from collections import deque

    with patch("esnext.minimal_agent.build_chat_model") as build:
        build.side_effect = lambda **kw: ScriptedChatModel(
            worker_replies=deque(["tool: ask_input|请提供实验参数。"]),
            supervisor_replies=deque(),
            trace=kw["trace"],
            status_cb=kw["status_cb"],
            log_path=kw["log_path"],
        )
        result = run_agent("Need more input", cwd=tmp_path, max_steps=4)
    assert result.status == "waiting"
    assert result.final_output == "请提供实验参数。"


def test_runtime_supervisor_preserves_waiting_status(tmp_path: Path, monkeypatch) -> None:
    manager = make_agent_manager(monkeypatch, tmp_path, "tool: ask_input|请补充数据集路径。")
    result = manager.handle(
        StageRequest(target="Need dataset path", output_path=tmp_path / "agent.md", workspace_root=tmp_path, use_agent=True)
    )
    agent = next(iter(manager.runtime_supervisor._agents.values()))
    assert result.status == "waiting"
    assert result.summary == "请补充数据集路径。"
    assert agent.status == "waiting"
    assert agent.resume_mode == "interrupt"
    assert agent.progress_text == "请补充数据集路径。"
    assert agent.pending_text == "请补充数据集路径。"


def test_waiting_session_can_resume_with_interrupt(tmp_path: Path, monkeypatch) -> None:
    patch_scripted_model(monkeypatch, "tool: ask_input|请补充数据集路径。", "answer: 已收到数据集路径。")
    supervisor = RuntimeSupervisor()
    first = supervisor.start(
        RuntimeTask("task9999", "interactive", "Need dataset path", tmp_path / "agent.md", tmp_path, "Need dataset path", True)
    )
    agent_id = next(iter(supervisor._agents.values())).agent_id
    resumed = supervisor.resume(agent_id, "/data/dataset")
    assert first.status == "waiting"
    assert resumed.status == "completed"
    assert "已收到数据集路径" in resumed.summary or "completed" in resumed.summary


def test_background_session_can_resume_with_message(tmp_path: Path, monkeypatch) -> None:
    patch_scripted_model(monkeypatch, "answer: BACKGROUND: 实验已启动。", "answer: 实验已完成。")
    supervisor = RuntimeSupervisor()
    first = supervisor.start(
        RuntimeTask("taskbg01", "interactive", "Run experiment", tmp_path / "agent.md", tmp_path, "Run experiment", True)
    )
    agent = next(iter(supervisor._agents.values()))
    assert first.status == "background"
    assert agent.resume_mode == "message"
    assert agent.pending_text == "实验已启动。"
    resumed = supervisor.resume(agent.agent_id, "实验结果已经回来了。")
    assert resumed.status == "completed"
    assert agent.pending_text == ""


def test_stage_manager_agent_goal_flow(tmp_path: Path, monkeypatch) -> None:
    manager = make_agent_manager(monkeypatch, tmp_path, "answer: 您好！", "answer: Done.")
    output = tmp_path / "agent.md"
    result = manager.handle(
        StageRequest(target="Try and stop cleanly.", output_path=output, workspace_root=tmp_path, use_agent=True)
    )
    assert result.status == "completed"
    assert output.exists()
    content = output.read_text(encoding="utf-8")
    assert "Status: `completed`" in content


def test_runtime_supervisor_can_run_supervisor_agent(tmp_path: Path, monkeypatch) -> None:
    patch_scripted_model(monkeypatch, "answer: Done.", supervisor_replies=("answer: TASK_COMPLETED: Supervisor marked the task done.",), scope_root=tmp_path)
    supervisor = RuntimeSupervisor()
    result = supervisor.start(
        RuntimeTask("tasksup1", "interactive", "Finish the task", tmp_path / "agent.md", tmp_path, "Finish the task", True)
    )
    assert result.status == "completed"
    deadline = time.time() + 3
    while time.time() < deadline:
        task = supervisor.get_task("tasksup1")
        if task and task["summary"] == "Supervisor marked the task done.":
            break
        time.sleep(0.05)
    task = supervisor.get_task("tasksup1")
    assert task is not None
    assert task["status"] == "completed"
    assert task["summary"] == "Supervisor marked the task done."


def test_runtime_supervisor_can_cancel_worker(tmp_path: Path, monkeypatch) -> None:
    patch_scripted_model(monkeypatch, "answer: BACKGROUND: 实验已启动。", scope_root=tmp_path)
    supervisor = RuntimeSupervisor()
    supervisor.start(
        RuntimeTask("taskcancelw", "interactive", "Run experiment", tmp_path / "agent.md", tmp_path, "Run experiment", True)
    )
    agent = next(iter(supervisor._agents.values()))
    cancelled = supervisor.cancel_worker(agent.agent_id)
    assert cancelled.status == "cancelled"
    assert supervisor._agents[agent.agent_id].status == "cancelled"
    resumed = supervisor.resume(agent.agent_id, "继续")
    assert resumed.status == "cancelled"


def test_runtime_supervisor_does_not_forward_running_progress(tmp_path: Path) -> None:
    from esnext.models import AgentRecord

    supervisor = RuntimeSupervisor()
    agent_id = "agent-progress"
    supervisor._agents[agent_id] = AgentRecord(agent_id, "progress", "objective", "running")
    supervisor._handle_update(agent_id, RuntimeUpdate("running", "Step 1"))
    assert not supervisor._supervisor_queue
