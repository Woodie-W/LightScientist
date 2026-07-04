from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .research_stages import PHASE_DESCRIPTIONS, STAGES, stage_spec


def workspace_root(path: str | Path) -> Path:
    return Path(path).resolve()


def state_path(root: Path) -> Path:
    return root / ".lightscientist" / "project_state.json"


def events_path(root: Path) -> Path:
    return root / ".lightscientist" / "events.jsonl"


def resolve_workspace_path(root: Path, relative_path: str) -> Path:
    path = (root / relative_path).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("path outside workspace") from exc
    return path


def _read_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return dict(default or {})
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(default or {})


def read_state(root: Path) -> dict[str, Any]:
    return _read_json(state_path(root), {"status": "idle", "phase": "", "stage": "", "topic": "", "workspace_root": str(root)})


def read_events(root: Path, limit: int = 200) -> list[dict[str, Any]]:
    path = events_path(root)
    if not path.exists():
        return []
    items: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except Exception:
            continue
    return items[-limit:]


def stage_runs(root: Path) -> list[dict[str, Any]]:
    base = root / ".lightscientist" / "stage-runs"
    if not base.exists():
        return []
    runs = []
    for path in sorted(base.glob("*/agent-run.md")):
        runs.append(
            {
                "task_id": path.parent.name,
                "path": str(path.relative_to(root)),
                "updated_at": path.stat().st_mtime,
                "summary": _first_nonempty(path.read_text(encoding="utf-8").splitlines()[10:20]) if path.exists() else "",
            }
        )
    return list(reversed(runs))


def _first_nonempty(lines: list[str]) -> str:
    for line in lines:
        line = line.strip()
        if line:
            return line
    return ""


def list_artifacts(root: Path, limit: int = 24) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for prefix in ("phase1-idea", "phase2-experiment", "phase3-paper"):
        base = root / prefix
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            items.append(
                {
                    "path": str(path.relative_to(root)),
                    "size": path.stat().st_size,
                    "updated_at": path.stat().st_mtime,
                    "kind": prefix,
                }
            )
    items.sort(key=lambda item: float(item["updated_at"]), reverse=True)
    return items[:limit]


def artifact_phases(root: Path) -> list[dict[str, Any]]:
    groups = [
        ("idea", "Idea", ["phase1-idea"]),
        ("experiment", "Experiment", ["phase2-experiment", "research.md", "research.jsonl", "research-dashboard.md", "research.ideas.md"]),
        ("paper", "Paper", ["phase3-paper"]),
    ]
    phases: list[dict[str, Any]] = []
    for key, title, paths in groups:
        items: list[dict[str, Any]] = []
        for rel in paths:
            path = root / rel
            if not path.exists():
                continue
            if path.is_file():
                items.append(_artifact_item(root, path, key))
                continue
            for child in sorted(path.rglob("*")):
                if child.is_file():
                    items.append(_artifact_item(root, child, key))
        items.sort(key=lambda item: item["path"])
        phases.append(
            {
                "key": key,
                "title": title,
                "count": len(items),
                "updated_at": max((float(item["updated_at"]) for item in items), default=0.0),
                "items": items,
            }
        )
    return phases


def _artifact_item(root: Path, path: Path, phase: str) -> dict[str, Any]:
    rel = str(path.relative_to(root))
    ext = path.suffix.lower() or "(none)"
    preview_kind = _preview_kind(path)
    return {
        "path": rel,
        "size": path.stat().st_size,
        "updated_at": path.stat().st_mtime,
        "kind": phase,
        "subgroup": _artifact_subgroup(rel, phase),
        "ext": ext,
        "preview_kind": preview_kind,
        "previewable": preview_kind != "none",
    }


def _artifact_subgroup(relative_path: str, phase: str) -> str:
    parts = Path(relative_path).parts
    if phase == "experiment" and parts and parts[0] != "phase2-experiment":
        return "state"
    if len(parts) >= 3:
        return parts[1]
    return "root"


def _preview_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt", ".json", ".jsonl", ".tex", ".py", ".log", ".csv", ".yaml", ".yml"}:
        return "text"
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}:
        return "image"
    if suffix == ".pdf":
        return "pdf"
    return "none"


def build_pipeline(state: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    current = str(state.get("stage", ""))
    completed = {str(item.get("stage", "")) for item in events if item.get("type") == "stage_finished"}
    failed = {str(item.get("stage", "")) for item in events if item.get("type") == "stage_failed"}
    phases: list[dict[str, Any]] = []
    for phase, desc in PHASE_DESCRIPTIONS.items():
        nodes = []
        for name, spec in STAGES.items():
            if spec.phase != phase:
                continue
            status = "pending"
            if name == current:
                status = "active"
            elif name in failed:
                status = "failed"
            elif name in completed:
                status = "completed"
            nodes.append(
                {
                    "name": name,
                    "output_path": spec.output_path,
                    "default_next": spec.default_next,
                    "allowed_next": list(spec.allowed_next),
                    "status": status,
                    "human_gate": spec.human_gate,
                }
            )
        phases.append({"phase": phase, "description": list(desc), "nodes": nodes})
    active_spec = stage_spec(current) if current in STAGES else None
    return {
        "current_stage": current,
        "current_phase": state.get("phase", ""),
        "required_output": active_spec.output_path if active_spec else "",
        "allowed_next": list(active_spec.allowed_next) if active_spec else [],
        "phases": phases,
    }


def build_workers(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    workers: dict[str, dict[str, Any]] = {}
    supervisor = {"agent_id": "supervisor", "status": "idle", "message": "", "step_count": 0, "action_count": 0}
    for item in events:
        agent_id = str(item.get("agent_id", ""))
        layer = str(item.get("layer", ""))
        if layer == "L2" and agent_id == "supervisor":
            supervisor["status"] = "active"
            supervisor["message"] = str(item.get("message", "") or item.get("type", ""))
            supervisor["step_count"] = int(item.get("step_count", supervisor["step_count"]))
            supervisor["action_count"] = int(item.get("action_count", supervisor["action_count"]))
            continue
        if not agent_id or layer != "L2" or not agent_id.startswith("agent-"):
            continue
        rec = workers.setdefault(
            agent_id,
            {
                "agent_id": agent_id,
                "task_id": str(item.get("task_id", "")),
                "stage": str(item.get("stage", "")),
                "status": "unknown",
                "progress_text": "",
                "step_count": 0,
                "action_count": 0,
                "output_path": str(item.get("output_path", "")),
                "last_event_type": "",
            },
        )
        rec["task_id"] = str(item.get("task_id", rec["task_id"]))
        rec["stage"] = str(item.get("stage", rec["stage"]))
        rec["output_path"] = str(item.get("output_path", rec["output_path"]))
        rec["last_event_type"] = str(item.get("type", ""))
        if item.get("message"):
            rec["progress_text"] = str(item["message"])
        if item.get("status"):
            rec["status"] = str(item["status"])
        elif item.get("type") == "worker_created":
            rec["status"] = "running"
        rec["step_count"] = int(item.get("step_count", rec["step_count"]))
        rec["action_count"] = int(item.get("action_count", rec["action_count"]))
    return [supervisor, *sorted(workers.values(), key=lambda item: item["agent_id"])]


def current_skill(root: Path, stage: str) -> dict[str, Any]:
    if not stage:
        return {"stage": "", "path": "", "content": ""}
    path = root / ".lightscientist" / "skills" / f"{stage}.md"
    return {
        "stage": stage,
        "path": str(path.relative_to(root)) if path.exists() else "",
        "content": path.read_text(encoding="utf-8") if path.exists() else "",
    }


def list_skills(root: Path) -> list[dict[str, Any]]:
    skills_root = Path(__file__).resolve().parents[2] / "skills"
    items = []
    for path in sorted(skills_root.glob("*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        desc = ""
        for line in text.splitlines():
            if line.lower().startswith("description:"):
                desc = line.split(":", 1)[1].strip()
                break
        items.append({"name": path.parent.name, "path": str(path), "description": desc})
    return items


def process_excerpt(root: Path, limit: int = 4000) -> str:
    path = root / "PROCESS.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")[:limit]


def safe_read_workspace_file(root: Path, relative_path: str, limit: int = 120_000) -> dict[str, Any]:
    path = resolve_workspace_path(root, relative_path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(relative_path)
    return {
        "path": str(path.relative_to(root)),
        "size": path.stat().st_size,
        "content": path.read_text(encoding="utf-8", errors="replace")[:limit],
    }


def build_overview(root: Path) -> dict[str, Any]:
    state = read_state(root)
    events = read_events(root, limit=240)
    workers = build_workers(events)
    return {
        "state": state,
        "pipeline": build_pipeline(state, events),
        "workers": workers,
        "recent_events": list(reversed(events[-40:])),
        "artifacts": list_artifacts(root),
        "stage_runs": stage_runs(root),
        "process_excerpt": process_excerpt(root),
        "current_skill": current_skill(root, str(state.get("stage", ""))),
    }
