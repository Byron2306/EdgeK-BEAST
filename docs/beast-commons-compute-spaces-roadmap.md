# BEAST Commons Compute Spaces Roadmap

## Core Thesis

BEAST Commons is a local-first, governed alternative to model-hosting platforms:
not a place to spend more compute, but a place to publish, verify, reuse, and
exchange artifacts that reduce compute.

The inversion is the point:

- Conventional AI platforms host models and apps that consume CPU, RAM, GPU,
  disk, bandwidth, and tokens.
- BEAST Commons hosts skills, tools, crystals, KV/cache profiles, route policies,
  traces, and proof receipts that preserve capability while lowering CPU, RAM,
  GPU, disk, bandwidth, token use, latency, and cloud dependency.

In short:

> Hugging Face Spaces asks: "What can you run if you rent enough compute?"
>
> BEAST Commons asks: "What useful work can you stop recomputing?"

This is the mad idea: a compute-space marketplace where the valuable object is
not raw inference output, but verified compute displacement.

## Why This Is Different

Most AI systems try to pack more capability into larger parameter spaces. BEAST
can pursue a second path: move capability into an optimized execution plane.

Instead of:

```text
prompt -> giant model -> next token -> next token -> next token
```

BEAST can optimize:

```text
task -> policy -> context -> tool -> swarm -> crystal -> verifier -> receipt -> promotion
```

The intelligence is not only inside a model. It is distributed across:

- Meta Tool Commons
- Compute Forge
- Crystal Compute
- KV/cache transport
- Provider Economist
- OpenClaw/NemoClaw/ZeroClaw
- Ollama scout models
- capability registry
- approval gates
- verification loops
- rollback and Chronicle receipts

That means a small local model can act as an intent router and policy follower
while BEAST supplies structure, memory, tools, and verification.

## The Virtualization Analogy

Cloud computing virtualizes physical resources:

| Physical resource | Cloud abstraction |
| --- | --- |
| CPU cycles | vCPU quotas, time slices, serverless execution |
| RAM pages | guest memory, container limits, memory pressure signals |
| GPU kernels | full GPU assignment, MIG slices, vGPU, inference endpoints |
| Disk blocks | volumes, snapshots, object storage |
| Network interfaces | virtual networks, load balancers, service meshes |

BEAST Commons can virtualize a higher layer:

| BEAST resource | Commons abstraction |
| --- | --- |
| Repeated reasoning | crystals and fused inference recipes |
| Repeated context selection | context fingerprints and source-plan priors |
| Repeated tool choice | ranked meta-tool priors |
| Repeated orchestration | swarm role recipes |
| Repeated provider calls | route cards and provider fitness |
| Repeated prefill/context work | KV/cache blocks and transport profiles |
| Repeated failures | negative capability files |
| Repeated approvals | policy templates and risk receipts |
| Repeated verification | known test and checker bundles |

The resulting resource is not just compute. It is reusable verified work.

## BEAST Compute Spaces

A BEAST Compute Space is a governed package of capability-reducing artifacts.
It is similar in spirit to a hosted model demo, but its purpose is to displace
future compute rather than consume more of it.

Example package:

```text
Space: provider_gateway_repair
Task class: hard_gateway_repair
Hardware profile: CPU-only laptop, optional Ollama scout
Artifacts:
- skill_recipe: provider id normalization
- meta_tool_recipe: recursive secret redaction
- crystal: empty async stream chunk preservation
- route_policy: local scout before cloud escalation
- verifier_bundle: py_compile + pytest tests -q
- rollback_policy: snapshot before write
- receipts: benchmark, fingerprints, cost estimate, approval trail
Reduction claim:
- fewer cloud calls
- fewer tokens
- no GPU required
- verified patch outcome preserved
Authority:
- advisory until local approval
```

## Cloud Product Split

The cloud-ready BEAST Commons shape has two layers.

### 1. Public Commons Registry

This is the cloud-visible catalog. It publishes hypotheses, not authority.

It may host:

- Compute Space manifests
- artifact hashes
- signed receipt descriptors
- verifier bundle descriptions
- provider-fitness cards
- reduction claims
- reproduction status
- risk and approval metadata
- public documentation

It must not host:

- raw private prompts
- private source code
- secrets or private keys
- absolute local paths
- private rollback snapshots
- raw company data
- private test fixtures
- artifact payload bytes unless explicitly public-safe

The public registry projection is available locally as:

```text
GET /
GET /ui
GET /edgek/public-commons-registry
GET /edgek/public-commons-registry/{space_id}
```

The default port-8000 web UI now presents BEAST Commons directly: live Space
cards, local adoption status, federation counts, non-financial credit state,
scale-gauntlet milestones, and the critical latency framing of "broken vs
working" rather than "fast vs faster." The old root service metadata is
available at `GET /edgek/root-info`.

The primary action is not “Run Space.” It is:

```text
Import as quarantined hypothesis
```

### 2. Local BEAST Adoption Engine

This stays on the operator’s machine. It is the only layer allowed to convert a
public hypothesis into trusted local capability.

The local flow is:

```text
download/import manifest
→ quarantine artifact
→ verify hashes/signature
→ dry-run replay
→ run local verifier
→ compare local fingerprints
→ ask for approval
→ adopt into local Commons
→ promote to Crystal Compute only after local proof
```

Adoption states:

```text
quarantined_hypothesis → reproduced → approved_candidate → adopted → promoted
```

That split is the product boundary: the cloud can help discover useful compute
displacement, but only local BEAST can decide whether it becomes capability.

## Artifact Types

### 1. Crystals

Crystals are compact reusable inference artifacts. They encode a verified route,
repair pattern, decision boundary, or workflow fragment.

Examples:

- provider gateway repair crystal
- recursive redaction crystal
- async stream preservation crystal
- rollback-safe patch crystal
- failure memory crystal

### 2. Fused Crystals

Fused crystals combine tools, skills, swarm recipes, and outcome evidence into a
larger reusable capability.

Example:

```text
tool recipe + skill recipe + verifier bundle + provider route + rollback policy
= fused repair crystal
```

### 3. Meta Tool Recipes

Meta tool recipes describe how to use a tool safely and effectively without
shipping raw prompts or private workspace data.

Examples:

- workspace symbol search
- pytest verifier
- route-card renderer
- MCP document retrieval
- LiteLLM config validator

### 4. Swarm Role Recipes

Swarm role recipes crystallize repeated local orchestration patterns.

Examples:

- cartographer selects relevant context
- sentinel checks secrets and risk
- verifier selects tests
- scribe records Chronicle and promotion evidence
- critic reviews high-risk patch plans

### 5. KV/Cache Transport Profiles

KV/cache artifacts capture reusable prefill or cache transport behavior.

Examples:

- Ollama CPU KV profile
- vLLM storage handoff profile
- repeated context prefix fingerprint
- cache hit route policy

These should never store raw prompt/source payloads. They store fingerprints,
block metadata, transport class, engine, size buckets, and verified reuse
outcomes.

### 6. Provider Fitness Cards

Provider fitness cards capture which provider/model family works well for a
task class under a role.

Examples:

- `nvidia_nim` for patch reasoning
- `ollama/qwen2.5:0.5b` as policy follower
- local deterministic executor for low-risk file inspection

### 7. Verifier Bundles

Verifier bundles define the tests, static checks, and acceptance gates that make
a compute reduction trustworthy.

Examples:

- `py_compile + pytest`
- secret redaction checks
- route-card schema validation
- hidden regression tests

## Proof of Useful Compute Reduction

The Commons needs receipts before it needs currency.

Each artifact should be scored by how much verified work it saves, not by hype.

Candidate metric:

```text
Compute Displacement Value =
    preserved capability
  * verification confidence
  * reuse frequency
  * safety score
  / compute cost
  / maintenance burden
  / risk
```

Minimum receipt fields:

- artifact ID
- artifact type
- source and lineage
- task class
- hardware profile
- baseline route
- optimized route
- provider calls avoided
- tokens avoided
- latency avoided
- GPU avoided
- RAM/disk/network deltas where known
- verifier result
- rollback availability
- approval requirement
- privacy policy
- fingerprint hash
- promotion state

## Training Data for Optimization

BEAST already emits the data needed for this:

- PREC lifecycle traces
- provider call receipts
- Compute Governor receipts
- route decisions
- tiny-model orchestration runs
- Commons evidence plane rows
- KV/cache events
- Crystal Compute promotions
- negative capability evidence
- approval outcomes
- rollback outcomes
- benchmark artifacts
- test pass/fail records

This data should train a BEAST-native policy learner.

The learner should not generate prose as its primary job. It should choose
execution moves:

```json
{
  "route": "local_ollama_then_openclaw",
  "tools": ["workspace_search", "pytest", "meta_tool_commons_rank"],
  "subagents": ["cartographer", "sentinel", "verifier"],
  "reuse": ["crystal:provider_gateway_repair"],
  "approval_required": true,
  "expected_compute_reduction": 0.73,
  "risk": "medium"
}
```

This is the "BEAST brainstem": a local policy model trained over verified
pipeline outcomes instead of billions of next-token predictions.

## Governance Rules

BEAST Commons must not become a blind auto-install marketplace.

Rules:

- Shared artifacts are advisory by default.
- Local approval is required before adoption.
- Raw prompts, secrets, source code, and private paths are never exported.
- Artifacts must include schema hashes and fingerprints.
- Promotion requires verifier evidence.
- Demotion and expiry are first-class.
- High-risk tools require explicit local policy gates.
- Currency or exchange value, if it ever exists, must be receipt-backed.

## Roadmap

### Phase 0: Name the Plane

Status: **concept defined**.

- [x] Define BEAST Commons as "Spaces for crystallized compute".
- [x] Define compute reduction as the primary value proposition.
- [x] Separate raw compute hosting from reusable verified work.
- [x] Tie Commons to existing Crystal Compute, Compute Forge, Meta Tool Commons,
  KV/cache transport, and Swarm.

Exit criteria:

- The project has a written thesis and vocabulary.

### Phase 1: Local Compute Space Manifest

Status: **in progress**.

Build a local manifest format for a BEAST Compute Space.

Deliverables:

- [x] `beast_space.json` schema
- [x] artifact list with hashes
- [x] hardware profile
- [x] verifier bundle references
- [x] reduction claims
- [x] safety/approval metadata
- [x] local-only import/export command

Exit criteria:

- One existing Tiny Llama Opus case study can be packaged as a local Compute
  Space without leaking workspace data.

### Phase 2: Compute Reduction Receipts

Status: **in progress**.

Create a receipt format that compares baseline route to optimized BEAST route.

Deliverables:

- [x] baseline provider route capture
- [x] optimized route capture
- [x] token and call displacement fields
- [x] latency and verifier fields
- [x] GPU/RAM/disk fields where measurable
- [x] fingerprint and provenance fields
- [x] Markdown and JSON renderers

Exit criteria:

- A Space can prove "what it avoided" with a signed local receipt.

### Phase 3: Commons Space Registry

Status: **local prototype implemented**.

Expose local Spaces through BEAST API and TUI.

Deliverables:

- [x] `/edgek/commons-spaces`
- [x] `/edgek/commons-spaces/{space_id}`
- [x] TUI page for Spaces
- [x] source-diverse artifact table
- [x] reduction scoreboard
- [x] approval-gated import/adopt flow

Exit criteria:

- Operators can inspect local Spaces and adopt artifacts through approval gates.

### Phase 4: Policy Learner

Status: **shadow prototype implemented**.

Train a small local policy/ranker over BEAST receipts.

Deliverables:

- [x] trace-to-example extractor
- [x] route/tool/subagent label builder
- [x] tiny local ranker baseline
- [x] static heuristic baseline
- [x] offline evaluation harness
- [x] shadow-mode integration

Exit criteria:

- BEAST can recommend a lower-compute route in shadow mode and report whether
  the recommendation would have preserved verification success.

Current evidence note:

- The evaluator reports `in_sample_insufficient_for_holdout` when fewer than two
  policy examples are available. Shadow recommendations never suppress or alter
  the active route.

### Phase 5: Space Packaging and Replay

Status: **local replay prototype implemented**.

Make Spaces portable and replayable.

Deliverables:

- [x] content-addressed bundle
- [x] privacy scrubber
- [x] verifier replay command
- [x] deterministic replay mode where possible
- [x] import dry-run
- [x] trust score based on local reproduction

Exit criteria:

- A Space created on one machine can be imported elsewhere and locally
  revalidated before adoption.

Current hardening note:

- Portable exports and imports block private key filenames and private key
  material by default, including test PEM fixtures such as `node_ed25519.pem`,
  `id_rsa`, `*.key`, and `*.pem`.

### Phase 6: Federated Commons

Status: **governed local federation prototype implemented**.

Allow sharing without central trust.

Deliverables:

- [x] signed manifests
- [x] optional post-quantum seal support
- [x] contributor reputation based on reproduced receipts
- [x] abuse controls
- [x] artifact expiry and revocation
- [x] local allowlists

Exit criteria:

- BEAST can ingest remote Commons artifacts as hypotheses while preserving local
  authority.

Current authority boundary:

- Federation envelopes use portable Ed25519 signatures and add ML-DSA/ML-KEM
  seals when `liboqs` is available.
- Ingested envelopes remain quarantined hypotheses. Adoption still requires a
  validated local bundle, local reproduction, and explicit operator approval.

### Phase 6.5: Public Commons Registry Projection

Status: **local cloud-safe prototype implemented**.

Deliverables:

- [x] public-safe registry projection
- [x] per-Space public card
- [x] cloud boundary metadata
- [x] “import as quarantined hypothesis” action
- [x] local adoption-engine steps embedded in cards
- [x] artifact hashes without artifact payload bytes
- [x] reproduction status and risk/approval metadata
- [x] API endpoints for static/cloud registry serving

Exit criteria:

- A BEAST instance can publish a cloud-safe Commons Registry view without
  exporting secrets, private keys, raw prompts, source, local paths, rollback
  snapshots, or private fixtures.

### Phase 6.6: Docker Commons Federation Lab

Status: **local multi-node lab scaffold implemented**.

Purpose:

- Run multiple BEAST Commons nodes with separate registries, signing keys,
  adoption ledgers, reproduction receipts, and federation state.
- Seed nodes with privacy-scrubbed benchmark-derived Space hypotheses.
- Exercise signed federation envelopes and local allowlist/ingest/reproduce
  flows without claiming a real public cloud deployment.

Files:

- `Dockerfile.commons-node`
- `docker-compose.commons-lab.yml`
- `scripts/seed_commons_node.py`
- `scripts/commons_lab_smoke.py`

Run:

```bash
docker compose -f docker-compose.commons-lab.yml up --build
python3 scripts/commons_lab_smoke.py
```

Node ports:

- `http://127.0.0.1:8101`
- `http://127.0.0.1:8102`
- `http://127.0.0.1:8103`

What this proves:

- Multiple independent Commons nodes can host public-safe Space registries.
- Signed envelopes can move between nodes as quarantined hypotheses.
- Local allowlisting remains required.
- Reproduction remains local.

What this does not yet prove:

- Real internet federation.
- Cross-OS/hardware reproducibility.
- Production workload reuse frequency.
- 10,000-Space operational scale.

Current lab evidence:

- Docker daemon run completed on 2026-06-22.
- Three Commons nodes started on ports `8101`, `8102`, and `8103`.
- Each node seeded at least `11` valid Spaces: one Tiny Llama gateway repair
  Space plus benchmark-derived metadata Spaces that passed
  privacy/manifest/receipt checks.
- Each node crossed the first scale ladder: `10` Spaces.
- Node A exported a content-addressed Space bundle over HTTP.
- Node B downloaded Node A's bundle through `/edgek/commons-spaces/import-remote`.
- Node B verified bundle content hashes, bundle seal, privacy scan, manifest,
  and artifact hashes locally before import.
- Node A prepared a signed federation envelope for the same Space.
- Node B allowlisted Node A's Ed25519 public key hash.
- Node B ingested the envelope as `quarantined_hypothesis`.
- Node B reproduced the imported Space locally with deterministic replay and
  updated Node A reputation to `1/1` successful reproductions, reputation
  score `0.75`.

Lab crypto caveat:

- The Docker image does not include a production PQC provider, so bundle/receipt
  seals use the stdlib HMAC development fallback.
- The lab uses a shared `BEAST_CRYSTAL_SEAL_KEY` only to make portable bundle
  verification possible in Docker. Federation identity still uses per-node
  Ed25519 keys. Production federation should use portable public signatures
  rather than a shared HMAC fallback.

Adversarial lab checks:

- Tampered bundle artifacts are rejected by content hash validation.
- Tampered signed envelopes fail signature verification.
- Non-allowlisted federation envelopes cannot become adopted Spaces.
- Forbidden export/import patterns for private keys, raw prompts, local paths,
  rollback snapshots, and source/private fixtures fail privacy scanning.
- Missing verifier artifacts fail reproduction and do not create successful
  reputation evidence.
- Stale fingerprints remain quarantined instead of becoming adopted capability.
- Duplicate Space imports deduplicate by manifest/content hash.
- Repeated reproduction submissions from the same node do not inflate
  reputation.

Test command:

```bash
python3 -m pytest tests/test_commons_adversarial.py tests/test_commons_space_registry.py tests/test_commons_replay_federation.py tests/test_commons_spaces_api.py -q
```

### Phase 6.7: BEAST-Native Ollama-to-Ollama Inference Inversion

Status: **local cross-node gauntlet implemented**.

Purpose:

- Let two local Ollama-backed BEAST nodes exchange crystallized compute without
  calling a cloud API.
- Ensure model-to-model communication uses BEAST infrastructure as the protocol,
  not freeform chat as authority.
- Treat local BEAST proof as authoritative and tiny-model text as advisory.

Protocol rule:

- Every model handoff must carry a `beast_inference_inversion_handoff` object
  containing task envelope, insight packet, quality cascade, pathway/route card,
  forge scorecard, workflow card, public registry card, skill-tree state, and
  verifier receipt availability.
- The local adoption engine decides trust from bundle verification, privacy
  scan, manifest validation, replay receipts, and approval state.
- Ollama may summarize or advise, but it cannot mint trust or currency by
  itself.

File:

- `scripts/cross_node_ollama_reuse_gauntlet.py`

Run:

```bash
python3 scripts/cross_node_ollama_reuse_gauntlet.py
```

Latest receipt:

- `benchmarks/results/cross_node_ollama_reuse_gauntlet_latest.json`

Current local evidence:

- Node A and Node B both built BEAST-native handoff packets with complete
  language contracts:
  `task_envelope`, `insight_packet`, `quality_cascade`,
  `pathway_route_card`, `forge_card`, `workflow_card`,
  `public_registry_card`, `skill_tree_state`, and `verifier_receipts`.
- Node B imported or deduplicated Node A's Space through the Commons bundle
  route.
- Node B reproduced the Space locally with deterministic replay.
- Node B adopted the reproduced Space locally.
- Ollama returned an advisory reuse decision with `cloud_api_needed: false`.
- Observed cloud provider API calls: `0`.
- Crystal credit was correctly refused because deterministic replay/adoption is
  not yet enough for live repeated-workload displacement credit.

What this proves:

- Cross-node inference inversion can happen locally using BEAST artifacts as the
  language layer.
- Crystallized compute can move from one node to another as a verified Space
  without cloud inference.
- The currency layer remains stricter than model prose.

What this does not yet prove:

- Repeated real workload displacement.
- Live verifier success across heterogeneous hardware/OS.
- Credit eligibility from production traffic.
- Long-running malicious-node isolation.

### Phase 6.8: Live Displacement and Forge-Fed Commons

Status: **local live displacement harness and Forge candidate feed implemented**.

Purpose:

- Move from deterministic replay to live verifier reproduction.
- Record repeated task-boundary matches as local workload evidence.
- Let Compute Forge grind CPU work into potential Commons registrations:
  crystals, fused crystals, meta-tools, skills, swarm recipes, and failure
  oracles.
- Make mutations and ablations first-class promotion gates.

Files:

- `scripts/live_commons_displacement_harness.py`
- `scripts/forge_commons_grind_gauntlet.py`

Run:

```bash
python3 scripts/forge_commons_grind_gauntlet.py
python3 scripts/live_commons_displacement_harness.py --space-id tiny_llama_opus_gateway_repair --target . --repeats 3
```

Latest receipts:

- `benchmarks/results/forge_commons_grind_gauntlet_latest.json`
- `benchmarks/results/live_commons_displacement_harness_latest.json`

Current local evidence:

- Forge mined `4` defensive crystals and fused them into
  `commons_space_registration_operator`.
- Forge generated `42` Commons registration candidates from crystals, fused
  crystals, meta-tools, skills, swarm recipes, and mutation/ablation cases.
- The Commons registration candidate endpoint now includes Forge candidates
  from `data/forge_nodes/*.json`.
- Mutation/ablation cases include expected oracles for artifact hash tamper,
  signed-envelope tamper, missing verifier artifacts, stale fingerprints,
  component ablations, and forbidden privacy patterns.
- The live displacement harness ran the Tiny Llama gateway Space verifier with
  `python -m pytest tests -q`.
- Live verifier passed, with trust score `1.0`.
- The harness recorded `3` repeated task-boundary matches, `0` cloud API
  calls observed, and `3` cloud calls avoided.
- Non-financial compute reduction credit issued:
  `ccredit_3b3f28b4b171669c8da4`, `241` simulated units.

Claim boundary:

- Forge output is not adopted authority. It is a registration feed.
- Mutation and ablation cases are negative evidence gates, not destructive
  actions.
- Credit still requires valid manifest/receipt, local live reproduction,
  verified adoption, duplicate suppression, and explicit approval.

### Phase 6.9: Scale Economics Ladder

Status: **proof-density and scenario-pricing ladder implemented**.

Purpose:

- Answer when repeated proof changes economics.
- Measure how many Spaces have valid manifests, live reproduction, adoption,
  repeated workload matches, and issued non-financial credit.
- Keep financial pricing as an explicit scenario assumption, not a product
  claim.

File:

- `scripts/commons_scale_economics_ladder.py`

Run:

```bash
python3 scripts/commons_scale_economics_ladder.py \
  --target-spaces 10 \
  --matches-per-space 3 \
  --cloud-call-cost 0.02 \
  --token-cost-per-1m 5 \
  --setup-cost 1 \
  --marketplace-take-rate 0.1
```

Latest receipt:

- `benchmarks/results/commons_scale_economics_ladder_latest.json`

Current local evidence:

- Valid Spaces: `10`.
- Live reproduced Spaces: `1`.
- Credit-eligible Spaces: `1`.
- Credited Spaces: `1`.
- Repeated workload matches: `3`.
- Cloud calls avoided: `3`.
- Gap to first market signal `10 Spaces × 3 matches = 30 displacements`:
  corpus size reached, but proof still needs `9` more Spaces with repeated
  matches and `27` more matches.
- Seeded benchmark-derived metadata Spaces: `9`.
- One candidate was correctly blocked by privacy scanning for an
  `absolute_workspace_path` finding.
- Forge tier inventory currently includes `42` Forge-fed candidates:
  `1` fused inference crystal, `4` forge crystals, `2` meta-tools,
  `2` skills, `2` swarm recipes, `30` mutation/ablation cases, and
  `1` Forge proposal.

Example scenario result:

- Assumptions: `$0.02` per avoided cloud call, `$5/M` tokens,
  `3,900` tokens per match, `$1` setup cost, `10%` marketplace take.
- `10 × 3` gives `30` displacements and `117,000` estimated tokens avoided.
- Gross avoided cost: `$1.185`.
- Break-even for `$1` setup cost: `26` displacements.
- Marketplace revenue at `10%`: `$0.1185`.

Tiered credit pricing model:

- Tier 1 Tiny Replay: `$0.01` base per displacement.
- Tier 2 Skill / Meta-Tool: `$0.015` base per displacement.
- Tier 3 Fused Crystal: `$0.02` base per displacement.
- Tier 4 Promotion Candidate: `$0.03` base per displacement.
- Tiered value uses proof depth, fusion complexity, match frequency, and
  anti-gaming strength multipliers.
- Total premium is capped at `3.0x`; credits cannot fall below `0.5x` base.
- Observed `tiny_llama_opus_gateway_repair` currently prices as Tier 3:
  `$0.06` per displacement after cap, `$0.18` for `3` matches.

Tiered 10-Space portfolio example:

- `3` Tier 2 rare skill Spaces, `4` Tier 3 early fused Spaces,
  `2` Tier 4 proven Spaces, and `1` Tier 3 launch Space.
- Total listed displacements: `38`.
- Tiered credit value: `$2.8215`.
- Flat `$0.02` value: `$0.76`.
- Marketplace take at `10%`: `$0.28215`.
- Note: the source scenario text listed the launch Space but omitted it from
  the written subtotal; the implementation includes all listed rows.

Fused-tier scenario:

- Tier: `fused_inference_crystal`.
- Tier multiplier: `3.0`.
- Effective cloud call cost: `$0.06`.
- Effective tokens per match: `11,700`.
- `10 × 3` gives `351,000` estimated tokens avoided.
- Gross avoided cost: `$3.555`.
- Break-even for `$1` setup cost: `9` displacements.
- Marketplace revenue at `10%`: `$0.3555`.

Marketplace readiness gates:

- Public marketplace: not ready until at least `10` Spaces have repeated
  local proof.
- Large-scale anti-gaming: minimum local controls are present; needs scale
  pressure.
- Cross-machine repeated adoption: not proven.
- Long-term credit value: not ready until credits retain predictive value
  across expiry, demotion, and workload drift.
- Production workload frequency: not ready until real production traffic
  confirms match rates.
- Financial pricing: scenario-only until willingness-to-pay, legal/accounting,
  abuse controls, and baseline costs are validated.

### Phase 7: Compute Reduction Economy

Status: **non-financial local simulation implemented**.

Only after receipts, replay, and governance work.

Deliverables:

- [x] proof-of-useful-compute-reduction model
- [x] anti-gaming rules
- [x] duplicate detection
- [x] verified adoption history
- [x] reward simulation
- [x] non-financial credit system first

Exit criteria:

- Value is attached to reproduced useful reduction, not claimed compute.

Current claim boundary:

- Credits require a valid manifest and receipt, an explicitly approved adoption,
  and a locally sealed live verifier reproduction.
- Counterfactual token claims receive zero observed-token credit. Exact semantic
  duplicates receive no additional credit.
- Units are capped, non-transferable, non-redeemable, and have no assigned
  financial value. The simulation does not predict future reduction.

## First Prototype

Use the Tiny Llama Opus case study as the first Space.

Status: **completed locally on 2026-06-22**.

Prototype steps:

1. [x] Package the case study artifacts:
   - prompt
   - normalized orchestration plan
   - patch plan
   - verifier results
   - rollback receipt
   - promotion candidate
   - Commons evidence rows
2. [x] Produce a `beast_space.json` manifest.
3. [x] Produce a compute reduction receipt:
   - tiny local model route
   - tools used
   - provider calls avoided or escalated
   - verifier pass/fail
   - risk gates
4. [x] Show it in the TUI.
5. [x] Let an operator approve adoption into local Commons.
6. [x] Replay the verifier bundle.
7. [x] Promote successful artifacts into Crystal Compute.

Prototype evidence:

- Space: `tiny_llama_opus_gateway_repair`
- Artifacts: 9, including a privacy-safe prompt fingerprint; the raw prompt,
  source code, verifier output, and rollback snapshot are not exported.
- Adoption: `adopt_32f069762f6995fe42a6`
- Live reproductions: `repro_8cce309de6e64edc900b`,
  `repro_51ecdb76c868cbd76781`, and `repro_344048452d24d9a232c0`
- Advisory Crystal: `space_crystal_94bf08b0c7b924c98f61`, with enforcement
  explicitly disabled
- Non-financial credit: `ccredit_b9e57662a02461f982af`, 205 simulated units
- Completion hash:
  `sha256:000bfe78ff40937fcd993af4739f1ca6e226ac5d06c84dbf9d048a549f56eecb`

## Strategic Positioning

BEAST Commons is not another model zoo.

It is:

- a capability efficiency exchange
- a local-first agentic systems registry
- a marketplace of verified reductions
- a crystallized compute library
- a governance layer for reusable AI work

The slogan:

> Local-first. Governed. Self-improving. Compute-reducing.

Or, more directly:

> BEAST Commons: Spaces for work you never want to pay to recompute.
