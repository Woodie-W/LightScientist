#!/usr/bin/env python3
"""Crash deduplication and triage for fuzzing experiments.

Deduplicates crashes by stack hash, categorizes by ASAN error type,
and computes time-to-first-crash metrics.

Usage:
    python tools/crash.py --crash-dir results/run-001/trial-01/crashes/ --binary ./target
    python tools/crash.py --crash-dirs results/run-001/trial-*/crashes/ --binary ./target --output crash_analysis.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CrashInfo:
    file_path: str
    stack_hash: str
    error_type: str = "unknown"
    stack_trace: str = ""
    file_size: int = 0
    discovery_time: float | None = None

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "stack_hash": self.stack_hash,
            "error_type": self.error_type,
            "stack_trace_preview": self.stack_trace[:500] if self.stack_trace else "",
            "file_size": self.file_size,
            "discovery_time": self.discovery_time,
        }


@dataclass
class CrashAnalysis:
    total_crashes: int = 0
    unique_crashes: int = 0
    categories: dict[str, int] = field(default_factory=dict)
    unique_crash_list: list[CrashInfo] = field(default_factory=list)
    time_to_first_crash: float | None = None

    def to_dict(self) -> dict:
        return {
            "total_crashes": self.total_crashes,
            "unique_crashes": self.unique_crashes,
            "categories": self.categories,
            "time_to_first_crash": self.time_to_first_crash,
            "crashes": [c.to_dict() for c in self.unique_crash_list],
        }


def get_stack_trace(binary: str, crash_input: str, timeout: int = 10) -> str:
    """Run the target with the crash input and capture the ASAN stack trace."""
    env = dict(os.environ)
    env["ASAN_OPTIONS"] = "abort_on_error=1:symbolize=1:detect_leaks=0"

    try:
        result = subprocess.run(
            [binary, crash_input],
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stderr
    except subprocess.TimeoutExpired:
        return ""
    except OSError:
        return ""


def compute_stack_hash(stack_trace: str) -> str:
    """Hash the top N frames of a stack trace for deduplication."""
    frames: list[str] = []
    for line in stack_trace.splitlines():
        line = line.strip()
        match = re.match(r"#\d+\s+\S+\s+in\s+(\S+)", line)
        if match:
            frames.append(match.group(1))
            if len(frames) >= 5:
                break

    if not frames:
        match_summary = re.search(r"(SUMMARY: \S+ \S+)", stack_trace)
        if match_summary:
            frames.append(match_summary.group(1))

    if not frames:
        return hashlib.md5(stack_trace.encode()).hexdigest()[:12]

    key = "|".join(frames)
    return hashlib.md5(key.encode()).hexdigest()[:12]


def classify_error(stack_trace: str) -> str:
    """Classify the error type from an ASAN/UBSAN stack trace."""
    patterns = {
        "heap-buffer-overflow": r"heap-buffer-overflow",
        "stack-buffer-overflow": r"stack-buffer-overflow",
        "global-buffer-overflow": r"global-buffer-overflow",
        "use-after-free": r"heap-use-after-free",
        "use-after-return": r"use-after-return",
        "double-free": r"double-free|attempting free on",
        "memory-leak": r"detected memory leaks",
        "stack-overflow": r"stack-overflow",
        "null-deref": r"SEGV on unknown address 0x0+\b",
        "segfault": r"SEGV|segmentation fault",
        "integer-overflow": r"integer overflow",
        "divide-by-zero": r"division by zero",
        "undefined-behavior": r"undefined behavior|UndefinedBehaviorSanitizer",
        "assertion-failure": r"assertion|ASSERT|abort",
    }

    trace_lower = stack_trace.lower()
    for error_type, pattern in patterns.items():
        if re.search(pattern, stack_trace, re.IGNORECASE):
            return error_type

    if "ERROR:" in stack_trace:
        return "asan-other"
    return "unknown"


def analyze_crashes(
    crash_dirs: list[str],
    binary: str | None = None,
    use_stack_hash: bool = True,
) -> CrashAnalysis:
    """Analyze crash files across one or more directories."""
    analysis = CrashAnalysis()
    seen_hashes: dict[str, CrashInfo] = {}
    all_crashes: list[CrashInfo] = []

    for crash_dir in crash_dirs:
        crash_path = Path(crash_dir)
        if not crash_path.exists():
            continue

        for crash_file in sorted(crash_path.iterdir()):
            if not crash_file.is_file():
                continue
            if crash_file.name.startswith(".") or crash_file.name == "README.txt":
                continue

            analysis.total_crashes += 1

            stack_trace = ""
            if binary and use_stack_hash:
                stack_trace = get_stack_trace(binary, str(crash_file))

            if stack_trace:
                stack_hash = compute_stack_hash(stack_trace)
                error_type = classify_error(stack_trace)
            else:
                content = crash_file.read_bytes()
                stack_hash = hashlib.md5(content).hexdigest()[:12]
                error_type = "unknown"

            mtime = crash_file.stat().st_mtime
            crash_info = CrashInfo(
                file_path=str(crash_file),
                stack_hash=stack_hash,
                error_type=error_type,
                stack_trace=stack_trace,
                file_size=crash_file.stat().st_size,
                discovery_time=mtime,
            )
            all_crashes.append(crash_info)

            if stack_hash not in seen_hashes:
                seen_hashes[stack_hash] = crash_info

    analysis.unique_crashes = len(seen_hashes)
    analysis.unique_crash_list = list(seen_hashes.values())

    for crash in analysis.unique_crash_list:
        analysis.categories[crash.error_type] = (
            analysis.categories.get(crash.error_type, 0) + 1
        )

    if all_crashes:
        times = [c.discovery_time for c in all_crashes if c.discovery_time is not None]
        if times:
            analysis.time_to_first_crash = min(times)

    return analysis


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze fuzzing crashes")
    parser.add_argument("--crash-dir", help="Single crash directory")
    parser.add_argument("--crash-dirs", nargs="+", help="Multiple crash directories")
    parser.add_argument("--binary", help="Target binary for stack trace replay")
    parser.add_argument("--no-replay", action="store_true", help="Skip crash replay, use file hash only")
    parser.add_argument("--output", help="Save analysis to JSON file")
    args = parser.parse_args()

    crash_dirs: list[str] = []
    if args.crash_dir:
        crash_dirs.append(args.crash_dir)
    if args.crash_dirs:
        crash_dirs.extend(args.crash_dirs)

    if not crash_dirs:
        parser.error("Provide --crash-dir or --crash-dirs")

    analysis = analyze_crashes(
        crash_dirs,
        binary=args.binary,
        use_stack_hash=not args.no_replay,
    )

    result = analysis.to_dict()

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        print(f"[crash] Saved analysis to {args.output}")

    print(f"[crash] Total crashes: {analysis.total_crashes}")
    print(f"[crash] Unique crashes: {analysis.unique_crashes}")
    if analysis.categories:
        print(f"[crash] Categories: {analysis.categories}")

    print(f"METRIC unique_crashes={analysis.unique_crashes}")


if __name__ == "__main__":
    main()
