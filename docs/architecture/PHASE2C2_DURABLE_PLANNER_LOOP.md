# Phase 2C.2: Durable Planner Loop

Phase 2C.2 adds a bounded, provider-neutral next-action loop to the durable AgentRun runtime.

## Contract

A planner turn may return exactly one typed decision:

- `tool`: execute one registered tool with validated arguments;
- `complete`: finish with an evidence-grounded summary;
- `blocked`: stop with an explicit blocker.

Free-form model prose is not executable. Unknown tools and malformed decisions are rejected before action.

## Durability

Planner state is stored under the AgentRun checkpoint as `planner`, including turn count, last decision, bounded observations, final summary, and blocker. Each decision and accepted observation is also appended to the hash-chained AgentRun event ledger.

## Authority

This slice exposes read-only tools only. It does not grant promotion or workspace mutation authority. SourcePlan remains the human promotion boundary.

## Routes

- `POST /edgek/agent-runs/{run_id}/planner/execute`
- `GET /edgek/agent-runs/{run_id}/planner`

The execute route supports deterministic `simulate_decisions` for offline proof and otherwise calls the configured provider through the existing BEAST client using a strict JSON decision prompt.
