from __future__ import annotations

import json, sys, time, uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

from deepagents import create_deep_agent
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from .backends import LoggingWorkspaceBackend, ask_input, log_step, suspend_background
from .data_models import AgentProgress, AgentSessionInfo, HasAgentProgress, HasAgentSessionInfo, RuntimeUpdate
from .model_config import MODEL, build_chat_model
from .prompts import load_prompt

SYS = load_prompt("worker")


@dataclass(slots=True)
class AgentRunResult(HasAgentSessionInfo, HasAgentProgress):
    """Final result for one start/resume cycle of a third-layer session."""

    status: Literal["completed", "failed", "max_steps_reached", "running", "waiting", "background", "cancelled"]
    info: AgentSessionInfo
    messages: list[dict[str, str]]
    last_model_output: str = ""  # Raw last assistant output before result normalization.
    last_action: str = ""  # Normalized last tool/action summary, such as execute or ask_input.
    final_output: str = ""  # User-facing final text, waiting question, or background note.
    progress: AgentProgress = field(default_factory=AgentProgress)
    error: str = ""
    command_outputs: list[str] = field(default_factory=list)  # Logged workspace-tool outputs.

    @classmethod
    def from_trace(cls, trace: "RunTrace", status: str, final_output: str | None = None) -> "AgentRunResult":
        return cls(
            status,
            trace.info.snapshot(),
            trace.messages,
            trace.last_model_output,
            trace.last_action,
            trace.final_output if final_output is None else final_output,
            trace.progress.snapshot(),
            trace.error,
            trace.command_outputs,
        )


@dataclass(slots=True)
class RunTrace(HasAgentSessionInfo, HasAgentProgress):
    """Mutable trace collected during one start/resume cycle."""

    info: AgentSessionInfo
    status: Literal["running", "waiting", "background", "completed", "failed"] = "running"
    progress: AgentProgress = field(default_factory=AgentProgress)
    last_model_output: str = ""
    last_action: str = ""
    final_output: str = ""
    error: str = ""
    max_steps_reached: bool = False
    command_outputs: list[str] = field(default_factory=list)
    messages: list[dict[str, str]] = field(default_factory=list)

@dataclass(slots=True)
class AgentSession(HasAgentSessionInfo):
    info: AgentSessionInfo
    system_prompt: str
    checkpointer: MemorySaver
    tools: list[Any] = field(default_factory=list)
    resume_mode: Literal["message", "interrupt"] = "message"
    last_result: AgentRunResult | None = None


def start_agent_session(
    goal: str, *, cwd: str | Path | None = None, model: str = MODEL, max_steps: int = 8, system_prompt: str = SYS,
    status_cb: Callable[[RuntimeUpdate], None] | None = None, log_path: str | Path | None = None, tools: list[Any] | None = None,
) -> AgentSession:
    wd = Path(cwd).resolve() if cwd else Path.cwd()
    lp = Path(log_path).resolve() if log_path else (wd / "agent-debug.log")
    info = AgentSessionInfo(uuid.uuid4().hex[:8], uuid.uuid4().hex[:8], wd, lp, model, max_steps)
    session = AgentSession(info, system_prompt, MemorySaver(), list(tools or []))
    session.last_result = resume_agent_session(session, goal, status_cb=status_cb, start=True)
    return session


def resume_agent_session(
    session: AgentSession, user_input: str, *, status_cb: Callable[[RuntimeUpdate], None] | None = None, start: bool = False,
) -> AgentRunResult:
    trace = RunTrace(session.info.snapshot())
    is_waiting_resume = bool(not start and session.resume_mode == "interrupt" and session.last_result and session.last_result.status == "waiting")
    phase = "run-start" if start else "resume-start"
    log_step(session.log_path, phase, f"session_id: {session.session_id}\nthread_id: {session.thread_id}\ninput: {user_input}\nmodel: {session.model}\nmax_steps: {session.max_steps}\ncwd: {session.cwd}")
    chat = build_chat_model(trace=trace, status_cb=status_cb, log_path=session.log_path, model=session.model, max_steps=session.max_steps, log_step=log_step, to_msg=_to_msg, dump_msg=_dump_msg, status_from_output=_status_from_output)
    agent = create_deep_agent(
        model=chat,
        system_prompt=session.system_prompt,
        tools=[ask_input, suspend_background, *session.tools],
        backend=LoggingWorkspaceBackend(trace=trace, log_path=session.log_path, root_dir=session.cwd),
        subagents=[],
        middleware=(),
        checkpointer=session.checkpointer,
    )
    try:
        payload: Any = {"messages": [{"role": "user", "content": user_input}]}
        if is_waiting_resume: payload = Command(resume=user_input)
        result = agent.invoke(payload, config={"configurable": {"thread_id": session.thread_id}, "recursion_limit": session.max_steps * 8 + 20})
    except Exception as e:
        trace.status, trace.error = "failed", str(e)
        log_step(session.log_path, "run-end", f"status: failed\nstep: {trace.step_count}\nmessage: {e}")
        session.last_result = AgentRunResult.from_trace(trace, "failed")
        return session.last_result
    waiting = _waiting_from_result(result)
    waiting_via_interrupt = bool(waiting)
    if not waiting and trace.last_action.startswith("ask_input: "):
        waiting = trace.last_action.removeprefix("ask_input: ").strip()
    if waiting:
        session.resume_mode = "interrupt" if waiting_via_interrupt else "message"
        trace.status, trace.final_output = "waiting", waiting
        log_step(session.log_path, "run-end", f"status: waiting\nstep: {trace.step_count}\nmessage: {waiting}")
        if status_cb:
            status_cb(RuntimeUpdate("waiting", waiting, trace.progress.snapshot()))
    elif trace.last_action.startswith("suspend_background: "):
        note = trace.last_action.removeprefix("suspend_background: ").strip()
        session.resume_mode = "message"
        trace.status, trace.final_output = "background", note
        log_step(session.log_path, "run-end", f"status: background\nstep: {trace.step_count}\nmessage: {note}")
        if status_cb:
            status_cb(RuntimeUpdate("background", note, trace.progress.snapshot()))
    else:
        session.resume_mode = "message"
    final = trace.final_output or _final_from_result(result)
    status = "max_steps_reached" if trace.max_steps_reached else trace.status
    session.last_result = AgentRunResult.from_trace(trace, status, final)
    return session.last_result



# ---------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------
def _to_msg(msg: BaseMessage) -> dict[str, str] | None:
    if isinstance(msg, SystemMessage): return {"role": "system", "content": str(msg.content)}
    if isinstance(msg, HumanMessage): return {"role": "user", "content": str(msg.content)}
    if isinstance(msg, ToolMessage): return {"role": "tool", "content": str(msg.content)}
    if isinstance(msg, AIMessage): return {"role": "assistant", "content": str(msg.content or "")}
    return None


def _dump_msg(msg: AIMessage) -> str:
    return json.dumps({"role": "assistant", "content": msg.content, "tool_calls": msg.tool_calls}, ensure_ascii=False, indent=2)


def _final_from_result(result: Any) -> str:
    if not isinstance(result, dict): return ""
    msgs = result.get("messages") or []
    return str(getattr(msgs[-1], "content", "") or "") if msgs else ""


def _status_from_output(text: str) -> tuple[Literal["completed"], str]:
    return "completed", text.strip()


def _waiting_from_result(result: Any) -> str:
    if not isinstance(result, dict): return ""
    interrupts = result.get("__interrupt__") or []
    if not interrupts: return ""
    value = getattr(interrupts[0], "value", interrupts[0])
    if isinstance(value, dict): return str(value.get("question", "") or "")
    return str(value or "")



# ---------------------------------------------------------------
# 下面是非正式代码，测试用
# ---------------------------------------------------------------
def run_agent(
    goal: str, *, cwd: str | Path | None = None, model: str = MODEL, max_steps: int = 8, system_prompt: str = SYS,
    status_cb: Callable[[RuntimeUpdate], None] | None = None, log_path: str | Path | None = None,
) -> AgentRunResult:
    session = start_agent_session(goal, cwd=cwd, model=model, max_steps=max_steps, system_prompt=system_prompt, status_cb=status_cb, log_path=log_path)
    return session.last_result or AgentRunResult("failed", session.info.snapshot(), [], error="Agent session did not return a result.")

def cli_main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    goal = " ".join(argv).strip() or "List the files in the current directory"
    result = run_agent(goal, cwd=Path.cwd())
    print(f"status: {result.status}")
    print(f"steps: {result.step_count}")
    print(f"actions: {result.action_count}")
    if result.last_action:
        print(f"last_action: {result.last_action}")
    if result.final_output:
        print(result.final_output)
    return 0 if result.status in {"completed", "waiting", "background"} else 1
