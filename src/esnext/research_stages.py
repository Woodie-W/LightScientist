"""First-layer research stage table."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class StageSpec:
    name: str
    phase: str
    skill_path: str
    output_path: str
    default_next: str
    allowed_next: tuple[str, ...] = field(default_factory=tuple)
    human_gate: bool = False


SKILL_ROOT = Path(__file__).resolve().parents[2] / "skills"


def _skill(name: str) -> str:
    return str(SKILL_ROOT / name / "SKILL.md")


STAGES: dict[str, StageSpec] = {
    "idea.survey": StageSpec("idea.survey", "idea", _skill("idea-survey"), "phase1-idea/LITERATURE_SURVEY.md", "idea.generate", ("idea.generate", "idea.evaluate")),
    "idea.generate": StageSpec("idea.generate", "idea", _skill("idea-generate"), "phase1-idea/IDEAS_CANDIDATES.md", "idea.evaluate", ("idea.survey", "idea.evaluate", "idea.probe_batch")),
    "idea.evaluate": StageSpec("idea.evaluate", "idea", _skill("idea-evaluate"), "phase1-idea/IDEA_REPORT.md", "idea.gate", ("idea.survey", "idea.generate", "idea.probe_batch", "idea.gate")),
    "idea.probe_batch": StageSpec("idea.probe_batch", "idea", _skill("idea-probe"), "phase1-idea/probes", "idea.probe_collect", ("idea.generate", "idea.evaluate", "idea.probe_collect")),
    "idea.probe_collect": StageSpec("idea.probe_collect", "idea", _skill("idea-probe-collect"), "phase1-idea/PROBE_SUMMARY.md", "idea.gate", ("idea.generate", "idea.evaluate", "idea.gate")),
    "idea.gate": StageSpec("idea.gate", "idea", "", "phase1-idea/IDEA_REPORT.md", "experiment.setup", ("experiment.setup", "idea.generate", "idea.probe_batch"), True),
    "experiment.setup": StageSpec("experiment.setup", "experiment", _skill("fuzz-setup"), "phase2-experiment/SETUP_COMPLETE.md", "experiment.loop", ("experiment.loop",)),
    "experiment.loop": StageSpec("experiment.loop", "experiment", _skill("fuzz-loop"), "phase2-experiment/EXPERIMENT_RESULTS.md", "experiment.analyze", ("experiment.setup", "experiment.analyze", "experiment.gate")),
    "experiment.analyze": StageSpec("experiment.analyze", "experiment", _skill("fuzz-analyze"), "phase2-experiment/EXPERIMENT_RESULTS.md", "experiment.gate", ("experiment.loop", "experiment.gate")),
    "experiment.gate": StageSpec("experiment.gate", "experiment", _skill("fuzz-analyze"), "phase2-experiment/EXPERIMENT_RESULTS.md", "paper.plan", ("paper.plan", "experiment.loop", "experiment.analyze"), True),
    "paper.plan": StageSpec("paper.plan", "paper", _skill("paper-plan"), "phase3-paper/PAPER_PLAN.md", "paper.figure", ("paper.figure", "paper.write")),
    "paper.figure": StageSpec("paper.figure", "paper", _skill("paper-figure"), "phase3-paper/figures", "paper.write", ("paper.write", "paper.review")),
    "paper.write": StageSpec("paper.write", "paper", _skill("paper-write"), "phase3-paper/paper/main.pdf", "paper.review", ("paper.figure", "paper.review")),
    "paper.review": StageSpec("paper.review", "paper", _skill("paper-review"), "phase3-paper/PAPER_SUMMARY.md", "done", ("paper.write", "done")),
}

PHASE_DESCRIPTIONS = {
    "idea": (
        "idea.survey: collect and read related work",
        "idea.generate: generate candidate ideas",
        "idea.evaluate: evaluate novelty and feasibility",
        "idea.probe_batch: run small feasibility probes",
        "idea.probe_collect: compare probe reports",
        "idea.gate: decide whether to enter formal experiments",
    ),
    "experiment": (
        "experiment.setup: prepare fuzzer, target, seeds, and smoke test",
        "experiment.loop: run the autonomous experiment loop",
        "experiment.analyze: analyze results and write experiment report",
        "experiment.gate: decide whether to enter paper writing",
    ),
    "paper": (
        "paper.plan: plan the paper",
        "paper.figure: produce figures and tables",
        "paper.write: write and compile the paper",
        "paper.review: review and summarize the paper",
    ),
}


def stage_spec(name: str) -> StageSpec:
    if name not in STAGES:
        raise KeyError(f"Unknown research stage: {name}")
    return STAGES[name]
