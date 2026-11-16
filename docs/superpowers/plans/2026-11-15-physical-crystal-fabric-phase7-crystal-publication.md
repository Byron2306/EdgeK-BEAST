# Physical Crystal Fabric — Delivery 7: Commons publication, quarantine, reproduction and shadow economy

**Sources of truth (operator ruling 2026-11-15):** *BEAST Inference Economy Inversion Working Paper v0.9*
(`evidence/inference_economy_v0_9.pdf`, "v0.9") and *Proof-Governed Experiential Compilation Working Paper v1.0*
("PGEC"). Where code or plans disagree with the papers, the papers win; conflicts are logged in the ledger.

**Target (operator ruling 2026-11-15, 23:34):** BEAST's own Commons, not Hugging Face. The HF dataset path is
out of scope. `CrystalPublisher` stays an optional, default-off exporter that no CLI or route wires up.

## Flow
promoted crystal → privacy-filtered publication bundle (manifest, compatibility, proofs, Xet 4 KiB chunks, Ed25519
signature) → Commons Space bundle (`.beast-space.zip`: content-addressed, privacy-scanned, sealed; v0.9 §7.13.3) →
verify_only bucket revision on the lattice-attested nodes 8111-8113 through the 8101 control plane (client signing
key and ML-KEM channel stay inside the gateway; node-signed receipts act as witnesses; quorum is all nodes; v0.9
§7.13.2) → import back as a quarantined hypothesis (CommonsEnterprisePlane custody) → local held-out reproduction
(≥3 variants, zero model calls) → **operator** promotion (PGEC §2.4 Promotion Sovereignty) → reuse → measured
reduction receipt → shadow-ledger credit.

## Paper principles applied
| Principle | Source | Where |
|---|---|---|
| The governed runtime episode is the unit of experience; resource evidence R is part of it | PGEC §2.3 eq.(1), §3.2 | D5 Episode Envelope budget feeds every receipt |
| Candidates carry no right to execute or promote | PGEC §2.2 | import lands `quarantined`; never served |
| Promotion only after independent verification, and promotion is a separate human act | PGEC abstract, §1, §2.4 | `replay_candidate(promote=False)`; CLI `--approve-by` |
| Proof Preservation: valid only while current evidence ≥ promotion evidence | PGEC §2.4 | quarantine + local reproduction; demotion on failed postcondition |
| Applicability failure → refuse/revalidate/escalate, zero effect | PGEC eq.(5), §5.7 | D6 misfit refusal; demotion |
| V_K = C_avoided − (C_lookup + C_verify + C_risk + C_maintenance); estimates ≠ realised savings | PGEC eq.(6), §7; v0.9 Table 3, §9 | `recurrence_value`; credit = max(0, V_K) |
| No saving counts unless verification quality is preserved | v0.9 §7.12.4 contract, §7.13.5 | receipt verifier requires baseline and reuse passed |
| False reuse is a redline; false hits mean demotion, rollback and credit reversal | PGEC §4.3 eq.(8); v0.9 §7.13.1 | `record_false_reuse` + `clawback` |
| Append-only, chain-witnessed ledger; tampering is quarantined, never rewritten | v0.9 §7.13.2 | hash-chained `CrystalShadowLedger.verify_chain` |
| Internal credits only, not crypto or redeemable; value is scenario-only until independent adoption | v0.9 §7.13.3, §9 | `LEDGER_POLICY` (non-transferable, non-redeemable, no settlement) |
| Similarity or vectors nominate, they never authorise | PGEC §3.3, v0.9 §7.10 | no similarity path in D6/D7 |
| Publish proofs, not private evidence or hidden authority | PGEC §8.2; v0.9 §7.13 sanitisation gate | `assert_publishable`; Space privacy scan |

## Credit model (operator ruling 23:41 / 23:47)
- Per verified reuse: `credit = max(0, V_K)` (PGEC eq. 6), from measured Episode Envelope budgets. Weights:
  model turn 1.0, tool call 0.1, 1k *observed* tokens 0.5, wall second 0.01. C_maintenance 0.05. C_risk =
  the crystal's local false-reuse rate × C_avoided. Estimated tokens are flagged (`tokens_estimated`) and excluded
  from both sides.
- Baseline: this node's own sealed source envelope when present (`local_envelope`); otherwise the publisher's
  measured envelope budget, which is bound into the signed candidate digest (`publisher_signed_envelope`, flagged).
- Credit goes to the publishing identity (signing key id) and its Commons space. A ledger credits only reuse it
  witnessed locally. Remote claims, reproduction runs, quarantined crystals, self-reuse (same controller), duplicate
  reuse fingerprints and failed verification earn 0. Every refusal is still recorded.
- Ratings: 1-5 stars map linearly to a 0.5x-1.5x multiplier on that one reuse's credit. Only that receipt's own
  verified reuser may rate, once. A publisher can't rate its own crystal. Ratings never gate promotion, trust or reuse.
- Sybil and self-dealing: local-witness-only accounting, controller mapping for self-dealing, unique reuse
  fingerprints and rating-per-receipt, and `aggregate_federated`, which counts only attested nodes' chain-valid
  exports, rejects foreign witnesses and same-controller entries, and counts duplicate entries once.
- Demotion (failed postcondition) appends a `false_reuse` entry and a `clawback` reversing all outstanding credit
  for the crystal. It is idempotent, and later ratings are refused.
- Receipts and ledger entries attach to a successor Space revision (`economy/reduction_receipts.json`,
  `economy/shadow_ledger.json`, lineage `parent_manifest_hash`). Reproduction receipts are recorded as evidence.

## Tasks
1. Publication bundle + privacy filter (`crystal_publication.py`) — tests `tests/test_crystal_publication.py`.
2. Commons Space + verify_only bucket revision + witness quorum + quarantined import (`crystal_commons.py`) —
   `tests/test_crystal_commons.py` (fake transport over the real `CommonsBucketStore` and real
   `CommonsEnterprisePlane.admit_remote_revision`).
3. Shadow economy (`crystal_economy.py`; runtime hook after `agent.episode.sealed`) — `tests/test_crystal_economy.py`.
4. CLI `scripts/coding_crystals.py publish|pull|reproduce|ledger` — offline by default; `--live` talks only to a
   loopback gateway.
5. Promotion sovereignty in the production path — `tests/test_coding_crystal_wiring.py`.

## Live lab procedure (Byron's own Commons lab; 8101 not restarted)
```
BEAST_CODING_CRYSTALS=1 .venv/bin/python scripts/coding_crystals.py publish <CRYSTAL_ID> --live
BEAST_CODING_CRYSTALS=1 .venv/bin/python scripts/coding_crystals.py pull commons-node-b <CRYSTAL_ID> --live --workspace <CONSUMER_WS>
BEAST_CODING_CRYSTALS=1 .venv/bin/python scripts/coding_crystals.py reproduce <CRYSTAL_ID> --workspace <CONSUMER_WS> --approve-by <OPERATOR>
BEAST_CODING_CRYSTALS=1 .venv/bin/python scripts/coding_crystals.py ledger --workspace <CONSUMER_WS>
```

## Open decisions for the operator
- Cost weights and C_maintenance (ruling above; easy to change in `COST_WEIGHTS`).
- Controller mapping (which node or user identities share an operator) for self-dealing; default is identity equality.
- Whether Commons replay records (`/edgek/commons-spaces/{id}/replay`) should also carry crystal reproduction
  receipts. Today they live in the shadow ledger and in the successor Space bundle.
