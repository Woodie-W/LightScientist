const state = {
  activeTab: "overview",
  artifactPhase: "idea",
  artifactFilters: { subgroup: "all", ext: "all" },
  overview: null,
  pipeline: null,
  artifacts: null,
  knowledge: null,
  events: [],
  filters: { layer: "all", type: "all" },
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

async function api(path) {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`);
  return res.json();
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}

function fmtTime(ts) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString();
}

function fmtBytes(size) {
  if (size == null) return "—";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function statusChip(status, extra = "") {
  const cls =
    status === "completed" ? "completed" :
    status === "failed" ? "failed" :
    status === "waiting_user" || status === "waiting" ? "waiting" :
    status === "running" || status === "active" ? "active" : "";
  return `<span class="chip ${cls}">${escapeHtml(status)}${extra ? ` · ${escapeHtml(extra)}` : ""}</span>`;
}

async function refresh() {
  try {
    const [overview, pipeline, artifacts, knowledge, events] = await Promise.all([
      api("/api/overview"),
      api("/api/pipeline"),
      api("/api/artifacts"),
      api("/api/knowledge"),
      api("/api/events?limit=240"),
    ]);
    state.overview = overview;
    state.pipeline = pipeline;
    state.artifacts = artifacts;
    state.knowledge = knowledge;
    state.events = events.events || [];
    render();
  } catch (err) {
    $("#tab-overview").innerHTML = `<div class="card"><div class="card-title">WebUI Error</div><p class="muted prewrap">${escapeHtml(err.message)}</p></div>`;
  }
}

function renderHeader() {
  const info = state.overview?.state;
  if (!info) return;
  $("#header-status").innerHTML = [
    escapeHtml(`${info.phase || "—"} / ${info.stage || "—"}`),
    escapeHtml(info.status || "idle"),
    `${(state.overview.workers || []).filter((w) => w.agent_id?.startsWith("agent-")).length} workers`,
    `updated ${fmtTime(Math.max(...state.events.map((e) => e.time || 0), 0))}`,
  ].join(" | ");
}

function renderOverview() {
  const data = state.overview;
  if (!data) return;
  const info = data.state;
  const workers = data.workers || [];
  const stage = data.pipeline || {};
  const artifacts = (data.artifacts || []).slice(0, 8);
  const recent = (data.recent_events || []).slice(0, 16);

  $("#tab-overview").innerHTML = `
    <div class="grid-2">
      <div class="stack">
        <div class="card">
          <div class="card-header">
            <div>
              <div class="card-kicker">Project</div>
              <div class="card-title">${escapeHtml(info.project_id || "LightScientist Project")}</div>
            </div>
            ${statusChip(info.status || "idle", info.mode || "")}
          </div>
          <div class="metric-grid">
            <div class="metric"><div class="metric-label">Phase</div><div class="metric-value">${escapeHtml(info.phase || "—")}</div></div>
            <div class="metric"><div class="metric-label">Stage</div><div class="metric-value">${escapeHtml(info.stage || "—")}</div></div>
            <div class="metric"><div class="metric-label">Workspace</div><div class="metric-value mono">${escapeHtml(info.workspace_root || "—")}</div></div>
            <div class="metric"><div class="metric-label">Current Output</div><div class="metric-value mono">${escapeHtml(info.output_path || "—")}</div></div>
          </div>
        </div>

        <div class="card">
          <div class="card-header">
            <div class="card-kicker">Pipeline</div>
            <div class="muted mono">${escapeHtml(stage.required_output || "—")}</div>
          </div>
          <div class="ribbon">
            ${["idea", "experiment", "paper"].map((phase) => `<span class="chip ${info.phase === phase ? "phase-active" : ""}">${phase}</span>`).join("")}
          </div>
          <div class="two-col-inline">
            <div>
              <div class="metric-label">Allowed Next</div>
              <div class="prewrap">${(stage.allowed_next || []).map(escapeHtml).join("\n") || "—"}</div>
            </div>
            <div>
              <div class="metric-label">Current Skill</div>
              <div class="mono">${escapeHtml(data.current_skill?.path || "—")}</div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-header"><div class="card-title">Recent Events</div><div class="card-kicker">L1 / L2 / L3</div></div>
          <div class="event-list">
            ${recent.map(renderEventRow).join("") || `<div class="muted">No events yet.</div>`}
          </div>
        </div>
      </div>

      <div class="stack">
        <div class="card">
          <div class="card-header"><div class="card-title">Supervisor & Workers</div><div class="card-kicker">Live Runtime</div></div>
          <div class="worker-list">
            ${workers.map(renderWorkerRow).join("") || `<div class="muted">No workers detected.</div>`}
          </div>
        </div>

        <div class="card">
          <div class="card-header"><div class="card-title">Recent Artifacts</div><div class="card-kicker">Workspace</div></div>
          <div class="artifact-list">
            ${artifacts.map(renderArtifactRow).join("") || `<div class="muted">No artifacts yet.</div>`}
          </div>
        </div>

        <div class="card">
          <div class="card-header"><div class="card-title">PROCESS Memory</div><div class="card-kicker">Long-term Summary</div></div>
          <div class="prewrap muted">${escapeHtml(data.process_excerpt || "PROCESS.md is empty.")}</div>
        </div>
      </div>
    </div>
  `;
  wirePreviewButtons();
}

function renderPipeline() {
  const pipeline = state.pipeline;
  if (!pipeline) return;
  $("#tab-pipeline").innerHTML = `
    <div class="grid-2">
      <div class="stack">
        <div class="card">
          <div class="card-header">
            <div class="card-title">Three-Layer Stack</div>
            <div class="card-kicker">Control Structure</div>
          </div>
          <div class="worker-list">
            <div class="worker-row active">
              <div class="worker-head"><div class="worker-name">L1 · Research Controller</div>${statusChip(state.overview?.state?.status || "idle")}</div>
              <div class="worker-meta">Current phase: ${escapeHtml(state.overview?.state?.phase || "—")} · Stage: ${escapeHtml(state.overview?.state?.stage || "—")}</div>
            </div>
            <div class="worker-row ${state.overview?.workers?.[0]?.status === "active" ? "active" : ""}">
              <div class="worker-head"><div class="worker-name">L2 · Runtime Supervisor</div>${statusChip(state.overview?.workers?.[0]?.status || "idle")}</div>
              <div class="worker-meta">${escapeHtml(state.overview?.workers?.[0]?.message || "No recent supervisor event.")}</div>
            </div>
            ${(state.overview?.workers || []).filter((w) => w.agent_id !== "supervisor").map((w) => `
              <div class="worker-row ${w.status === "running" ? "active" : ""}">
                <div class="worker-head"><div class="worker-name">L3 · ${escapeHtml(w.agent_id)}</div>${statusChip(w.status || "unknown")}</div>
                <div class="worker-meta">${escapeHtml(w.progress_text || "No progress text.")}</div>
              </div>
            `).join("")}
          </div>
        </div>
      </div>

      <div class="stack">
        ${pipeline.phases.map((phase) => `
          <div class="card">
            <div class="card-header">
              <div class="card-title">${escapeHtml(phase.phase)}</div>
              <div class="card-kicker">${escapeHtml((phase.description || [])[0] || "")}</div>
            </div>
            <div class="stage-list">
              ${(phase.nodes || []).map((node) => `
                <div class="stage-row ${node.status === "active" ? "active" : ""}">
                  <div class="stage-head">
                    <div class="stage-name">${escapeHtml(node.name)}</div>
                    ${statusChip(node.status || "pending", node.human_gate ? "gate" : "")}
                  </div>
                  <div class="stage-meta mono">output: ${escapeHtml(node.output_path || "—")}</div>
                  <div class="stage-meta">next: ${(node.allowed_next || []).map(escapeHtml).join(", ") || "—"}</div>
                </div>
              `).join("")}
            </div>
          </div>
        `).join("")}
      </div>
    </div>
  `;
}

function renderKnowledge() {
  const data = state.knowledge;
  if (!data) return;
  const skills = data.skills || [];
  const current = data.current_skill || {};
  $("#tab-knowledge").innerHTML = `
    <div class="grid-2">
      <div class="stack">
        <div class="card">
          <div class="card-header"><div class="card-title">Current Stage Skill</div><div class="card-kicker">${escapeHtml(current.stage || "—")}</div></div>
          <div class="mono muted">${escapeHtml(current.path || "No active skill file.")}</div>
          <div class="prewrap muted" style="margin-top:0.8rem;">${escapeHtml((current.content || "").slice(0, 5000) || "No content.")}</div>
        </div>
        <div class="card">
          <div class="card-header"><div class="card-title">PROCESS.md</div><div class="card-kicker">Project Memory</div></div>
          <div class="prewrap muted">${escapeHtml(data.process_excerpt || "PROCESS.md is empty.")}</div>
        </div>
      </div>
      <div class="stack">
        <div class="card">
          <div class="card-header"><div class="card-title">Skills</div><div class="card-kicker">${skills.length} total</div></div>
          <div class="skill-list">
            ${skills.map((skill) => `
              <div class="skill-row">
                <div class="skill-head">
                  <div class="skill-name">${escapeHtml(skill.name)}</div>
                  ${skill.name === current.path?.split("/").pop()?.replace(".md", "") ? statusChip("active") : ""}
                </div>
                <div class="skill-meta">${escapeHtml(skill.description || "No description.")}</div>
              </div>
            `).join("")}
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderArtifacts() {
  const data = state.artifacts;
  if (!data) return;
  const phaseMap = new Map((data.phases || []).map((phase) => [phase.key, phase]));
  const phases = [
    phaseMap.get("idea") || { key: "idea", title: "Idea", count: 0, updated_at: 0, items: [] },
    phaseMap.get("experiment") || { key: "experiment", title: "Experiment", count: 0, updated_at: 0, items: [] },
    phaseMap.get("paper") || { key: "paper", title: "Paper", count: 0, updated_at: 0, items: [] },
  ];
  if (!phases.some((phase) => phase.key === state.artifactPhase)) state.artifactPhase = "idea";
  const active = phases.find((phase) => phase.key === state.artifactPhase);
  const allItems = active?.items || [];
  const subgroups = [...new Set(allItems.map((item) => item.subgroup).filter(Boolean))].sort();
  const exts = [...new Set(allItems.map((item) => item.ext).filter(Boolean))].sort();
  const items = allItems.filter((item) => {
    const subgroupOk = state.artifactFilters.subgroup === "all" || item.subgroup === state.artifactFilters.subgroup;
    const extOk = state.artifactFilters.ext === "all" || item.ext === state.artifactFilters.ext;
    return subgroupOk && extOk;
  });
  $("#tab-artifacts").innerHTML = `
    <div class="stack">
      <div class="card">
        <div class="card-header">
          <div class="card-title">Artifacts</div>
          <div class="card-kicker">Stage Outputs</div>
        </div>
        <div class="phase-switch phase-switch-inline">
          ${phases.map((phase) => `
            <button class="phase-button ${phase.key === state.artifactPhase ? "is-active" : ""}" data-phase="${phase.key}">
              <span>${escapeHtml(phase.title)}</span>
              <span class="phase-meta">${phase.count}</span>
            </button>
          `).join("")}
        </div>
      </div>
      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-title">${escapeHtml(active?.title || "Artifacts")}</div>
            <div class="card-kicker">${items.length} visible / ${allItems.length} total</div>
          </div>
          <div class="muted mono">${fmtTime(active?.updated_at || 0)}</div>
        </div>
        <div class="artifact-filter-block">
          <div class="metric-label">Subtask</div>
          <div class="phase-switch phase-switch-inline">
            ${["all", ...subgroups].map((subgroup) => `
              <button class="filter-button ${state.artifactFilters.subgroup === subgroup ? "is-active" : ""}" data-filter-kind="subgroup" data-filter-value="${escapeHtml(subgroup)}">
                ${escapeHtml(subgroup)}
              </button>
            `).join("")}
          </div>
        </div>
        <div class="artifact-filter-block">
          <div class="metric-label">Type</div>
          <div class="phase-switch phase-switch-inline">
            ${["all", ...exts].map((ext) => `
              <button class="filter-button ${state.artifactFilters.ext === ext ? "is-active" : ""}" data-filter-kind="ext" data-filter-value="${escapeHtml(ext)}">
                ${escapeHtml(ext)}
              </button>
            `).join("")}
          </div>
        </div>
        <div class="artifact-list">
          ${items.map(renderArtifactRow).join("") || `<div class="muted">No artifacts in this filter.</div>`}
        </div>
      </div>
    </div>
  `;
  $$(".phase-button").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.artifactPhase = btn.dataset.phase;
      state.artifactFilters = { subgroup: "all", ext: "all" };
      renderArtifacts();
    });
  });
  $$(".filter-button").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.artifactFilters[btn.dataset.filterKind] = btn.dataset.filterValue;
      renderArtifacts();
    });
  });
  wirePreviewButtons();
}

function renderLogs() {
  const events = state.events.filter((item) => {
    const layerOk = state.filters.layer === "all" || item.layer === state.filters.layer;
    const typeOk = state.filters.type === "all" || item.type === state.filters.type;
    return layerOk && typeOk;
  });

  const types = [...new Set(state.events.map((item) => item.type).filter(Boolean))].sort();
  $("#tab-logs").innerHTML = `
    <div class="card">
      <div class="card-header">
        <div class="card-title">Structured Event Log</div>
        <div class="card-kicker">${events.length} visible</div>
      </div>
      <div class="filters">
        <select id="filter-layer">
          ${["all", "L1", "L2", "L3"].map((layer) => `<option value="${layer}" ${state.filters.layer === layer ? "selected" : ""}>${layer}</option>`).join("")}
        </select>
        <select id="filter-type">
          <option value="all">all types</option>
          ${types.map((type) => `<option value="${escapeHtml(type)}" ${state.filters.type === type ? "selected" : ""}>${escapeHtml(type)}</option>`).join("")}
        </select>
      </div>
      <div class="event-list">
        ${events.map(renderEventRow).join("") || `<div class="muted">No matching events.</div>`}
      </div>
    </div>
  `;
  $("#filter-layer").addEventListener("change", (e) => { state.filters.layer = e.target.value; renderLogs(); });
  $("#filter-type").addEventListener("change", (e) => { state.filters.type = e.target.value; renderLogs(); });
}

function renderEventRow(item) {
  return `
    <div class="event-row">
      <div class="event-head">
        <div>
          ${statusChip(item.layer || "—")}
          <span class="chip">${escapeHtml(item.type || "event")}</span>
        </div>
        <div class="event-meta mono">${escapeHtml(item.stage || item.task_id || "")}</div>
      </div>
      <div style="margin-top:0.55rem;">${escapeHtml(item.message || "(no message)")}</div>
      <div class="event-meta mono" style="margin-top:0.55rem;">${fmtTime(item.time)}${item.agent_id ? ` · ${escapeHtml(item.agent_id)}` : ""}</div>
    </div>
  `;
}

function renderWorkerRow(worker) {
  return `
    <div class="worker-row ${worker.status === "running" || worker.status === "active" ? "active" : ""}">
      <div class="worker-head">
        <div class="worker-name">${escapeHtml(worker.agent_id)}</div>
        ${statusChip(worker.status || "unknown")}
      </div>
      <div class="worker-meta">${escapeHtml(worker.progress_text || worker.message || "No recent update.")}</div>
      <div class="two-col-inline">
        <div><div class="metric-label">Steps</div><div class="mono">${escapeHtml(worker.step_count ?? 0)}</div></div>
        <div><div class="metric-label">Actions</div><div class="mono">${escapeHtml(worker.action_count ?? 0)}</div></div>
      </div>
    </div>
  `;
}

function renderArtifactRow(item) {
  return `
    <div class="artifact-row">
      <div class="artifact-head">
        <div>
          <div class="artifact-name mono">${escapeHtml(item.path)}</div>
          <div class="artifact-meta">${escapeHtml(item.subgroup || "root")} · ${escapeHtml(item.ext || "(none)")} · ${fmtBytes(item.size)}</div>
        </div>
        ${item.previewable ? `<button class="preview-button" data-path="${escapeHtml(item.path)}" data-preview-kind="${escapeHtml(item.preview_kind)}">Preview</button>` : ""}
      </div>
    </div>
  `;
}

function wirePreviewButtons() {
  $$(".preview-button").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const path = btn.dataset.path;
      const kind = btn.dataset.previewKind || "text";
      $("#preview-title").textContent = path;
      if (kind === "image") {
        $("#preview-body").innerHTML = `<img class="preview-image" src="/api/file/raw?path=${encodeURIComponent(path)}" alt="${escapeHtml(path)}" />`;
      } else if (kind === "pdf") {
        $("#preview-body").innerHTML = `<iframe class="preview-frame" src="/api/file/raw?path=${encodeURIComponent(path)}"></iframe>`;
      } else {
        const data = await api(`/api/file?path=${encodeURIComponent(path)}`);
        $("#preview-body").innerHTML = `<pre class="preview-text">${escapeHtml(data.content)}</pre>`;
      }
      $("#preview-dialog").showModal();
    });
  });
}

function render() {
  renderHeader();
  renderOverview();
  renderPipeline();
  renderArtifacts();
  renderKnowledge();
  renderLogs();
}

function initTabs() {
  $$(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.activeTab = btn.dataset.tab;
      $$(".tab").forEach((b) => b.classList.toggle("is-active", b === btn));
      $$(".tab-panel").forEach((panel) => panel.classList.add("is-hidden"));
      $(`#tab-${state.activeTab}`).classList.remove("is-hidden");
    });
  });
}

function initDialog() {
  $("#preview-close").addEventListener("click", () => $("#preview-dialog").close());
}

initTabs();
initDialog();
refresh();
setInterval(refresh, 3000);
