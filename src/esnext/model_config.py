from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult
from langchain_openai import ChatOpenAI
from pydantic import ConfigDict, Field

from .data_models import RuntimeUpdate
from .events import EventBus

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-pro"

BASE_URL = os.getenv("LIGHTSCIENTIST_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL)
MODEL = os.getenv("LIGHTSCIENTIST_MODEL") or os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL)
API_KEY = os.getenv("LIGHTSCIENTIST_API_KEY") or os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_THINKING = os.getenv("LIGHTSCIENTIST_THINKING") or os.getenv("DEEPSEEK_THINKING", "enabled")
DEEPSEEK_REASONING_EFFORT = os.getenv("LIGHTSCIENTIST_REASONING_EFFORT") or os.getenv("DEEPSEEK_REASONING_EFFORT", "high")


def chat_provider_options() -> dict[str, object]:
    if "api.deepseek.com" not in BASE_URL:
        return {}
    return {
        "extra_body": {"thinking": {"type": DEEPSEEK_THINKING}},
        "reasoning_effort": DEEPSEEK_REASONING_EFFORT,
    }


class LoggingChatOpenAI(ChatOpenAI):
    trace: Any = Field(exclude=True)
    status_cb: Callable[[RuntimeUpdate], None] | None = Field(default=None, exclude=True)
    log_path: Path | None = Field(default=None, exclude=True)
    log_step: Callable[[Path | None, str, str], None] = Field(exclude=True)
    to_msg: Callable[[BaseMessage], dict[str, str] | None] = Field(exclude=True)
    dump_msg: Callable[[AIMessage], str] = Field(exclude=True)
    status_from_output: Callable[[str], tuple[str, str]] = Field(exclude=True)
    event_bus: EventBus | None = Field(default=None, exclude=True)
    event_layer: str = "L3"
    event_context: dict[str, object] = Field(default_factory=dict, exclude=True)
    max_steps: int = 8
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def _llm_type(self) -> str:
        return "lightscientist-chatopenai"

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: Any = None, **kwargs: Any) -> ChatResult:
        if self.trace.step_count >= self.max_steps:
            self.trace.status, self.trace.max_steps_reached, self.trace.error = "failed", True, "Maximum step limit reached."
            self.log_step(self.log_path, "run-end", f"status: max_steps_reached\nstep: {self.trace.step_count}\nmessage: {self.trace.error}")
            self.trace.action_count += 1
            self._emit("model_max_steps", self.trace.error)
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        self.trace.step_count += 1
        self.trace.action_count += 1
        step = self.trace.step_count
        self.trace.messages = [m for msg in messages if (m := self.to_msg(msg))]
        if self.status_cb:
            self.status_cb(RuntimeUpdate("running", f"Step {step}: querying model.", self.trace.progress.snapshot()))
        model_name = str(getattr(self, "model_name", "") or getattr(self, "model", ""))
        self._emit("model_call", f"Step {step}: querying model.", step=step, model=model_name)
        result = super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        msg = result.generations[0].message
        self.trace.last_model_output = self.dump_msg(msg)
        self.log_step(self.log_path, f"step-{step}-model-output", self.trace.last_model_output)
        self._emit("model_output", str(msg.content or "") or "(tool call)", step=step, has_tool_calls=bool(msg.tool_calls))
        if msg.tool_calls:
            call = msg.tool_calls[0]
            self.trace.last_action = f'{call["name"]}: {call["args"]}'
            self.log_step(self.log_path, f"step-{step}-tool-call", self.trace.last_action)
            self._emit("tool_call", f'{call["name"]}: {call["args"]}', step=step, tool=call["name"], args=call["args"])
            if self.status_cb:
                self.status_cb(RuntimeUpdate("running", f'Step {step}: calling {call["name"]}.', self.trace.progress.snapshot()))
        else:
            self.trace.status, self.trace.final_output = self.status_from_output(str(msg.content or ""))
            self.log_step(self.log_path, f"step-{step}-final-answer", self.trace.final_output)
            self._emit("model_final", self.trace.final_output, step=step, status=self.trace.status)
            if self.status_cb:
                self.status_cb(RuntimeUpdate(self.trace.status, f"Step {step}: {self.trace.final_output or self.trace.status}.", self.trace.progress.snapshot()))
            self.log_step(self.log_path, "run-end", f"status: {self.trace.status}\nstep: {step}\nmessage: {self.trace.final_output}")
        return result

    def _emit(self, kind: str, message: str = "", **data: object) -> None:
        if not self.event_bus: return
        context = dict(self.event_context)
        self.event_bus.emit(
            self.event_layer,
            kind,
            message,
            task_id=str(context.pop("task_id", "")),
            agent_id=str(context.pop("agent_id", "")),
            stage=str(context.pop("stage", "")),
            **context,
            **data,
        )


def build_chat_model(
    *, trace: Any, status_cb: Callable[[RuntimeUpdate], None] | None, log_path: Path, model: str, max_steps: int,
    log_step: Callable[[Path | None, str, str], None], to_msg: Callable[[BaseMessage], dict[str, str] | None],
    dump_msg: Callable[[AIMessage], str], status_from_output: Callable[[str], tuple[str, str]],
    event_bus: EventBus | None = None, event_layer: str = "L3", event_context: dict[str, object] | None = None,
) -> BaseChatModel:
    return LoggingChatOpenAI(
        model=model,
        base_url=BASE_URL,
        api_key=API_KEY,
        temperature=0.2,
        use_responses_api=False,
        http_client=httpx.Client(trust_env=False),
        **chat_provider_options(),
        trace=trace,
        status_cb=status_cb,
        log_path=log_path,
        log_step=log_step,
        to_msg=to_msg,
        dump_msg=dump_msg,
        status_from_output=status_from_output,
        event_bus=event_bus,
        event_layer=event_layer,
        event_context=dict(event_context or {}),
        max_steps=max_steps,
    )
