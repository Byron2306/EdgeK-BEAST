# BEAST Proof-Local Compute Integration Proposal

Status: **proposed**  
Target environment: **CPU-first, local-first, optional LAN federation**  
Primary thesis: **route work to the place where the strongest safe proof already exists**

## Executive Summary

Inference infrastructure increasingly reduces cost by managing physical state:
KV pages, prompt prefixes, retrieved context, model partitions, scheduling slots,
network paths, and hardware tiers. BEAST should use those systems where they are
available, but it should not duplicate their token schedulers, allocators, or
cache engines.

BEAST's distinct layer is verified semantic reuse:

```text
physical inference systems virtualize memory and execution
BEAST virtualizes verified work
```

This proposal introduces **Proof-Local Compute**: a CPU-capable architecture in
which Compute Governor chooses among local replay, local Ollama, a trusted LAN
peer, an adopted Commons Space, or an approved provider according to proof
strength, privacy, latency, bandwidth, and local reproduction cost.

The immediate implementation does not require GPUs, RDMA, CXL, SmartNICs, or
distributed model sharding. It uses the infrastructure BEAST already has:

- Compute Governor for admission and route authority;
- Compute Forge for offline preparation and verification;
- Commons Spaces for portable hypotheses and reproduction evidence;
- Federated Commons for signed exchange and local allowlisting;
- Crystal Compute for promoted capability;
- KV transport and durable inference storage for private local state;
- Chronicle, receipts, and Crystal Chain for evidence and lifecycle history;
- Ollama for real CPU inference;
- Docker nodes for LAN/federation experiments.

The result is not a new inference engine. It is a governed control and asset
plane above inference engines.

## Goals

1. Reduce repeated inference, context processing, artifact transfer, and failed
   routes on CPU-only systems.
2. Let LAN peers advertise proof without exporting private payloads.
3. Transfer manifests and verifier descriptions before large artifacts.
4. Make stale or missing evidence degrade to recomputation, never unsafe reuse.
5. Record successful and blocked work as tamper-evident lifecycle evidence.
6. Preserve a generic adapter boundary for future vLLM, SGLang, LMCache, Ray,
   Dynamo, and llm-d deployments without requiring them today.
7. Let dense verified history become a governed training scaffold for local
   adapters, compressed task models, and sparse compute routes.

## Non-Goals

- Reimplement continuous batching, PagedAttention, RadixAttention, CUDA memory
  allocation, tensor parallelism, or model-serving schedulers.
- Pretend GPU-only systems run on the current CPU host.
- Exchange raw private KV tensors through Public Commons.
- Treat semantic similarity as sufficient authority for reuse.
- Turn local Crystal Chain records into a public financial cryptocurrency.
- Run arbitrary code delivered by an active packet or remote Space.
- Split model layers across unreliable internet peers in the first release.
- Mutate base model weights blindly or treat adapter output as authority before
  local policy and verifier gates pass.

## Architectural Rule

> Weak consistency is acceptable only when failure degrades to recomputation,
> never to unsafe reuse.

Examples:

- stale peer advertisement -> local miss or new verification;
- missing artifact -> manifest-only result;
- expired receipt -> quarantine;
- fingerprint mismatch -> demotion;
- incompatible engine cache -> recompute prefill;
- unavailable peer -> local or approved-provider fallback;
- failed replay -> no adoption and no credit.

## Existing BEAST Ownership

No new top-level "inference fabric" should take authority from existing layers.

| Concern | Existing owner | Proposed extension |
| --- | --- | --- |
| Admission, budgets, risk, route choice | Compute Governor | Proof-local route scoring and bandwidth escrow |
| Offline CPU preparation | Compute Forge | Build summaries, verifier capsules, mutation cases, and peer advertisements |
| Local model execution | Inference Engine Fabric / Ollama | CPU execution and health evidence |
| Exact and semantic replay | Durable Inference Storage / Verified Reuse | Shared proof identity and context-aware safety gates |
| Private cache state | KV Cache Transport / Ollama context cache | Local-only backend profile; no public payload export |
| Portable capability package | Commons Spaces | Receipt packets and staged artifact retrieval |
| Peer trust and exchange | Federated Commons | Signed capability advertisements and replay challenges |
| Promotion and decay | Crystal Compute | Proof-depth tiers, demotion, expiry, negative evidence |
| Lifecycle integrity | Crystal Chain | Cross-node chain-head attestations |
| Telemetry and learning | Chronicle / OTel / Trace Miner | One correlation ID across route, transfer, replay, and verification |
| Local specialization | Capability Crystallization / Compute Forge | Crystal-to-adapter datasets, sparse route candidates, guarded distillation |

## Landscape Decisions

### Adopt Now on CPU

| Research direction | BEAST use |
| --- | --- |
| Prompt and contextual summary caching | Cache verified intermediate summaries and evidence packets, keyed by full fingerprints |
| Generative caching | Store bounded reusable action templates that must be instantiated and reverified locally |
| Context-aware semantic caching | Require task, policy, repository, tool, skill, and conversation-state compatibility |
| Cost-aware routing | Extend Provider Economist with proof locality, LAN RTT, transfer size, and replay cost |
| Speculative decoding analogy | Let a tiny local model propose routes/actions while deterministic verifiers and approval gates retain authority |
| Active-packet analogy | Use inert proof-carrying envelopes containing rules and hashes, never executable packet code |
| P2P cache-routing analogy | Gossip safe metadata and prefer peers with compatible evidence; stale metadata causes only misses |
| Edge partitioning analogy | Split the agent workflow across verifier roles, not neural-network layers |

### Implement as Adapter Contracts

| System family | Contract to preserve |
| --- | --- |
| vLLM / PagedAttention / vAttention | Engine capabilities, prefix-cache hit evidence, token and latency receipts |
| SGLang | Structured program execution, constrained output, prefix/radix reuse evidence |
| LMCache / CacheBlend | External KV backend, compatibility proof, movement and reuse receipts |
| Ray Serve | Replica health, prefix-aware routing observation, autoscaling state |
| NVIDIA Dynamo / DistServe / Splitwise | Prefill/decode role, transfer metadata, cache locality, phase latency |
| llm-d / KServe | Kubernetes route observation and cache-event evidence |
| llama.cpp | Direct CPU endpoint, prompt-slot/cache profile, GGUF and KV-quantization identity |

These adapters report capabilities and evidence. Compute Governor remains the
policy authority.

### Defer Until Appropriate Hardware Exists

- tensor parallelism;
- GPU PagedAttention and FlashAttention benchmarks;
- LMCache GPU offload and NIXL transfer;
- prefill/decode disaggregation across accelerators;
- SmartNIC or P4 data-plane enforcement;
- CXL-attached shared KV pools;
- peer GPU memory harvesting;
- internet-scale model-layer partitioning.

The proposal retains schemas for these features so future hardware does not
require an architectural rewrite.

## Proposed Architecture

```text
                         PUBLIC / FEDERATED PLANE
   signed advertisement -> manifest -> hashes -> verifier description
              |                                       |
              v                                       v
       Federated Commons --------------------> Commons quarantine
              |                                       |
              +------------- replay challenge --------+

                          LOCAL TRUST PLANE
   Task Envelope
        |
        v
   Compute Governor
        |
        +-- exact adopted crystal? -------> local verifier ------+
        |                                                       |
        +-- semantic evidence match? -----> bounded replay ------+
        |                                                       |
        +-- trusted LAN proof? -----------> staged retrieval ----+--> receipt
        |                                                       |
        +-- local CPU inference? ---------> Ollama/llama.cpp ----+
        |                                                       |
        +-- unresolved and approved? -----> provider ------------+
                                                                |
                                                                v
                Chronicle + Crystal Chain + Commons reproduction
                                   |
                                   v
                  Capability lattice + Adapter Forge candidates
```

## Core Concepts

### 1. Proof-Local Routing

Compute Governor should evaluate route candidates by expected safe completion,
not raw latency alone.

Suggested route score:

```text
proof_locality_score =
    verifier_strength
  * fingerprint_compatibility
  * reproduction_confidence
  * freshness
  * peer_reputation
  * expected_displacement
  / (replay_cost + transfer_cost + privacy_risk + false_reuse_risk)
```

The score ranks candidates; it never bypasses hard policy gates.

Default ladder:

```text
adopted exact crystal
-> compatible local stored inference
-> local deterministic transform
-> trusted LAN replay challenge
-> local Ollama/llama.cpp
-> approved provider fabric
```

### 2. Receipt Packets

A receipt packet is a small, inert, privacy-safe header announcing potentially
useful work.

```json
{
  "beast_object_type": "proof_receipt_packet",
  "version": "1.0",
  "space_id": "provider_gateway_repair",
  "manifest_hash": "sha256:...",
  "artifact_root_hash": "sha256:...",
  "task_class": "hard_gateway_repair",
  "privacy_class": "public_metadata_only",
  "proof_depth": "locally_reproduced",
  "verifier_bundle_hash": "sha256:...",
  "fingerprint_class": "repository_scoped",
  "replay_required": true,
  "expires_at": "...",
  "promotion_state": "quarantined_hypothesis",
  "credit_eligible": false,
  "chain_head": "sha256:..."
}
```

It contains no prompt, source, secret, rollback snapshot, private fixture, raw
KV state, or executable verifier payload.

### 3. Negative Bandwidth

**Negative bandwidth** is payload transfer avoided by sending proof metadata
first.

Transfer stages:

```text
stage 0: signed advertisement
stage 1: receipt packet
stage 2: manifest + artifact hashes
stage 3: verifier description
stage 4: selected public-safe artifacts
stage 5: full eligible bundle
```

Any failed signature, privacy, expiry, compatibility, or allowlist check aborts
before the next stage.

Metrics:

- bytes advertised;
- bytes requested;
- bytes avoided through early rejection;
- full bundles avoided;
- verifier bytes versus artifact bytes;
- payload-to-proof ratio.

### 4. Bandwidth Escrow

Before downloading a bundle, Compute Governor estimates:

```text
transfer_value = expected_verified_compute_saved
                 / (bytes_to_transfer + local_replay_cost + privacy_risk)
```

Possible decisions:

- `request_receipt_only`;
- `request_manifest`;
- `request_verifier_description`;
- `request_selected_artifacts`;
- `approve_full_bundle`;
- `reject_transfer`.

This is an advisory estimate until local reproduction supplies measured data.

### 5. Compute NAT

BEAST already sits in front of provider calls. Proof-local routing formalizes a
Compute NAT behavior:

```text
requested route: external inference
translated route: adopted crystal / local replay / LAN verifier / local model
fallback route: original approved provider
```

Every translation must preserve the original task envelope, risk class,
approval policy, and fallback. Translation produces a receipt linking the
requested route to the executed route.

### 6. LAN Crystal Swarm

Docker or physical LAN nodes advertise narrow verified roles:

```text
Node A: Commons registry and signed advertisements
Node B: deterministic verifier and test sandbox
Node C: CPU Ollama scout
Node D: secret/privacy scanner
Node E: Forge summary and fingerprint worker
```

Nodes exchange task envelopes, hashes, replay challenges, and receipts using
the existing BEAST object language. They do not pass unconstrained natural
language between agents as authority.

### 7. Proof-Carrying Capsules

A Commons Space bundle becomes a **proof-carrying capsule**. Its contents are
data plus an inert verification contract:

- signed manifest;
- artifact hash tree;
- privacy classification;
- verifier description;
- reproduction challenge;
- fingerprint requirements;
- risk and approval boundary;
- expiry and demotion policy;
- reduction receipt descriptors;
- Crystal Chain head reference.

The receiver executes only locally installed verifier primitives. A remote
capsule cannot provide arbitrary executable commands.

### 8. Semantic Compute Pages

PagedAttention manages physical KV pages. BEAST can introduce a higher-level
analogy: **semantic compute pages**.

A semantic page is a content-addressed, separately verifiable unit such as:

- task classifier result;
- selected context plan;
- provider route card;
- verifier plan;
- rollback recipe;
- policy decision;
- failure lesson;
- contextual summary;
- deterministic transformation.

Pages can be loaded, invalidated, replicated, expired, or recomputed
independently. They are not trusted merely because their hash matches; the hash
establishes identity, while local verification establishes authority.

### 9. Compute Composting

Failed work should emit bounded reusable evidence:

```text
failed route
-> failure classification
-> negative capability
-> mutation test
-> provider fitness penalty
-> possible counterfactual crystal
-> expiry or revalidation trigger
```

Credits are not issued for failure itself. Value appears only when a later real
task avoids the same verified failure mode.

### 10. Cross-Signed Crystal Chain Heads

The current Crystal Chain is locally tamper-evident but can be replaced by a
filesystem administrator. Federation can strengthen it without introducing a
cryptocurrency:

1. Each node periodically signs its chain head.
2. Trusted peers store the signed head as an attestation.
3. Later heads commit to the previous locally attested head.
4. Peers detect rollback, fork, or silent history replacement.
5. Consensus is not required; disagreement triggers quarantine and audit.

```json
{
  "beast_object_type": "crystal_chain_head_attestation",
  "node_id": "commons-node-a",
  "height": 142,
  "head_hash": "sha256:...",
  "previous_attested_head": "sha256:...",
  "signed_at": "...",
  "signature": {"algorithm": "...", "value": "..."}
}
```

This supplies distributed witnessing rather than pretending to provide global
Byzantine consensus.

### 11. Capability Lattice and Crystal-to-Adapter Distillation

The deepest version of Proof-Local Compute is not only external displacement.
BEAST first crystallizes verified behavior outside the model, then lets enough
verified crystals reshape the local compute substrate.

There are two different compute changes:

| Layer | Mechanism | Authority |
| --- | --- | --- |
| External compute displacement | model call -> verified output -> crystal -> future zero-call reuse | deterministic only when fingerprints and verifiers match |
| Internal compute transformation | many crystals -> capability lattice -> adapter, compressed task model, or sparse route | advisory until local policy and verifiers pass |

A crystal is deterministic: given compatible state, execute a known verified
capability. An adapter is probabilistic: given a related task, produce a better
candidate for BEAST to verify. They are complementary, not interchangeable.

The safe alchemy chain is:

```text
dense parameter space
-> governed inference traces
-> verified crystals
-> capability lattice
-> adapter distillation / model compression / sparse route proposal
-> cheaper local compute under the same BEAST gates
```

The capability lattice is the training scaffold. It is built from:

- task family and boundary fingerprints;
- verified prompts or task envelopes that are safe to retain locally;
- repaired Action IR;
- accepted patches or deterministic transforms;
- visible and hidden verifier outcomes;
- negative capability records and failure cases;
- provider-fitness and route-fitness receipts;
- rollback, approval, and policy metadata.

Initial specializers should be narrow CPU-friendly adapters or small local
models for BEAST-native behaviors:

- valid Action IR generation;
- schema-valid JSON emission;
- provider alias normalization;
- path-guard and write-policy obedience;
- secret redaction and privacy classification;
- route diagnostics and fallback selection;
- smaller patch generation;
- task-family recognition.

BEAST should not directly rearrange base model matrices first. It should
derive a capability lattice from verified outputs, then train small adapters,
prune routes, or specialize smaller local models around the behaviors that
actually survive tests, fingerprints, and policy gates.

Distilled artifacts never bypass the normal ladder:

```text
exact crystal
-> semantic page
-> adapter-assisted local candidate
-> local Ollama/llama.cpp
-> trusted LAN replay
-> approved provider
```

Adapter output is just a proposal. It must still produce Action IR, artifacts,
or patches that pass local policy, verifier, privacy, rollback, and approval
gates before it can become a new crystal.

The strategic culmination is:

```text
BEAST stops treating model intelligence as a one-way service.
Verified inference residue becomes local training material.
Local training material becomes narrower governed skill.
Narrow governed skill produces more crystals with less rescue.
Those crystals strengthen the Commons and the next distillation loop.
```

## Required Data Contracts

### Proof Route Request

```json
{
  "beast_object_type": "proof_route_request",
  "task_envelope_hash": "sha256:...",
  "task_class": "...",
  "required_verifiers": ["..."],
  "privacy_class": "local_only",
  "risk_class": "high",
  "max_lan_rtt_ms": 50,
  "max_transfer_bytes": 1000000,
  "allowed_routes": ["local_replay", "trusted_lan", "local_ollama"],
  "fallback": "require_approval"
}
```

### Node Capability Advertisement

```json
{
  "beast_object_type": "node_capability_advertisement",
  "node_id": "...",
  "capability_hashes": ["sha256:..."],
  "verifier_classes": ["pytest_subset", "schema_validation"],
  "engine_profiles": ["ollama_cpu"],
  "privacy_classes_accepted": ["public_metadata_only"],
  "load_bucket": "low",
  "rtt_bucket_ms": 10,
  "expires_at": "...",
  "signature": {}
}
```

Advertisements use buckets rather than exact private infrastructure details.

### Proof Route Receipt

```json
{
  "beast_object_type": "proof_route_receipt",
  "requested_route": "cloud_provider",
  "executed_route": "trusted_lan_replay",
  "peer_id": "...",
  "manifest_hash": "sha256:...",
  "local_verification": "passed",
  "bytes_transferred": 18422,
  "bytes_avoided": 821578,
  "cloud_calls_avoided": 1,
  "measured_tokens_avoided": 3900,
  "fallback_preserved": true,
  "chain_block_hash": "sha256:..."
}
```

### Distillation Candidate Receipt

A distillation candidate receipt records that a set of crystals may be useful
training material. It does not claim the resulting adapter is trusted.

```json
{
  "beast_object_type": "distillation_candidate_receipt",
  "version": "1.0",
  "candidate_id": "action_ir_adapter_v0",
  "source_lattice_hash": "sha256:...",
  "task_families": ["provider_gateway_repair", "schema_repair"],
  "source_crystal_count": 128,
  "negative_case_count": 41,
  "privacy_class": "local_training_only",
  "training_mode": "cpu_adapter",
  "base_model_identity": {
    "engine": "ollama",
    "model": "qwen2.5:0.5b",
    "quantization": "..."
  },
  "allowed_outputs": ["action_ir", "route_card", "patch_candidate"],
  "required_verifiers": ["schema_validation", "policy_gate", "pytest_subset"],
  "authority": "proposal_only",
  "promotion_state": "adapter_candidate",
  "chain_block_hash": "sha256:..."
}
```

Public Commons may publish the receipt, lattice hash, proof density, and
evaluation summary. It must not publish private prompts, source, rollback
snapshots, private fixtures, or raw training rows unless those rows have a
separate public-safe export decision.

## Compute Governor Changes

Add proof-local candidate stages without embedding network or engine logic into
the Governor:

1. Build a route request from the existing Compute Plan.
2. Query local adopted capabilities.
3. Query fresh signed peer advertisements.
4. Ask a `ProofRoutePlanner` to return ranked candidates.
5. Apply hard Governor privacy, budget, risk, and approval gates.
6. Execute through the existing replay, local-engine, federation, or provider
   adapter.
7. Record one correlated route and displacement receipt.

The planner is advisory. Governor owns the final decision.

## Compute Forge Changes

Add CPU work types:

- `build_semantic_page`;
- `qualify_context_summary`;
- `build_receipt_packet`;
- `run_replay_challenge`;
- `measure_transfer_value`;
- `mutate_proof_identity`;
- `attest_chain_head`;
- `compact_failure_evidence`;
- `build_capability_lattice`;
- `prepare_distillation_dataset`;
- `train_cpu_adapter_candidate`;
- `evaluate_adapter_candidate`;
- `mutate_distilled_behavior`.

Forge accounting must distinguish:

- compute invested;
- candidate estimated value;
- reproduced displacement;
- realized displacement.

Only realized, independently evidenced reuse is credit eligible.

Adapter or compressed-model candidates are not credit eligible by themselves.
Credit can be issued only for later verified displacement: fewer rescues, fewer
cloud escalations, fewer local tokens, or successful zero-call crystal reuse
on real task boundaries.

## Commons and Federation Changes

### Public Commons

Publish:

- receipt packets;
- manifests and artifact hashes;
- verifier descriptions;
- reproduction summaries;
- compatibility and hardware profiles;
- chain-head attestations;
- expiry, risk, and approval metadata.

Do not publish:

- raw prompts or source;
- raw KV tensors;
- exact private network topology;
- private LAN addresses;
- remote executable verifier commands;
- local cache payloads;
- private chain event payloads.

### Federated Commons

Add:

- signed advertisement gossip;
- request-by-hash artifact retrieval;
- replay challenge/response;
- chain-head witnessing;
- duplicate and loop suppression;
- TTL and revocation propagation;
- per-peer transfer quotas.

## Security and Abuse Model

| Threat | Required control |
| --- | --- |
| Malicious receipt packet | Signature, allowlist, schema validation, quarantine |
| Hash-valid malicious artifact | Local privacy scan and verifier allowlist; hashes prove identity, not safety |
| Replay farming | Unique workload evidence, node/task deduplication, no self-credit |
| Sybil peers | Local allowlisting and independent reproduction; no universal reputation authority |
| Stale advertisement | Short TTL; stale data produces a miss |
| Chain rollback | Cross-signed head attestations and fork detection |
| LAN metadata leakage | Bucketed load/RTT, hashed capabilities, no private paths |
| Oversized bundle attack | Manifest-first size declaration, quotas, streaming limits |
| Verifier command injection | Only locally installed verifier IDs may execute |
| Semantic false hit | Full identity match plus local replay and behavior verifier |
| Credit inflation | Measured displacement, duplicate suppression, decay, reversal on false reuse |
| Adapter poisoning | Lattice provenance, negative cases, held-out verifiers, proposal-only authority |
| Over-specialized adapter | Boundary tests, mutation suites, demotion when rescue or false-hit rates rise |

## Mutation and Ablation Plan

### Identity Mutations

- model revision;
- tokenizer revision;
- system policy;
- tool schema;
- skill tree;
- repository fingerprint;
- tenant privacy class;
- verifier version;
- artifact hash;
- chain head;
- expiry;
- source lattice hash;
- adapter identity;
- base model identity;
- distilled training window.

Expected result: reuse is rejected or quarantined.

### Distillation Mutations

- remove negative cases;
- train on only successful crystals;
- stale policy snapshot;
- swapped tool schema;
- mismatched repository fingerprint;
- corrupted Action IR target;
- hidden-test regression;
- adapter trained against the wrong base model;
- sparse route forced outside its task boundary.

Expected result: adapter remains proposal-only, hidden/verifier scores drop,
promotion is blocked, and no credit is issued for claimed improvement.

### Network Mutations

- stale advertisement;
- forged signature;
- duplicate announcement;
- replayed challenge response;
- high RTT;
- bandwidth collapse;
- partial bundle transfer;
- peer disconnect;
- conflicting chain heads;
- cyclic peer routing.

Expected result: bounded fallback, no unsafe adoption, no duplicate credit.

### Ablations

Compare:

1. provider-only;
2. local Ollama only;
3. exact local replay;
4. semantic page reuse;
5. LAN manifest-first routing;
6. LAN full-bundle eager transfer;
7. proof-local routing without reputation;
8. proof-local routing without bandwidth escrow;
9. proof-local routing without chain witnessing;
10. adapter-assisted local candidate;
11. adapter-assisted candidate without negative cases;
12. adapter-assisted candidate without hidden verifier gates.

Measure verifier outcome, cloud calls, tokens, CPU time, latency, bytes, false
reuse, failed transfers, and credit correctness.

## CPU-First Delivery Plan

### Phase 1: Receipt Packets and Staged Retrieval

Status: **implemented and exercised across three CPU Docker nodes on 2026-06-22**.

Implement:

- `ProofReceiptPacket` schema;
- public projection and privacy scan;
- manifest-first remote import;
- byte accounting and early abort receipts.

Exit criteria:

- three Docker nodes exchange receipt packets;
- forbidden data never appears in public projections;
- invalid packets abort before bundle transfer;
- byte savings are measured, not estimated alone.

### Phase 2: LAN Proof Router

Status: **implemented as signed advisory routing with Compute Governor enforcement gates on 2026-06-22**.

Implement:

- signed capability advertisements;
- TTL cache;
- RTT/load buckets;
- `ProofRoutePlanner` advisory ranking;
- Compute Governor gates and fallback.

Exit criteria:

- peer loss falls back safely;
- stale metadata causes only missed reuse;
- no cloud call occurs when a locally reproduced route succeeds;
- no peer route crosses its privacy class.

Implementation:

- `app/kernel/proof_local_compute.py`
- `app/kernel/federated_commons.py`
- `app.kernel.governance.compute_governor.py`
- `scripts/commons_lab_smoke.py`
- `tests/test_proof_local_compute.py`
- `tests/test_proof_local_api.py`

API surface:

```text
GET  /edgek/proof-local/spaces/{space_id}/receipt
GET  /edgek/proof-local/spaces/{space_id}/manifest
GET  /edgek/proof-local/spaces/{space_id}/verifiers
POST /edgek/proof-local/receipt-packets/ingest
POST /edgek/proof-local/import-staged
POST /edgek/proof-local/advertisements/prepare
POST /edgek/proof-local/advertisements/ingest
POST /edgek/proof-local/route
```

Current lab evidence:

- Node A published one Ed25519-signed, `public_metadata_only` receipt packet.
- Nodes B and C independently allowlisted Node A's pinned public-key hash and
  accepted the packet as a receipt-only hypothesis.
- A packet mutated after signing was rejected before bundle transfer.
- Node B stopped after manifest verification: `3,673` bytes were received and
  `3,025` signed compressed bundle bytes were avoided from a `6,698`-byte
  bundle.
- Node B then fetched that same bundle through the staged path; its bytes were
  accepted only after matching the SHA-256 digest carried by the signed receipt
  packet and passing the existing local bundle verification gates.
- Nodes B and C accepted Node A's signed, expiring capability advertisement.
- Before local reproduction the Governor returned `quarantine_and_replay`.
- After binding the request to a real local reproduction receipt, the Governor
  returned `trusted_lan_replay` with `provider_execution_requested=false`.
- Caller-supplied `local_replay_verified=true` is ignored; only a locally stored
  matching reproduction ID can unlock the route.
- Evidence receipt:
  `benchmarks/results/proof_local_phase12_lab_latest.json`.

Current claim boundary:

- CPU Docker LAN only, not public internet federation.
- The route planner is advisory; Compute Governor owns authority.
- Receipt and manifest transfer savings are measured, but no financial or
  compute credit is issued for avoided bytes.
- Cross-OS reproduction and production workload frequency remain unproven.

### Phase 3: Semantic Compute Pages

Status: **implemented as CPU-safe local page layer on 2026-06-22**.

Implement:

- content-addressed intermediate summaries, route cards, verifier plans, and
  negative capabilities;
- full `InferenceArtifactIdentity` binding;
- independent expiry and invalidation;
- local behavior verification.

Exit criteria:

- repeated workloads reuse individual pages;
- every identity mutation causes a miss;
- page reuse improves CPU time or tokens without reducing verifier success.

Implementation:

- `app/kernel/semantic_compute_pages.py`
- `scripts/semantic_compute_pages_phase3.py`
- `tests/test_semantic_compute_pages.py`
- API:
  - `GET /edgek/proof-local/semantic-pages`
  - `POST /edgek/proof-local/semantic-pages/build`

Current local evidence:

- Four independently addressed page kinds are built from local Phase 7 evidence:
  intermediate summary, route card, verifier plan, and negative capability.
- Pages bind to BEAST's canonical `InferenceArtifactIdentity`, including model,
  tokenizer, prompt/system hashes, engine, model revision, policy, tool schema,
  skill tree, repository fingerprint, and privacy class.
- Page lookup is exact and fail-closed: model revision, tool schema, skill tree,
  repository fingerprint, verifier fingerprint, or privacy-class mutations all
  miss.
- Pages have independent TTL expiry, explicit invalidation, content-hash
  validation, privacy scanning, and local reuse receipts.
- Latest receipt:
  `benchmarks/results/semantic_compute_pages/phase3_semantic_compute_pages_latest.json`.

### Phase 4: Cross-Signed Chain Heads

Status: **implemented as local cross-signed witness and append-only lattice ledger on 2026-06-22**.

Implement:

- node head signing;
- peer witnessing;
- fork and rollback detection;
- quarantine on disagreement;
- non-financial audit dashboard.

Exit criteria:

- replacing or truncating one node's chain is detected by another node;
- consensus failure cannot promote capability;
- private event payloads remain local.

Implementation:

- `app/kernel/crystal_chain_witness.py`
- `app/kernel/crystal_lattice_ledger.py`
- `scripts/proof_local_phase4_chain_witness.py`
- `tests/test_proof_local_phase4.py`
- API:
  - `GET /edgek/crystal-chain/witness`
  - `POST /edgek/crystal-chain/witness/attest`
  - `GET /edgek/crystal-lattice`
  - `POST /edgek/crystal-lattice/checkpoint`
  - `POST /edgek/crystal-lattice/defrag`

Run:

```bash
python3 scripts/proof_local_phase4_chain_witness.py
```

Current local evidence:

- Vector/matrix lattice heads are appended to
  `crystal_lattice_checkpoint` records rather than relying only on mutable
  `*_latest` artifacts.
- Lattice defrag creates a compact latest-head snapshot without rewriting or
  deleting checkpoint history.
- Crystal Chain heads are signed with OpenSSL Ed25519 attestations.
- Two peer witness stores verified the same Node A attestation.
- A clean audited chain allowed promotion.
- A truncated chain produced `rollback_detected` and `promotion_allowed=false`.
- A tampered/forked chain produced `quarantine` and
  `promotion_allowed=false`.
- Attestations export only hashes, heights, public signature material, and
  metadata; private event payloads remain local.
- Latest receipt:
  `benchmarks/results/proof_local_phase4_chain_witness_latest.json`.

### Phase 5: Context-Aware Generative Crystals

Status: **implemented as bounded template instantiation with false-hit demotion on 2026-06-22**.

Implement:

- bounded action templates;
- local parameter instantiation;
- deterministic verifier plan;
- rollback and approval requirements;
- false-hit tracking and automatic demotion.

Exit criteria:

- templates generalize across structurally similar real tasks;
- instantiated actions always pass local policy and verifier gates;
- failed generalization causes demotion and credit reversal.

Implementation:

- `app/kernel/generative_crystals.py`
- `scripts/proof_local_phase5_generative_crystals.py`
- `tests/test_proof_local_phase5.py`
- API:
  - `GET /edgek/proof-local/generative-crystals`
  - `POST /edgek/proof-local/generative-crystals/gauntlet`

Run:

```bash
python3 scripts/proof_local_phase5_generative_crystals.py
```

Current local evidence:

- Registered a bounded `route_diagnostics` template with explicit
  `task_id`, `task_family`, verifier parameter, rollback action, approval
  requirement, risk class, and context boundary hash.
- Instantiated the same template across two structurally similar local route
  tasks.
- Rendered deterministic Action IR and verifier plans locally:
  `provider_fitness_check` plus `schema_validation`.
- Both positive instantiations passed local verifier receipts.
- A tool-schema boundary mutation missed and degraded to recomputation.
- Two failed verifier receipts triggered automatic demotion.
- Demotion set `credit_reversal_required=true`.
- Latest receipt:
  `benchmarks/results/proof_local_phase5_generative_crystals_latest.json`.

### Phase 6: Optional Hardware Adapters

Status: **implemented as CPU-first capability-gated adapter cards on 2026-06-22**.

When hardware exists, validate adapters independently:

- llama.cpp prompt slots on CPU;
- vLLM prefix cache;
- SGLang structured execution;
- LMCache offload and transfer;
- Ray prefix-aware routing;
- Dynamo prefill/decode routing;
- llm-d cache-event routing.

No adapter becomes authoritative until Forge produces compatibility, mutation,
failure, and reproduction evidence.

Implementation:

- `app/kernel/hardware_adapter_validation.py`
- `scripts/proof_local_phase6_hardware_adapters.py`
- `tests/test_phase6_and_adapter_comparison.py`
- API:
  - `GET /edgek/proof-local/hardware-adapters`

Run:

```bash
python3 scripts/proof_local_phase6_hardware_adapters.py
```

Current local evidence:

- Produced capability cards for Ollama, llama.cpp, vLLM, SGLang, TGI,
  LMCache, Ray Serve, NVIDIA Dynamo, and llm-d.
- The host policy remains `cpu_first_capability_gated`.
- Ollama is the CPU-ready local profile.
- GPU/external engines remain `metadata_only_not_authoritative` when not
  configured or not CPU-supported.
- No optional adapter is promoted without Forge compatibility, mutation,
  failure, and reproduction evidence.
- Latest receipt:
  `benchmarks/results/proof_local_phase6_hardware_adapters_latest.json`.

### Held-Out Adapter Comparison Gauntlet

Status: **implemented as proposal-only held-out evaluator on 2026-06-22**.

Purpose:

- Compare baseline `qwen2.5:0.5b`, BEAST Modelfile wrapper,
  trained BEAST LoRA artifact, and crystal-only route on held-out task
  envelopes that are not the 304 Phase 7 training rows.
- Measure raw JSON parse rate, BEAST object type, `proposal_only` authority,
  task-family match, required verifier presence, schema validity, hidden
  verifier pass, unsafe action attempts, latency, generated tokens, and memory.
- Preserve the promotion rule: no adapter executes; adapters may only propose;
  BEAST verifiers decide.

Implementation:

- `app/kernel/adapter_comparison.py`
- `scripts/heldout_adapter_comparison_gauntlet.py`
- API:
  - `POST /edgek/proof-local/adapter-comparison`

Run offline/sandbox-safe:

```bash
python3 scripts/heldout_adapter_comparison_gauntlet.py
```

Run live from the host Ollama environment:

```bash
OLLAMA_HOST=http://127.0.0.1:11434 \
python3 scripts/heldout_adapter_comparison_gauntlet.py \
  --live-ollama \
  --ollama-host http://127.0.0.1:11434
```

Current local evidence:

- Offline run measured crystal-only and verified LoRA artifact lanes.
- Baseline Qwen and BEAST Modelfile lanes are marked
  `not_run_live_ollama_disabled` until the host executes the live Ollama run.
- Crystal-only route scored `1.0` on parse, schema, authority, task-family
  match, required verifier, hidden verifier, and unsafe-action checks.
- Trained micro LoRA artifact is verified but marked
  `artifact_verified_not_executable` until an approved runtime harness exists.
- Latest receipt:
  `benchmarks/results/heldout_adapter_comparison_latest.json`.

### Phase 7: Crystal-to-Adapter Distillation

Status: **implemented as CPU-safe proposal scaffold on 2026-06-22**.

Implement only after enough repeated crystals exist to justify specialization.
This is CPU-first and may begin with tiny local adapters, prompt-slot profiles,
or small task models rather than GPU training.

Implement:

- capability lattice builder;
- local-only distillation dataset export with privacy scan;
- adapter candidate receipt;
- CPU adapter or small-model training harness;
- hidden verifier evaluation;
- mutation and ablation suite;
- Governor route candidate for `adapter_assisted_local`;
- demotion when rescue burden, false reuse, or unsafe output rises.

Exit criteria:

- adapter candidate improves schema validity, hidden pass rate, or rescue burden
  against a fixed base local model;
- exact crystal path remains preferred when boundary matches;
- adapter output never bypasses policy, verifier, rollback, or approval gates;
- all training rows are locally governed and public exports remain scrubbed;
- failed specialization produces negative capability evidence rather than
  silent promotion.

Implementation:

- `app/kernel/crystal_distillation.py`
- `scripts/crystal_to_adapter_distillation.py`
- `scripts/create_ollama_crystal_adapter.py`
- `scripts/train_crystal_lora_lattice.py`
- `scripts/export_true_lora_package.py`
- `scripts/train_true_lora_adapter.py`
- `scripts/train_micro_lora_crystal_adapter.py`
- `scripts/verify_micro_lora_adapter.py`
- `scripts/verify_ollama_crystal_runtime.py`
- `scripts/crystal_lora_route_head.py`
- `scripts/proof_local_phase_backlog.py`
- `tests/test_crystal_distillation.py`
- API:
  - `GET /edgek/proof-local/distillation`
  - `POST /edgek/proof-local/distillation/build`
  - `GET /edgek/proof-local/distillation/dataset`
  - `POST /edgek/proof-local/distillation/ollama-model`
  - `POST /edgek/proof-local/distillation/lora-lattice`
  - `GET /edgek/proof-local/distillation/lora-lattice`
  - `POST /edgek/proof-local/distillation/true-lora-package`
- TUI:
  - Intelligence page now shows Phase 7 lattice signals, family count,
    adapter candidate decision, governed distillation gain, and parameter
    activation avoidance proxy.

Current local evidence:

- Harvested `304` local crystal/failure signals from `benchmarks/results`.
- Built `16` capability-lattice family nodes.
- Exported `304` privacy-scrubbed local-only training rows.
- Included `93` negative cases from failure buckets.
- Produced adapter candidate `adapter_candidate_4b1ac598b8306cb512ef`.
- Candidate decision: `candidate_ready_for_local_training`.
- Mutation suite: passed.
- Authority remains `proposal_only`; no weights are promoted and no credit is
  issued until later local verifier-gated displacement is measured.
- Created real Ollama derived model `beast-crystal-qwen25-05b:latest` from
  `qwen2.5:0.5b` using a BEAST agent-awareness Modelfile. This is not
  weight-level LoRA, but it is a real local Ollama model with BEAST system
  contract embedded.
- Runtime priority is **local Ollama primary**. The Hugging Face/PEFT path is
  an optional export/training lane, not the BEAST runtime center.
- Ollama runtime package verification passed offline and live from the host
  Ollama socket:
  `benchmarks/results/crystal_to_adapter_distillation/ollama_crystal_runtime_verification_latest.json`.
- Live local model output parsed as
  `adapter_assisted_local_proposal`, preserved `proposal_only` authority,
  included a non-empty `task_envelope`, required `provider_fitness_check`,
  asserted `agent_awareness.must_use_beast_systems=true`, and included the
  canonical minimum BEAST systems:
  `task_envelope`, `prec_lifecycle`, `compute_governor`, `chronicle`, and
  `local_verifiers`.
- Live contract violations: `[]`.
- Codex's managed sandbox may still be unable to initiate the Ollama socket
  directly; host-executed receipts are the source of truth for live runtime
  evidence.
- Vectorized crystallized compute into a `512`-dimensional local lattice.
- Trained actual low-rank matrices: `lora_A` `[512, 16]`, `lora_B` `[16, 16]`,
  `delta_W` `[512, 16]`, and `bias` `[16]`.
- Matrix training accuracy on the local lattice: `0.947368` across `16` task
  families.
- Matrix insertion boundary is explicit: BEAST adapter-assisted route/proposal
  head, not direct Ollama GGUF mutation.
- Added a local matrix-assisted route/proposal head that uses the trained
  crystal lattice matrices before Ollama. It predicted `schema_validation` for
  a local schema task with confidence `0.673181` and emitted an
  awareness-valid BEAST proposal.
- Latest route-head receipt:
  `benchmarks/results/crystal_to_adapter_distillation/crystal_lora_route_head_latest.json`.
- Exported an optional PEFT/LoRA-ready package for true adapter training against
  `Qwen/Qwen2.5-0.5B-Instruct`:
  `benchmarks/results/crystal_to_adapter_distillation/true_lora_package_latest`.
- True LoRA training is currently blocked by missing local dependencies:
  `torch`, `transformers`, `peft`, and `datasets` in the default interpreter.
- `.venv-lora` contains the LoRA stack, but the target Hugging Face base model
  `Qwen/Qwen2.5-0.5B-Instruct` is not cached locally and network resolution is
  unavailable in the current sandbox.
- Training command once the base model is cached:
  `python3 scripts/train_true_lora_adapter.py --package benchmarks/results/crystal_to_adapter_distillation/true_lora_package_latest`.
- Trained an offline micro true-LoRA adapter from crystal SFT rows using a tiny
  GPT-style causal LM initialized from local config only:
  `benchmarks/results/crystal_to_adapter_distillation/micro_lora_adapter_latest`.
- Micro LoRA evidence:
  - rows used: `128`;
  - rank: `8`;
  - epochs: `2`;
  - loss decreased from `5.147113` to `4.80921`;
  - real adapter weights:
    `micro_lora_adapter_latest/adapter/adapter_model.safetensors`.
- Micro LoRA verification passed:
  `benchmarks/results/crystal_to_adapter_distillation/micro_lora_verification_latest.json`.
- Latest report:
  `benchmarks/results/crystal_to_adapter_distillation/phase7_crystal_to_adapter_latest.json`.
- Latest matrix receipt:
  `benchmarks/results/crystal_to_adapter_distillation/crystal_lora_lattice_training_latest.json`.
- Latest phase backlog:
  `benchmarks/results/crystal_to_adapter_distillation/proof_local_phase_backlog_latest.json`.

### Phase 8: Loaded LoRA Runtime Comparison

Status: **implemented as proposal-only runtime harness on 2026-06-22**.

Purpose:

- Complete the compute ladder with one decisive held-out comparison:
  baseline `qwen2.5:0.5b`, BEAST Modelfile wrapper, real loaded micro LoRA
  adapter, crystal-only deterministic route, and optional cloud-provider
  fallback.
- Prove whether trained adapter weights change behavior at runtime, not merely
  that an adapter artifact exists.
- Preserve the promotion rule: no adapter executes; adapters may only propose;
  BEAST verifiers decide.

Implementation:

- `scripts/run_loaded_micro_lora_adapter.py`
- `app/kernel/adapter_comparison.py`
- `scripts/heldout_adapter_comparison_gauntlet.py`
- API:
  - `POST /edgek/proof-local/adapter-comparison`

Run the full local comparison:

```bash
BEAST_LORA_PYTHON=.venv-lora/bin/python \
OLLAMA_HOST=http://127.0.0.1:11434 \
python3 scripts/heldout_adapter_comparison_gauntlet.py \
  --live-ollama \
  --ollama-host http://127.0.0.1:11434
```

Run the LoRA runtime lane alone:

```bash
BEAST_LORA_PYTHON=.venv-lora/bin/python \
python3 scripts/run_loaded_micro_lora_adapter.py \
  --task-id heldout_schema_002 \
  --task-family schema_validation \
  --required-verifier schema_validation
```

Optional cloud-provider lane:

- The cloud lane is intentionally disabled unless `--live-cloud` is set.
- `--live-cloud` runs the local command in `BEAST_CLOUD_PROVIDER_COMMAND`.
- This keeps the benchmark honest: no external fallback is claimed unless a
  provider route is explicitly configured.

Current local evidence boundary:

- The micro LoRA adapter is now loadable as a PEFT runtime proposal lane.
- New micro-LoRA training receipts include the tiny base-model seed and config
  so future runs can reconstruct the base initialization deterministically.
- Older receipts without the seed are still runnable, but the runtime status
  records `measured_base_reconstruction_seed_missing`; that is behavioral
  evidence, not a fully reproducible weight-change claim.
- The adapter lane remains `proposal_only_measurement`; promotion to execution
  is impossible by design.
- Latest receipts are written to:
  `benchmarks/results/adapter_comparison/heldout_adapter_comparison_latest.json`
  and the mode-specific live/offline receipts in the same directory.

## Success Metrics

### Capability

- verified task completion rate;
- reproduction rate across nodes;
- false-reuse rate;
- demotion and expiry rate;
- boundary-match precision;
- adapter-assisted hidden pass rate;
- rescue burden per task family.

### Compute

- measured cloud calls avoided;
- measured prompt/output tokens avoided;
- CPU seconds invested versus avoided;
- local inference calls avoided;
- verifier cost per successful reuse;
- governed distillation gain;
- parameter activation avoidance.

### Network

- bytes avoided through staged retrieval;
- receipt-to-payload ratio;
- full bundles avoided;
- LAN route success by RTT bucket;
- failed/cancelled transfer bytes;
- duplicate advertisement suppression.

### Governance

- unsafe adoptions;
- privacy-boundary violations;
- chain rollback/fork detections;
- approval bypasses;
- credit reversals;
- malicious peer isolation time.

## Product Possibilities

### Proof-Local Commons Map

A registry view showing where proof exists without exposing private topology:

```text
gateway repair       local adopted       proof depth 5
secret redaction     2 trusted LAN peers proof depth 4
schema repair        Commons hypothesis  proof depth 2
unknown refactor     no proof            provider approval required
```

### Negative Bandwidth Dashboard

Show:

- manifest-only rejections;
- bytes not transferred;
- bundles avoided;
- tasks translated by Compute NAT;
- LAN versus cloud routes;
- proof locality and reproduction density.

### Capability CDN

Not a CDN for model output. A discovery and staged-delivery network for
privacy-safe, proof-carrying capability packages. Payload remains optional and
local verification remains mandatory.

### Crystal Chain Explorer

A human-readable projection of promotion, reproduction, demotion, expiry, and
peer-head attestations. It must clearly label local evidence, peer witnessing,
and the absence of global consensus.

### Capability Lattice Studio

A local-only workbench for seeing which task families have enough proof to
train or refresh a specialized adapter. It should show crystal density,
negative cases, hidden verifier performance, privacy eligibility, and whether
the candidate remains proposal-only or can be promoted into a governed local
route.

## Novelty Boundary

BEAST should not claim novelty for caching, routing, edge execution, packet
programming, speculative inference, or hash chains individually.

The credible synthesis is:

> BEAST converts verified semantic work into locally governed, portable,
> lifecycle-managed capability, then routes future work toward the strongest
> compatible proof while measuring compute and communication displaced. Once
> enough proof accumulates, BEAST can distill that evidence into narrower
> local compute that still answers to the same verifiers.

That moves the conversation from efficient inference toward **accountable
non-inference**.

## Recommended First Build

Build Phase 1 and Phase 2 together as a bounded Docker/LAN gauntlet:

1. Node A publishes a signed receipt packet for an existing Space.
2. Node B rejects one mutated packet before requesting the manifest.
3. Node B requests a valid manifest and verifier description without the full
   bundle.
4. Compute Governor compares local replay, LAN reproduction, Ollama, and cloud
   fallback.
5. Node B fetches only required artifacts and reproduces locally.
6. Both nodes record correlated receipts and cross-sign their Crystal Chain
   heads.
7. Repeat with latency, packet loss, stale metadata, duplicates, privacy
   mutations, and peer failure.

This proves the defining behavior on current CPU hardware:

```text
send proof before payload
route toward reproducible evidence
fall back safely
reward only measured displacement
```
