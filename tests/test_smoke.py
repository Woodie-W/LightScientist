from __future__ import annotations

from pathlib import Path

from esnext.cli import main, repl
from esnext.manager import StageManager
from esnext.minimal_agent import run_agent
from esnext.models import StageRequest
from esnext.runtime import RuntimeSupervisor


def make_agent_manager(*replies: str) -> StageManager:
    manager = StageManager(runtime_supervisor=RuntimeSupervisor(executor=None))
    it = iter(replies)
    manager.runtime_supervisor.executor.agent_query_fn = lambda _: next(it)
    return manager


def test_stage_manager_non_agent_flow_is_not_implemented(tmp_path: Path) -> None:
    manager = StageManager()
    result = manager.handle(StageRequest(target="plain text", output_path=tmp_path / "result.md", workspace_root=tmp_path))
    assert result.status == "failed"
    assert "Only the agent path is implemented" in result.summary


def test_runtime_supervisor_tracks_agent_records(tmp_path: Path) -> None:
    output = tmp_path / "agent.md"
    manager = make_agent_manager("answer: Done.")
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


def test_stage_manager_builds_default_output_path(tmp_path: Path) -> None:
    manager = make_agent_manager("answer: Done.")
    result = manager.handle(StageRequest(target="Try and stop cleanly.", output_path=None, workspace_root=tmp_path, use_agent=True))
    assert result.output_path == tmp_path / "agent-run.md"


def test_cli_run_uses_default_output_path(tmp_path: Path, capsys, monkeypatch) -> None:
    manager = make_agent_manager("answer: Done.")
    monkeypatch.setattr("esnext.cli.StageManager", lambda: manager)
    exit_code = main(["run", "Try and stop cleanly.", "--workspace", str(tmp_path), "--agent"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "output:" in captured.out
    assert (tmp_path / "agent-run.md").exists()


def test_repl_runs_until_quit(tmp_path: Path, capsys, monkeypatch) -> None:
    manager = make_agent_manager("answer: Done.")
    inputs = iter(["Try and stop cleanly.", "quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    exit_code = repl(manager=manager, workspace=tmp_path)
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "LightScientist REPL" in captured.out
    assert "status: completed" in captured.out
    assert (tmp_path / "agent-run.md").exists()


def test_minimal_agent_run_handles_command_and_final_answer(tmp_path: Path) -> None:
    replies = iter([
        "tool: printf 'hello from agent'",
        "answer: Done.",
    ])
    result = run_agent("Say hello", cwd=tmp_path, query_fn=lambda _: next(replies), max_steps=4)
    assert result.status == "completed"
    assert result.step_count == 2
    assert "hello from agent" in "".join(result.command_outputs)
    log_text = (tmp_path / "agent-debug.log").read_text(encoding="utf-8")
    assert "[step-1-model-output]" in log_text
    assert "execute: printf 'hello from agent'" in log_text
    assert "[run-end]" in log_text


def test_minimal_agent_run_handles_final_answer(tmp_path: Path) -> None:
    replies = iter([
        "tool: pwd",
        "answer: 当前工作目录是 /tmp/example",
    ])
    result = run_agent("Where am I?", cwd=tmp_path, query_fn=lambda _: next(replies), max_steps=4)
    assert result.status == "completed"
    assert result.final_output == "当前工作目录是 /tmp/example"


def test_stage_manager_agent_goal_flow(tmp_path: Path) -> None:
    manager = make_agent_manager("answer: 您好！", "answer: Done.")
    output = tmp_path / "agent.md"
    result = manager.handle(
        StageRequest(target="Try and stop cleanly.", output_path=output, workspace_root=tmp_path, use_agent=True)
    )
    assert result.status == "completed"
    assert output.exists()
    content = output.read_text(encoding="utf-8")
    assert "Status: `completed`" in content
