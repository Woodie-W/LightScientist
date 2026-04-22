from __future__ import annotations

from pathlib import Path

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ConfigDict, Field

from esnext.cli import main, repl
from esnext.manager import StageManager
from esnext.minimal_agent import run_agent
from esnext.models import StageRequest
from esnext.runtime import RuntimeSupervisor


class ScriptedChatModel(BaseChatModel):
    replies: list[str]
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
        raw = self.replies.pop(0)
        trace.last_model_output = raw
        from esnext.minimal_agent import log_step

        log_step(self.log_path, f"step-{step}-model-output", raw)
        if raw.startswith("tool:"):
            cmd = raw.split(":", 1)[1].strip()
            trace.last_action = f"execute: {cmd}"
            log_step(self.log_path, f"step-{step}-tool-call", trace.last_action)
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[{"name": "execute", "args": {"command": cmd}, "id": f"call_{step}", "type": "tool_call"}]))])
        trace.final_output = raw.removeprefix("answer:").strip()
        log_step(self.log_path, f"step-{step}-final-answer", trace.final_output)
        if self.status_cb:
            self.status_cb("completed", f"Step {step}: final answer submitted.")
        log_step(self.log_path, "run-end", f"status: completed\nstep: {step}\nmessage: {trace.final_output}")
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


def patch_scripted_model(monkeypatch, *replies: str) -> None:
    monkeypatch.setattr(
        "esnext.minimal_agent.build_chat_model",
        lambda *, trace, status_cb, log_path, model, max_steps, query_fn=None: ScriptedChatModel(
            replies=list(replies), trace=trace, status_cb=status_cb, log_path=log_path
        ),
    )


def make_agent_manager(monkeypatch, *replies: str) -> StageManager:
    patch_scripted_model(monkeypatch, *replies)
    manager = StageManager(runtime_supervisor=RuntimeSupervisor(executor=None))
    return manager


def test_stage_manager_non_agent_flow_is_not_implemented(tmp_path: Path) -> None:
    manager = StageManager()
    result = manager.handle(StageRequest(target="plain text", output_path=tmp_path / "result.md", workspace_root=tmp_path))
    assert result.status == "failed"
    assert "Only the agent path is implemented" in result.summary


def test_runtime_supervisor_tracks_agent_records(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "agent.md"
    manager = make_agent_manager(monkeypatch, "answer: Done.")
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
    agents = supervisor.list_agents()
    assert len(agents) == 1
    assert agents[0].status == "completed"
    assert agents[0].result is result
    assert agents[0].progress_text == result.summary
    assert any("Agent ID:" in note for note in result.notes)


def test_stage_manager_builds_default_output_path(tmp_path: Path, monkeypatch) -> None:
    manager = make_agent_manager(monkeypatch, "answer: Done.")
    result = manager.handle(StageRequest(target="Try and stop cleanly.", output_path=None, workspace_root=tmp_path, use_agent=True))
    assert result.output_path == tmp_path / "agent-run.md"


def test_cli_run_uses_default_output_path(tmp_path: Path, capsys, monkeypatch) -> None:
    manager = make_agent_manager(monkeypatch, "answer: Done.")
    monkeypatch.setattr("esnext.cli.StageManager", lambda: manager)
    exit_code = main(["run", "Try and stop cleanly.", "--workspace", str(tmp_path), "--agent"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "output:" in captured.out
    assert (tmp_path / "agent-run.md").exists()


def test_repl_runs_until_quit(tmp_path: Path, capsys, monkeypatch) -> None:
    manager = make_agent_manager(monkeypatch, "answer: Done.")
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

    with patch("esnext.minimal_agent.build_chat_model") as build:
        build.side_effect = lambda **kw: ScriptedChatModel(
            replies=["tool: printf 'hello from agent'", "answer: Done."],
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

    with patch("esnext.minimal_agent.build_chat_model") as build:
        build.side_effect = lambda **kw: ScriptedChatModel(
            replies=["tool: pwd", "answer: 当前工作目录是 /tmp/example"],
            trace=kw["trace"],
            status_cb=kw["status_cb"],
            log_path=kw["log_path"],
        )
        result = run_agent("Where am I?", cwd=tmp_path, max_steps=4)
    assert result.status == "completed"
    assert result.final_output == "当前工作目录是 /tmp/example"


def test_stage_manager_agent_goal_flow(tmp_path: Path, monkeypatch) -> None:
    manager = make_agent_manager(monkeypatch, "answer: 您好！", "answer: Done.")
    output = tmp_path / "agent.md"
    result = manager.handle(
        StageRequest(target="Try and stop cleanly.", output_path=output, workspace_root=tmp_path, use_agent=True)
    )
    assert result.status == "completed"
    assert output.exists()
    content = output.read_text(encoding="utf-8")
    assert "Status: `completed`" in content
