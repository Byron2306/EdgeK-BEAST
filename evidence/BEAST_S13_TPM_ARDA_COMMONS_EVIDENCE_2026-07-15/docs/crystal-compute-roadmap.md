# Crystal Compute Roadmap

Crystal Compute extends BEAST's existing Meta Tool Commons, skill learning, and
capability promotion system. Capability annealing is therefore not a new base
layer: the current commons and learning machinery already proposes, tests,
adopts, promotes, demotes, and retires capabilities. This roadmap adds durable
compute evidence around that lifecycle so BEAST can learn from failure,
alternatives, budget pressure, and historical execution structure.

## Priorities

| Rank | Program | Expected impact | Dependency |
| ---: | --- | --- | --- |
| 1 | Negative Capability Files | Very high: prevents repeated known failures | Shared outcome evidence |
| 2 | Proof-of-Friction Routing | Very high: makes retries, repair, latency, and cost affect selection | Outcome aggregation |
| 3 | Counterfactual Crystals | High: records why rejected routes were weaker | Calibrated outcome evidence |
| 4 | Compute Escrow | High: reserves and settles compute against verified delivery | Trustworthy friction and cost signals |
| 5 | Temporal Skill Forks | High: permits bounded experiments against stable crystals | Promotion and rollback metrics |
| 6 | Semantic RAID | Medium-high: protects high-value crystal evidence | Content-addressed artifact storage |
| 7 | Crystal Annealing | Medium: extends existing skill annealing to compute artifacts | Fork and outcome history |
| 8 | Artifact Fossil Layers | Medium initially, foundational later: replayable lineage | Storage retention policy |

## Phase 1: Failure Memory

Status: **operational**.

Deliverables:

- [x] Define a privacy-safe `OutcomeEvidence` contract for success, failure,
  recovery, latency, cost, token use, confidence movement, retries, repairs,
  selected capabilities, and rejected capabilities.
- [x] Add scoped Negative Capability records with evidence IDs, confidence,
  expiry, revalidation, and a three-failure activation threshold.
- [x] Persist evidence atomically and deduplicate repeated reports.
- [x] Feed active provider-scoped negatives into Provider Economist exclusions.
- [x] Record crystallization shadow outcomes through the shared contract.
- [x] Emit outcome evidence from provider streaming, deterministic execution,
  verified reuse, and approval-resume boundaries.
- [x] Expose negative records and their evidence in API, MCP, and TUI views.
- [x] Add expiry/revalidation maintenance and auditable operator overrides.

Exit criteria:

- One failure can never create a hard routing exclusion.
- Three matching failures activate only the exact capability, task class, and
  provider/model/tool scope observed.
- Two later clean successes move a weakened record into revalidation.
- Raw prompts, source, secrets, and unbounded exception text are never stored.
- Every exclusion identifies its evidence records and expiry.
- Routing behavior is unchanged when no active negative evidence is supplied.

## Phase 2: Friction-Aware Routing

Status: **complete in shadow mode**.

- [x] Aggregate retry count, repair depth, latency, approval pauses,
  recovery dependence, and verified cost by capability and route.
- [x] Calculate confidence-weighted friction penalties beside Provider Economist
  scores while preserving the current selected route in shadow mode.
- [x] Feed friction profiles through Compute Governor adaptive-routing calls.
- [x] Keep hard exclusions evidence-thresholded; use weak evidence only as a score
  penalty.
- [x] Add latency variance and approval-duration measurements.
- [x] Calibrate reported confidence against verified completion.
- [x] Run paired routing benchmarks and measure how often friction would change
  the selected route before enabling enforcement.

Result: paired routing benchmark preserves the current route in shadow mode while
measuring friction displacement pressure (`33.3%` in the current synthetic
paired suite). Enforcement remains disabled pending broader live traffic.

Target: reduce repeated repair depth by 30% without lowering clean completion.

## Phase 3: Counterfactual Crystals

Status: **complete in advisory mode**.

- [x] Capture bounded rejected-route snapshots at each consequential decision.
- [x] Predict failure class, cost, latency, and confidence for each alternative.
- [x] Resolve counterfactuals when later traffic exercises a rejected route.
- [x] Promote only calibrated counterfactual patterns; retain speculative records as
  advisory evidence.

Result: local counterfactual benchmark creates bounded rejected-route crystals
and resolves them when later traffic exercises the rejected provider. Promotion
remains disabled unless later resolved traffic calibrates the pattern.

Target: every provider/capability selection can explain both the winner and the
strongest rejected alternative.

## Phase 4: Compute Escrow

Status: **complete in escrow shadow mode**.

- [x] Reserve cloud calls, tokens, latency, and USD at task admission.
- [x] Release budget by PREC phase and settle only against verified outcomes.
- [x] Refund unused reservations and charge recovery overhead to the responsible
  route's friction history.
- [x] Permit operator-approved emergency local-compute claims.

Result: local escrow benchmark reserves, settles, and refunds compute budgets
with `100%` verified-delivery settlement in the current synthetic suite.
Production budget enforcement remains policy-gated.

Target: reduce compute cost per verified result by 20% while preventing budget
oversubscription during parallel work.

## Phase 5: Temporal Forks and Crystal Annealing

Status: **complete in bounded local mode**.

- [x] Run stable, candidate, and experimental crystal channels.
- [x] Allocate bounded traffic with automatic rollback.
- [x] Use the existing Meta Tool Commons adoption and skill-learning mechanisms for
  proposal and consolidation.
- [x] Extend annealing to merge duplicate compute crystals, split crystals with
  multimodal failure patterns, and retire stale lineages.

Result: local temporal-fork benchmark caps candidate traffic at `25%`, caps
experimental traffic at `5%`, rolls back failed experimental forks without
degrading stable traffic, promotes only clean candidate evidence, and exercises
merge/split/retire annealing operations.

Target: experimental capabilities cannot degrade the stable channel, and every
promotion has clean-completion, friction, cost, and rollback evidence.

## Phase 6: Durable Intelligence

Status: **complete in local durable mode**.

- [x] Store immutable semantic shards with integrity manifests and redundant
  indexes (Semantic RAID).
- [x] Preserve differential lifecycle checkpoints and decision lineage (Artifact
  Fossil Layers).
- [x] Run corruption reconstruction drills and value-aware garbage collection.

Result: local durable-intelligence benchmark detects primary shard corruption,
repairs it from a redundant mirror, replays promotion lineage deterministically,
and retains high-value semantic shards through value-aware garbage collection.

Target: zero unrecoverable promoted-crystal corruption and deterministic replay
of every promotion decision.

## Program Metrics

- repeated known-failure rate;
- clean completion and rescue rates;
- average retry and repair depth;
- confidence calibration error;
- compute cost per verified result;
- negative-record activation, expiry, and false-exclusion rates;
- stable-versus-candidate promotion precision;
- replay coverage and artifact integrity.

## Rollout Policy

Phase 1 records are local and fail open. Negative evidence becomes enforceable
only after the activation threshold, remains narrowly scoped, and expires.
Subsequent phases begin in shadow mode, emit comparison receipts, and require a
rollback path before they influence production routing.
