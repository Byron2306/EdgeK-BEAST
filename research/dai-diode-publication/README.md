# DAI-Diode Publication Closure

This directory is the publication, mutation, ablation, and independent-reproduction harness for the DAI-Diode evidence lineage.

It is intentionally separate from the live BEAST runtime. The publication capsule is evidence, not an installer, and **never grants production or execution authority**.

## Precise claim under test

> **Bounded deterministic intelligence** is the reproducible derivation of semantically meaningful answers, refusals, or decisions from a declared evidence world by inspectable deterministic rules, with explicit authority limits, complete provenance, and replayable verification, without hidden stochastic dependence in the decision core.

The final DAI-Diode claim is intentionally narrow:

> DAI-Diode demonstrates bounded, provenance-governed deterministic intelligence over a closed evidence world, including multi-capability composition, principled refusal, shared text/visual semantics, and heterogeneous attested quorum over an exact digest-bound proposition.

This repository does **not** claim AGI, open-world omniscience, arbitrary natural-language understanding, model obsolescence, or production authority.

## What this harness closes

The harness is designed to eliminate the exact classes of challenge identified across the Phase 3, 3.1, 5, and 6.2 capsules:

- security-critical Python `assert` checks;
- optimized-mode fail-open behavior;
- unlisted files and basename-only exclusions;
- path traversal, symlink, case-fold, and Unicode-normalization collisions;
- mutable or decorative checksum sidecars;
- predecessor mismatch and dangling lineage references;
- self-contained key identity being mistaken for publisher identity;
- route and semantic-digest fields being trusted rather than recomputed;
- destructive source overlays;
- non-self-contained tests and reproduction commands;
- conflation of artifact verification with semantic reproduction;
- claims based on a same-author oracle;
- zero-provider-call claims without a network-denial witness;
- quorum claims without exact proposal, nonce, epoch, world-state, capability, and evidence-root binding.

## Directory contract

A publication candidate is assembled under `candidate/`:

```text
candidate/
  artifacts/                 # immutable prior DAI ZIP capsules
  arena/                     # frozen cases, independent oracle, outputs
  evidence/                  # quorum packets, raw attestations, JWKS, receipts
  lineage/LINEAGE_LEDGER.json
  reports/                   # mutation, ablation, reproduction, network witness
  docs/                      # claims, nonclaims, threat model, prior art
  publisher.ed25519.pub.pem
```

`dai_publication.py build` creates a signed deterministic release directory and ZIP. The release manifest inventories every file except the manifest and detached signature packet themselves; those two paths are exact top-level exclusions, never basename exclusions.

## Required release gates

A release is publishable only when all gates are green:

1. **Frozen integrity** — exact file-set equality and every size/digest verified.
2. **Publisher anchor** — signing-key fingerprint and outer ZIP digest are published outside the artifact.
3. **Lineage closure** — Phase 1 through the final phase are connected by exact digest edges; nested fossils are opened and verified.
4. **Semantic replay** — the declared deterministic core reproduces the same normalized semantic result on clean machines.
5. **Mutation resistance** — every hostile mutation is rejected.
6. **Ablation validity** — removing required capabilities, evidence, policy, provenance, or witnesses causes the predicted refusal or quorum failure.
7. **Independent oracle** — held-out cases and expected outcomes were authored after solver freeze by someone other than the solver author.
8. **Independent reproduction** — at least two external operators reproduce from public instructions.
9. **Independent quorum** — at least three separately controlled operators/keys/providers evaluate the same exact proposal.
10. **Offline proof** — the post-ledger run occurs with egress denied and an external network witness preserved.
11. **Claims discipline** — every public sentence maps to a machine-readable claim and a pass condition.
12. **Prior-art review** — the world-first statement remains `to our knowledge` unless a documented comparison matrix survives review.

## Commands

```bash
cd research/dai-diode-publication
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'

make test
make selftest
```

Build a candidate after copying the DAI archives and evidence into `candidate/`:

```bash
export SOURCE_DATE_EPOCH=1785888000
python dai_publication.py discover-lineage candidate/artifacts \
  --output candidate/lineage/LINEAGE_LEDGER.json

python dai_publication.py validate-candidate candidate

python dai_publication.py build candidate \
  --release-id DAI-Diode-Final__Bounded-Deterministic-Intelligence__RC1 \
  --private-key /secure/offline/publisher.ed25519.pem \
  --output dist

python dai_publication.py verify dist/DAI-Diode-Final__Bounded-Deterministic-Intelligence__RC1.zip \
  --trusted-fingerprint sha256:<externally-published-fingerprint>

python dai_publication.py mutate \
  dist/DAI-Diode-Final__Bounded-Deterministic-Intelligence__RC1.zip \
  --output reports/mutation
```

Run system-specific ablations with an adapter command. The adapter receives `DAI_ABLATION_INPUT` and must write `DAI_ABLATION_OUTPUT`:

```bash
python dai_publication.py ablate candidate/arena/ABLATION_PLAN.json \
  --adapter 'python scripts/run_dai_phase6_arena.py --input {input} --output {output}' \
  --output candidate/reports/ablation.json
```

## Publication order

1. Freeze source at a clean signed Git commit.
2. Freeze the independent arena and oracle.
3. Ingest Phase 1 through Phase 6.2 evidence without modifying prior capsules.
4. Generate and manually review the lineage ledger.
5. Run clean-room verification, reproduction, mutation, ablation, and offline tests.
6. Collect independent operator reports and quorum packets.
7. Build the deterministic release ZIP.
8. Publish the ZIP digest and key fingerprint in a signed Git tag, GitHub release, and transparency-backed attestation.
9. Deposit the same ZIP in Zenodo or an institutional repository for a DOI.
10. Submit the paper and prior-art matrix for outside review.

## The words this package is trying to earn

When the technical gates pass, the defensible statement is:

> **DAI-Diode validates bounded deterministic intelligence as an engineering architecture.**

When the prior-art matrix and independent review also survive, the defensible priority statement is:

> **To our knowledge, DAI-Diode is the first publicly documented system to combine closed-world deterministic entailment, signed provenance, authority-bounded expression, multi-domain capability composition, and heterogeneous attested quorum in a replayable evidence architecture.**

The harness is deliberately built to make either statement fail closed if the evidence does not support it.
