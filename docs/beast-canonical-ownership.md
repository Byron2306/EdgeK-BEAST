# BEAST Canonical Ownership Map

Date: 2026-07-08

This document tracks the canonical owners introduced by the BEAST/Gortex
upgrade and the reintegration workstream. The goal is to prevent older proof
engines, compatibility imports, route families, and evidence stores from
becoming peer authorities.

## Ownership Rules

| Concern | Canonical Owner | Inputs / Adapters | Notes |
|---|---|---|---|
| Code work and context | Code Cortex | Workspace Graph, Gortex, local indexers, semantic fallback, Context Packet | Context Packet is an output format, not a competing selector. |
| Mutation | SourcePlan | Action IR, Symbol Surgeon, Source Workbench | No source writes outside SourcePlan approval/apply/rollback. |
| Isolation and promotion | Worktree Forge | Git worktrees, verifier receipts, promotion gates | High-risk edits should move from recommendation to enforcement. |
| Policy and safety | Policy Gate Result | Mode Router, Spec Covenant, Safety Governor, Agent Passport, Output Governor | Shared shape should normalize allow/warn/approval/block decisions. |
| Compute route planning | Agent Scheduler | Mission Lattice, Crystal Runtime, Local Route Optimizer, Provider Economist, Inference Fabric | Every local/cloud/crystal route should emit one scheduler receipt. |
| Crystal edit memory | Mission Crystal Lattice | SourcePlan evidence, graph shape, policy hash, safety decision, verification | Advisory only until SourcePlan replay candidates are separately gated. |
| Evidence discovery | Evidence Bus | SourcePlan evidence, Chronicle, Memory Hull, Scheduler, Safety, Spec, Worktree, Crystal, Commons | Stores pointers and summaries, not raw proof payloads. |
| Operator view | Mission Cockpit | Evidence Bus, Code Cortex, Scheduler, Worktree Forge, Safety, Spec, Lattice | Cockpit reads canonical surfaces first, filesystem fallback second. |
| Capability discovery | Capability Plane | Capability Registry, Skill Registry, Skill Tree, Plugin Marketplace, Capability Exchange, Commons | Promotion/routing should use one facade. |

## Compatibility Imports

These paths remain for backward compatibility. New code should import the
canonical path instead.

| Compatibility Path | Canonical Path | Status |
|---|---|---|
| `app.kernel.task_envelope` | `app.kernel.execution.task_envelope` | `DEPRECATED_COMPAT_IMPORT` |
| `app.kernel.ollama_scout` | `app.kernel.local.ollama_scout` | `DEPRECATED_COMPAT_IMPORT` |
| `app.kernel.commons_spaces` | `app.kernel.networking.commons_spaces` | `DEPRECATED_COMPAT_IMPORT` |
| `app.kernel.canon_registry` | `app.kernel.registry.canon_registry` | `DEPRECATED_COMPAT_IMPORT` |
| `app.kernel.forensic_memory` | `app.kernel.storage.forensic_memory` | `DEPRECATED_COMPAT_IMPORT` |
| `app.kernel.insight_compiler` | `app.kernel.data_processing.insight_compiler` | `DEPRECATED_COMPAT_IMPORT` |
| `app.kernel.beast_cli_executor` | `app.kernel.deployment.beast_cli_executor` | `DEPRECATED_COMPAT_IMPORT` |

## Route Family Ownership

| Route Family | Owner | Reintegration Direction |
|---|---|---|
| `/edgek/code-cortex/*` | Code Cortex | Keep as code-intelligence front door. |
| `/edgek/sourceplan/*` and patch-plan flows | SourcePlan | Keep as only mutation path. |
| `/edgek/worktree-forge/*` | Worktree Forge | Promote high-risk recommendations to gates. |
| `/edgek/mode-router/*` | Policy Gate Result | Normalize into shared gate receipts. |
| `/edgek/spec-covenant/*` | Policy Gate Result | Keep as project-rule compiler input. |
| `/edgek/safety-governor/*` | Policy Gate Result | Keep as command/workspace safety input. |
| `/edgek/agent-scheduler/*` | Agent Scheduler | Keep as compute route planner. |
| `/edgek/mission-lattice/*` | Mission Crystal Lattice | Keep advisory until replay candidates are implemented. |
| `/edgek/mission-cockpit/*` | Mission Cockpit | Read canonical surfaces first. |
| `/edgek/crystal-*`, `/edgek/compute/*`, `/edgek/proof-local/*` | Agent Scheduler / Evidence Bus | Register receipts and feed scheduler instead of parallel routing. |
| `/edgek/commons-*`, `/edgek/meta-tool-commons/*`, `/edgek/capability-*` | Capability Plane / Evidence Bus | Use one facade before routing/promotion. |

## First Reintegration Milestones

1. Mark compatibility shims.
2. Add Evidence Bus pointer index.
3. Register SourcePlan positive and negative evidence packets.
4. Add Evidence Bus summary to Mission Cockpit.
5. Add shim import guard tests.
6. Move `AdaptiveDispatcher` behind Agent Scheduler.
7. Normalize policy receipts into `PolicyGateResult`.
