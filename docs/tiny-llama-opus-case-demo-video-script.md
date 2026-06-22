# BEAST Power Console Demo Script

## Tiny Model, Real Work

Goal: record the Opus/Codex-style case study from the TUI using the isolated
Tiny Llama/Qwen 0.5B demo lane.

## Setup

Start the TUI:

```bash
bin/beast tui
```

Press `Ctrl+T` from Mission Control to arm the Tiny Llama Opus case demo. This
creates the isolated case repo, captures the expected failing baseline, selects
the bounded context, and sets the session provider/model to:

- provider: `ollama`
- model: `qwen2.5:0.5b`
- artifact: `benchmarks/results/tiny_llama_opus_case_study_tui_recording`

## Recording Beats

### 0:00-0:15 Opening

Screen: Mission Control with PREC ribbon, providers, capabilities, Commons, and
Swarm visible.

Narration:

> This is BEAST. A local-first governed agentic coding environment. Today I am
> going to show something that challenges the bigger-models-are-always-better
> narrative, using only a 0.5 billion parameter local model.

### 0:15-0:45 Live Session and Streaming

Actions:

- Press `2` for Live Session.
- Press `s` to start a session.
- Press `Enter`, type the Opus case repair prompt, press `Enter`.
- Let the streaming response and PREC/tool events update.

Narration:

> Here is the cockpit. I start a live session and ask it to repair a broken
> provider gateway package. Watch both the assistant text and the internal PREC
> stages update. Even with a tiny model, BEAST keeps the workflow responsive
> through local scout fallback, streaming handling, and bounded context.

### 0:45-1:20 Context and Planning

Actions:

- Press `c` to open the context picker.
- Show the selected isolated case files.
- Press `o` to build the governed source patch plan.
- Press `f` to preview the unified diff.
- Toggle one hunk with `Space`, then turn it back on.

Narration:

> I bind the context to the relevant files. Then I ask for a governed patch
> plan. BEAST runs the full loop: perceive, reason, economize, crystallize. The
> result is an explicit operation list. Now I preview the diff. Each hunk can be
> toggled before anything is written.

### 1:20-2:00 Approval, Apply, Verification

Actions:

- Press `y` to approve the plan.
- Press `u` to apply selected hunks.
- Show the tool event for isolated `pytest`.
- Show Chronicle crystallization/rollback message.

Narration:

> Nothing gets written without approval. I approve, apply the selected hunks,
> and verification runs automatically. BEAST records rollback state, runs syntax
> checks, runs the isolated case pytest, and crystallizes the result into the
> Chronicle.

### 2:00-2:30 Tiny Model Orchestration

Actions:

- Open the normalized orchestration plan artifact or Swarm events.
- Optionally run the command palette item: `Run/record Tiny Llama Opus case gauntlet`.

Narration:

> Behind the scenes, the repair is driven by a 0.5B Qwen2.5 model. It does not
> write code by magic. It uses BEAST scaffolding: Meta Tool Commons, Capability
> Registry, Swarm orchestration, OpenClaw planning, approval gates, verification,
> receipts, and promotion. The tiny model acts as the intent router and policy
> follower. The system does the heavy lifting.

### 2:30-3:00 Rollback and Safety

Actions:

- Press `z` to demonstrate rollback, or show the rollback receipt.

Narration:

> Want to undo? One key. Rollback is always available. Every high-risk action
> leaves an audit trail. This is what governed agentic coding looks like.

### 3:00-3:40 Closing

Screen: Mission Control, Chronicle, and the latest Tiny Llama case result.

Narration:

> BEAST shows that we do not always need bigger models and more compute. We need
> better systems: strong memory, clear governance, observable execution, and
> closed learning loops. This workflow, from prompt to verified patch to
> promotion candidate, runs locally with strong safety.

End screen:

- Local-first. Governed. Self-improving.
- Built as a side project in South Africa.

## Production Notes

- Overlay keypresses in the corner.
- Zoom in slightly on the diff/hunk table.
- Show `qwen2.5:0.5b` at least twice.
- Keep the narration tight and let the TUI do most of the proof.
