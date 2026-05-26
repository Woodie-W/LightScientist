from __future__ import annotations

import json, sys, time, uuid
from pathlib import Path
from typing import Any, Callable, Literal

from deepagents import create_deep_agent
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from .backends import CommandProcessRegistry, LoggingWorkspaceBackend, ask_input, finish_cancelled, log_step, suspend_background
from .data_models import AgentRunResult, AgentSession, AgentSessionInfo, RunTrace, RuntimeUpdate
from .events import EventBus
from .model_config import MODEL, build_chat_model
from .prompts import load_prompt

SYS = load_prompt("worker")


def start_agent_session(
    goal: str, *, cwd: str | Path | None = None, model: str = MODEL, max_steps: int = 0, system_prompt: str = SYS,
    status_cb: Callable[[RuntimeUpdate], None] | None = None, log_path: str | Path | None = None, tools: list[Any] | None = None,
    include_lifecycle_tools: bool = True, event_bus: EventBus | None = None, event_layer: str = "L3",
    event_context: dict[str, object] | None = None,
) -> AgentSession:
    session = create_agent_session(cwd=cwd, model=model, max_steps=max_steps, system_prompt=system_prompt, log_path=log_path, tools=tools, include_lifecycle_tools=include_lifecycle_tools)
    session.last_result = resume_agent_session(session, goal, status_cb=status_cb, start=True, event_bus=event_bus, event_layer=event_layer, event_context=event_context)
    return session


def create_agent_session(
    *, cwd: str | Path | None = None, model: str = MODEL, max_steps: int = 0, system_prompt: str = SYS,
    log_path: str | Path | None = None, tools: list[Any] | None = None, include_lifecycle_tools: bool = True,
) -> AgentSession:
    wd = Path(cwd).resolve() if cwd else Path.cwd()
    lp = Path(log_path).resolve() if log_path else (wd / "agent-debug.log")
    info = AgentSessionInfo(uuid.uuid4().hex[:8], uuid.uuid4().hex[:8], wd, lp, model, max_steps)
    return AgentSession(info, system_prompt, MemorySaver(), list(tools or []), include_lifecycle_tools=include_lifecycle_tools, process_registry=CommandProcessRegistry())


def resume_agent_session(
    session: AgentSession, user_input: str, *, status_cb: Callable[[RuntimeUpdate], None] | None = None, start: bool = False,
    event_bus: EventBus | None = None, event_layer: str = "L3", event_context: dict[str, object] | None = None,
) -> AgentRunResult:
    trace = RunTrace(session.info.snapshot())
    event_data = dict(event_context or {})
    is_waiting_resume = bool(not start and session.resume_mode == "interrupt" and session.last_result and session.last_result.status == "waiting")
    phase = "run-start" if start else "resume-start"
    log_step(session.log_path, phase, f"session_id: {session.session_id}\nthread_id: {session.thread_id}\ninput: {user_input}\nmodel: {session.model}\nmax_steps: {session.max_steps}\ncwd: {session.cwd}")
    _emit_event(event_bus, event_layer, "agent_session_start", phase, session=session, data=event_data)
    chat = build_chat_model(
        trace=trace, status_cb=status_cb, log_path=session.log_path, model=session.model, max_steps=session.max_steps,
        log_step=log_step, to_msg=_to_msg, dump_msg=_dump_msg, status_from_output=_status_from_output,
        event_bus=event_bus, event_layer=event_layer, event_context=event_data,
    )
    agent = create_deep_agent(
        model=chat,
        system_prompt=session.system_prompt,
        tools=[*([ask_input, suspend_background, finish_cancelled] if session.include_lifecycle_tools else []), *session.tools],
        backend=LoggingWorkspaceBackend(
            trace=trace, log_path=session.log_path, root_dir=session.cwd, process_registry=session.process_registry,
            event_bus=event_bus, event_layer=event_layer, event_context=event_data,
        ),
        subagents=[],
        middleware=(),
        checkpointer=session.checkpointer,
    )
    try:
        payload: Any = {"messages": [{"role": "user", "content": user_input}]}
        if is_waiting_resume: payload = Command(resume=user_input)
        result = agent.invoke(payload, config={"configurable": {"thread_id": session.thread_id}, "recursion_limit": _recursion_limit(session.max_steps)})
    except Exception as e:
        trace.status, trace.error = "failed", str(e)
        log_step(session.log_path, "run-end", f"status: failed\nstep: {trace.step_count}\nmessage: {e}")
        session.last_result = AgentRunResult.from_trace(trace, "failed")
        _emit_event(event_bus, event_layer, "agent_session_failed", str(e), session=session, data=event_data)
        return session.last_result
    waiting = _waiting_from_result(result)
    waiting_via_interrupt = bool(waiting)
    if not waiting and trace.last_action.startswith("ask_input: "):
        waiting = trace.last_action.removeprefix("ask_input: ").strip()
    if waiting:
        session.resume_mode = "interrupt" if waiting_via_interrupt else "message"
        trace.status, trace.final_output = "waiting", waiting
        log_step(session.log_path, "run-end", f"status: waiting\nstep: {trace.step_count}\nmessage: {waiting}")
        _emit_event(event_bus, event_layer, "agent_waiting", waiting, session=session, data=event_data)
        if status_cb:
            status_cb(RuntimeUpdate("waiting", waiting, trace.progress.snapshot()))
    elif trace.last_action.startswith("suspend_background: "):
        note = trace.last_action.removeprefix("suspend_background: ").strip()
        session.resume_mode = "message"
        trace.status, trace.final_output = "background", note
        log_step(session.log_path, "run-end", f"status: background\nstep: {trace.step_count}\nmessage: {note}")
        _emit_event(event_bus, event_layer, "agent_background", note, session=session, data=event_data)
        if status_cb:
            status_cb(RuntimeUpdate("background", note, trace.progress.snapshot()))
    elif trace.last_action.startswith("finish_cancelled: "):
        summary = trace.last_action.removeprefix("finish_cancelled: ").strip()
        session.resume_mode = "message"
        trace.status, trace.final_output = "cancelled", summary
        log_step(session.log_path, "run-end", f"status: cancelled\nstep: {trace.step_count}\nmessage: {summary}")
        _emit_event(event_bus, event_layer, "agent_cancelled", summary, session=session, data=event_data)
        if status_cb:
            status_cb(RuntimeUpdate("cancelled", summary, trace.progress.snapshot()))
    else:
        session.resume_mode = "message"
    final = trace.final_output or _final_from_result(result)
    status = "max_steps_reached" if trace.max_steps_reached else trace.status
    session.last_result = AgentRunResult.from_trace(trace, status, final)
    _emit_event(event_bus, event_layer, "agent_session_end", final or status, session=session, data={**event_data, "status": status, "step_count": trace.step_count, "action_count": trace.action_count})
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
    return json.dumps(
        {
            "role": "assistant",
            "content": msg.content,
            "tool_calls": msg.tool_calls,
            "reasoning_content": msg.additional_kwargs.get("reasoning_content", ""),
        },
        ensure_ascii=False,
        indent=2,
    )


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


def _emit_event(event_bus: EventBus | None, layer: str, kind: str, message: str, *, session: AgentSession, data: dict[str, object]) -> None:
    if not event_bus: return
    payload = dict(data)
    event_bus.emit(
        layer,
        kind,
        message,
        task_id=str(payload.pop("task_id", "")),
        agent_id=str(payload.pop("agent_id", "")),
        stage=str(payload.pop("stage", "")),
        session_id=session.session_id,
        thread_id=session.thread_id,
        **payload,
    )


def _recursion_limit(max_steps: int) -> int:
    return max_steps * 8 + 20 if max_steps > 0 else 10_000



# ---------------------------------------------------------------
# 下面是非正式代码，测试用
# ---------------------------------------------------------------
def run_agent(
    goal: str, *, cwd: str | Path | None = None, model: str = MODEL, max_steps: int = 0, system_prompt: str = SYS,
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
