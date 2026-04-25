from __future__ import annotations

import json, threading
import time
from collections import deque
from pathlib import Path

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ConfigDict, Field

from esnext.backends import CommandProcessRegistry, WorkspaceBackend
from esnext.cli import main, repl
from esnext.executor import ExecutionRuntime
from esnext.manager import StageManager
from esnext.minimal_agent import _status_from_output, resume_agent_session, run_agent, start_agent_session
from esnext.data_models import RuntimeTask, RuntimeUpdate, StageRequest, SupervisorEvent
from esnext.research_controller import ResearchController
from esnext.research_stages import STAGES, stage_spec
from esnext.runtime import RuntimeSupervisor
from esnext.runtime import supervisor_event_input
from esnext.prompts import load_prompt


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
        trace.action_count += 1
        step = trace.step_count
        trace.messages = [m for msg in messages if (m := self._to_msg(msg))]
        if self.status_cb:
            self.status_cb(RuntimeUpdate("running", f"Step {step}: querying model.", trace.progress.snapshot()))
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
            if name == "suspend_background":
                trace.last_action = f"suspend_background: {arg}"
                log_step(self.log_path, f"step-{step}-tool-call", trace.last_action)
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[{"name": "suspend_background", "args": {"note": arg}, "id": f"call_{step}", "type": "tool_call"}]))])
            if name == "finish_cancelled":
                trace.last_action = f"finish_cancelled: {arg}"
                log_step(self.log_path, f"step-{step}-tool-call", trace.last_action)
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[{"name": "finish_cancelled", "args": {"summary": arg}, "id": f"call_{step}", "type": "tool_call"}]))])
            if name == "finish_stage":
                status, summary, output, next_stage = (arg.split("|") + ["", "", "", ""])[:4]
                trace.last_action = f"finish_stage: {status}"
                log_step(self.log_path, f"step-{step}-tool-call", trace.last_action)
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[{"name": "finish_stage", "args": {"status": status, "summary": summary, "output_path": output, "next_stage": next_stage}, "id": f"call_{step}", "type": "tool_call"}]))])
            if name == "request_user_decision":
                question, options = (arg.split("|") + ["", ""])[:2]
                trace.last_action = f"request_user_decision: {question}"
                log_step(self.log_path, f"step-{step}-tool-call", trace.last_action)
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[{"name": "request_user_decision", "args": {"question": question, "options": options}, "id": f"call_{step}", "type": "tool_call"}]))])
            cmd = spec if not sep else arg
            trace.last_action = f"execute: {cmd}"
            log_step(self.log_path, f"step-{step}-tool-call", trace.last_action)
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[{"name": "execute", "args": {"command": cmd}, "id": f"call_{step}", "type": "tool_call"}]))])
        trace.status, trace.final_output = _status_from_output(raw.removeprefix("answer:").strip())
        log_step(self.log_path, f"step-{step}-final-answer", trace.final_output)
        if self.status_cb:
            self.status_cb(RuntimeUpdate(trace.status, f"Step {step}: {trace.final_output or trace.status}.", trace.progress.snapshot()))
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
    assert supervisor._results[agents[0].agent_id] is result
    assert agents[0].progress_text == result.summary
    assert any("Agent ID:" in note for note in result.notes)


def test_stage_manager_builds_default_output_path(tmp_path: Path, monkeypatch) -> None:
    manager = make_agent_manager(monkeypatch, tmp_path, "answer: Done.")
    result = manager.handle(StageRequest(target="Try and stop cleanly.", output_path=None, workspace_root=tmp_path, use_agent=True))
    assert result.output_path.name == "agent-run.md"
    assert result.output_path.parent.name.startswith("agent-")


def test_research_controller_builds_stage_prompt(tmp_path: Path) -> None:
    controller = ResearchController(tmp_path, topic="seed scheduling", mode="auto")
    prompt = controller.build_stage_prompt()
    assert "Current stage: idea.survey" in prompt
    assert f"Skill to read first: {stage_spec('idea.survey').skill_path}" in prompt
    assert "phase1-idea/LITERATURE_SURVEY.md" in prompt
    assert "idea -> experiment -> paper -> done" in prompt


def test_research_controller_can_start_from_selected_stage(tmp_path: Path) -> None:
    controller = ResearchController(tmp_path, topic="reproduce paper X", mode="auto", start_stage="experiment.setup")
    prompt = controller.build_stage_prompt()
    state = json.loads((tmp_path / ".lightscientist/project_state.json").read_text(encoding="utf-8"))
    assert state["phase"] == "experiment"
    assert state["stage"] == "experiment.setup"
    assert "Project topic:\nreproduce paper X" in prompt
    assert f"Skill to read first: {stage_spec('experiment.setup').skill_path}" in prompt


def test_all_configured_stage_skills_exist() -> None:
    for spec in STAGES.values():
        if spec.skill_path:
            assert Path(spec.skill_path).exists(), spec.skill_path


def test_copied_skill_dependencies_exist() -> None:
    root = Path("/data/auto-research/LightScientist")
    for rel in (
        "tools/arxiv_search.py",
        "tools/coverage.py",
        "tools/crash.py",
        "templates/fuzz_experiment.sh.tmpl",
    ):
        assert (root / rel).exists(), rel


def test_research_controller_runs_one_stage_and_advances(tmp_path: Path, monkeypatch) -> None:
    patch_scripted_model(
        monkeypatch,
        "tool: mkdir -p phase1-idea && printf 'survey' > phase1-idea/LITERATURE_SURVEY.md",
        "answer: Done.",
        scope_root=tmp_path,
    )
    result = ResearchController(tmp_path, topic="seed scheduling", mode="auto").run_once()
    state = json.loads((tmp_path / ".lightscientist/project_state.json").read_text(encoding="utf-8"))
    events = (tmp_path / ".lightscientist/events.jsonl").read_text(encoding="utf-8")
    assert result.status == "completed"
    assert result.output_path == tmp_path / "phase1-idea/LITERATURE_SURVEY.md"
    assert state["stage"] == "idea.generate"
    assert "stage_transition" in events


def test_research_controller_accepts_allowed_next_stage(tmp_path: Path, monkeypatch) -> None:
    patch_scripted_model(
        monkeypatch,
        "tool: mkdir -p phase1-idea && printf 'survey' > phase1-idea/LITERATURE_SURVEY.md",
        "answer: Done.",
        supervisor_replies=("answer: TASK_COMPLETED: survey done\nNEXT_STAGE: idea.evaluate",),
        scope_root=tmp_path,
    )
    result = ResearchController(tmp_path, topic="seed scheduling", mode="auto").run_once()
    state = json.loads((tmp_path / ".lightscientist/project_state.json").read_text(encoding="utf-8"))
    events = (tmp_path / ".lightscientist/events.jsonl").read_text(encoding="utf-8")
    assert result.status == "completed"
    assert state["stage"] == "idea.evaluate"
    assert "next_stage_accepted" in events


def test_research_controller_accepts_finish_stage_tool_next_stage(tmp_path: Path, monkeypatch) -> None:
    patch_scripted_model(
        monkeypatch,
        "tool: mkdir -p phase1-idea && printf 'survey' > phase1-idea/LITERATURE_SURVEY.md",
        "answer: Done.",
        supervisor_replies=("tool: finish_stage|completed|survey done|phase1-idea/LITERATURE_SURVEY.md|idea.evaluate",),
        scope_root=tmp_path,
    )
    result = ResearchController(tmp_path, topic="seed scheduling", mode="auto").run_once()
    state = json.loads((tmp_path / ".lightscientist/project_state.json").read_text(encoding="utf-8"))
    artifacts = json.loads((tmp_path / ".lightscientist/artifacts.json").read_text(encoding="utf-8"))
    assert result.status == "completed"
    assert result.summary == "survey done"
    assert state["stage"] == "idea.evaluate"
    assert artifacts["idea.survey"][0]["path"] == "phase1-idea/LITERATURE_SURVEY.md"
    assert artifacts["idea.survey"][0]["summary"] == "survey done"


def test_research_controller_surfaces_manual_user_decision_request(tmp_path: Path, monkeypatch) -> None:
    patch_scripted_model(
        monkeypatch,
        "tool: mkdir -p phase1-idea && printf 'survey' > phase1-idea/LITERATURE_SURVEY.md",
        "answer: Done.",
        supervisor_replies=("tool: request_user_decision|是否进入实验阶段？|yes/no",),
        scope_root=tmp_path,
    )
    result = ResearchController(tmp_path, topic="seed scheduling", mode="manual").run_once()
    state = json.loads((tmp_path / ".lightscientist/project_state.json").read_text(encoding="utf-8"))
    assert result.status == "waiting"
    assert "是否进入实验阶段" in result.summary
    assert state["status"] == "waiting_user"


def test_research_controller_rejects_invalid_next_stage(tmp_path: Path, monkeypatch) -> None:
    patch_scripted_model(
        monkeypatch,
        "tool: mkdir -p phase1-idea && printf 'survey' > phase1-idea/LITERATURE_SURVEY.md",
        "answer: Done.",
        supervisor_replies=("answer: TASK_COMPLETED: survey done\nNEXT_STAGE: paper.write",),
        scope_root=tmp_path,
    )
    ResearchController(tmp_path, topic="seed scheduling", mode="auto").run_once()
    state = json.loads((tmp_path / ".lightscientist/project_state.json").read_text(encoding="utf-8"))
    events = (tmp_path / ".lightscientist/events.jsonl").read_text(encoding="utf-8")
    assert state["stage"] == "idea.generate"
    assert "next_stage_rejected" in events


def test_cli_research_can_select_start_stage(tmp_path: Path, monkeypatch) -> None:
    patch_scripted_model(
        monkeypatch,
        "tool: mkdir -p phase2-experiment && printf 'setup' > phase2-experiment/SETUP_COMPLETE.md",
        "answer: Done.",
        scope_root=tmp_path,
    )
    exit_code = main(["research", "reproduce paper X", "--workspace", str(tmp_path), "--mode", "auto", "--stage", "experiment.setup"])
    state = json.loads((tmp_path / ".lightscientist/project_state.json").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert state["stage"] == "experiment.loop"


def test_cli_run_uses_default_output_path(tmp_path: Path, capsys, monkeypatch) -> None:
    manager = make_agent_manager(monkeypatch, tmp_path, "answer: Done.")
    monkeypatch.setattr("esnext.cli.StageManager", lambda: manager)
    exit_code = main(["run", "Try and stop cleanly.", "--workspace", str(tmp_path), "--agent"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "output:" in captured.out
    assert any(tmp_path.glob("agent-*/agent-run.md"))


def test_repl_runs_until_quit(tmp_path: Path, capsys, monkeypatch) -> None:
    manager = make_agent_manager(monkeypatch, tmp_path, "answer: Done.")
    inputs = iter(["Try and stop cleanly.", "quit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))
    exit_code = repl(manager=manager, workspace=tmp_path)
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "LightScientist REPL" in captured.out
    assert "status: completed" in captured.out
    assert any(tmp_path.glob("agent-*/agent-run.md"))


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
    assert result.action_count == 3
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
    assert supervisor._agents[agent_id].workspace_root == tmp_path / agent_id
    assert supervisor._agents[agent_id].output_path == tmp_path / agent_id / "agent-run.md"


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
    assert result.output_path.parent.name == agent.agent_id
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
    patch_scripted_model(monkeypatch, "tool: suspend_background|实验已启动。", "", "answer: 实验已完成。")
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
    assert first.output_path == tmp_path / agent.agent_id / "agent-run.md"


def test_stage_manager_agent_goal_flow(tmp_path: Path, monkeypatch) -> None:
    manager = make_agent_manager(monkeypatch, tmp_path, "answer: 您好！", "answer: Done.")
    output = tmp_path / "agent.md"
    result = manager.handle(
        StageRequest(target="Try and stop cleanly.", output_path=output, workspace_root=tmp_path, use_agent=True)
    )
    assert result.status == "completed"
    assert result.output_path.exists()
    assert result.output_path.parent.name.startswith("agent-")
    content = result.output_path.read_text(encoding="utf-8")
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


def test_runtime_supervisor_does_not_expose_worker_lifecycle_tools_to_supervisor(tmp_path: Path, monkeypatch) -> None:
    patch_scripted_model(monkeypatch, "answer: Done.", supervisor_replies=("answer: TASK_CONTINUE: checked.",), scope_root=tmp_path)
    supervisor = RuntimeSupervisor()
    supervisor.start(
        RuntimeTask("toolvis", "interactive", "Finish the task", tmp_path / "agent.md", tmp_path, "Finish the task", True)
    )
    deadline = time.time() + 3
    while time.time() < deadline and supervisor._supervisor is None:
        time.sleep(0.05)
    session = supervisor._supervisor
    assert session is not None
    tool_names = {tool.name for tool in session.tools}
    assert "start_worker" in tool_names
    assert "ask_input" not in tool_names
    assert "suspend_background" not in tool_names
    assert "finish_cancelled" not in tool_names
    assert not session.include_lifecycle_tools


def test_research_controller_exposes_artifact_listing_tool(tmp_path: Path) -> None:
    controller = ResearchController(tmp_path, topic="seed scheduling", mode="auto")
    out = tmp_path / "phase1-idea/LITERATURE_SURVEY.md"
    out.parent.mkdir(parents=True)
    out.write_text("survey", encoding="utf-8")
    controller._record_artifact("idea.survey", out, "survey summary")
    tools = {tool.name: tool for tool in controller._stage_tools()}
    raw = tools["list_artifacts"].invoke({"stage": ""})
    records = json.loads(raw)
    assert records[0]["stage"] == "idea.survey"
    assert records[0]["path"] == "phase1-idea/LITERATURE_SURVEY.md"
    assert records[0]["summary"] == "survey summary"


def test_runtime_supervisor_can_cancel_worker(tmp_path: Path, monkeypatch) -> None:
    patch_scripted_model(monkeypatch, "tool: suspend_background|实验已启动。", "", "tool: finish_cancelled|已整理取消交付。", "", scope_root=tmp_path)
    supervisor = RuntimeSupervisor()
    supervisor.start(
        RuntimeTask("taskcancelw", "interactive", "Run experiment", tmp_path / "agent.md", tmp_path, "Run experiment", True)
    )
    agent = next(iter(supervisor._agents.values()))
    cancelled = supervisor.cancel_worker(agent.agent_id)
    assert cancelled.status == "cancelled"
    assert cancelled.summary == "已整理取消交付。"
    assert cancelled.output_path.exists()
    assert supervisor._results[agent.agent_id] is cancelled
    assert supervisor._agents[agent.agent_id].status == "cancelled"
    assert supervisor.executor.get_session(agent.agent_id) is None
    resumed = supervisor.resume(agent.agent_id, "继续")
    assert resumed.status == "cancelled"


def test_executor_cancel_times_out_and_returns_cancelled(tmp_path: Path, monkeypatch) -> None:
    patch_scripted_model(monkeypatch, "tool: suspend_background|实验已启动。", "", scope_root=tmp_path)
    executor = ExecutionRuntime(cancel_timeout=0.01)
    result = executor.start(
        "agent-timeout",
        RuntimeTask("timeout", "interactive", "Run experiment", tmp_path / "agent-run.md", tmp_path, "Run experiment", True),
    )
    assert result.status == "background"
    monkeypatch.setattr("esnext.executor.resume_agent_session", lambda *_, **__: time.sleep(1))
    cancelled = executor.cancel("agent-timeout")
    assert cancelled.status == "cancelled"
    assert "timed out" in cancelled.summary
    assert executor.get_session("agent-timeout") is None


def test_runtime_supervisor_does_not_forward_running_progress(tmp_path: Path) -> None:
    from esnext.data_models import AgentProgress, AgentRecord

    supervisor = RuntimeSupervisor()
    agent_id = "agent-progress"
    supervisor._agents[agent_id] = AgentRecord(agent_id, "progress", "objective", "running")
    supervisor._handle_update(agent_id, RuntimeUpdate("running", "Step 1", AgentProgress(1, 2, 3.0)))
    assert supervisor._agents[agent_id].progress.step_count == 1
    assert supervisor._agents[agent_id].progress.action_count == 2
    assert not supervisor._supervisor_queue


def test_runtime_supervisor_reports_stall_once_and_clears_on_progress(tmp_path: Path) -> None:
    from esnext.data_models import AgentProgress, AgentRecord

    supervisor = RuntimeSupervisor(stall_timeout=0.01)
    agent_id = "agent-stall"
    old_progress = AgentProgress(step_count=1, action_count=2, last_activity_at=time.monotonic() - 1)
    supervisor._agents[agent_id] = AgentRecord(agent_id, "stall", "objective", "running", progress=old_progress)
    with supervisor._queue_ready:
        supervisor._check_worker_stalls_locked()
        supervisor._check_worker_stalls_locked()
        assert supervisor._agents[agent_id].stall_reported
        assert len(supervisor._supervisor_queue) == 1
        supervisor._agents[agent_id].progress = AgentProgress(step_count=1, action_count=3)
        supervisor._check_worker_stalls_locked()
        assert not supervisor._agents[agent_id].stall_reported
        assert len(supervisor._supervisor_queue) == 1


def test_runtime_supervisor_does_not_stall_blocked_workers(tmp_path: Path) -> None:
    from esnext.data_models import AgentProgress, AgentRecord

    supervisor = RuntimeSupervisor(stall_timeout=0.01)
    old_progress = AgentProgress(step_count=1, action_count=2, last_activity_at=time.monotonic() - 1)
    supervisor._agents["agent-waiting"] = AgentRecord("agent-waiting", "waiting", "objective", "waiting", progress=old_progress)
    supervisor._agents["agent-background"] = AgentRecord("agent-background", "background", "objective", "background", progress=old_progress)
    with supervisor._queue_ready:
        supervisor._check_worker_stalls_locked()
        assert not supervisor._agents["agent-waiting"].stall_reported
        assert not supervisor._agents["agent-background"].stall_reported
        assert not supervisor._supervisor_queue


def test_runtime_supervisor_schedules_worker_resume(tmp_path: Path, monkeypatch) -> None:
    from esnext.data_models import AgentRecord

    calls = []
    supervisor = RuntimeSupervisor()
    agent_id = "agent-background"
    supervisor._agents[agent_id] = AgentRecord(agent_id, "background", "objective", "background")
    monkeypatch.setattr(supervisor, "_run", lambda mode, aid, arg: calls.append((mode, aid, arg)))
    assert "scheduled" in supervisor._schedule_worker_resume(agent_id, 0, "请检查实验是否有进展。")
    with supervisor._queue_ready:
        supervisor._resume_due_workers_locked()
        assert len(supervisor._scheduled_resumes) == 0
    deadline = time.time() + 1
    while time.time() < deadline and not calls:
        time.sleep(0.01)
    assert calls == [("resume", agent_id, "请检查实验是否有进展。")]


def test_workspace_backend_can_kill_running_execute(tmp_path: Path) -> None:
    registry = CommandProcessRegistry()
    backend = WorkspaceBackend(root_dir=tmp_path, process_registry=registry, timeout=30)
    result_box = {}
    thread = threading.Thread(target=lambda: result_box.setdefault("result", backend.execute("sleep 30")), daemon=True)
    thread.start()
    deadline = time.time() + 2
    while time.time() < deadline and registry.running_count() == 0:
        time.sleep(0.01)
    assert registry.running_count() == 1
    assert registry.kill_all(grace_seconds=0.1) == 1
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert result_box["result"].exit_code != 0


def test_runtime_supervisor_tools_dispatch_workers_without_waiting(tmp_path: Path, monkeypatch) -> None:
    supervisor = RuntimeSupervisor()
    supervisor._task = {"task_id": "taskasync", "objective": "objective", "worker_ids": [], "status": "running", "summary": ""}
    supervisor._workspace_root = tmp_path
    monkeypatch.setattr(supervisor, "_run", lambda mode, agent_id, arg: time.sleep(0.5))
    tools = {tool.name: tool for tool in supervisor._runtime_tools()}
    started = time.monotonic()
    raw = tools["start_worker"].invoke({"objective": "do work"})
    assert time.monotonic() - started < 0.2
    result = json.loads(raw)
    assert result["status"] == "accepted"
    assert result["agent_id"] in supervisor._agents


def test_supervisor_prompt_adds_status_specific_guidance() -> None:
    assert "intentional suspension" in supervisor_event_input("task", SupervisorEvent("a", "background"))
    assert "schedule_worker_resume" in supervisor_event_input("task", SupervisorEvent("a", "background"))
    assert "missing input" in supervisor_event_input("task", SupervisorEvent("a", "waiting"))
    assert "not shown progress" in supervisor_event_input("task", SupervisorEvent("a", "running", "Worker stalled.", kind="stall"))
    assert "Output: /tmp/out.md" in SupervisorEvent("a", "completed", output_path=Path("/tmp/out.md")).to_prompt_text()
    assert "second-layer supervisor" in load_prompt("supervisor")
    assert "ask_input" in load_prompt("worker")
