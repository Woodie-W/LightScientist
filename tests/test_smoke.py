from __future__ import annotations

from pathlib import Path

from esnext.cli import main
from esnext.manager import StageManager
from esnext.minimal_agent import ActionFormatError, parse_action, run_agent
from esnext.models import StageRequest
from esnext.runtime import RuntimeSupervisor


def test_stage_manager_summarize_file_flow(tmp_path: Path) -> None:
    source = tmp_path / "sample.txt"
    source.write_text("Line one\n\nLine two\nLine three\n", encoding="utf-8")
    output = tmp_path / "summary.md"

    manager = StageManager()
    result = manager.handle(
        StageRequest(
            target=str(source),
            output_path=output,
            workspace_root=tmp_path,
        )
    )

    assert result.status == "completed"
    assert output.exists()
    content = output.read_text(encoding="utf-8")
    assert "# File Summary" in content
    assert "Line one" in content
    assert "Stage:" in content


def test_runtime_supervisor_tracks_agent_records(tmp_path: Path) -> None:
    output = tmp_path / "note.md"
    supervisor = RuntimeSupervisor()
    manager = StageManager(runtime_supervisor=supervisor)
    result = manager.handle(
        StageRequest(
            target="Stage 2 three-layer skeleton is running.",
            output_path=output,
            workspace_root=tmp_path,
        )
    )

    assert result.status == "completed"
    agents = supervisor.list_agents()
    assert len(agents) == 1
    assert agents[0].status == "completed"
    assert agents[0].result is result
    assert agents[0].progress_text == result.summary
    assert any("Agent ID:" in note for note in result.notes)


def test_stage_manager_write_note_flow(tmp_path: Path) -> None:
    output = tmp_path / "note.md"
    manager = StageManager()
    result = manager.handle(
        StageRequest(
            target="Stage 2 three-layer skeleton is running.",
            output_path=output,
            workspace_root=tmp_path,
        )
    )

    assert result.status == "completed"
    assert "Wrote note artifact." in result.summary
    assert output.exists()
    note_content = output.read_text(encoding="utf-8")
    assert "Stage 2 three-layer skeleton is running." in note_content
    assert "local command line only" in note_content


def test_cli_run_inspect_path(tmp_path: Path, capsys) -> None:
    target_dir = tmp_path / "workspace"
    target_dir.mkdir()
    (target_dir / "a.txt").write_text("a", encoding="utf-8")
    (target_dir / "b.txt").write_text("b", encoding="utf-8")
    output = tmp_path / "inspect.md"

    exit_code = main(
        [
            "run",
            str(target_dir),
            "--output",
            str(output),
            "--workspace",
            str(tmp_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "status: completed" in captured.out
    assert output.exists()
    assert "`a.txt`" in output.read_text(encoding="utf-8")


def test_parse_action_rejects_malformed_output() -> None:
    try:
        parse_action("no action here")
    except ActionFormatError as e:
        assert "malformatted" in str(e)
    else:
        raise AssertionError("ActionFormatError was not raised")


def test_minimal_agent_run_handles_command_and_exit(tmp_path: Path) -> None:
    replies = iter([
        "```bash-action\nprintf 'hello from agent'\n```",
        "```bash-action\nexit\n```",
    ])
    result = run_agent("Say hello", cwd=tmp_path, query_fn=lambda _: next(replies), max_steps=4)
    assert result.status == "terminated"
    assert result.step_count == 2
    assert "hello from agent" in "".join(result.command_outputs)


def test_stage_manager_agent_goal_flow(tmp_path: Path) -> None:
    replies = iter(["bad output", "```bash-action\nexit\n```"])
    manager = StageManager(runtime_supervisor=RuntimeSupervisor(executor=None))
    manager.runtime_supervisor.executor.agent_query_fn = lambda _: next(replies)
    output = tmp_path / "agent.md"
    result = manager.handle(
        StageRequest(target="Try and stop cleanly.", output_path=output, workspace_root=tmp_path, use_agent=True)
    )
    assert result.status == "completed"
    assert output.exists()
    content = output.read_text(encoding="utf-8")
    assert "Status: `completed`" in content
