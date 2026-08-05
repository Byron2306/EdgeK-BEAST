---
title: DIO Phase 2 Semantic Witness
emoji: \"🧭\"
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# DIO Hugging Face remote witness

This is the Phase-2.1A remote signed software witness scaffold.

It exposes:

- `GET /health`
- `POST /attest`
- `POST /evaluate`

Authority boundary:

- claim: remote signed software witness with independently executed verifier
- nonclaim: hardware attestation
- nonclaim: execution or production authority
- nonclaim: ML-KEM session evidence is a vote signature

## Required Space secrets

Set one signing secret:

```text
BEAST_DIO_WITNESS_PRIVATE_KEY_B64=<base64 raw Ed25519 private key bytes>
```

Recommended identity/build pins:

```text
BEAST_DIO_WITNESS_NODE_ID=dio:hf:semantic-witness-01
BEAST_DIO_WITNESS_ROLE=semantic_witness
BEAST_DIO_WITNESS_VERIFIER_COMMIT=sha256:<pinned verifier source/build digest>
BEAST_DIO_WITNESS_CONTAINER_MANIFEST=sha256:<pinned container/source manifest digest>
```

The corresponding public key fingerprint must be pinned locally before the
orchestrator counts the Space's vote.

## Local dry run

For a local non-authority smoke test only:

```bash
BEAST_DIO_WITNESS_ALLOW_EPHEMERAL_IDENTITY=1 \
uvicorn app.dio_hf_witness_main:app --host 127.0.0.1 --port 7860
```

Do not count an ephemeral local key as remote quorum authority.
