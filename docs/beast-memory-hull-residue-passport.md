# BEAST Memory Hull, Residue Seal, and Agent Passport

Status: **production-grade local BEAST layer implemented**.

This layer folds editable memory, artifact signing, and agent identity policy
into BEAST without replacing Chronicle, Commons, or vector retrieval.

## Memory Hull

Default shape:

```text
~/.beast/vault/
  projects/
  tasks/
  decisions/
  provider_receipts/
  quality_cascade/
  residue/
  policies/
```

Each run can write human-readable Markdown residue plus a signed JSON sidecar.
The Markdown is intentionally editable and inspectable. The sidecar preserves
tamper-evident provenance, including a signed hash of the Markdown body.

Production hardening now includes:

- atomic Markdown, sidecar, and index writes
- path containment under the configured vault root
- a signed `.index/residue_index.json`
- inventory verification and simple indexed search/listing
- BEAST correlation, caller, and system-compatibility metadata

Implementation:

- `app/kernel/storage/memory_hull.py`

## Residue Seal

Residue Seal signs task manifests, provider receipts, quality-cascade results,
compressed context summaries, policy decisions, and repository fingerprints
with a purpose-specific Ed25519 key.

It does not reuse mTLS, federation, or provider keys.

Production hardening now includes native in-process Ed25519 signing via
`cryptography`, OpenSSL fallback/backward verification, payload and message
hash checks, public-key hash validation, expected-purpose verification, atomic
key creation, and a health report.

Implementation:

- `app/kernel/security/residue_seal.py`

## Agent Passport

Agent Passport models BEAST workload identity using SPIFFE-shaped IDs now, with
a future path to mTLS/SPIRE later.

Examples:

```text
spiffe://beast.local/mcp/server
spiffe://beast.local/proxy/gateway
spiffe://beast.local/provider/nim
spiffe://beast.local/tool/github
spiffe://beast.local/scout/repo-reader
```

Default policy examples:

- Scout can read/append Memory Hull notes.
- Proxy can call provider adapters.
- Runtime governor can approve cloud escalation only when quality cascade is
  approved.
- Unapproved cloud provider calls are denied by default.

Production hardening now includes normalized SPIFFE IDs, expiring passports,
policy linting, deny precedence, deterministic decision ids, policy-set/facts
hashes, optional residue-sealed decisions, and a strict `authorize` helper for
BEAST runtime gates.

Implementation:

- `app/kernel/security/agent_passport.py`

## Claim boundary

This is a production-grade local identity and residue layer. It is ready to
back BEAST runtime policy checks, signed memory residue, and local audit trails.
It is still intentionally not a full mTLS deployment or SPIRE control plane;
the SPIFFE-shaped contract is ready for that binding when deployed.
