"""Deterministic first-layer research controller."""

from __future__ import annotations

import json, re, time
from collections.abc import Callable
from pathlib import Path

from .data_models import ExecutionResult, ResearchMode, ResearchState, RuntimeTask
from .events import EventBus, JsonlEventSink
from .research_stages import PHASE_DESCRIPTIONS, stage_spec
from .runtime import RuntimeSupervisor


class ResearchController:
    """Runs one research stage at a time using the second-layer supervisor."""

    def __init__(
        self, workspace_root: str | Path, topic: str = "", mode: ResearchMode = "manual",
        start_stage: str = "idea.survey",
        decision_timeout: float = 3.0,
        supervisor_factory: Callable[[], RuntimeSupervisor] | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.state_dir = self.workspace_root / ".lightscientist"
        self.state_path = self.state_dir / "project_state.json"
        self.events_path = self.state_dir / "events.jsonl"
        self.process_path = self.workspace_root / "PROCESS.md"
        self.event_bus = event_bus or EventBus([JsonlEventSink(self.events_path)])
        self.decision_timeout = decision_timeout
        self.supervisor_factory = supervisor_factory
        self._stage_decision: dict[str, str] = {}
        self.state = self._load_or_create_state(topic, mode, start_stage)

    def run(self) -> ExecutionResult:
        result = ExecutionResult(self.state.current_task_id or self.state.project_id, "completed", "", self._path(self.state.output_path))
        while True:
            result = self._run_stage()
            if result.status != "completed" or self.state.stage == "done":
                return result

    def _run_stage(self) -> ExecutionResult:
        if self.state.stage == "done":
            return ExecutionResult(
                self.state.current_task_id or self.state.project_id,
                "completed",
                "Research project is already done.",
                self._path(self.state.output_path),
            )
        spec = stage_spec(self.state.stage)
        if spec.human_gate:
            return self._handle_gate(self._path(spec.output_path))

        task_id = self.state.current_task_id or f"stage-{self.state.stage.replace('.', '-')}"
        prompt = self.build_stage_prompt()
        run_output = self.state_dir / "stage-runs" / task_id / "agent-run.md"
        if run_output.exists(): run_output.unlink()
        self.state.status = "running"
        self.state.current_task_id = task_id
        self.state.phase = spec.phase
        self.state.user_feedback = ""
        self._save_state()
        self._append_event("stage_started", stage=self.state.stage, task_id=task_id)
        self._stage_decision = {}
        supervisor = self.supervisor_factory() if self.supervisor_factory else RuntimeSupervisor(supervisor_tools=self._stage_tools(), event_bus=self.event_bus)
        result = supervisor.start(RuntimeTask(task_id, self.state.stage, prompt, run_output, self.workspace_root, prompt, True, False))
        stage_status, stage_summary, stage_output, next_stage = self._read_stage_decision(supervisor, task_id, result.summary)
        output_path = self._path(stage_output or spec.output_path)
        self.state.output_path = str(output_path)
        if stage_status == "failed":
            self._set_status("failed", event_type="stage_failed", reason=stage_summary)
            return ExecutionResult(task_id, "failed", stage_summary, output_path)
        if stage_status == "blocked":
            self._set_status(
                "waiting_user",
                pending=stage_summary,
                next_stage=self._validated_next_stage(spec, next_stage) if next_stage else "",
                event_type="stage_blocked",
                question=stage_summary,
            )
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
        self._append_process(spec, output_path, stage_summary)
        self._append_event("stage_finished", stage=self.state.stage, status="completed", output_path=str(output_path))
        self._transition_to(self._resolved_next_stage(spec, next_stage))
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
        skill_line = f"Skill to read first: {self._stage_skill_path(spec)}" if spec.skill_path else "No skill file for this gate stage."
        feedback = f"\nLatest user feedback:\n{self.state.user_feedback}\n" if self.state.user_feedback else "\n"
        phase2_state = f"\nPhase 2 state:\n{self._phase2_state_text()}\n" if spec.phase == "experiment" else "\n"
        return f"""You are the second-layer supervisor for one research stage.

Global pipeline:
idea -> experiment -> paper -> done

Project topic:
{self.state.topic}
{feedback}
{phase2_state}

Current phase: {spec.phase}
Current stage: {spec.name}

Current phase stages:
{phase_lines}

{skill_line}

Read `PROCESS.md` first when it exists for the high-level project history.

Read standard phase files directly when needed:
- idea: `phase1-idea/LITERATURE_SURVEY.md`, `phase1-idea/IDEAS_CANDIDATES.md`, `phase1-idea/IDEA_REPORT.md`
- experiment: `research.md`, `research.jsonl`, `phase2-experiment/worklog.md`, `phase2-experiment/EXPERIMENT_RESULTS.md`
- paper: `phase3-paper/PAPER_PLAN.md`, `phase3-paper/figures/`, `phase3-paper/paper/main.pdf`

Required output:
{spec.output_path}

Allowed next stages:
{allowed}

Rules:
- Work only on the current stage.
- If a skill path is provided, read that SKILL.md before acting.
- Use only workspace-visible paths such as `PROCESS.md`, `source_task/...`, `source_seed/...`, `source_results/...`, and `phase*/...`.
- Do not read from `/`, `/data`, `/home`, or any other absolute filesystem path.
- Do not edit .lightscientist/project_state.json directly.
- Write the required output file before reporting completion.
- When writing workspace artifacts, always use workspace-relative paths such as `{spec.output_path}`. Do not use absolute paths for stage deliverables.
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
            self._append_event("finish_stage_called", stage=self.state.stage, status=normalized, output_path=output_path, next_stage=next_stage, summary=summary)
            return json.dumps({"status": "accepted", "stage_status": normalized}, ensure_ascii=False)

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
                self._append_event("user_decision_rejected", stage=self.state.stage, question=question, reason="auto mode")
                return json.dumps({"status": "rejected", "reason": "auto mode; avoid user interruption"}, ensure_ascii=False)
            text = question if not options else f"{question}\nOptions: {options}"
            self._stage_decision = {"status": "blocked", "summary": text, "output_path": "", "next_stage": ""}
            self._append_event("user_decision_requested", stage=self.state.stage, question=question, options=options)
            return json.dumps({"status": "waiting_user", "question": text}, ensure_ascii=False)

        return [finish_stage_tool, request_user_decision_tool]

    def reply_user(self, text: str) -> ExecutionResult:
        if self.state.status != "waiting_user":
            return ExecutionResult(self.state.current_task_id or self.state.project_id, "failed", "No pending user decision.", self._path(self.state.output_path))
        answer, _, reason = text.strip().partition(" ")
        answer, reason = answer.lower(), reason.strip()
        if answer not in {"y", "n"}:
            return ExecutionResult(self.state.current_task_id or self.state.project_id, "failed", "Reply must start with `y` or `n`.", self._path(self.state.output_path))
        self.state.user_feedback = reason
        self._append_event("user_reply", stage=self.state.stage, answer=answer, reason=reason)
        if answer == "y" and self.state.pending_next_stage:
            self._transition_to(self.state.pending_next_stage)
        elif answer == "n" and stage_spec(self.state.stage).human_gate:
            self._transition_to(self._rejected_gate_stage())
        else:
            self._set_status("idle")
        return self.run()

    def _handle_gate(self, output_path: Path) -> ExecutionResult:
        spec = stage_spec(self.state.stage)
        if self.state.mode == "manual":
            self._set_status("waiting_user", pending=f"Confirm transition from {self.state.stage} to {spec.default_next}?", next_stage=spec.default_next)
            self._append_event("gate_waiting", stage=self.state.stage, next_stage=spec.default_next)
            return ExecutionResult(self.state.current_task_id or self.state.stage, "waiting", self.state.pending_question, output_path)
        self._append_event("gate_auto_approved", stage=self.state.stage, next_stage=spec.default_next)
        self._transition_to(spec.default_next)
        return ExecutionResult(self.state.current_task_id or self.state.stage, "completed", f"Auto-approved gate to {spec.default_next}.", output_path)

    def _set_status(self, status: str, pending: str = "", next_stage: str = "", event_type: str = "", **data: object) -> None:
        self.state.status = status
        self.state.pending_question = pending
        self.state.pending_next_stage = next_stage
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
        self.state.pending_next_stage = ""
        self._save_state()
        self._append_event("stage_transition", **{"from": old, "to": next_stage})

    def _rejected_gate_stage(self) -> str:
        spec = stage_spec(self.state.stage)
        for name in spec.allowed_next:
            if name != spec.default_next and stage_spec(name).phase == spec.phase:
                return name
        return spec.name

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

    def _resolved_next_stage(self, spec, proposed: str) -> str:
        if proposed:
            return self._validated_next_stage(spec, proposed)
        if spec.name == "experiment.loop":
            next_stage = "experiment.analyze" if self._phase2_state()["results_ready"] else "experiment.loop"
            self._append_event("next_stage_inferred", stage=spec.name, next_stage=next_stage)
            return next_stage
        return spec.default_next

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
        payload = dict(data)
        stage = str(payload.pop("stage", getattr(getattr(self, "state", None), "stage", "")) or "")
        task_id = str(payload.pop("task_id", getattr(getattr(self, "state", None), "current_task_id", "")) or "")
        self.event_bus.emit("L1", event_type, self._event_message(event_type, payload), stage=stage, task_id=task_id, **payload)

    def _event_message(self, event_type: str, data: dict[str, object]) -> str:
        if event_type == "stage_transition":
            return f"{data.get('from', '')} -> {data.get('to', '')}"
        if event_type in {"stage_started", "stage_finished", "stage_failed", "stage_blocked", "stage_suspended"}:
            return str(data.get("summary") or data.get("reason") or data.get("question") or data.get("status") or "")
        if event_type in {"finish_stage_called", "user_decision_requested", "user_decision_rejected"}:
            return str(data.get("summary") or data.get("question") or data.get("reason") or "")
        return ""

    def _phase2_state(self) -> dict[str, object]:
        research_md = self.workspace_root / "research.md"
        research_jsonl = self.workspace_root / "research.jsonl"
        worklog = self.workspace_root / "phase2-experiment/worklog.md"
        results = self.workspace_root / "phase2-experiment/EXPERIMENT_RESULTS.md"
        state: dict[str, object] = {
            "research_md": research_md.exists(),
            "research_jsonl": research_jsonl.exists(),
            "worklog": worklog.exists(),
            "results_ready": results.exists(),
            "runs": 0,
            "keep": 0,
            "discard": 0,
            "crash": 0,
            "sanity_fail": 0,
            "best_keep": "",
        }
        if not research_jsonl.exists():
            return state
        primary = "branch_cov"
        best_value: float | None = None
        best_note = ""
        for line in research_jsonl.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if item.get("type") == "config":
                primary = str(item.get("metrics", {}).get("primary", {}).get("name", primary))
                continue
            state["runs"] = int(state["runs"]) + 1
            status = str(item.get("status", ""))
            if status in {"keep", "discard", "crash", "sanity_fail"}:
                state[status] = int(state[status]) + 1
            value = item.get("results", {}).get(primary, {}).get("mean")
            if status == "keep" and isinstance(value, (int, float)) and (best_value is None or float(value) > best_value):
                best_value = float(value)
                best_note = f"run {item.get('run', '?')}: {primary}={value} ({item.get('description', '')})".strip()
        state["best_keep"] = best_note
        return state

    def _phase2_state_text(self) -> str:
        state = self._phase2_state()
        lines = [
            f"- research.md: {'present' if state['research_md'] else 'missing'}",
            f"- research.jsonl: {'present' if state['research_jsonl'] else 'missing'}",
            f"- worklog: {'present' if state['worklog'] else 'missing'}",
            f"- experiment results: {'present' if state['results_ready'] else 'missing'}",
            f"- runs: {state['runs']} | keep: {state['keep']} | discard: {state['discard']} | crash: {state['crash']} | sanity_fail: {state['sanity_fail']}",
        ]
        if state["best_keep"]:
            lines.append(f"- best keep: {state['best_keep']}")
        return "\n".join(lines)

    def _append_process(self, spec, output_path: Path, summary: str) -> None:
        rel = str(output_path.relative_to(self.workspace_root)) if output_path.is_relative_to(self.workspace_root) else str(output_path)
        workspace = {"idea": "phase1-idea/", "experiment": "phase2-experiment/", "paper": "phase3-paper/"}.get(spec.phase, "./")
        lines = [
            f"## {spec.name}",
            f"- Workspace: {workspace}",
            f"- Main output: {rel}",
            f"- Summary: {summary or 'No summary provided.'}",
        ]
        if spec.phase == "experiment":
            lines.append("- Extra files: research.md, research.jsonl, phase2-experiment/worklog.md")
        with self.process_path.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n\n")

    def _stage_skill_path(self, spec) -> str:
        if not spec.skill_path:
            return ""
        target = self.state_dir / "skills" / f"{spec.name}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(Path(spec.skill_path).read_text(encoding="utf-8"), encoding="utf-8")
        return str(target.relative_to(self.workspace_root)).replace("\\", "/")

    def _path(self, value: str) -> Path:
        path = Path(value) if value else self.workspace_root / "research-result.md"
        return path if path.is_absolute() else self.workspace_root / path

    def _project_id(self, topic: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", topic.strip().lower()).strip("-")
        return cleaned[:48] or "research"
