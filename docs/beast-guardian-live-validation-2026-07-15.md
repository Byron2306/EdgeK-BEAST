# BEAST Socket Guardian live validation — 2026-07-15

Status: live host-local validation evidence. This is not production hardware
attestation, HSM/Vault key custody, reboot acceptance, or a deployment approval.

## Observed live topology

- ARDA Guardian operation authority: `127.0.0.1:18401`, container healthy.
- Socket Guardian: installed user service, active.
- BEAST consumer: installed/enabled user service, healthy on `127.0.0.1:8101`.
- Commons consumer: installed/enabled user service, responsive on
  `127.0.0.1:8601` and path-restricted.
- Systemd retains BEAST, Commons, ARDA, Seraph UI, and Seraph API listeners.
- BEAST and Commons were observed at listener generation 3 and Guardian health
  `healthy`. Unstarted ARDA/Seraph consumers remain `reserved/unknown`.

The authority validates a bearer credential from a protected file, exact
canonical request digest, operation allowlist, workspace, policy generation,
appraisal, deployment capability, registry digest, ProcessLease owner scope,
and executable digest. It issues separately signed short-lived decision,
one-use capability, and appraisal objects. The Guardian consumes each
capability atomically in its durable ledger.

The appraisal binds the reviewed Metatron sovereign-proof manifest digest but
is explicitly labelled `local_validation`. Static proof binding is not a fresh
TPM quote, event-log appraisal, Secure Boot measurement, or external witness.

## Live acceptance

Consumer replacement proved:

- both server PIDs changed;
- lease IDs, ports, and listener generations remained constant;
- no competing bind succeeded during replacement;
- both Guardian health states returned to `healthy`; and
- the Commons outer boundary continued to deny unrelated routes with HTTP 404.

Guardian replacement proved:

- the Guardian PID changed;
- BEAST and Commons PIDs changed;
- listener generations advanced exactly once;
- ports remained constant and continuously owned; and
- both services returned healthy through newly signed descriptor handoffs.

Installed unit validation passed with `systemd-analyze --user verify`. The
focused BEAST/Guardian/Sensorium/Commons family passed 76 tests; the Metatron
ARDA authority family passed 8 tests.

## Evidence digests

| Evidence | SHA-256 |
|---|---|
| Deployment appraisal | `9ab7a62b394667b613a1a36d6d5a416209c6f0729ab4b74ced769ceef1dd9a3f` |
| Consumer restart acceptance | `32c808d60abbe549f4ccbb7d2eea92e75eeaf35092e37ae913cba6fac1239a33` |
| Guardian replacement acceptance | `2e116527d211a7c728aafb4023683b4007aed908399840e48adfc6fb15b01a83` |
| Final BEAST handoff receipt at evidence capture | `05ce04dd898732fe75e91e9ddcdfb6c39795f5d000e93878fcd911316cbd5a7f` |
| Final Commons handoff receipt at evidence capture | `9dedcec467cb3108a0d1d3c4c968f2e19faf69d9c32500f6de0244efdb8a58e6` |

The mutable evidence files remain under `~/.local/state/beast/`; secrets and
private keys remain under `~/.config/beast/` with mode 0600 and are not copied
into this repository.

## Defects exposed and corrected

1. The HTTP adapter trusted unsigned appraisal metadata. Appraisals now have a
   canonical Ed25519 signature covering authority, audience, policy,
   appraisal reference, request digest, expiry, nonce, key, state, and evidence
   digest.
2. The ARDA preflight used a synthetic `lease:` prefix while real Guardian
   identities use `portlease:`. The authority now accepts only the real typed
   identity family.
3. Hardened read-only services exposed runtime writes under source directories.
   Plugin and `.beast` runtime state now honor `BEAST_STATE_ROOT`; Commons
   Spaces honor the service state root. Source code remains read-only.

## Open production gates

- perform an explicitly scheduled workstation reboot and confirm enabled-unit
  activation, generation recovery, health, and port continuity evidence;
- replace local file signing keys with managed HSM/Vault/KMS custody;
- replace static sovereign-proof binding with fresh measured boot/TPM and
  revocation-aware appraisal evidence;
- use mTLS or an equivalent authenticated authority transport if the endpoint
  ever leaves loopback;
- provision Commons artifact/node/Space trust roots and signed witnesses so
  its current `configuration_required` admission state can become ready; and
- activate reviewed `.test` DNS/reverse-proxy routing under change control.

## TPM follow-up

A subsequent host-local TPM run closed part of the measured-identity gap:

- a fresh nonce-bound quote over SHA-256 PCRs `0,2,4,7,10,14` verified;
- Secure Boot was enabled;
- the firmware EK certificate key matched the TPM-derived EK; and
- the complete Nuvoton EK chain validated against pinned host-local roots.

The latest evidence digest is
`sha256:ad7d8901eaa622405afe8642c23a9a551f9eb8cba7234c1501f02b94349ac198`.
AK credential activation now passes using an offline verifier and the physical
TPM. Firmware replay matches PCRs `2,4,7,14`; the IMA replay matches PCR `10`;
and HP's official V72 `01.11.00` SoftPaq history supplies the published PCR0
baseline that matches the live TPM exactly. The packet now reports
`eligible_for_commons: true` at the evidence collector layer. It has not
replaced or upgraded the Guardian deployment appraisal.
