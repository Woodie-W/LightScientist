from __future__ import annotations

import json, sys, uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

from deepagents import create_deep_agent
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, interrupt
from langchain.tools import tool
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from .backends import LoggingWorkspaceBackend, log_step
from .model_config import MODEL, build_chat_model

SYS = (
    "Use the built-in workspace tools when needed: execute, read_file, write_file, edit_file, grep, glob, ls, "
    "write_todos, read_todos, and task. "
    "If you need upper-layer input, call the ask_input tool with a concise question. "
    "If a long-running job should continue later, answer with 'BACKGROUND: <status>'. "
    "Otherwise answer directly when the task is done."
)


@dataclass(slots=True)
class AgentRunResult:
    status: Literal["completed", "failed", "max_steps_reached", "running", "waiting", "background", "cancelled"]
    session_id: str
    thread_id: str
    messages: list[dict[str, str]]
    last_model_output: str = ""
    last_action: str = "" # TODO lastaction 含义，和command_outputs的区别
    final_output: str = ""
    step_count: int = 0
    error: str = ""
    command_outputs: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RunTrace:
    status: Literal["running", "waiting", "background", "completed", "failed"] = "running"
    step_count: int = 0
    last_model_output: str = ""
    last_action: str = ""
    final_output: str = ""
    error: str = ""
    max_steps_reached: bool = False
    command_outputs: list[str] = field(default_factory=list)
    messages: list[dict[str, str]] = field(default_factory=list)


# 类似于 hooks
@tool
def ask_input(question: str) -> str:
    """Ask the upper layer for more input and pause the graph."""
    response = interrupt({"type": "waiting", "question": question})
    return str(response or "")


@dataclass(slots=True)
class AgentSession:
    session_id: str
    thread_id: str
    cwd: Path
    log_path: Path
    model: str
    max_steps: int
    system_prompt: str
    checkpointer: MemorySaver
    tools: list[Any] = field(default_factory=list)
    resume_mode: Literal["message", "interrupt"] = "message"
    last_result: AgentRunResult | None = None


def start_agent_session(
    goal: str, *, cwd: str | Path | None = None, model: str = MODEL, max_steps: int = 8, system_prompt: str = SYS,
    status_cb: Callable[[str, str], None] | None = None, log_path: str | Path | None = None, tools: list[Any] | None = None,
) -> AgentSession:
    wd = Path(cwd).resolve() if cwd else Path.cwd()
    lp = Path(log_path).resolve() if log_path else (wd / "agent-debug.log")
    session = AgentSession(uuid.uuid4().hex[:8], uuid.uuid4().hex[:8], wd, lp, model, max_steps, system_prompt, MemorySaver(), list(tools or []))
    session.last_result = resume_agent_session(session, goal, status_cb=status_cb, start=True)
    return session


def resume_agent_session(
    session: AgentSession, user_input: str, *, status_cb: Callable[[str, str], None] | None = None, start: bool = False,
) -> AgentRunResult:
    trace = RunTrace()
    is_waiting_resume = bool(not start and session.resume_mode == "interrupt" and session.last_result and session.last_result.status == "waiting")
    phase = "run-start" if start else "resume-start"
    log_step(session.log_path, phase, f"session_id: {session.session_id}\nthread_id: {session.thread_id}\ninput: {user_input}\nmodel: {session.model}\nmax_steps: {session.max_steps}\ncwd: {session.cwd}")
    chat = build_chat_model(trace=trace, status_cb=status_cb, log_path=session.log_path, model=session.model, max_steps=session.max_steps, log_step=log_step, to_msg=_to_msg, dump_msg=_dump_msg, status_from_output=_status_from_output)
    agent = create_deep_agent(
        model=chat,
        system_prompt=session.system_prompt,
        tools=[ask_input, *session.tools],
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
        session.last_result = AgentRunResult("failed", session.session_id, session.thread_id, trace.messages, trace.last_model_output, trace.last_action, trace.final_output, trace.step_count, str(e), trace.command_outputs)
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
            status_cb("waiting", waiting)
    else:
        session.resume_mode = "message"
    final = trace.final_output or _final_from_result(result)
    status = "max_steps_reached" if trace.max_steps_reached else trace.status
    session.last_result = AgentRunResult(status, session.session_id, session.thread_id, trace.messages, trace.last_model_output, trace.last_action, final, trace.step_count, trace.error, trace.command_outputs)
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


def _status_from_output(text: str) -> tuple[Literal["background", "completed"], str]:
    raw = text.strip()
    for prefix, status in (("BACKGROUND:", "background"),):
        if raw.upper().startswith(prefix):
            return status, raw[len(prefix) :].strip()
    return "completed", raw


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
    status_cb: Callable[[str, str], None] | None = None, log_path: str | Path | None = None,
) -> AgentRunResult:
    session = start_agent_session(goal, cwd=cwd, model=model, max_steps=max_steps, system_prompt=system_prompt, status_cb=status_cb, log_path=log_path)
    return session.last_result or AgentRunResult("failed", session.session_id, session.thread_id, [], error="Agent session did not return a result.")

def cli_main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    goal = " ".join(argv).strip() or "List the files in the current directory"
    result = run_agent(goal, cwd=Path.cwd())
    print(f"status: {result.status}")
    print(f"steps: {result.step_count}")
    if result.last_action:
        print(f"last_action: {result.last_action}")
    if result.final_output:
        print(result.final_output)
    return 0 if result.status in {"completed", "waiting", "background"} else 1
