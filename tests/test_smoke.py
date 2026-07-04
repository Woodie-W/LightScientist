from __future__ import annotations

import json, threading
import importlib
import time
from collections import deque
from pathlib import Path

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ConfigDict, Field

from esnext.backends import CommandProcessRegistry, WorkspaceBackend
from esnext.cli import main, repl
from esnext.events import ConsoleEventSink, EventBus, JsonlEventSink
from esnext.executor import ExecutionRuntime
from esnext.manager import StageManager
from esnext.minimal_agent import _recursion_limit, _status_from_output, resume_agent_session, run_agent, start_agent_session
from esnext.data_models import RuntimeTask, RuntimeUpdate, StageRequest, SupervisorEvent
from esnext.research_controller import ResearchController
from esnext.research_stages import STAGES, stage_spec
from esnext.runtime import RuntimeSupervisor
from esnext.runtime import supervisor_event_input
from esnext.prompts import load_prompt
from esnext.webui_data import build_overview, safe_read_workspace_file


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
    assert "Skill to read first: .lightscientist/skills/idea.survey.md" in prompt
    assert (tmp_path / ".lightscientist/skills/idea.survey.md").exists()
    assert "Read `PROCESS.md` first" in prompt
    assert "phase1-idea/LITERATURE_SURVEY.md" in prompt
    assert "idea -> experiment -> paper -> done" in prompt


def test_research_controller_builds_prompt_with_user_feedback(tmp_path: Path) -> None:
    controller = ResearchController(tmp_path, topic="seed scheduling", mode="auto")
    controller.state.user_feedback = "focus on libpng first"
    prompt = controller.build_stage_prompt()
    assert "Latest user feedback:" in prompt
    assert "focus on libpng first" in prompt


def test_research_controller_can_start_from_selected_stage(tmp_path: Path) -> None:
    controller = ResearchController(tmp_path, topic="reproduce paper X", mode="auto", start_stage="experiment.setup")
    prompt = controller.build_stage_prompt()
    state = json.loads((tmp_path / ".lightscientist/project_state.json").read_text(encoding="utf-8"))
    assert state["phase"] == "experiment"
    assert state["stage"] == "experiment.setup"
    assert "Project topic:\nreproduce paper X" in prompt
    assert "Skill to read first: .lightscientist/skills/experiment.setup.md" in prompt


def test_research_controller_builds_experiment_prompt_with_phase2_state(tmp_path: Path) -> None:
    (tmp_path / "phase2-experiment").mkdir()
    (tmp_path / "research.md").write_text("goal", encoding="utf-8")
    (tmp_path / "phase2-experiment/worklog.md").write_text("worklog", encoding="utf-8")
    (tmp_path / "research.jsonl").write_text(
        '{"type":"config","metrics":{"primary":{"name":"score"}}}\n'
        '{"run":1,"status":"keep","description":"baseline","results":{"score":{"mean":64}}}\n',
        encoding="utf-8",
    )
    controller = ResearchController(tmp_path, topic="reproduce paper X", mode="auto", start_stage="experiment.loop")
    prompt = controller.build_stage_prompt()
    assert "Phase 2 state:" in prompt
    assert "- research.jsonl: present" in prompt
    assert "- runs: 1" in prompt
    assert "- statuses: keep: 1" in prompt
    assert "- primary metric: score" in prompt


def test_all_configured_stage_skills_exist() -> None:
    for spec in STAGES.values():
        if spec.skill_path:
            assert Path(spec.skill_path).exists(), spec.skill_path


def test_copied_skill_dependencies_exist() -> None:
    root = Path("/data/auto-research/LightScientist")
    for rel in (
        "tools/arxiv_search.py",
        "skills/experiment-setup/SKILL.md",
        "skills/experiment-loop/SKILL.md",
        "skills/experiment-analyze/SKILL.md",
    ):
        assert (root / rel).exists(), rel


def test_workspace_backend_rejects_absolute_read_path(tmp_path: Path) -> None:
    backend = WorkspaceBackend(root_dir=tmp_path)
    result = backend.read("/data/moew/CORAL/examples/meow/task.yaml")
    assert result.error is not None
    assert "Absolute paths are not allowed" in result.error


def test_workspace_backend_keeps_relative_write_in_workspace(tmp_path: Path) -> None:
    backend = WorkspaceBackend(root_dir=tmp_path)
    result = backend.write("inside.txt", "ok")
    assert result.error is None
    assert (tmp_path / "inside.txt").read_text(encoding="utf-8") == "ok"


def test_workspace_backend_rejects_absolute_write_path(tmp_path: Path) -> None:
    backend = WorkspaceBackend(root_dir=tmp_path)
    result = backend.write("/data/moew/phase3-paper/PAPER_PLAN.md", "bad")
    assert result.error is not None
    assert "Absolute write paths are not allowed" in result.error


def test_workspace_backend_rejects_absolute_edit_path(tmp_path: Path) -> None:
    backend = WorkspaceBackend(root_dir=tmp_path)
    result = backend.edit("/data/moew/phase3-paper/PAPER_PLAN.md", "a", "b")
    assert result.error is not None
    assert "Absolute edit paths are not allowed" in result.error


def test_workspace_backend_allows_relative_read_via_workspace_symlink(tmp_path: Path) -> None:
    source = tmp_path / "source_task"
    target = tmp_path / "target"
    target.mkdir()
    (target / "task.yaml").write_text("task: ok\n", encoding="utf-8")
    source.symlink_to(target, target_is_directory=True)
    backend = WorkspaceBackend(root_dir=tmp_path)
    result = backend.read("source_task/task.yaml")
    assert result.error is None
    assert result.file_data
    assert "task: ok" in result.file_data["content"]


def test_model_config_defaults_to_deepseek(monkeypatch) -> None:
    monkeypatch.delenv("LIGHTSCIENTIST_BASE_URL", raising=False)
    monkeypatch.delenv("LIGHTSCIENTIST_MODEL", raising=False)
    monkeypatch.delenv("LIGHTSCIENTIST_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    import esnext.model_config as model_config

    cfg = importlib.reload(model_config)
    assert cfg.BASE_URL == "https://api.deepseek.com"
    assert cfg.MODEL == "deepseek-v4-pro"
    assert cfg.API_KEY == "test-key"
    assert cfg.chat_provider_options()["reasoning_effort"] == "high"


def test_model_config_does_not_send_deepseek_options_to_other_endpoints(monkeypatch) -> None:
    monkeypatch.setenv("LIGHTSCIENTIST_BASE_URL", "http://localhost:1234/v1")
    monkeypatch.setenv("LIGHTSCIENTIST_MODEL", "local-model")
    monkeypatch.setenv("LIGHTSCIENTIST_API_KEY", "local-key")
    import esnext.model_config as model_config

    cfg = importlib.reload(model_config)
    assert cfg.BASE_URL == "http://localhost:1234/v1"
    assert cfg.MODEL == "local-model"
    assert cfg.API_KEY == "local-key"
    assert cfg.chat_provider_options() == {}


def test_default_max_steps_is_unlimited(monkeypatch) -> None:
    monkeypatch.delenv("LIGHTSCIENTIST_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    import esnext.model_config as model_config

    cfg = importlib.reload(model_config)
    assert cfg.LoggingChatOpenAI.model_fields["max_steps"].default == 0
    assert _recursion_limit(0) == 10_000


def test_model_config_deepseek_adapter_patches_reasoning_into_request(monkeypatch) -> None:
    monkeypatch.delenv("LIGHTSCIENTIST_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.setenv("DEEPSEEK_THINKING", "enabled")
    import esnext.model_config as model_config

    cfg = importlib.reload(model_config)
    adapter = cfg.provider_adapter()
    payload = [{"role": "assistant", "content": "", "tool_calls": [{"id": "1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}]}]
    source = [AIMessage(content="", tool_calls=[{"name": "read_file", "args": {}, "id": "1", "type": "tool_call"}], additional_kwargs={"reasoning_content": "think-1"})]
    patched = adapter.patch_request_messages(payload, source)
    assert patched[0]["reasoning_content"] == "think-1"


def test_model_config_deepseek_adapter_extracts_reasoning_from_response(monkeypatch) -> None:
    monkeypatch.delenv("LIGHTSCIENTIST_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.setenv("DEEPSEEK_THINKING", "enabled")
    import esnext.model_config as model_config

    cfg = importlib.reload(model_config)
    adapter = cfg.provider_adapter()
    result = ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[]))])
    patched = adapter.patch_chat_result(result, {"choices": [{"message": {"role": "assistant", "content": "", "reasoning_content": "think-2"}}]})
    assert patched.generations[0].message.additional_kwargs["reasoning_content"] == "think-2"


def test_model_config_deepseek_adapter_uses_pending_reasoning_fallback(monkeypatch) -> None:
    monkeypatch.delenv("LIGHTSCIENTIST_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.setenv("DEEPSEEK_THINKING", "enabled")
    import esnext.model_config as model_config

    cfg = importlib.reload(model_config)
    adapter = cfg.provider_adapter()
    payload = [{"role": "assistant", "content": None, "tool_calls": [{"id": "1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}]}]
    patched = adapter.patch_request_messages(payload, [AIMessage(content="", tool_calls=[])], "think-3")
    assert patched[0]["reasoning_content"] == "think-3"


def test_research_controller_runs_one_stage_and_advances(tmp_path: Path, monkeypatch) -> None:
    patch_scripted_model(
        monkeypatch,
        "tool: mkdir -p phase1-idea && printf 'survey' > phase1-idea/LITERATURE_SURVEY.md",
        "answer: Done.",
        scope_root=tmp_path,
    )
    result = ResearchController(tmp_path, topic="seed scheduling", mode="auto")._run_stage()
    state = json.loads((tmp_path / ".lightscientist/project_state.json").read_text(encoding="utf-8"))
    events = (tmp_path / ".lightscientist/events.jsonl").read_text(encoding="utf-8")
    process = (tmp_path / "PROCESS.md").read_text(encoding="utf-8")
    assert result.status == "completed"
    assert result.output_path == tmp_path / "phase1-idea/LITERATURE_SURVEY.md"
    assert state["stage"] == "idea.generate"
    assert "stage_transition" in events
    assert "## idea.survey" in process
    assert "- Workspace: phase1-idea/" in process
    assert "- Main output: phase1-idea/LITERATURE_SURVEY.md" in process


def test_research_controller_accepts_allowed_next_stage(tmp_path: Path, monkeypatch) -> None:
    patch_scripted_model(
        monkeypatch,
        "tool: mkdir -p phase1-idea && printf 'survey' > phase1-idea/LITERATURE_SURVEY.md",
        "answer: Done.",
        supervisor_replies=("answer: TASK_COMPLETED: survey done\nNEXT_STAGE: idea.evaluate",),
        scope_root=tmp_path,
    )
    result = ResearchController(tmp_path, topic="seed scheduling", mode="auto")._run_stage()
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
    result = ResearchController(tmp_path, topic="seed scheduling", mode="auto")._run_stage()
    state = json.loads((tmp_path / ".lightscientist/project_state.json").read_text(encoding="utf-8"))
    assert result.status == "completed"
    assert result.summary == "survey done"
    assert state["stage"] == "idea.evaluate"
    assert state["output_path"] == str(tmp_path / "phase1-idea/LITERATURE_SURVEY.md")


def test_research_controller_surfaces_manual_user_decision_request(tmp_path: Path, monkeypatch) -> None:
    patch_scripted_model(
        monkeypatch,
        "tool: mkdir -p phase1-idea && printf 'survey' > phase1-idea/LITERATURE_SURVEY.md",
        "answer: Done.",
        supervisor_replies=("tool: request_user_decision|是否进入实验阶段？|yes/no",),
        scope_root=tmp_path,
    )
    result = ResearchController(tmp_path, topic="seed scheduling", mode="manual")._run_stage()
    state = json.loads((tmp_path / ".lightscientist/project_state.json").read_text(encoding="utf-8"))
    assert result.status == "waiting"
    assert "是否进入实验阶段" in result.summary
    assert state["status"] == "waiting_user"


def test_research_controller_reply_yes_transitions_and_runs_next_stage(tmp_path: Path, monkeypatch) -> None:
    patch_scripted_model(
        monkeypatch,
        "tool: mkdir -p phase2-experiment && printf 'setup' > phase2-experiment/SETUP_COMPLETE.md",
        "answer: Done.",
        "tool: mkdir -p phase2-experiment && printf '{\"type\":\"config\",\"metrics\":{\"primary\":{\"name\":\"score\"}}}\\n{\"run\":1,\"status\":\"keep\",\"description\":\"baseline\",\"results\":{\"score\":{\"mean\":64}}}\\n' > research.jsonl",
        "answer: Done.",
        "tool: mkdir -p phase2-experiment && printf 'analysis' > phase2-experiment/EXPERIMENT_RESULTS.md",
        "answer: Done.",
        "answer: Done.",
        scope_root=tmp_path,
    )
    controller = ResearchController(tmp_path, topic="seed scheduling", mode="manual", start_stage="idea.gate")
    waiting = controller.run()
    result = controller.reply_user("y start with libpng")
    state = json.loads((tmp_path / ".lightscientist/project_state.json").read_text(encoding="utf-8"))
    assert waiting.status == "waiting"
    assert result.status == "waiting"
    assert result.output_path == tmp_path / "phase2-experiment/EXPERIMENT_RESULTS.md"
    assert state["stage"] == "experiment.gate"


def test_research_controller_reply_no_revisits_same_phase(tmp_path: Path, monkeypatch) -> None:
    patch_scripted_model(
        monkeypatch,
        "tool: mkdir -p phase1-idea && printf 'ideas' > phase1-idea/IDEAS_CANDIDATES.md",
        "answer: Done.",
        "tool: mkdir -p phase1-idea && printf 'report' > phase1-idea/IDEA_REPORT.md",
        "answer: Done.",
        scope_root=tmp_path,
    )
    controller = ResearchController(tmp_path, topic="seed scheduling", mode="manual", start_stage="idea.gate")
    controller.run()
    result = controller.reply_user("n find more ideas")
    state = json.loads((tmp_path / ".lightscientist/project_state.json").read_text(encoding="utf-8"))
    events = (tmp_path / ".lightscientist/events.jsonl").read_text(encoding="utf-8")
    assert result.status == "waiting"
    assert state["stage"] == "idea.gate"
    assert '"from": "idea.gate", "to": "idea.generate"' in events


def test_experiment_loop_stays_in_loop_without_final_results(tmp_path: Path, monkeypatch) -> None:
    patch_scripted_model(
        monkeypatch,
        "tool: printf '{\"type\":\"config\",\"metrics\":{\"primary\":{\"name\":\"score\"}}}\\n{\"run\":1,\"status\":\"keep\",\"description\":\"baseline\",\"results\":{\"score\":{\"mean\":64}}}\\n' > research.jsonl",
        "answer: Done.",
        scope_root=tmp_path,
    )
    controller = ResearchController(tmp_path, topic="seed scheduling", mode="auto", start_stage="experiment.loop")
    result = controller._run_stage()
    state = json.loads((tmp_path / ".lightscientist/project_state.json").read_text(encoding="utf-8"))
    assert result.status == "completed"
    assert result.output_path == tmp_path / "research.jsonl"
    assert state["stage"] == "experiment.loop"


def test_experiment_loop_advances_to_analyze_when_results_exist(tmp_path: Path, monkeypatch) -> None:
    patch_scripted_model(
        monkeypatch,
        "tool: mkdir -p phase2-experiment && printf '{\"type\":\"config\",\"metrics\":{\"primary\":{\"name\":\"score\"}}}\\n{\"run\":1,\"status\":\"keep\",\"description\":\"baseline\",\"results\":{\"score\":{\"mean\":64}}}\\n' > research.jsonl && printf 'results' > phase2-experiment/EXPERIMENT_RESULTS.md",
        "answer: Done.",
        scope_root=tmp_path,
    )
    controller = ResearchController(tmp_path, topic="seed scheduling", mode="auto", start_stage="experiment.loop")
    result = controller._run_stage()
    state = json.loads((tmp_path / ".lightscientist/project_state.json").read_text(encoding="utf-8"))
    assert result.status == "completed"
    assert state["stage"] == "experiment.analyze"


def test_research_controller_rejects_invalid_next_stage(tmp_path: Path, monkeypatch) -> None:
    patch_scripted_model(
        monkeypatch,
        "tool: mkdir -p phase1-idea && printf 'survey' > phase1-idea/LITERATURE_SURVEY.md",
        "answer: Done.",
        supervisor_replies=("answer: TASK_COMPLETED: survey done\nNEXT_STAGE: paper.write",),
        scope_root=tmp_path,
    )
    ResearchController(tmp_path, topic="seed scheduling", mode="auto")._run_stage()
    state = json.loads((tmp_path / ".lightscientist/project_state.json").read_text(encoding="utf-8"))
    events = (tmp_path / ".lightscientist/events.jsonl").read_text(encoding="utf-8")
    assert state["stage"] == "idea.generate"
    assert "next_stage_rejected" in events


def test_cli_research_can_select_start_stage(tmp_path: Path, monkeypatch) -> None:
    patch_scripted_model(
        monkeypatch,
        "tool: mkdir -p phase2-experiment && printf 'setup' > phase2-experiment/SETUP_COMPLETE.md",
        "answer: Done.",
        "tool: mkdir -p phase2-experiment && printf '{\"type\":\"config\",\"metrics\":{\"primary\":{\"name\":\"score\"}}}\\n{\"run\":1,\"status\":\"keep\",\"description\":\"baseline\",\"results\":{\"score\":{\"mean\":64}}}\\n' > research.jsonl",
        "answer: Done.",
        "tool: mkdir -p phase2-experiment && printf 'analysis' > phase2-experiment/EXPERIMENT_RESULTS.md",
        "answer: Done.",
        "answer: Done.",
        scope_root=tmp_path,
    )
    exit_code = main(["research", "reproduce paper X", "--workspace", str(tmp_path), "--mode", "manual", "--stage", "experiment.setup"])
    state = json.loads((tmp_path / ".lightscientist/project_state.json").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert state["stage"] == "experiment.gate"


def test_cli_research_can_reply_to_manual_gate(tmp_path: Path, monkeypatch) -> None:
    patch_scripted_model(
        monkeypatch,
        "tool: mkdir -p phase2-experiment && printf 'setup' > phase2-experiment/SETUP_COMPLETE.md",
        "answer: Done.",
        "tool: mkdir -p phase2-experiment && printf '{\"type\":\"config\",\"metrics\":{\"primary\":{\"name\":\"score\"}}}\\n{\"run\":1,\"status\":\"keep\",\"description\":\"baseline\",\"results\":{\"score\":{\"mean\":64}}}\\n' > research.jsonl",
        "answer: Done.",
        "tool: mkdir -p phase2-experiment && printf 'analysis' > phase2-experiment/EXPERIMENT_RESULTS.md",
        "answer: Done.",
        "answer: Done.",
        scope_root=tmp_path,
    )
    main(["research", "seed scheduling", "--workspace", str(tmp_path), "--mode", "manual", "--stage", "idea.gate"])
    exit_code = main(["research", "--workspace", str(tmp_path), "--reply", "y proceed"])
    state = json.loads((tmp_path / ".lightscientist/project_state.json").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert state["stage"] == "experiment.gate"


def test_cli_run_uses_default_output_path(tmp_path: Path, capsys, monkeypatch) -> None:
    manager = make_agent_manager(monkeypatch, tmp_path, "answer: Done.")
    monkeypatch.setattr("esnext.cli.StageManager", lambda **_: manager)
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


def test_event_bus_writes_jsonl_and_console(tmp_path: Path, capsys) -> None:
    bus = EventBus([JsonlEventSink(tmp_path / "events.jsonl"), ConsoleEventSink()])
    bus.emit("L3", "tool_call", "execute echo hi", task_id="task1", agent_id="agent-task1", tool="execute")
    captured = capsys.readouterr()
    raw = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    event = json.loads(raw)
    assert "[L3 tool_call] task1 agent-task1 execute echo hi" in captured.out
    assert event["type"] == "tool_call"
    assert event["layer"] == "L3"
    assert event["tool"] == "execute"


def test_cli_run_watch_prints_agent_events(tmp_path: Path, capsys, monkeypatch) -> None:
    patch_scripted_model(
        monkeypatch,
        "tool: printf 'hello from watched agent'",
        "answer: Done.",
        supervisor_replies=("answer: TASK_COMPLETED: watched.",),
        scope_root=tmp_path,
    )
    exit_code = main(["run", "Say hello", "--workspace", str(tmp_path), "--agent", "--watch"])
    captured = capsys.readouterr()
    events = (tmp_path / ".lightscientist/events.jsonl").read_text(encoding="utf-8")
    assert exit_code == 0
    assert "[L2 worker_created]" in captured.out
    assert "[L3 tool_call]" in captured.out
    assert '"type": "tool_result"' in events
    assert '"type": "worker_status"' in events


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


def test_runtime_supervisor_allows_only_one_worker(tmp_path: Path, monkeypatch) -> None:
    supervisor = RuntimeSupervisor()
    supervisor._task = {"task_id": "tasksingle", "objective": "objective", "worker_ids": [], "status": "running", "summary": ""}
    supervisor._workspace_root = tmp_path
    monkeypatch.setattr(supervisor, "_run", lambda mode, agent_id, arg: time.sleep(0.5))
    tools = {tool.name: tool for tool in supervisor._runtime_tools()}
    first = json.loads(tools["start_worker"].invoke({"objective": "do work"}))
    second = json.loads(tools["start_worker"].invoke({"objective": "do more work"}))
    assert first["status"] == "accepted"
    assert second["status"] == "failed"
    assert "limited to one worker" in second["summary"]
    assert len(supervisor._agents) == 1


def test_webui_overview_reads_workspace_state(tmp_path: Path) -> None:
    state_dir = tmp_path / ".lightscientist"
    state_dir.mkdir()
    (state_dir / "project_state.json").write_text(
        json.dumps({"project_id": "demo", "phase": "paper", "stage": "paper.plan", "status": "running", "workspace_root": str(tmp_path)}),
        encoding="utf-8",
    )
    (state_dir / "events.jsonl").write_text(
        json.dumps({"type": "stage_started", "layer": "L1", "stage": "paper.plan", "time": 1}) + "\n"
        + json.dumps({"type": "worker_progress", "layer": "L2", "agent_id": "agent-stage-paper-plan", "stage": "paper.plan", "status": "running", "message": "Step 1", "step_count": 1, "action_count": 2, "time": 2}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / ".lightscientist" / "skills").mkdir()
    (tmp_path / ".lightscientist" / "skills" / "paper.plan.md").write_text("skill", encoding="utf-8")
    (tmp_path / "phase3-paper").mkdir()
    (tmp_path / "phase3-paper" / "PAPER_PLAN.md").write_text("plan", encoding="utf-8")
    overview = build_overview(tmp_path)
    assert overview["state"]["stage"] == "paper.plan"
    assert overview["workers"][1]["agent_id"] == "agent-stage-paper-plan"
    assert overview["current_skill"]["path"] == ".lightscientist/skills/paper.plan.md"
    assert overview["artifacts"][0]["path"] == "phase3-paper/PAPER_PLAN.md"


def test_webui_safe_read_workspace_file_blocks_escape(tmp_path: Path) -> None:
    (tmp_path / "note.md").write_text("hello", encoding="utf-8")
    assert safe_read_workspace_file(tmp_path, "note.md")["content"] == "hello"
    try:
        safe_read_workspace_file(tmp_path, "../outside.txt")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_supervisor_prompt_adds_status_specific_guidance() -> None:
    assert "intentional suspension" in supervisor_event_input("task", SupervisorEvent("a", "background"))
    assert "schedule_worker_resume" in supervisor_event_input("task", SupervisorEvent("a", "background"))
    assert "missing input" in supervisor_event_input("task", SupervisorEvent("a", "waiting"))
    assert "not shown progress" in supervisor_event_input("task", SupervisorEvent("a", "running", "Worker stalled.", kind="stall"))
    assert "Output: /tmp/out.md" in SupervisorEvent("a", "completed", output_path=Path("/tmp/out.md")).to_prompt_text()
    assert "second-layer supervisor" in load_prompt("supervisor")
    assert "ask_input" in load_prompt("worker")
