# Physical Crystal Fabric Spine Design

## Purpose

BEAST will connect its existing AgentRun, Sensorium, crystal, ForgeKV, Commons,
Crystal Bus, and Socket Guardian components through one governed physical
fabric. The design preserves the proven security boundary: remote Commons
nodes store and reproduce hypotheses but never receive execution authority.

## Architecture

Every AgentRun, swarm lane, tool invocation, provider request, verification,
and failure produces one canonical Episode Envelope. Sensorium evaluates the
envelope and may create negative, context, skill, verifier, KV, or executable
typed-IR crystal candidates. Durable artifacts live in a content-addressed
store; sealed memfd capsules are transient local hydration and transport.

Local capsule handoff uses one consolidated Crystal Bus over
`AF_UNIX/SOCK_SEQPACKET` with `SCM_RIGHTS`, peer credentials, process leases,
workspace identity, policy generation, sequence protection, and one-use
capability authority. Socket Guardian owns listening sockets and descriptor
custody and emits signed lifecycle receipts.

Remote publication sends only privacy-filtered manifests, portable content
chunks, compatibility metadata, and proofs through an ML-KEM-bound channel.
Raw native KV state and memfd descriptors never cross a node boundary. A
remote artifact returns as a quarantined hypothesis and requires node-local
held-out reproduction before sovereign promotion.

## Trust and Identity

A live Commons endpoint is identified by the tuple:

- node ID and pinned Ed25519 public key;
- signed descriptor digest and workload digest;
- lattice or ARDA policy generation;
- endpoint-possession proof;
- Guardian lease generation, network namespace, and trust domain where
  available.

An HTTP response, process name, container state, or host/port alone never
establishes identity. Endpoint changes are admitted only after the candidate
descriptor passes the existing signature, workload, authority, and trust
checks. Failed candidates leave the existing endpoint untouched.

## Topology Contract

One generated topology manifest is authoritative for Docker publication,
remote registry endpoints, Guardian service bindings, health checks, and IDE
display. Runtime discovery may propose a new endpoint, but only signed
reconciliation can update the registry. Stale endpoints remain visible as
history rather than silently becoming trusted aliases.

## Crystal Authority Classes

- Negative crystals deny or constrain known-bad reuse.
- Context and RAG crystals are data-only.
- Skill crystals provide governed recipes but no implicit tool authority.
- Verifier crystals provide deterministic checks.
- KV crystals require exact model, tokenizer, template, runtime,
  architecture, quantization, rope, policy, privacy, and repository identity.
- Executable crystals contain promoted typed IR and require an expiring,
  one-use local capability.
- Capsules are transport containers and never grant authority themselves.

## Delivery Sequence

1. Signed endpoint reconciliation and one topology contract.
2. Descriptor-aware Docker and control-plane health.
3. Live Socket Guardian ownership for BEAST and Commons services.
4. Consolidated Crystal Bus transport and custody receipts.
5. Canonical Episode Envelope across AgentRun, swarm, tools, and providers.
6. Candidate extraction, negative evidence, held-out replay, and promotion.
7. ForgeKV/Commons publication and local quarantine/reproduction.
8. IDE observability for topology, custody, compatibility, and promotion.

Each delivery is independently testable and fail-closed. Historical evidence
may guide recovery but never substitutes for a fresh live possession check.

## Explicit Non-Goals

- Commons nodes do not execute promoted crystals.
- Remote publication does not export native KV arrays, memfd descriptors,
  source secrets, raw prompts, or unredacted workspace content.
- Reconciliation does not trust DNS, Docker metadata, or discovery catalogs
  without signed descriptor verification.
- This design does not replace the existing promotion registry or authority
  ledgers; it connects them through canonical identities and receipts.
