# Security policy

## Release verification

BEAST proof capsules are verified by digest, detached signature, transparency
log inclusion, and local certificate receipts.

The C4-X physical-truth release key is pinned in [RELEASE_KEYS.md](RELEASE_KEYS.md).

Current release key fingerprint:

```text
SHA256:dPClisgoezAMAYxhiU2O/E0x6hueE3MBqPXmUvHLfRg
```

Current Rekor entry:

```text
https://rekor.sigstore.dev/api/v1/log/entries/108e9186e8c5677ac634a8c30255042bd7a67e75e414ca8d4a0ec2544e768e8b26b6e4b8c388633d
```

Current artifact SHA-256:

```text
sha256:50a8ce87c2140e26d85fc31a04ea78e5e737202ce1d69a476f7b4b88e4a2d8ce
```

## Verification boundary

The pinned SSH key proves continuity for BEAST C4-X proof-bundle signatures once
the repository, release notes, and preregistration publish the same fingerprint.
It does not by itself prove institutional identity, employment, or NWU
endorsement.

For final public release provenance, prefer Sigstore Fulcio/OIDC keyless
signing from a declared GitHub workflow, plus RFC 3161 or Sigstore timestamp
evidence for independently trusted time.

## Reporting issues

Report security issues through the repository issue tracker or the maintainer's
published contact channel. Do not include secrets, API keys, private signing
keys, or sensitive operational logs in public reports.
