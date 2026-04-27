from __future__ import annotations

import json, sys, threading, time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(slots=True)
class AgentEvent:
    layer: str
    kind: str
    message: str = ""
    task_id: str = ""
    agent_id: str = ""
    stage: str = ""
    data: dict[str, object] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, object]:
        item: dict[str, object] = {"type": self.kind, "time": self.ts, "layer": self.layer}
        if self.message: item["message"] = self.message
        if self.task_id: item["task_id"] = self.task_id
        if self.agent_id: item["agent_id"] = self.agent_id
        if self.stage: item["stage"] = self.stage
        for key, value in self.data.items():
            if key not in item:
                item[key] = value
        return item


class EventSink(Protocol):
    def emit(self, event: AgentEvent) -> None: ...


class EventBus:
    def __init__(self, sinks: list[EventSink] | None = None) -> None:
        self.sinks = list(sinks or [])

    def emit(
        self, layer: str, kind: str, message: str = "", *, task_id: str = "",
        agent_id: str = "", stage: str = "", data: dict[str, object] | None = None,
        **extra: object,
    ) -> None:
        payload = dict(data or {})
        payload.update(extra)
        event = AgentEvent(layer, kind, message, task_id, agent_id, stage, payload)
        for sink in self.sinks:
            try:
                sink.emit(event)
            except Exception:
                continue


class JsonlEventSink:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def emit(self, event: AgentEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")


class ConsoleEventSink:
    def __init__(self, stream=None, max_message: int = 240) -> None:
        self.stream = stream or sys.stdout
        self.max_message = max_message
        self._lock = threading.Lock()

    def emit(self, event: AgentEvent) -> None:
        scope = " ".join(x for x in (event.stage, event.task_id, event.agent_id) if x)
        head = f"[{event.layer} {event.kind}]"
        msg = self._short(event.message or self._fallback_message(event))
        line = f"{head} {scope} {msg}".rstrip()
        with self._lock:
            print(line, file=self.stream, flush=True)

    def _fallback_message(self, event: AgentEvent) -> str:
        for key in ("status", "tool", "summary", "output", "path"):
            if key in event.data:
                return str(event.data[key])
        return ""

    def _short(self, text: str) -> str:
        clean = " ".join(str(text).split())
        return clean if len(clean) <= self.max_message else clean[: self.max_message - 3] + "..."
