"""Deterministic first-layer research controller."""

from __future__ import annotations

import json, re, time
from collections.abc import Callable
from pathlib import Path

from .data_models import ExecutionResult, ResearchMode, ResearchState, RuntimeTask
from .research_stages import PHASE_DESCRIPTIONS, stage_spec
from .runtime import RuntimeSupervisor


class ResearchController:
    """Runs one research stage at a time using the second-layer supervisor."""

    def __init__(
        self, workspace_root: str | Path, topic: str = "", mode: ResearchMode = "manual",
        start_stage: str = "idea.survey",
        decision_timeout: float = 3.0,
        supervisor_factory: Callable[[], RuntimeSupervisor] | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.state_dir = self.workspace_root / ".lightscientist"
        self.state_path = self.state_dir / "project_state.json"
        self.events_path = self.state_dir / "events.jsonl"
        self.artifacts_path = self.state_dir / "artifacts.json"
        self.decision_timeout = decision_timeout
        self.supervisor_factory = supervisor_factory
        self._stage_decision: dict[str, str] = {}
        self.state = self._load_or_create_state(topic, mode, start_stage)

    def run_once(self) -> ExecutionResult:
        if self.state.stage == "done":
            return ExecutionResult(
                self.state.current_task_id or self.state.project_id,
                "completed",
                "Research project is already done.",
                self._path(self.state.last_output_path),
            )
        spec = stage_spec(self.state.stage)
        if spec.human_gate:
            return self._handle_gate(self._path(spec.output_path))

        task_id = self.state.current_task_id or f"stage-{self.state.stage.replace('.', '-')}"
        prompt = self.build_stage_prompt()
        run_output = self.state_dir / "stage-runs" / task_id / "agent-run.md"
        self.state.status = "running"
        self.state.current_task_id = task_id
        self.state.phase = spec.phase
        self._save_state()
        self._append_event("stage_started", stage=self.state.stage, task_id=task_id)
        self._stage_decision = {}
        supervisor = self.supervisor_factory() if self.supervisor_factory else RuntimeSupervisor(supervisor_tools=self._stage_tools())
        result = supervisor.start(RuntimeTask(task_id, self.state.stage, prompt, run_output, self.workspace_root, prompt, True, False))
        stage_status, stage_summary, stage_output, next_stage = self._read_stage_decision(supervisor, task_id, result.summary)
        output_path = self._path(stage_output or spec.output_path)
        self.state.last_summary = stage_summary
        self.state.last_output_path = str(output_path)
        if stage_status == "failed":
            self._set_status("failed", event_type="stage_failed", reason=stage_summary)
            return ExecutionResult(task_id, "failed", stage_summary, output_path)
        if stage_status == "blocked":
            self._set_status("waiting_user", pending=stage_summary, event_type="stage_blocked", question=stage_summary)
            return ExecutionResult(task_id, "waiting", stage_summary, output_path)
        if result.status in {"waiting", "background"}:
            self._set_status(
                "waiting_user" if result.status == "waiting" else "running",
                pending=result.summary if result.status == "waiting" else "",
                event_type="stage_suspended",
                status=result.status,
                summary=result.summary,
            )
            return result
        if result.status != "completed":
            self._set_status("failed", event_type="stage_failed", reason=result.summary)
            return ExecutionResult(task_id, "failed", result.summary, output_path)
        if not output_path.exists():
            summary = f"Stage completed but required output is missing: {output_path}"
            self._set_status("failed", event_type="stage_failed", reason=summary)
            return ExecutionResult(task_id, "failed", summary, output_path)
        self._record_artifact(self.state.stage, output_path, stage_summary)
        self._append_event("stage_finished", stage=self.state.stage, status="completed", output_path=str(output_path))
        self._transition_to(self._validated_next_stage(spec, next_stage))
        return ExecutionResult(
            task_id,
            "completed",
            stage_summary,
            output_path,
            artifacts=[output_path, *result.artifacts],
            notes=result.notes,
        )

    def build_stage_prompt(self) -> str:
        spec = stage_spec(self.state.stage)
        phase_lines = "\n".join(f"- {line}" for line in PHASE_DESCRIPTIONS.get(spec.phase, ()))
        allowed = "\n".join(f"- {name}" for name in spec.allowed_next)
        skill_line = f"Skill to read first: {spec.skill_path}" if spec.skill_path else "No skill file for this gate stage."
        return f"""You are the second-layer supervisor for one research stage.

Global pipeline:
idea -> experiment -> paper -> done

Project topic:
{self.state.topic}

Current phase: {spec.phase}
Current stage: {spec.name}

Current phase stages:
{phase_lines}

{skill_line}

Required output:
{spec.output_path}

Allowed next stages:
{allowed}

Rules:
- Work only on the current stage.
- If a skill path is provided, read that SKILL.md before acting.
- Do not edit .lightscientist/project_state.json directly.
- Write the required output file before reporting completion.
- Use list_artifacts when you need summaries or paths from prior stages.
- When the stage is completed, failed, or blocked, call finish_stage.
- Use request_user_decision only for project-level decisions that cannot be answered from files or workers.
- In auto mode, avoid user interruption; decide from available evidence or finish the stage as failed.
"""

    def _stage_tools(self) -> list[object]:
        from langchain.tools import tool

        @tool("finish_stage", parse_docstring=True)
        def finish_stage_tool(status: str, summary: str, output_path: str = "", next_stage: str = "") -> str:
            """Submit the current research stage result to the first-layer controller.

            Use this exactly once when the current stage is completed, failed, or
            blocked. This tool does not directly change project_state.json; the
            first-layer controller validates the result and applies allowed
            transitions.

            Args:
                status: One of "completed", "failed", or "blocked".
                summary: Concise stage summary or blocking reason.
                output_path: Main stage artifact path, if any.
                next_stage: Suggested next stage, if different from default.

            Returns:
                JSON acknowledgement.
            """
            normalized = status.strip().lower()
            if normalized not in {"completed", "failed", "blocked"}:
                normalized = "failed"
                summary = f"Invalid finish_stage status. {summary}".strip()
            self._stage_decision = {
                "status": normalized,
                "summary": summary,
                "output_path": output_path,
                "next_stage": next_stage,
            }
            return json.dumps({"status": "accepted", "stage_status": normalized}, ensure_ascii=False)

        @tool("list_artifacts", parse_docstring=True)
        def list_artifacts_tool(stage: str = "") -> str:
            """List prior stage artifacts and their summaries.

            Use this when you need context from previous research stages. This
            returns artifact paths and concise handoff summaries only; read the
            files directly if more detail is needed.

            Args:
                stage: Optional stage name to filter, such as "idea.evaluate".

            Returns:
                JSON list of artifact records.
            """
            return json.dumps(self._list_artifacts(stage), ensure_ascii=False)

        @tool("request_user_decision", parse_docstring=True)
        def request_user_decision_tool(question: str, options: str = "") -> str:
            """Request a project-level human decision from the CLI user.

            Use this only when the stage cannot continue without human judgment.
            In auto mode, this tool does not interrupt the run; the supervisor
            should decide from available evidence or finish the stage as failed.

            Args:
                question: Short concrete question to show to the user.
                options: Optional choices or expected answer format.

            Returns:
                JSON result indicating whether the request was accepted.
            """
            if self.state.mode == "auto":
                return json.dumps({"status": "rejected", "reason": "auto mode; avoid user interruption"}, ensure_ascii=False)
            text = question if not options else f"{question}\nOptions: {options}"
            self._stage_decision = {"status": "blocked", "summary": text, "output_path": "", "next_stage": ""}
            return json.dumps({"status": "waiting_user", "question": text}, ensure_ascii=False)

        return [finish_stage_tool, request_user_decision_tool, list_artifacts_tool]

    def _handle_gate(self, output_path: Path) -> ExecutionResult:
        spec = stage_spec(self.state.stage)
        if self.state.mode == "manual":
            self._set_status("waiting_user", pending=f"Confirm transition from {self.state.stage} to {spec.default_next}?")
            self._append_event("gate_waiting", stage=self.state.stage, next_stage=spec.default_next)
            return ExecutionResult(self.state.current_task_id or self.state.stage, "waiting", self.state.pending_question, output_path)
        self._append_event("gate_auto_approved", stage=self.state.stage, next_stage=spec.default_next)
        self._transition_to(spec.default_next)
        return ExecutionResult(self.state.current_task_id or self.state.stage, "completed", f"Auto-approved gate to {spec.default_next}.", output_path)

    def _set_status(self, status: str, pending: str = "", event_type: str = "", **data: object) -> None:
        self.state.status = status
        self.state.pending_question = pending
        self._save_state()
        if event_type:
            self._append_event(event_type, stage=self.state.stage, **data)

    def _transition_to(self, next_stage: str) -> None:
        old = self.state.stage
        self.state.stage = next_stage
        self.state.phase = "done" if next_stage == "done" else stage_spec(next_stage).phase
        self.state.status = "completed" if next_stage == "done" else "idle"
        self.state.current_task_id = ""
        self.state.pending_question = ""
        self._save_state()
        self._append_event("stage_transition", **{"from": old, "to": next_stage})

    def _read_stage_decision(self, supervisor: RuntimeSupervisor, task_id: str, fallback: str) -> tuple[str, str, str, str]:
        deadline = time.monotonic() + self.decision_timeout
        status = ""
        summary = fallback
        while time.monotonic() < deadline:
            if self._stage_decision:
                return (
                    self._stage_decision.get("status", ""),
                    self._stage_decision.get("summary", fallback),
                    self._stage_decision.get("output_path", ""),
                    self._stage_decision.get("next_stage", ""),
                )
            task = supervisor.get_task(task_id)
            if task and str(task.get("summary", "")):
                status = str(task.get("status", ""))
                summary = str(task["summary"])
                if task.get("status") in {"completed", "failed"}:
                    break
            time.sleep(0.05)
        match = re.search(r"(?im)^\s*NEXT_STAGE\s*:\s*([a-z0-9_.-]+)\s*$", summary)
        return status, summary, "", match.group(1) if match else ""

    def _validated_next_stage(self, spec, proposed: str) -> str:
        if not proposed:
            return spec.default_next
        accepted = proposed in spec.allowed_next
        self._append_event("next_stage_accepted" if accepted else "next_stage_rejected", stage=spec.name, next_stage=proposed)
        return proposed if accepted else spec.default_next

    def _load_or_create_state(self, topic: str, mode: ResearchMode, start_stage: str) -> ResearchState:
        if self.state_path.exists():
            return ResearchState.from_dict(json.loads(self.state_path.read_text(encoding="utf-8")))
        spec = stage_spec(start_stage)
        project_id = self._project_id(topic or "research")
        state = ResearchState(project_id, topic, mode, spec.phase, spec.name, "idle", self.workspace_root)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self._append_event("project_created", project_id=project_id, stage=spec.name, topic=topic)
        return state

    def _save_state(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.state.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _append_event(self, event_type: str, **data: object) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        event = {"type": event_type, "time": time.time(), **data}
        with self.events_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _list_artifacts(self, stage: str = "") -> list[dict[str, object]]:
        if not self.artifacts_path.exists():
            return []
        data = json.loads(self.artifacts_path.read_text(encoding="utf-8"))
        return [{"stage": item_stage, **record} for item_stage, records in data.items() if not stage or item_stage == stage for record in records]

    def _record_artifact(self, stage: str, path: Path, summary: str) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        data = json.loads(self.artifacts_path.read_text(encoding="utf-8")) if self.artifacts_path.exists() else {}
        records = data.setdefault(stage, [])
        rel_path = str(path.relative_to(self.workspace_root)) if path.is_relative_to(self.workspace_root) else str(path)
        record = {"path": rel_path, "summary": summary, "created_at": time.time()}
        records[:] = [item for item in records if item.get("path") != rel_path]
        records.append(record)
        self.artifacts_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self._append_event("artifact_recorded", stage=stage, path=rel_path)

    def _path(self, value: str) -> Path:
        path = Path(value) if value else self.workspace_root / "research-result.md"
        return path if path.is_absolute() else self.workspace_root / path

    def _project_id(self, topic: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", topic.strip().lower()).strip("-")
        return cleaned[:48] or "research"
