from __future__ import annotations

import os, re, subprocess, sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

import requests

ENV = {"PAGER": "cat", "MANPAGER": "cat", "LESS": "-R", "PIP_PROGRESS_BAR": "off", "TQDM_DISABLE": "1"}
FORMAT_MSG = "Your output was malformatted.\nPlease include exactly 1 action formatted as:\n\n```bash-action\nls -R\n```"
SYS = "You are a helpful assistant. When you want to run a command, wrap it in ```bash-action\\n<command>\\n```. To finish, run the exit command."
BASE_URL = os.getenv("LIGHTSCIENTIST_BASE_URL", "http://100.104.128.29:1234/v1")
MODEL = os.getenv("LIGHTSCIENTIST_MODEL", "unsloth/qwen3.5-35b-a3b")
API_KEY = os.getenv("LIGHTSCIENTIST_API_KEY", "lmstudio")


class AgentRuntimeError(RuntimeError): ...
class NonTerminatingError(AgentRuntimeError): ...
class ActionFormatError(NonTerminatingError): ...
class ActionTimeoutError(NonTerminatingError): ...
class ModelRequestError(NonTerminatingError): ...
class TerminationRequested(AgentRuntimeError): ...


@dataclass(slots=True)
class AgentRunResult:
    status: Literal["completed", "failed", "terminated", "max_steps_reached"]
    messages: list[dict[str, str]]
    last_model_output: str = ""
    last_action: str = ""
    final_output: str = ""
    step_count: int = 0
    error: str = ""
    command_outputs: list[str] = field(default_factory=list)


def log_step(log_path: Path | None, title: str, body: str = "") -> None:
    if not log_path:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"[{title}]\n")
        if body:
            f.write(body.rstrip() + "\n")
        f.write("\n")


def query_lm(messages: list[dict[str, str]], model: str = MODEL, base_url: str = BASE_URL, api_key: str = API_KEY) -> str:
    os.environ.update({k: "" for k in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"]})
    s = requests.Session()
    s.trust_env = False
    try:
        r = s.post(
            f"{base_url}/chat/completions",
            json={"model": model, "messages": messages, "temperature": 0.2},
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=30,
        )
    except Exception as e:
        raise ModelRequestError(f"Model request failed: {e}") from e
    if r.status_code != 200:
        raise ModelRequestError(f"Model request failed with status {r.status_code}: {r.text[:400]}")
    try:
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        raise ModelRequestError(f"Model response parse failed: {e}") from e


def parse_action(text: str) -> str:
    matches = re.findall(r"```bash-action\s*\n(.*?)\n```", text, re.DOTALL)
    if len(matches) != 1:
        raise ActionFormatError(FORMAT_MSG)
    return matches[0].strip()


def execute_action(command: str, cwd: Path | None = None, env: dict[str, str] | None = None, timeout: int = 30) -> str:
    if command.strip() == "exit":
        raise TerminationRequested("LM requested to quit")
    try:
        r = subprocess.run(
            command, shell=True, text=True, cwd=str(cwd) if cwd else None, env=os.environ | ENV | (env or {}),
            encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise ActionTimeoutError("Your last command timed out. Avoid interactive tools and try a shorter non-interactive command.") from e
    return r.stdout


def run_agent(
    goal: str, *, cwd: str | Path | None = None, model: str = MODEL, max_steps: int = 8,
    extra_env: dict[str, str] | None = None, query_fn: Callable[[list[dict[str, str]]], str] | None = None,
    system_prompt: str = SYS, status_cb: Callable[[str, str], None] | None = None, log_path: str | Path | None = None,
) -> AgentRunResult:
    query = query_fn or (lambda msgs: query_lm(msgs, model))
    wd = Path(cwd).resolve() if cwd else None
    lp = Path(log_path).resolve() if log_path else (wd / "agent-debug.log" if wd else None)
    msgs = [{"role": "system", "content": system_prompt}, {"role": "user", "content": goal}]
    log_step(lp, "run-start", f"goal: {goal}\nmodel: {model}\nmax_steps: {max_steps}\ncwd: {wd}")
    last_out = last_action = last_lm = ""
    outs: list[str] = []
    for step in range(1, max_steps + 1):
        try:
            if status_cb:
                status_cb("running", f"Step {step}: querying model.")
            last_lm = query(msgs)
            log_step(lp, f"step-{step}-model-output", last_lm)
            msgs.append({"role": "assistant", "content": last_lm})
            last_action = parse_action(last_lm)
            log_step(lp, f"step-{step}-action", last_action)
            if status_cb:
                status_cb("running", f"Step {step}: running {last_action[:80]}.")
            last_out = execute_action(last_action, cwd=wd, env=extra_env)
            log_step(lp, f"step-{step}-command-output", last_out)
            outs.append(last_out)
            msgs.append({"role": "user", "content": last_out})
        except NonTerminatingError as e:
            last_out = str(e)
            log_step(lp, f"step-{step}-non-terminating-error", last_out)
            if status_cb:
                status_cb("blocked", last_out)
            msgs.append({"role": "user", "content": last_out})
        except TerminationRequested as e:
            log_step(lp, "run-end", f"status: terminated\nstep: {step}\nmessage: {e}")
            return AgentRunResult("terminated", msgs, last_lm, last_action, str(e), step, command_outputs=outs)
    log_step(lp, "run-end", f"status: max_steps_reached\nstep: {max_steps}\nmessage: Maximum step limit reached.")
    return AgentRunResult("max_steps_reached", msgs, last_lm, last_action, last_out, max_steps, "Maximum step limit reached.", outs)


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
    return 0 if result.status in {"completed", "terminated"} else 1
