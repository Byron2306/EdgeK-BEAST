# Discovery-Agnostic Reuse Experiment

**Purpose:** test whether BEAST can discover and safely reuse a verified
capability from semantic evidence and local verification rather than from a
known prompt, provider, cache key, skill name, or peer advertisement.

This is the next proof target. It is deliberately stricter than cache replay
and deliberately narrower than a claim of general intelligence.

## Claim under test

For a sealed family of tasks, a receiving BEAST node can identify an applicable
capability using only privacy-safe semantic/task evidence, reproduce it under
its own policy and verifier, and use it without a provider call. It must refuse
lookalikes, stale state, poisoned evidence, and out-of-bound variants.

## What is held constant

- verifier and exact postcondition class;
- policy ceiling and privacy class;
- initial repository/physical-state digest;
- resource envelope and timeout;
- local authority: discovery never grants execution authority.

## What must vary independently

| Surface | Positive variation | Negative variation |
| --- | --- | --- |
| Wording | Different user language and task-envelope phrasing. | Similar wording for a different operation. |
| Repository | Different names, layout, decoys, and non-semantic churn. | Changed dependency, test, symbol, or postcondition. |
| Runtime/provider | Discovery generated under one provider/runtime and consumed locally under another. | Model/tokenizer/policy mismatch outside the capability contract. |
| Discovery source | Local history, semantic index, static seed, DNS-SD/peer catalog, and imported Commons hypothesis. | Forged, stale, duplicate, or poisoned advertisement. |
| Host | Origin and receiver are separate physical hosts. | Attestation, verifier, policy, or clock mismatch. |

## Experimental arms

Every sealed task is randomized and blinded across these arms:

1. Bare local model.
2. Local model with ordinary retrieved context, but no crystal admission.
3. BEAST control plane with discovery disabled.
4. BEAST discovery and local reproduction enabled.
5. Deterministic crystal-only replay, when an eligible crystal exists.
6. Provider fallback after a required refusal.

The comparison between arms 3 and 4 measures discovery/reuse. The comparison
between arms 1 and 4 measures fixed-system uplift. Arm 5 prevents model output
from being incorrectly credited for deterministic capability execution.

## Corpus design

Start with 8–12 genuinely different task families, each with at least 10 sealed
held-out cases and 4 mandatory negative cases. Use real repository fixtures
with integration tests, not generated single-function exercises alone.

Examples: streaming protocol repair, schema migration, safe configuration
normalization, dependency/API migration, structured extraction, test repair,
file/build transformation, and a safe physical-operation family.

For every family, create:

- origin tasks that produce candidates;
- semantically distant, structurally compatible receiver tasks;
- lexical decoys with incompatible postconditions;
- state/policy/verifier drift mutations;
- secret-bearing or privacy-incompatible candidates;
- provider/runtime crossovers.

The corpus split, randomization seed, minimum effect size, sample size, and
scoring method are sealed before the first origin run.

## Admission protocol

```text
discover candidate
  -> compare semantic/task evidence
  -> inspect contract and negative boundary
  -> reproduce locally under receiving policy/verifier
  -> issue local applicability proof
  -> execute or replay
  -> verify postcondition
  -> account for total cost and emit receipt
```

No vector score, lattice relation, cache key, signature, or peer claim may skip
local reproduction and applicability proof.

## Primary outcomes and gates

| Metric | Required gate |
| --- | --- |
| Verified receiver completion | Higher than BEAST-with-discovery-disabled control, with a preregistered confidence interval. |
| Unsafe reuse | Zero across required drift, poisoned, and lexical-decoy cases. |
| Provider displacement | Measured calls/tokens avoided only after successful local verification. |
| Net economics | Positive median and confidence interval after discovery, transfer, replay, verifier, and amortized-origin costs. |
| Discovery precision | Report precision/recall and abstention; no forced match behavior. |
| Cross-runtime result | At least two independent local runtime implementations. |
| Cross-host replication | A separate physical receiver host independently verifies the sealed receipt. |

## Failure interpretation

- Good discovery but failed reproduction: discovery is hypothesis generation,
  not reuse; count a safe miss.
- Successful replay but negative-case admission: invalidate the capability and
  fail the safety gate.
- Faster replay but negative net economics: retain research evidence but deny
  economic promotion.
- Success only when the origin and receiver share obvious vocabulary: report
  lexical coupling; do not call it discovery-agnostic.

## Delivery sequence

1. Add the receipt schema and claim-ledger linkage. **Implemented as a sealed
   preflight contract in `app/kernel/compute/discovery_agnostic_reuse.py`.** It
   requires an injected attestation verifier; `commons_node_attestation_verifier`
   adapts existing TPM/ARDA-backed Commons node verification. The focused tests
   cover distant wording, semantic/state/negative-boundary refusal, stale or
   nonphysical receiver rejection, receipt tampering, portable receipt replay,
   and node-identity binding. `SemanticCapabilityContract` makes the discovery
   query explicit over operation/schema/invariants/tool schema/risk rather than
   over user wording. `scripts/verify_discovery_agnostic_receipt.py` can validate
   the sealed receipt on a separate host without executing the capability.
2. Build sealed corpus tooling and the six-arm runner.
3. Run one local-host dry run to validate accounting and mutation gates.
4. Run the preregistered local experiment with raw-output retention and blinded
   scoring.
5. Repeat receiver runs under a second runtime on the same host.
6. Package the origin artifact as a verify-only Commons hypothesis.
7. Run the receiver on a genuinely separate attested host and independently
   verify the receipts.

`scripts/run_discovery_agnostic_receiver.py` is the receiver-side runner for
steps 6–7. It requires an ARDA Ed25519 public key and a local verifier command;
the command receives only the sealed task/candidate documents and must validate
the receiver's own repository or physical state. An advertised candidate or a
successful signature without a local verifier exit status of zero remains a
safe miss.

Only steps 4–7 can advance the discovery-agnostic claim. Until then, existing
semantic discovery and Commons artifacts remain valuable infrastructure, not
proof of agnostic reuse.
