from __future__ import annotations

import json, os, sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

import requests
from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import ConfigDict, Field

ENV = {"PAGER": "cat", "MANPAGER": "cat", "LESS": "-R", "PIP_PROGRESS_BAR": "off", "TQDM_DISABLE": "1"}
SYS = "Use tools when needed. Use execute for shell commands. Answer directly when the task is done."
BASE_URL = os.getenv("LIGHTSCIENTIST_BASE_URL", "http://100.104.128.29:1234/v1")
MODEL = os.getenv("LIGHTSCIENTIST_MODEL", "unsloth/qwen3.5-35b-a3b")
API_KEY = os.getenv("LIGHTSCIENTIST_API_KEY", "lmstudio")


class AgentRuntimeError(RuntimeError): ...
class ModelRequestError(AgentRuntimeError): ...


@dataclass(slots=True)
class AgentRunResult:
    status: Literal["completed", "failed", "max_steps_reached"]
    messages: list[dict[str, str]]
    last_model_output: str = ""
    last_action: str = ""
    final_output: str = ""
    step_count: int = 0
    error: str = ""
    command_outputs: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RunTrace:
    step_count: int = 0
    last_model_output: str = ""
    last_action: str = ""
    final_output: str = ""
    error: str = ""
    max_steps_reached: bool = False
    command_outputs: list[str] = field(default_factory=list)
    messages: list[dict[str, str]] = field(default_factory=list)


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


class OpenAICompatChatModel(BaseChatModel):
    model_name: str = MODEL
    base_url: str = BASE_URL
    api_key: str = API_KEY
    temperature: float = 0.2
    tools: list[Any] = Field(default_factory=list, exclude=True)
    trace: RunTrace = Field(exclude=True)
    status_cb: Callable[[str, str], None] | None = Field(default=None, exclude=True)
    log_path: Path | None = Field(default=None, exclude=True)
    max_steps: int = 8
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def _llm_type(self) -> str:
        return "lightscientist-openai-compat"

    def bind_tools(self, tools: list[BaseTool] | Any, **kwargs: Any) -> BaseChatModel:
        return self.model_copy(update={"tools": list(tools)})

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: Any = None, **kwargs: Any) -> ChatResult:
        if self.trace.step_count >= self.max_steps:
            self.trace.max_steps_reached, self.trace.error = True, "Maximum step limit reached."
            log_step(self.log_path, "run-end", f"status: max_steps_reached\nstep: {self.trace.step_count}\nmessage: {self.trace.error}")
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.trace.error))])
        self.trace.step_count += 1
        step = self.trace.step_count
        self.trace.messages = [m for msg in messages if (m := self._to_msg(msg))]
        if self.status_cb:
            self.status_cb("running", f"Step {step}: querying model.")
        payload = {"model": self.model_name, "messages": self.trace.messages, "temperature": self.temperature}
        if self.tools:
            payload["tools"], payload["tool_choice"] = [convert_to_openai_tool(t) for t in self.tools], "auto"
        raw = self._request(payload)
        msg = raw["choices"][0]["message"]
        self.trace.last_model_output = json.dumps(msg, ensure_ascii=False, indent=2)
        log_step(self.log_path, f"step-{step}-model-output", self.trace.last_model_output)
        tool_calls = [{"name": t["function"]["name"], "args": json.loads(t["function"].get("arguments") or "{}"), "id": t["id"], "type": "tool_call"} for t in msg.get("tool_calls", [])]
        if tool_calls:
            call = tool_calls[0]
            self.trace.last_action = f'{call["name"]}: {call["args"]}'
            log_step(self.log_path, f"step-{step}-tool-call", self.trace.last_action)
            if self.status_cb:
                self.status_cb("running", f'Step {step}: calling {call["name"]}.')
        else:
            self.trace.final_output = str(msg.get("content") or "")
            log_step(self.log_path, f"step-{step}-final-answer", self.trace.final_output)
            if self.status_cb:
                self.status_cb("completed", f"Step {step}: final answer submitted.")
            log_step(self.log_path, "run-end", f"status: completed\nstep: {step}\nmessage: {self.trace.final_output}")
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=str(msg.get("content") or ""), tool_calls=tool_calls))])

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        os.environ.update({k: "" for k in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"]})
        s = requests.Session()
        s.trust_env = False
        try:
            r = s.post(f"{self.base_url}/chat/completions", json=payload, headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, timeout=30)
        except Exception as e:
            raise ModelRequestError(f"Model request failed: {e}") from e
        if r.status_code != 200:
            raise ModelRequestError(f"Model request failed with status {r.status_code}: {r.text[:400]}")
        try:
            return r.json()
        except Exception as e:
            raise ModelRequestError(f"Model response parse failed: {e}") from e

    def _to_msg(self, msg: BaseMessage) -> dict[str, Any] | None:
        if isinstance(msg, SystemMessage):
            return {"role": "system", "content": str(msg.content)}
        if isinstance(msg, HumanMessage):
            return {"role": "user", "content": str(msg.content)}
        if isinstance(msg, ToolMessage):
            return {"role": "tool", "tool_call_id": msg.tool_call_id, "content": str(msg.content)}
        if isinstance(msg, AIMessage):
            out = {"role": "assistant", "content": str(msg.content or "")}
            if msg.tool_calls:
                out["tool_calls"] = [{"id": t["id"], "type": "function", "function": {"name": t["name"], "arguments": json.dumps(t.get("args", {}), ensure_ascii=False)}} for t in msg.tool_calls]
            return out
        return None


class ScriptedChatModel(BaseChatModel):
    query_fn: Callable[[list[dict[str, Any]]], str] = Field(exclude=True)
    trace: RunTrace = Field(exclude=True)
    status_cb: Callable[[str, str], None] | None = Field(default=None, exclude=True)
    log_path: Path | None = Field(default=None, exclude=True)
    max_steps: int = 8
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def _llm_type(self) -> str:
        return "lightscientist-scripted"

    def bind_tools(self, tools: list[BaseTool] | Any, **kwargs: Any) -> BaseChatModel:
        return self

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: Any = None, **kwargs: Any) -> ChatResult:
        if self.trace.step_count >= self.max_steps:
            self.trace.max_steps_reached, self.trace.error = True, "Maximum step limit reached."
            log_step(self.log_path, "run-end", f"status: max_steps_reached\nstep: {self.trace.step_count}\nmessage: {self.trace.error}")
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.trace.error))])
        self.trace.step_count += 1
        step = self.trace.step_count
        self.trace.messages = [m for msg in messages if (m := OpenAICompatChatModel._to_msg(self, msg))]
        if self.status_cb:
            self.status_cb("running", f"Step {step}: querying model.")
        raw = self.query_fn(self.trace.messages)
        self.trace.last_model_output = raw
        log_step(self.log_path, f"step-{step}-model-output", raw)
        if raw.startswith("tool:"):
            cmd = raw.split(":", 1)[1].strip()
            self.trace.last_action = f"execute: {cmd}"
            log_step(self.log_path, f"step-{step}-tool-call", self.trace.last_action)
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[{"name": "execute", "args": {"command": cmd}, "id": f"call_{step}", "type": "tool_call"}]))])
        self.trace.final_output = raw.removeprefix("answer:").strip()
        log_step(self.log_path, f"step-{step}-final-answer", self.trace.final_output)
        if self.status_cb:
            self.status_cb("completed", f"Step {step}: final answer submitted.")
        log_step(self.log_path, "run-end", f"status: completed\nstep: {step}\nmessage: {self.trace.final_output}")
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.trace.final_output))])


def run_agent(
    goal: str, *, cwd: str | Path | None = None, model: str = MODEL, max_steps: int = 8,
    extra_env: dict[str, str] | None = None, query_fn: Callable[[list[dict[str, Any]]], str] | None = None,
    system_prompt: str = SYS, status_cb: Callable[[str, str], None] | None = None, log_path: str | Path | None = None,
) -> AgentRunResult:
    wd = Path(cwd).resolve() if cwd else Path.cwd()
    lp = Path(log_path).resolve() if log_path else (wd / "agent-debug.log")
    trace = RunTrace()
    log_step(lp, "run-start", f"goal: {goal}\nmodel: {model}\nmax_steps: {max_steps}\ncwd: {wd}")
    chat = ScriptedChatModel(query_fn=query_fn, trace=trace, status_cb=status_cb, log_path=lp, max_steps=max_steps) if query_fn else OpenAICompatChatModel(model_name=model, trace=trace, status_cb=status_cb, log_path=lp, max_steps=max_steps)
    agent = create_deep_agent(model=chat, system_prompt=system_prompt, backend=LoggingShellBackend(trace=trace, log_path=lp, root_dir=wd), subagents=[], middleware=(), checkpointer=False)
    try:
        result = agent.invoke({"messages": [{"role": "user", "content": goal}]}, config={"recursion_limit": max_steps * 8 + 20})
    except Exception as e:
        trace.error = str(e)
        log_step(lp, "run-end", f"status: failed\nstep: {trace.step_count}\nmessage: {e}")
        return AgentRunResult("failed", trace.messages, trace.last_model_output, trace.last_action, trace.final_output, trace.step_count, str(e), trace.command_outputs)
    final = trace.final_output or _final_from_result(result)
    status = "max_steps_reached" if trace.max_steps_reached else "completed"
    return AgentRunResult(status, trace.messages, trace.last_model_output, trace.last_action, final, trace.step_count, trace.error, trace.command_outputs)


def _final_from_result(result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    msgs = result.get("messages") or []
    return str(getattr(msgs[-1], "content", "") or "") if msgs else ""


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
    return 0 if result.status == "completed" else 1
