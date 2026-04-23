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

BASE_URL = os.getenv("LIGHTSCIENTIST_BASE_URL", "http://100.104.128.29:1234/v1")
MODEL = os.getenv("LIGHTSCIENTIST_MODEL", "unsloth/qwen3.5-35b-a3b")
API_KEY = os.getenv("LIGHTSCIENTIST_API_KEY", "lmstudio")


class LoggingChatOpenAI(ChatOpenAI):
    trace: Any = Field(exclude=True)
    status_cb: Callable[[str, str], None] | None = Field(default=None, exclude=True)
    log_path: Path | None = Field(default=None, exclude=True)
    log_step: Callable[[Path | None, str, str], None] = Field(exclude=True)
    to_msg: Callable[[BaseMessage], dict[str, str] | None] = Field(exclude=True)
    dump_msg: Callable[[AIMessage], str] = Field(exclude=True)
    status_from_output: Callable[[str], tuple[str, str]] = Field(exclude=True)
    max_steps: int = 8
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def _llm_type(self) -> str:
        return "lightscientist-chatopenai"

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None, run_manager: Any = None, **kwargs: Any) -> ChatResult:
        if self.trace.step_count >= self.max_steps:
            self.trace.status, self.trace.max_steps_reached, self.trace.error = "failed", True, "Maximum step limit reached."
            self.log_step(self.log_path, "run-end", f"status: max_steps_reached\nstep: {self.trace.step_count}\nmessage: {self.trace.error}")
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        self.trace.step_count += 1
        step = self.trace.step_count
        self.trace.messages = [m for msg in messages if (m := self.to_msg(msg))]
        if self.status_cb:
            self.status_cb("running", f"Step {step}: querying model.")
        result = super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        msg = result.generations[0].message
        self.trace.last_model_output = self.dump_msg(msg)
        self.log_step(self.log_path, f"step-{step}-model-output", self.trace.last_model_output)
        if msg.tool_calls:
            call = msg.tool_calls[0]
            self.trace.last_action = f'{call["name"]}: {call["args"]}'
            self.log_step(self.log_path, f"step-{step}-tool-call", self.trace.last_action)
            if self.status_cb:
                self.status_cb("running", f'Step {step}: calling {call["name"]}.')
        else:
            self.trace.status, self.trace.final_output = self.status_from_output(str(msg.content or ""))
            self.log_step(self.log_path, f"step-{step}-final-answer", self.trace.final_output)
            if self.status_cb:
                self.status_cb(self.trace.status, f"Step {step}: {self.trace.final_output or self.trace.status}.")
            self.log_step(self.log_path, "run-end", f"status: {self.trace.status}\nstep: {step}\nmessage: {self.trace.final_output}")
        return result


def build_chat_model(
    *, trace: Any, status_cb: Callable[[str, str], None] | None, log_path: Path, model: str, max_steps: int,
    log_step: Callable[[Path | None, str, str], None], to_msg: Callable[[BaseMessage], dict[str, str] | None],
    dump_msg: Callable[[AIMessage], str], status_from_output: Callable[[str], tuple[str, str]],
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
        log_step=log_step,
        to_msg=to_msg,
        dump_msg=dump_msg,
        status_from_output=status_from_output,
        max_steps=max_steps,
    )
