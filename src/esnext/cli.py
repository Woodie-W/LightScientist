"""CLI entrypoint for the current LightScientist skeleton."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .manager import StageManager
from .models import StageRequest


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


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "run":
        parser.error(f"Unsupported command: {args.command}")

    manager = StageManager()
    request = StageRequest(
        target=args.target,
        output_path=Path(args.output) if args.output else None,
        workspace_root=Path(args.workspace),
        use_agent=args.agent,
    )
    result = manager.handle(request)

    print(f"task_id: {result.task_id}")
    print(f"status: {result.status}")
    print(f"summary: {result.summary}")
    print(f"output: {result.output_path}")

    if result.notes:
        print("notes:")
        for note in result.notes:
            print(f"- {note}")

    return 0 if result.status == "completed" else 1
