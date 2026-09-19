# BEAST Coding Agent Recovery — Phase 12 Agent Gauntlet & Promotion

Date: 2026-09-19

Status: **IMPLEMENTATION COMPLETE — live gauntlet proof pending**

## Purpose

Phase 12 does not add another coding-agent authority plane. It is the programme exit gate.

The integrated agent must produce evidence across five required case families:

1. simple mutation;
2. cross-file reasoning;
3. verifier-driven repair;
4. large-repository navigation;
5. remote-target work.

## Promotion contract

Every case must prove completion, exact-source grounding, governed mutation, fresh verification, a valid event chain, and absence of unsupported completion claims.

Additional case-specific requirements:

- cross-file reasoning must use evidence from at least two relevant files;
- repair must be observed and remain within the bounded repair contract;
- large-repository navigation must use repository discovery without depending on manual file attachment;
- remote work must preserve target evidence and the same authority model as local execution.

The evaluator returns PROMOTE only when all five case receipts satisfy those requirements. Its decision is evidence evaluation only and grants no source, mutation or promotion authority.

## Implementation

- app/kernel/agents/phase12_gauntlet.py
- tests/test_agent_phase12_gauntlet.py
- scripts/proof/evaluate_phase12_agent_gauntlet.py

Existing live harnesses remain useful evidence producers, especially scripts/proof/run_canonical_agent_ollama_closure.py and scripts/proof/benchmark_real_ide_tasks.py. Phase 12 deliberately does not relabel old benchmark output as new proof.

## Baseline language

The repository-supported architectural baseline is:

- before: thin LLM wrapper with fragmented/disconnected BEAST organs;
- after: governed integrated coding-agent vertical slice.

This is an architectural comparison, not a performance benchmark. Phase 12 will not claim that BEAST is faster, more accurate, or better than another coding agent until live comparative evidence supports that statement.

## Runtime closure

Run the deterministic promotion-gate tests now. Run the five live case families on Debian, where the deferred Phase 10 SSH/container acceptance and Phase 11 Electron acceptance can be included in the same final proof bundle.

Until those receipts exist, Phase 12 implementation is complete but the recovery programme is not yet runtime-promoted.
