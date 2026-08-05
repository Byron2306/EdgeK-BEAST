# Two-stage final release architecture

## Why one ZIP cannot contain its own independent proof

A reproduction or witness report cannot truthfully bind to the SHA-256 of the final ZIP if that report is itself inside the ZIP. Adding the report changes the ZIP digest; updating the digest inside the report changes it again. That is a self-reference, not a reproducible publication design.

DAI-Diode therefore uses two immutable objects.

## Object 1 — the core capsule

`core/CORE_CAPSULE.zip` contains the frozen technical subject:

- original Phase 1 through Phase 6.2 artifacts;
- reviewed lineage ledger;
- deterministic solver and verifier;
- frozen arena cases and oracle commitment material;
- semantic and authority policies;
- schemas;
- source/build identities;
- no independent reports that need to refer to the completed core.

Build it first. Record:

- core ZIP SHA-256;
- core publisher key fingerprint;
- core release ID;
- signed source commit/tag;
- deterministic build epoch.

These values go into `core/CORE_CAPSULE.TRUST.json` in the later envelope.

## Object 2 — the publication envelope

The publication envelope contains:

- the unchanged core capsule;
- core trust record;
- signed independent oracle and case-author attestation;
- signed no-egress witness;
- mutation and ablation reports bound to the core digest;
- at least two signed clean-room reproduction reports;
- at least three signed independent Commons witness packets;
- raw attestation evidence;
- claims registry and final gate checklist;
- prior-art matrix and independent review;
- paper, nonclaims, schemas, SBOM, and provenance.

Every external report uses:

```json
"subject_core_capsule_sha256": "sha256:<core digest>"
```

The envelope then receives its own signed exact-file manifest and outer ZIP digest. That outer digest is published externally; it is never embedded as a self-reference.

## Build order

### 1. Freeze the core source

```bash
git status --short                # must be empty
git commit
git tag -s dai-diode-core-rc1 -m 'Freeze DAI-Diode core RC1'
```

### 2. Assemble and validate the core candidate

```bash
cp -a templates/candidate core-candidate
# Replace templates with the actual lineage, arena, code, evidence, and claims.
python dai_publication.py discover-lineage core-candidate/artifacts \
  --output core-candidate/lineage/LINEAGE_LEDGER.discovered.json
python dai_publication.py validate-candidate core-candidate --stage rc
```

### 3. Build the core capsule

Keep the private key outside the repository.

```bash
export SOURCE_DATE_EPOCH=<signed-tag-epoch>
python dai_publication.py build core-candidate \
  --release-id DAI-Diode-Core__Bounded-Deterministic-Intelligence__RC1 \
  --private-key /secure/offline/core-publisher.ed25519.pem \
  --output core-dist
```

Copy the resulting ZIP unchanged to:

```text
publication-candidate/core/CORE_CAPSULE.zip
```

Create `CORE_CAPSULE.TRUST.json` with its exact digest, release ID, and externally published core publisher fingerprint.

### 4. Freeze the independent arena commitment

Independent case author:

1. receives only the frozen public solver contract;
2. writes `ARENA_CASES.json` and `INDEPENDENT_ORACLE.json`;
3. hashes the cases file;
4. signs the oracle and case-author attestation before execution;
5. publishes their public key separately.

Sign with:

```bash
python dai_evidence.py sign-object \
  publication-candidate/arena/INDEPENDENT_ORACLE.json \
  --private-key /secure/operator/oracle-author.pem \
  --public-key-path keys/oracle-author.public.pem
```

Repeat for the case-author attestation.

### 5. Run mutation, ablation, and offline arena

Run against the exact core digest. Bind every report to:

```text
subject_core_capsule_sha256 = sha256:<core digest>
```

The network witness must be signed by the observer and must preserve the deny policy, socket/eBPF trace, packet summary, DNS attempts, and process tree.

### 6. Collect clean-room reproductions

Each operator receives only:

- public core ZIP;
- externally published ZIP digest;
- externally published core key fingerprint;
- public reproduction guide.

Each operator signs a report with a separate key and control domain. Reports must agree on the normalized semantic result digest.

### 7. Collect independent Commons votes

Publish one exact quorum context with:

- proposal digest;
- capability digest;
- evidence root;
- world-state hash;
- governance epoch;
- challenge nonce;
- verifier digest;
- evaluation time;
- quorum policy.

Each independent operator signs one `*.witness.json` packet and includes exact paths and digests for raw attestation evidence. The envelope validator rejects any binding mismatch, stale vote, duplicate identity, missing role, or collapsed control domain.

### 8. Validate the final candidate

```bash
python dai_evidence.py validate-final publication-candidate
```

The technical release cannot pass unless G01–G24, G27, and G28 are green. The world-first claim remains withheld unless G25 and G26 also pass.

### 9. Build the publication envelope

```bash
export SOURCE_DATE_EPOCH=<publication-signed-tag-epoch>
python dai_publication.py build publication-candidate \
  --release-id DAI-Diode__Bounded-Deterministic-Intelligence__Publication-1 \
  --private-key /secure/offline/publication-publisher.ed25519.pem \
  --output publication-dist
```

### 10. Verify with both external anchors

```bash
python dai_evidence.py verify-release \
  publication-dist/DAI-Diode__Bounded-Deterministic-Intelligence__Publication-1.zip \
  --expected-zip-sha256 sha256:<externally-published-envelope-digest> \
  --trusted-fingerprint sha256:<externally-published-envelope-key-fingerprint>
```

This verifier also rejects ZIP comments and explicit directory entries because neither is represented in the signed file inventory.

## Publication anchors

Publish the envelope ZIP digest and key fingerprint in at least:

1. a signed Git tag;
2. GitHub release notes;
3. a transparency-backed Sigstore/cosign attestation;
4. Zenodo, OSF, or an institutional repository deposit with DOI;
5. the paper appendix.

The same exact ZIP digest must appear everywhere.

## Claim discipline

The envelope may support:

> DAI-Diode validates bounded deterministic intelligence as an engineering architecture.

It may support the priority statement only if the source-backed prior-art matrix and an independent reviewer are green:

> To our knowledge, DAI-Diode is the first publicly documented system to combine closed-world deterministic entailment, signed provenance, authority-bounded expression, multi-domain capability composition, and heterogeneous attested quorum in a replayable evidence architecture.

Neither sentence grants execution or production authority.
