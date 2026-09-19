# BEAST Coding Agent Recovery — Phase 10 Distributed BEAST

Date: 2026-09-19

Status: **repository implementation complete; fresh runtime/CI proof required**

## Objective

Extend the Phase 5–9 source, mutation, verification, evidence, repair and learning contracts across local, SSH, container and Dev Container execution without creating a weaker remote authority path.

## Canonical distributed contract

A remote target changes **where** work executes, never **what counts as authority**.

1. Repository discovery, memory and crystals remain advisory.
2. Exact editable source still requires the exact-source lane.
3. Mutation remains confined to a bound Worktree Forge worktree.
4. Verification executes on the selected target and must bind its evidence to target kind, target identity, transport and current mutation epoch.
5. Failed verification keeps target evidence through repair classification and retry/degradation planning.
6. Retryable target/environment failures retry the same target verifier once, then degrade to a target-native bounded fallback.
7. Hard remote repair pressure may influence compute-route selection, but cannot grant source, mutation, verification or promotion authority.
8. SourcePlan synthesis still requires current passing verification for the latest mutation epoch.
9. Promotion remains independently governed and cannot be authorized by remote execution evidence alone.

## Implemented surfaces

The existing execution-target spine already supplies local/SSH/container target descriptors, target sessions, target-native tasks/tests, remote file read/write, protocol transport, extension routing and remote worktree execution.

Phase 10 closes the coding-agent authority seam by preserving remote verification transport in all three evidence surfaces:

- the immediate `worktree.verify` result;
- the checkpoint verification receipt;
- the `agent.verification.passed` / `agent.verification.failed` event.

The deterministic verification planner retains the target descriptor and selects target-native verification. Retryable remote failures preserve the same verifier once and then degrade to a bounded target-native syntax/compile fallback rather than silently switching to local execution.

## Recovery tests

`tests/test_agent_phase10_distributed_beast.py` covers remote target identity, same-target retry followed by target-native fallback, target/transport preservation through failed-verification evidence, and non-escalation of remote strategy into source or promotion authority.

The desktop execution-target parity gauntlet remains the broader integration acceptance surface. Live SSH/container/Compose handshakes remain environment-dependent and must be reported as skipped when no target is configured, never as passing.

## Exit assessment

The Phase 10 repository exit condition is satisfied at implementation level: local and remote coding requests use the same semantic and authority model, and remote verification/repair evidence remains target-bound.

This document does **not** claim a fresh live Phase 10 pass. The new recovery tests and execution-target parity gauntlet still need to run on an environment with the relevant Python dependencies, and live SSH/container acceptance requires configured targets.

Phase 11 may now unify these backend states in the operator surface without inventing UI-only authority.
