"""CLI entrypoint for the current LightScientist skeleton."""

from __future__ import annotations

import argparse, sys, time
from pathlib import Path
from typing import Sequence

from .manager import StageManager
from .data_models import ExecutionResult, StageRequest
from .events import ConsoleEventSink, EventBus, JsonlEventSink
from .research_controller import ResearchController
from .webui_api import serve_webui

OK_STATES = {"completed", "waiting", "background"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lightscientist",
        description="Current LightScientist three-layer skeleton prototype.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run one normalized task.")
    run_parser.add_argument("target", help="Task target: file path, directory path, note text, or agent goal.")
    run_parser.add_argument(
        "--output",
        help="Path to the markdown artifact written by the execution layer.",
    )
    run_parser.add_argument(
        "--workspace",
        default=".",
        help="Workspace root used to resolve relative task paths.",
    )
    run_parser.add_argument("--agent", action="store_true", help="Send the target to the minimal agent runtime.")
    run_parser.add_argument("--watch", action="store_true", help="Print live agent events while the task runs.")

    research_parser = subparsers.add_parser("research", help="Run one first-layer research stage.")
    research_parser.add_argument("topic", nargs="?", default="", help="Research goal or task description used when initializing a project.")
    research_parser.add_argument("--workspace", default=".", help="Workspace root for research state and artifacts.")
    research_parser.add_argument("--mode", choices=["auto", "manual"], default="manual", help="Gate mode for phase transitions.")
    research_parser.add_argument("--stage", default="idea.survey", help="Starting stage for a new project, e.g. idea.survey or experiment.setup.")
    research_parser.add_argument("--reply", help="Reply to a pending manual decision with `y [note]` or `n [note]`.")
    research_parser.add_argument("--watch", action="store_true", help="Print live agent events while the research controller runs.")

    webui_parser = subparsers.add_parser("webui", help="Serve the minimal LightScientist WebUI.")
    webui_parser.add_argument("--workspace", default=".", help="Workspace root to inspect.")
    webui_parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    webui_parser.add_argument("--port", type=int, default=8765, help="Bind port.")
    return parser


def print_result(result: ExecutionResult) -> None:
    print(f"task_id: {result.task_id}")
    print(f"status: {result.status}")
    print(f"summary: {result.summary}")
    print(f"output: {result.output_path}")
    if result.notes:
        print("notes:")
        for note in result.notes:
            print(f"- {note}")


def run_once(
    manager: StageManager, target: str, workspace: str | Path = ".", output: str | Path | None = None, use_agent: bool = False
) -> int:
    result = manager.handle(
        StageRequest(
            target=target,
            output_path=Path(output) if output else None,
            workspace_root=Path(workspace),
            use_agent=use_agent,
        )
    )
    print_result(result)
    return 0 if result.status in OK_STATES else 1


def build_event_bus(workspace: str | Path, watch: bool = False) -> EventBus:
    path = Path(workspace).resolve() / ".lightscientist" / "events.jsonl"
    sinks = [JsonlEventSink(path)]
    if watch:
        sinks.append(ConsoleEventSink())
    return EventBus(sinks)


def repl(manager: StageManager | None = None, workspace: str | Path = ".") -> int:
    manager = manager or StageManager()
    print("LightScientist REPL. Type `exit` or `quit` to leave.")
    while True:
        try:
            target = input("lightscientist> ").strip()
        except EOFError:
            print()
            return 0
        if not target:
            time.sleep(0.05)
            continue
        if target in {"exit", "quit"}:
            return 0
        run_once(manager, target, workspace=workspace, use_agent=True)
        time.sleep(0.05)


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return repl()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "research":
        event_bus = build_event_bus(args.workspace, args.watch)
        controller = ResearchController(args.workspace, topic=args.topic, mode=args.mode, start_stage=args.stage, event_bus=event_bus)
        result = controller.reply_user(args.reply) if args.reply else controller.run()
        print_result(result)
        return 0 if result.status in OK_STATES else 1
    if args.command == "webui":
        serve_webui(args.workspace, host=args.host, port=args.port)
        return 0
    if args.command != "run": parser.error(f"Unsupported command: {args.command}")
    event_bus = build_event_bus(args.workspace, args.watch)
    return run_once(StageManager(event_bus=event_bus), args.target, workspace=args.workspace, output=args.output, use_agent=args.agent)
