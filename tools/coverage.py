#!/usr/bin/env python3
"""Coverage collection and parsing for fuzzing experiments.

Supports gcov, llvm-cov, and AFL++ bitmap-based coverage.

Usage:
    python tools/coverage.py --method afl-bitmap --output-dir /path/to/fuzzer/output
    python tools/coverage.py --method llvm-cov --corpus-dir /path/to/corpus --binary ./target
    python tools/coverage.py --method gcov --corpus-dir /path/to/corpus --binary ./target --source-dir ./src
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CoverageData:
    method: str
    edges: int = 0
    branches: int = 0
    lines: int = 0
    functions: int = 0
    total_edges: int = 0
    total_branches: int = 0
    total_lines: int = 0
    total_functions: int = 0
    edge_pct: float = 0.0
    branch_pct: float = 0.0
    line_pct: float = 0.0
    timeline: list[dict[str, float]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "edges": self.edges,
            "branches": self.branches,
            "lines": self.lines,
            "functions": self.functions,
            "total_edges": self.total_edges,
            "total_branches": self.total_branches,
            "total_lines": self.total_lines,
            "total_functions": self.total_functions,
            "edge_pct": self.edge_pct,
            "branch_pct": self.branch_pct,
            "line_pct": self.line_pct,
            "timeline": self.timeline,
        }


def collect_afl_bitmap(output_dir: str) -> CoverageData:
    """Extract coverage from AFL++ fuzzer_stats and plot_data."""
    cov = CoverageData(method="afl-bitmap")

    stats_file = None
    for child in Path(output_dir).iterdir():
        candidate = child / "fuzzer_stats"
        if candidate.exists():
            stats_file = candidate
            break
    if stats_file is None:
        stats_file = Path(output_dir) / "fuzzer_stats"

    if stats_file.exists():
        for line in stats_file.read_text().splitlines():
            if ":" not in line:
                continue
            key, val = line.split(":", 1)
            key, val = key.strip(), val.strip()
            if key == "edges_found":
                cov.edges = int(val)
            elif key == "total_edges":
                cov.total_edges = int(val)

        if cov.total_edges > 0:
            cov.edge_pct = cov.edges / cov.total_edges * 100

    plot_file = None
    for child in Path(output_dir).iterdir():
        candidate = child / "plot_data"
        if candidate.exists():
            plot_file = candidate
            break

    if plot_file and plot_file.exists():
        for line in plot_file.read_text().splitlines():
            if line.startswith("#"):
                continue
            parts = line.split(",")
            if len(parts) >= 6:
                try:
                    timestamp = int(parts[0].strip())
                    edges = int(parts[3].strip())
                    cov.timeline.append({"time": timestamp, "edges": edges})
                except (ValueError, IndexError):
                    pass

    return cov


def collect_llvm_cov(corpus_dir: str, binary: str, profraw_dir: str | None = None) -> CoverageData:
    """Collect coverage using llvm-cov by running corpus through the binary."""
    cov = CoverageData(method="llvm-cov")

    work_dir = profraw_dir or "/tmp/llvm-cov-work"
    os.makedirs(work_dir, exist_ok=True)

    merged_prof = os.path.join(work_dir, "merged.profdata")

    env = dict(os.environ)
    env["LLVM_PROFILE_FILE"] = os.path.join(work_dir, "test-%p.profraw")

    corpus = Path(corpus_dir)
    if corpus.is_dir():
        inputs = sorted(corpus.iterdir())
        for inp in inputs:
            if inp.is_file():
                try:
                    subprocess.run(
                        [binary, str(inp)],
                        env=env,
                        capture_output=True,
                        timeout=10,
                    )
                except (subprocess.TimeoutExpired, OSError):
                    pass

    profraw_files = list(Path(work_dir).glob("*.profraw"))
    if not profraw_files:
        return cov

    subprocess.run(
        ["llvm-profdata", "merge", "-sparse"]
        + [str(f) for f in profraw_files]
        + ["-o", merged_prof],
        capture_output=True,
    )

    result = subprocess.run(
        ["llvm-cov", "report", binary, f"-instr-profile={merged_prof}"],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        for line in result.stdout.splitlines():
            if line.startswith("TOTAL"):
                parts = line.split()
                try:
                    cov.lines = int(parts[1])
                    cov.total_lines = int(parts[2]) if len(parts) > 2 else 0
                    if cov.total_lines > 0:
                        cov.line_pct = cov.lines / cov.total_lines * 100
                except (ValueError, IndexError):
                    pass

    return cov


def collect_gcov(corpus_dir: str, binary: str, source_dir: str) -> CoverageData:
    """Collect coverage using gcov (requires -fprofile-arcs -ftest-coverage)."""
    cov = CoverageData(method="gcov")

    corpus = Path(corpus_dir)
    if corpus.is_dir():
        for inp in sorted(corpus.iterdir()):
            if inp.is_file():
                try:
                    subprocess.run(
                        [binary, str(inp)],
                        capture_output=True,
                        timeout=10,
                    )
                except (subprocess.TimeoutExpired, OSError):
                    pass

    gcda_files = list(Path(source_dir).rglob("*.gcda"))
    if not gcda_files:
        return cov

    result = subprocess.run(
        ["gcov", "-b"] + [str(f) for f in gcda_files],
        capture_output=True,
        text=True,
        cwd=source_dir,
    )

    total_lines = 0
    covered_lines = 0
    total_branches = 0
    covered_branches = 0

    for line in result.stdout.splitlines():
        if "Lines executed:" in line:
            try:
                pct_str = line.split(":")[1].split("%")[0].strip()
                count_str = line.split("of")[1].strip()
                total = int(count_str)
                covered = int(float(pct_str) / 100 * total)
                total_lines += total
                covered_lines += covered
            except (ValueError, IndexError):
                pass
        elif "Branches executed:" in line:
            try:
                pct_str = line.split(":")[1].split("%")[0].strip()
                count_str = line.split("of")[1].strip()
                total = int(count_str)
                covered = int(float(pct_str) / 100 * total)
                total_branches += total
                covered_branches += covered
            except (ValueError, IndexError):
                pass

    cov.lines = covered_lines
    cov.total_lines = total_lines
    cov.branches = covered_branches
    cov.total_branches = total_branches
    if total_lines > 0:
        cov.line_pct = covered_lines / total_lines * 100
    if total_branches > 0:
        cov.branch_pct = covered_branches / total_branches * 100

    return cov


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect fuzzing coverage data")
    parser.add_argument("--method", required=True, choices=["afl-bitmap", "llvm-cov", "gcov"])
    parser.add_argument("--output-dir", help="Fuzzer output directory (for afl-bitmap)")
    parser.add_argument("--corpus-dir", help="Corpus directory (for llvm-cov, gcov)")
    parser.add_argument("--binary", help="Target binary (for llvm-cov, gcov)")
    parser.add_argument("--source-dir", help="Source directory (for gcov)")
    parser.add_argument("--save", help="Save results to JSON file")
    args = parser.parse_args()

    if args.method == "afl-bitmap":
        if not args.output_dir:
            parser.error("--output-dir required for afl-bitmap method")
        cov = collect_afl_bitmap(args.output_dir)
    elif args.method == "llvm-cov":
        if not args.corpus_dir or not args.binary:
            parser.error("--corpus-dir and --binary required for llvm-cov method")
        cov = collect_llvm_cov(args.corpus_dir, args.binary)
    elif args.method == "gcov":
        if not args.corpus_dir or not args.binary or not args.source_dir:
            parser.error("--corpus-dir, --binary, and --source-dir required for gcov")
        cov = collect_gcov(args.corpus_dir, args.binary, args.source_dir)
    else:
        parser.error(f"Unknown method: {args.method}")
        return

    result = cov.to_dict()

    if args.save:
        with open(args.save, "w") as f:
            json.dump(result, f, indent=2)
        print(f"[coverage] Saved to {args.save}")

    print(f"[coverage] Method: {cov.method}")
    if cov.edges:
        print(f"[coverage] Edges: {cov.edges}/{cov.total_edges} ({cov.edge_pct:.1f}%)")
    if cov.branches:
        print(f"[coverage] Branches: {cov.branches}/{cov.total_branches} ({cov.branch_pct:.1f}%)")
    if cov.lines:
        print(f"[coverage] Lines: {cov.lines}/{cov.total_lines} ({cov.line_pct:.1f}%)")
    if cov.timeline:
        print(f"[coverage] Timeline: {len(cov.timeline)} data points")

    print(f"METRIC branch_cov={cov.edges or cov.branches or cov.lines}")


if __name__ == "__main__":
    main()
