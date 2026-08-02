# Phase 1D: Pair Programmer Renderer Decomposition

**Date:** 2026-07-18  
**Status:** Complete  
**Scope:** `desktop-ide/renderer/js/beast-ai-coding.js`

## Objective

Replace the 1,282-line Pair Programmer controller with a compact composition root and fourteen focused renderer modules without changing the public `window.BeastAICoding` contract, DOM contracts, stream event names, SourcePlan authority, context policy, or operator approval behaviour.

## Result

`renderer/js/beast-ai-coding.js` is now a 32-line composition root. It creates one shared runtime capsule, composes fourteen factories, exposes the same twenty-four public methods, and binds the existing `beast:agent-sourceplan-applied` event.

The extracted modules are:

| Module | Responsibility |
|---|---|
| `agent-client.js` | Provider routing, session creation, run streaming, retry, recovery, cancellation and worktree launch |
| `agent-store.js` | Pair Programmer persistence, restoration and state patching |
| `agent-events.js` | Trace, progress, stream event decoding and watchdog state |
| `agent-view.js` | Open, expanded and prompt view state |
| `context-picker.js` | Operator-selected context, selection capture, suggestions and requested-context resolution |
| `context-manifest.js` | Context normalization, mentions, bounded manifest construction and Code Cortex expansion |
| `approval-cards.js` | Governed capability approval request handling |
| `tool-cards.js` | Human-readable narration for tools, commands, verification and agent events |
| `plan-view.js` | Action IR draft detection, proposal normalization and proposal summaries |
| `verification-view.js` | Operator-approved isolated verification and verifier-result projection |
| `sourceplan-handoff.js` | SourcePlan staging, review navigation and post-apply feedback |
| `conversation-renderer.js` | Messages, turns, narration, previews and proposal-turn updates |
| `mode-controller.js` | Ask, Edit and Agent semantics, profiles, initial progress and model instructions |
| `budget-view.js` | Compute-economy and crystal telemetry projection |

The existing transport and Action IR parser remain separately owned by:

- `beast-ai-transport.js`
- `beast-ai-intent.js`

## Architectural boundaries

- The composition root contains no run, persistence, SourcePlan, approval or verification implementation.
- Shared stream ownership is explicit through `runtime.streamState` rather than closure variables scattered across modules.
- Cross-module calls resolve through an injected API object, avoiding new global business functions.
- The public Pair Programmer API remains exactly twenty-four methods.
- No new renderer module receives Node, filesystem, process or direct network authority.
- Capability approval remains separate from SourcePlan promotion.
- Context suggestions remain advisory and operator-selected.

## Verification changes

Static proof scripts now inspect the composed AI renderer graph instead of assuming all Pair Programmer behaviour must remain in one file. The functional proposal fixture loads all fourteen modules before the composition root and still exercises:

- Agent Action IR streaming;
- proposal draft detection;
- validation projection;
- SourcePlan readiness;
- Ask-mode streaming;
- conversation completion.

A new `verify-phase1-renderer-boundaries.js` test enforces module presence, script order, ownership, entrypoint size and public API continuity.

## Measured outcome

- Pair Programmer entrypoint: **1,282 lines to 32 lines**
- Focused modules created: **14**
- Existing AI support modules retained: **2**
- Public methods preserved: **24**
- Behavioural parity foundation: **89/89**
- Execution-target verification: **12 passed, 3 environment-gated skips, 0 failures**
- Desktop static smoke: **24/24**
- Desktop launch smoke: **9/9**
- Visual acceptance: **110 scenarios, 0 failures**

## Follow-on work

Phase 1E can now focus on the backend `app/routes/ide.py` monolith. The renderer has stable seams for the future AgentRunEngine, durable approvals, replayable event transport and proper backend cancellation without another large UI rewrite.
