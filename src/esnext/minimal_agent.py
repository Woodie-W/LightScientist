from __future__ import annotations

import json, os, sys, uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

import httpx
from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatResult
from langchain_openai import ChatOpenAI
from pydantic import ConfigDict, Field

ENV = {"PAGER": "cat", "MANPAGER": "cat", "LESS": "-R", "PIP_PROGRESS_BAR": "off", "TQDM_DISABLE": "1"}
SYS = (
    "Use tools when needed. Use execute for shell commands. "
    "If you need upper-layer input, answer with 'WAITING: <question>'. "
    "If a long-running job should continue later, answer with 'BACKGROUND: <status>'. "
    "Otherwise answer directly when the task is done."
)
BASE_URL = os.getenv("LIGHTSCIENTIST_BASE_URL", "http://100.104.128.29:1234/v1")
MODEL = os.getenv("LIGHTSCIENTIST_MODEL", "unsloth/qwen3.5-35b-a3b")
API_KEY = os.getenv("LIGHTSCIENTIST_API_KEY", "lmstudio")


@dataclass(slots=True)
class AgentRunResult:
    status: Literal["completed", "failed", "max_steps_reached", "running", "waiting", "background", "cancelled"]
    session_id: str
    thread_id: str
    messages: list[dict[str, str]]
    last_model_output: str = ""
    last_action: str = ""
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
    last_result: AgentRunResult | None = None


def log_step(path: Path | None, title: str, body: str = "") -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"[{title}]\n")
        if body:
            f.write(body.rstrip() + "\n")
        f.write("\n")


class LoggingShellBackend(LocalShellBackend):
    def __init__(self, *, trace: RunTrace, log_path: Path, root_dir: Path, timeout: int = 30) -> None:
        super().__init__(root_dir=root_dir, virtual_mode=True, timeout=timeout, env=ENV, inherit_env=False)
        self.trace, self.log_path = trace, log_path

    def execute(self, command: str, *, timeout: int | None = None):
        result = super().execute(command, timeout=timeout)
        self.trace.command_outputs.append(result.output)
        log_step(self.log_path, f"step-{self.trace.step_count}-command-output", result.output)
        return result


class LoggingChatOpenAI(ChatOpenAI):
    trace: RunTrace = Field(exclude=True)
    status_cb: Callable[[str, str], None] | None = Field(default=None, exclude=True)
    log_path: Path | None = Field(default=None, exclude=True)
    max_steps: int = 8
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def _llm_type(self) -> str:
        return "lightscientist-chatopenai"

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: Any = None, **kwargs: Any) -> ChatResult:
        if self.trace.step_count >= self.max_steps:
            self.trace.status, self.trace.max_steps_reached, self.trace.error = "failed", True, "Maximum step limit reached."
            log_step(self.log_path, "run-end", f"status: max_steps_reached\nstep: {self.trace.step_count}\nmessage: {self.trace.error}")
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        self.trace.step_count += 1
        step = self.trace.step_count
        self.trace.messages = [m for msg in messages if (m := _to_msg(msg))]
        if self.status_cb:
            self.status_cb("running", f"Step {step}: querying model.")
        result = super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        msg = result.generations[0].message
        self.trace.last_model_output = _dump_msg(msg)
        log_step(self.log_path, f"step-{step}-model-output", self.trace.last_model_output)
        if msg.tool_calls:
            call = msg.tool_calls[0]
            self.trace.last_action = f'{call["name"]}: {call["args"]}'
            log_step(self.log_path, f"step-{step}-tool-call", self.trace.last_action)
            if self.status_cb:
                self.status_cb("running", f'Step {step}: calling {call["name"]}.')
        else:
            self.trace.status, self.trace.final_output = _status_from_output(str(msg.content or ""))
            log_step(self.log_path, f"step-{step}-final-answer", self.trace.final_output)
            if self.status_cb:
                self.status_cb(self.trace.status, f"Step {step}: {self.trace.final_output or self.trace.status}.")
            log_step(self.log_path, "run-end", f"status: {self.trace.status}\nstep: {step}\nmessage: {self.trace.final_output}")
        return result


def build_chat_model(
    *, trace: RunTrace, status_cb: Callable[[str, str], None] | None, log_path: Path, model: str, max_steps: int,
    query_fn: Callable[[list[dict[str, Any]]], str] | None = None,
) -> BaseChatModel:
    return LoggingChatOpenAI(
        model=model,
        base_url=BASE_URL,
        api_key=API_KEY,
        temperature=0.2,
        use_responses_api=False,
        http_client=httpx.Client(trust_env=False),
        trace=trace,
        status_cb=status_cb,
        log_path=log_path,
        max_steps=max_steps,
    )


def run_agent(
    goal: str, *, cwd: str | Path | None = None, model: str = MODEL, max_steps: int = 8,
    extra_env: dict[str, str] | None = None, query_fn: Callable[[list[dict[str, Any]]], str] | None = None,
    system_prompt: str = SYS, status_cb: Callable[[str, str], None] | None = None, log_path: str | Path | None = None,
) -> AgentRunResult:
    session = start_agent_session(goal, cwd=cwd, model=model, max_steps=max_steps, extra_env=extra_env, query_fn=query_fn, system_prompt=system_prompt, status_cb=status_cb, log_path=log_path)
    return session.last_result or AgentRunResult("failed", session.session_id, session.thread_id, [], error="Agent session did not return a result.")


def start_agent_session(
    goal: str, *, cwd: str | Path | None = None, model: str = MODEL, max_steps: int = 8,
    extra_env: dict[str, str] | None = None, query_fn: Callable[[list[dict[str, Any]]], str] | None = None,
    system_prompt: str = SYS, status_cb: Callable[[str, str], None] | None = None, log_path: str | Path | None = None,
) -> AgentSession:
    wd = Path(cwd).resolve() if cwd else Path.cwd()
    lp = Path(log_path).resolve() if log_path else (wd / "agent-debug.log")
    session = AgentSession(uuid.uuid4().hex[:8], uuid.uuid4().hex[:8], wd, lp, model, max_steps, system_prompt, MemorySaver())
    session.last_result = resume_agent_session(session, goal, extra_env=extra_env, query_fn=query_fn, status_cb=status_cb, start=True)
    return session


def resume_agent_session(
    session: AgentSession, user_input: str, *, extra_env: dict[str, str] | None = None,
    query_fn: Callable[[list[dict[str, Any]]], str] | None = None, status_cb: Callable[[str, str], None] | None = None,
    start: bool = False,
) -> AgentRunResult:
    trace = RunTrace()
    phase = "run-start" if start else "resume-start"
    log_step(session.log_path, phase, f"session_id: {session.session_id}\nthread_id: {session.thread_id}\ninput: {user_input}\nmodel: {session.model}\nmax_steps: {session.max_steps}\ncwd: {session.cwd}")
    chat = build_chat_model(trace=trace, status_cb=status_cb, log_path=session.log_path, model=session.model, max_steps=session.max_steps, query_fn=query_fn)
    agent = create_deep_agent(
        model=chat,
        system_prompt=session.system_prompt,
        backend=LoggingShellBackend(trace=trace, log_path=session.log_path, root_dir=session.cwd),
        subagents=[],
        middleware=(),
        checkpointer=session.checkpointer,
    )
    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": user_input}]},
            config={"configurable": {"thread_id": session.thread_id}, "recursion_limit": session.max_steps * 8 + 20},
        )
    except Exception as e:
        trace.status, trace.error = "failed", str(e)
        log_step(session.log_path, "run-end", f"status: failed\nstep: {trace.step_count}\nmessage: {e}")
        session.last_result = AgentRunResult("failed", session.session_id, session.thread_id, trace.messages, trace.last_model_output, trace.last_action, trace.final_output, trace.step_count, str(e), trace.command_outputs)
        return session.last_result
    final = trace.final_output or _final_from_result(result)
    status = "max_steps_reached" if trace.max_steps_reached else trace.status
    session.last_result = AgentRunResult(status, session.session_id, session.thread_id, trace.messages, trace.last_model_output, trace.last_action, final, trace.step_count, trace.error, trace.command_outputs)
    return session.last_result


def _to_msg(msg: BaseMessage) -> dict[str, str] | None:
    if isinstance(msg, SystemMessage):
        return {"role": "system", "content": str(msg.content)}
    if isinstance(msg, HumanMessage):
        return {"role": "user", "content": str(msg.content)}
    if isinstance(msg, ToolMessage):
        return {"role": "tool", "content": str(msg.content)}
    if isinstance(msg, AIMessage):
        return {"role": "assistant", "content": str(msg.content or "")}
    return None


def _dump_msg(msg: AIMessage) -> str:
    return json.dumps({"role": "assistant", "content": msg.content, "tool_calls": msg.tool_calls}, ensure_ascii=False, indent=2)


def _final_from_result(result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    msgs = result.get("messages") or []
    return str(getattr(msgs[-1], "content", "") or "") if msgs else ""


def _status_from_output(text: str) -> tuple[Literal["waiting", "background", "completed"], str]:
    raw = text.strip()
    for prefix, status in (("WAITING:", "waiting"), ("BACKGROUND:", "background")):
        if raw.upper().startswith(prefix):
            return status, raw[len(prefix) :].strip()
    return "completed", raw


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
