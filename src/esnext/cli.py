"""CLI entrypoint for the current LightScientist skeleton."""

from __future__ import annotations

import argparse, sys
from pathlib import Path
from typing import Sequence

from .manager import StageManager
from .models import ExecutionResult, StageRequest


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
    return 0 if result.status == "completed" else 1


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
            continue
        if target in {"exit", "quit"}:
            return 0
        run_once(manager, target, workspace=workspace, use_agent=True)


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return repl()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "run": parser.error(f"Unsupported command: {args.command}")
    return run_once(StageManager(), args.target, workspace=args.workspace, output=args.output, use_agent=args.agent)
