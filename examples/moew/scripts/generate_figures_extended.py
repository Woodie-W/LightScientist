#!/usr/bin/env python3
"""Regenerate figures/tables from attempts_merged.json (local + remote git)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

ROOT = Path(__file__).resolve().parent
FIG = ROOT / "figures"
FIG.mkdir(parents=True, exist_ok=True)

manifest = json.loads((ROOT / "attempts_merged.json").read_text())
local = manifest["local_attempts"]
remote = manifest["remote_attempts"]

remote_scored = [(r["eval_num"], r["score"]) for r in remote if r.get("score") is not None]
remote_scored.sort(key=lambda x: x[0])
local_scored = [(r["eval_num"], r["score"]) for r in local if r.get("score") is not None]

best_remote = max(remote_scored, key=lambda x: x[1])
best_local = max(local_scored, key=lambda x: x[1]) if local_scored else (0, 0.0)

# --- Figure 1: Remote full trajectory ---
fig, ax = plt.subplots(figsize=(14, 5.5))
nums = [x[0] for x in remote_scored]
scores = [x[1] for x in remote_scored]
ax.plot(nums, scores, "-", color="#1f77b4", linewidth=0.8, alpha=0.7)
# running best
run_best = []
cur = -1.0
for n, s in remote_scored:
    cur = max(cur, s)
    run_best.append((n, cur))
ax.plot([x[0] for x in run_best], [x[1] for x in run_best], "-", color="#d62728", linewidth=2, label="Running best")
ax.axhline(0.022, color="gray", linestyle=":", linewidth=1, alpha=0.6, label="Baseline 0.022")
ax.annotate(
    f"Best: {best_remote[1]:.5f}\n(eval #{best_remote[0]})",
    xy=best_remote,
    xytext=(best_remote[0] - 80, best_remote[1] + 0.008),
    arrowprops=dict(arrowstyle="->", color="darkred", lw=1.5),
    fontsize=9,
    fontweight="bold",
    color="darkred",
)
ax.set_xlabel("Evaluation Number (remote git)", fontsize=11, fontweight="bold")
ax.set_ylabel("Test-set Pearson", fontsize=11, fontweight="bold")
ax.set_title(
    f"MEOW Remote Run: {len(remote)} eval tags, {len(remote_scored)} scored",
    fontsize=13,
    fontweight="bold",
)
ax.set_xlim(0, max(nums) + 5)
ax.set_ylim(0.02, max(scores) * 1.05)
ax.legend(loc="lower right", fontsize=8)
ax.grid(True, alpha=0.3, linestyle="--")
plt.tight_layout()
fig.savefig(FIG / "figure1_remote_trajectory.pdf", dpi=150, bbox_inches="tight")
fig.savefig(FIG / "figure1_remote_trajectory.png", dpi=150, bbox_inches="tight")
plt.close()

# --- Figure 1b: Local CORAL run ---
fig, ax = plt.subplots(figsize=(12, 5))
nums_l = [x[0] for x in local_scored]
scores_l = [x[1] for x in local_scored]
ax.plot(nums_l, scores_l, "o-", color="#2ca02c", markersize=5, linewidth=1.5)
ax.annotate(
    f"Local best: {best_local[1]:.5f}\n(eval #{best_local[0]})",
    xy=best_local,
    xytext=(best_local[0] - 8, best_local[1] + 0.002),
    arrowprops=dict(arrowstyle="->", color="darkgreen", lw=1.5),
    fontsize=9,
    fontweight="bold",
    color="darkgreen",
)
ax.axhline(0.0677807047, color="#8c564b", linestyle="--", linewidth=1, label="Old report best (0.06778)")
ax.set_xlabel("Evaluation Number (local CORAL run)", fontsize=11, fontweight="bold")
ax.set_ylabel("Test-set Pearson", fontsize=11, fontweight="bold")
ax.set_title(f"Local CORAL Run 2026-05-19_112312: {len(local)} attempts", fontsize=13, fontweight="bold")
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)
plt.tight_layout()
fig.savefig(FIG / "figure1b_local_trajectory.pdf", dpi=150, bbox_inches="tight")
fig.savefig(FIG / "figure1b_local_trajectory.png", dpi=150, bbox_inches="tight")
plt.close()

# --- Table 1: top 30 remote ---
top_remote = sorted(
    [r for r in remote if r.get("score") is not None],
    key=lambda x: x["score"],
    reverse=True,
)[:30]
lines = [
    r"\\begin{tabular}{rlrr}",
    r"\\toprule",
    r"Rank & Eval & Pearson & Title \\\\",
    r"\\midrule",
]
for i, r in enumerate(top_remote, 1):
    title = re.sub(r"[_%&]", "", (r.get("title") or "")[:60])
    lines.append(
        f"{i} & {r['eval_num']} & {r['score']:.6f} & {title} \\\\"
    )
lines += [r"\\bottomrule", r"\\end{tabular}"]
(FIG / "table1_top_remote.tex").write_text("\n".join(lines))

# --- Table 2: phase milestones (auto by eval ranges) ---
milestones = [
    (1, "Baseline / early features"),
    (50, "~0.05+ feature expansion"),
    (150, "Nonlinear gates / pruning"),
    (250, "Blend models (LGB/XGB)"),
    (350, "NN residual / DeepLOB / Pearson NN"),
    (400, "Ridge alpha tuning (cs/time/rank)"),
    (best_remote[0], f"Global best eval #{best_remote[0]}"),
]
lines = [
    r"\\begin{tabular}{rlp{6cm}}",
    r"\\toprule",
    r"Eval & Pearson & Milestone \\\\",
    r"\\midrule",
]
for ev, label in milestones:
    scored_at = [s for n, s in remote_scored if n <= ev]
    p = scored_at[-1] if scored_at else 0.0
    best_at = max(scored_at) if scored_at else 0.0
    lines.append(f"{ev} & {best_at:.5f} & {label} \\\\")
lines += [r"\\bottomrule", r"\\end{tabular}"]
(FIG / "table2_phase_milestones.tex").write_text("\n".join(lines))

# --- Summary markdown for paper agent ---
summary = f"""# Extended Figures Report

**Generated from:** `attempts_merged.json`

## Data coverage

| Source | Count | Best Pearson |
|--------|-------|--------------|
| Local CORAL (`2026-05-19_112312`) | {len(local)} attempts | {best_local[1]:.6f} (eval #{best_local[0]}) |
| Remote git (`source_remote` tags) | {len(remote)} eval tags | {best_remote[1]:.6f} (eval #{best_remote[0]}) |

## Outputs

- `figures/figure1_remote_trajectory.pdf/png` — full remote eval trajectory
- `figures/figure1b_local_trajectory.pdf/png` — local CORAL continuation
- `figures/table1_top_remote.tex` — top 30 remote attempts
- `figures/table2_phase_milestones.tex` — coarse phase milestones

## Notes for paper.write

- Prior report (2026-05-26) covered only **46 local evals**, best **0.06778**.
- Remote continuation adds **eval 47–443** with best **{best_remote[1]:.6f}**.
- Local machine run added **{len(local)}** more attempts after resume; best **{best_local[1]:.6f}** (below remote best — remote is authoritative for peak score).
- Use `source_remote` + `attempts_merged.json` as primary trajectory; local run as supplementary WSL session.
"""
(ROOT / "FIGURES_REPORT_EXTENDED.md").write_text(summary)
print(summary)
