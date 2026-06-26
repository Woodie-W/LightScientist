# LightScientist WebUI Design

## Goal

Build a WebUI for `LightScientist` that keeps the clarity of the current CLI live output, borrows the restrained visual style of `CORAL-main/web`, but is redesigned around `LightScientist`'s three-layer research workflow instead of a fixed benchmark leaderboard.

This UI should make these things immediately visible:

- what project is running
- which research phase and stage is active
- what the second-layer supervisor is doing
- what each third-layer worker is doing
- what knowledge, skills, logs, and artifacts currently exist
- how the project is moving across `idea -> experiment -> paper -> done`

It should not assume there is a single fixed score metric or a benchmark leaderboard.


## Design Direction

Use the same general visual language as `CORAL-main/web`:

- light gray background
- dark neutral text
- serif display font for page titles
- sans body font
- mono font for logs and structured state
- compact pill tabs
- dense but readable information cards

But the information architecture should change:

- `CORAL` centers on runs, attempts, scores, and lineage
- `LightScientist` should center on projects, phases, stages, workers, knowledge, and artifacts


## Core UI Concept

The UI should feel like a **research operations console**, not a benchmark dashboard.

The top-level mental model is:

1. One project
2. One current first-layer stage
3. One second-layer supervisor managing the current stage
4. One or more third-layer workers producing artifacts
5. Files, knowledge, skills, and logs as persistent evidence


## Top Navigation

Keep the same simple header pattern as CORAL:

- left: product name + current project selector
- middle/right: tab pills
- far right: live status chips

Recommended tabs:

- `Overview`
- `Pipeline`
- `Workspace`
- `Knowledge`
- `Logs`
- `Runs`

Optional future tabs:

- `Metrics`
- `Settings`


## Header Status Strip

The header should always show a compact live strip:

- current phase
- current stage
- project status
- supervisor status
- active worker count
- waiting/background count
- last event time

Example:

```text
paper / paper.write | running | supervisor active | 1 worker | 0 waiting | 0 background | updated 3s ago
```


## Page 1: Overview

This is the landing page and should combine the most important signals.

### Layout

Two-column layout like CORAL.

Left column:

- Project summary card
- Stage progression timeline
- Current stage brief
- Recent events stream

Right column:

- Supervisor card
- Worker cards
- Recent artifacts
- Quick knowledge snapshot

### Panels

#### 1. Project Summary

Show:

- project id
- topic
- mode: `auto` or `manual`
- current phase
- current stage
- current status
- workspace root

This maps directly to:

- `.lightscientist/project_state.json`

#### 2. Stage Progress Timeline

This is one of the key LightScientist-specific innovations.

Instead of CORAL's attempt chart, show a clear stage flow:

```text
idea.survey -> idea.generate -> idea.evaluate -> idea.gate
experiment.setup -> experiment.loop -> experiment.analyze -> experiment.gate
paper.plan -> paper.figure -> paper.write -> paper.review
```

Use node colors:

- completed: dark
- active: highlighted
- pending: muted
- failed: red
- waiting_user: amber

This should be one of the main visual differences from CORAL.

#### 3. Current Stage Brief

Show:

- stage description
- required output
- allowed next stages
- latest stage summary if available

Data sources:

- `research_stages.py`
- latest `finish_stage` event
- `PROCESS.md`

#### 4. Supervisor Card

Show the second layer as a first-class object:

- task id
- supervisor session state
- whether busy or idle
- current decision context
- last decision
- queue length

Important because this is part of LightScientist's architecture, and CORAL does not have this exact concept.

#### 5. Worker Cards

Each third-layer worker card should show:

- worker id
- status
- current step count
- action count
- progress text
- current output path
- workspace path
- last activity time

This is the main real-time execution surface.

#### 6. Recent Events

Use the existing structured event stream:

- `.lightscientist/events.jsonl`

Render latest events with layer tags:

- `L1`
- `L2`
- `L3`

Color by kind:

- stage transition
- model call
- tool call
- tool result
- worker status
- finish stage

This page should feel like “high signal operational summary”.


## Page 2: Pipeline

This is the page that best expresses LightScientist's novel control structure.

### Purpose

Show the three-layer architecture in motion.

### Main Sections

#### 1. Layer Diagram

Top-to-bottom live diagram:

- Layer 1: Research Controller
- Layer 2: Runtime Supervisor
- Layer 3: Execution Runtime / Workers

Each layer box shows:

- status
- current objective
- latest emitted event

This is the best place to visually explain the system to others.

#### 2. Stage State Machine

This is not a static doc diagram. It should show:

- current node
- visited nodes
- next possible nodes
- whether current stage is gated

This directly reflects:

- `research_stages.py`
- `project_state.json`
- `PROCESS.md`

#### 3. Supervisor Queue

Show the second-layer event queue explicitly:

- queued events
- latest processed event
- waiting worker events
- background worker resumes

This panel is valuable for debugging supervisor behavior.

#### 4. Worker Sessions

For each current or recent worker session:

- agent id
- thread id
- resume mode
- session status
- latest summary

This page is the closest replacement for the mental model currently available only from CLI logs.


## Page 3: Workspace

This page should expose artifacts and file-based long-term memory.

### Layout

Three-panel layout:

- left: workspace tree
- center: file preview
- right: metadata / summaries

### Main Sections

#### 1. Standard Artifact Areas

Show pinned sections:

- `phase1-idea/`
- `phase2-experiment/`
- `phase3-paper/`
- `.lightscientist/`

#### 2. Core State Files

Show quick cards for:

- `PROCESS.md`
- `.lightscientist/project_state.json`
- `.lightscientist/events.jsonl`
- `research.jsonl` when present
- `research.md` when present

#### 3. Artifact Preview

Support preview of:

- markdown
- json/jsonl
- plain text logs
- pdf existence metadata
- images/figures

This is the page that replaces manual shell `cat` and `find` for common inspection.


## Page 4: Knowledge

This should intentionally borrow from CORAL's `Knowledge` page, but adapted.

### Split the page into three vertical bands

#### 1. Skills

Show all configured stage skills:

- idea skills
- experiment skills
- paper skills
- pipeline skills

Each skill card shows:

- skill name
- phase
- short description from front matter
- whether currently active

The currently active stage skill should be highlighted.

#### 2. Knowledge / Memory

This panel should aggregate:

- `PROCESS.md`
- stage summaries
- `research.md`
- selected report summaries

This is where LightScientist differs from CORAL:

- not just reusable skills
- also persistent project memory

If later you add a `memory/` directory like EvoScientist, this page should naturally absorb it.

#### 3. Notes / Evidence

Show evidence sources gathered by the project:

- report outlines
- experiment summaries
- generated notes
- phase summaries

This page should answer:

“what has the system already learned, and what reusable instructions is it using now?”


## Page 5: Logs

This should keep much of the spirit of CORAL's `Logs` page.

### Layout

Left sidebar:

- agent/session list
- filter by layer
- filter by status

Main panel:

- chronological structured log stream

Right contextual panel:

- selected event metadata
- related file path
- related worker/session info

### Required Features

#### 1. Layer Filter

Show logs by:

- all
- L1 only
- L2 only
- L3 only

#### 2. Type Filter

Filter:

- model calls
- tool calls
- tool results
- stage transitions
- worker status changes
- finish_stage

#### 3. Session Filter

Choose:

- supervisor
- specific worker

#### 4. Sticky Live Mode

When enabled, auto-scroll to newest events, like the current CLI `--watch`.

This page should feel like the browser version of the current terminal watch experience.


## Page 6: Runs

Because LightScientist is project-based rather than benchmark-based, this page should not be “attempt leaderboard”.

Instead it should be a **project run history page**.

### Show

- past projects
- each project's topic
- workspace path
- current/final phase
- final status
- start time
- last update time

If a project has multiple stage runs, show nested entries:

- `paper.plan`
- `paper.figure`
- `paper.write`
- etc.

This page replaces CORAL's run selector with a more project-centric history view.


## Panels Worth Reusing from CORAL

These ideas from CORAL are worth keeping:

- compact tabbed top nav
- run/project selector in header
- status chips in header
- dense overview cards
- dedicated Knowledge page
- dedicated Logs page
- live updates via SSE


## Panels That Need LightScientist-Specific Redesign

These should not be copied literally:

- leaderboard
- attempt score table as the main focus
- benchmark config as the primary identity
- DAG as attempt lineage only

Replace them with:

- stage pipeline timeline
- first/second/third layer live view
- artifact-centered workspace page
- skill + memory + evidence knowledge page


## Information Hierarchy

The UI should rank information in this order:

1. what stage is active now
2. what the system is doing now
3. what artifacts already exist
4. what knowledge and skills are shaping the current behavior
5. what happened recently
6. what happened historically


## Data Model Mapping

The WebUI should be built around existing local files and runtime events.

### Current direct sources

- `.lightscientist/project_state.json`
- `.lightscientist/events.jsonl`
- `.lightscientist/stage-runs/*/agent-run.md`
- `PROCESS.md`
- `research.jsonl`
- `research.md`
- phase artifact directories

### Existing runtime objects worth exposing through an API

- `ResearchState`
- `RuntimeTask`
- `AgentRecord`
- `ExecutionResult`
- `SupervisorEvent`


## Minimal Backend API for WebUI

You do not need a complicated backend first.

Start with a very small local API service that serves:

- `GET /api/project/state`
- `GET /api/project/process`
- `GET /api/project/events`
- `GET /api/project/files`
- `GET /api/project/file?path=...`
- `GET /api/project/skills`
- `GET /api/project/runs`
- `GET /api/project/workers`
- `GET /api/project/supervisor`
- `GET /api/project/stages`
- `GET /api/project/events/stream` (SSE)

This is enough for the first version.


## Real-Time Update Strategy

The simplest good design is:

- load initial state from JSON/file API
- update live via SSE from the event stream

Reuse the same event categories already used by CLI:

- `stage_started`
- `stage_finished`
- `stage_transition`
- `worker_created`
- `worker_status`
- `worker_progress`
- `model_call`
- `model_output`
- `tool_call`
- `tool_result`

This keeps the UI aligned with the current logging design.


## Recommended Frontend Stack

To stay close to CORAL's style and keep implementation simple:

- `React`
- `TypeScript`
- `Vite`
- `Tailwind CSS`

This also makes it easy to borrow layout patterns from `CORAL-main/web`.


## Visual Style Recommendation

Reuse the same kind of token system, but make the product identity distinct.

### Typography

- display: `Source Serif 4`
- body: `DM Sans`
- mono: `JetBrains Mono`

### Color direction

Keep the cool neutral palette, but add one restrained accent for LightScientist:

- base background: warm-cool paper gray
- accent: muted teal or muted rust

Suggested accent usage:

- stage highlights
- active worker
- selected tab
- phase chips

Avoid bright benchmark colors.


## Distinctive LightScientist Visual Elements

To make the product feel like its own system, add these elements:

### 1. Phase Ribbon

A horizontal ribbon near the top showing:

- Idea
- Experiment
- Paper

This is the product's main identity.

### 2. Layer Stack Card

A persistent compact widget showing:

- L1 current stage
- L2 current supervision state
- L3 current worker state

This is unique to LightScientist and should be visible on at least `Overview` and `Pipeline`.

### 3. Artifact Shelf

A compact card showing the latest stage deliverables:

- current report
- current figure set
- current experiment summary
- latest phase output

This gives a “research output” feel, unlike CORAL's score-first design.


## First Implementation Cut

The first usable version should include only:

- header
- Overview
- Pipeline
- Knowledge
- Logs
- basic Workspace browser

Do not build everything at once.

### Version 1 goals

- can inspect one project workspace
- can watch current stage progress live
- can inspect workers and supervisor
- can preview key artifacts
- can inspect skills and memory
- can read live logs

That alone is enough to demonstrate the system.


## Suggested Directory Layout

Recommended frontend placement:

```text
LightScientist/
  web/
    package.json
    vite.config.ts
    src/
      App.tsx
      main.tsx
      index.css
      lib/api.ts
      hooks/useSSE.ts
      components/
      pages/
```

Recommended minimal backend placement:

```text
src/esnext/webui_api.py
src/esnext/webui_data.py
```

Keep it thin. The backend should mostly read existing files and expose current in-memory status when available.


## Proposed Page-to-Data Mapping

### Overview

- `project_state.json`
- `PROCESS.md`
- recent `events.jsonl`
- active workers
- current supervisor snapshot

### Pipeline

- `research_stages.py`
- current `ResearchState`
- supervisor queue + worker states

### Workspace

- filesystem tree under workspace root
- previews of standard files

### Knowledge

- `skills/*/SKILL.md`
- current stage skill
- `PROCESS.md`
- summaries and notes

### Logs

- `events.jsonl`
- `stage-runs/*/agent-run.md`
- worker/supervisor filtered events

### Runs

- discovered workspace histories or configured run index


## Why This Design Fits LightScientist Better

Because the system's core novelty is not:

- parallel agent attempts
- score trajectories
- benchmark optimization only

It is:

- staged research control
- persistent multi-layer supervision
- skill-driven stage execution
- artifact-centered long-running research workflows

So the UI should make those structures visible.


## Final Recommendation

Use `CORAL-main/web` as the reference for:

- codebase choice
- visual restraint
- tabbed dashboard structure
- live event updates

But make `LightScientist`'s product identity center on:

- `Phase`
- `Stage`
- `Supervisor`
- `Worker`
- `Knowledge`
- `Artifacts`

That gives you a UI that feels related in quality and cleanliness, but clearly belongs to a different system.
