# Commons TPM Remote Validation

Status: local Linux TPM evidence reconciles with a durable HP vendor PCR0
baseline; remote cryptographic submission and ARDA appraisal are deliberately
not yet live.

## Current workstation proof

On 2026-07-15, BEAST collected a fresh nonce-bound TPM 2.0 quote from the local
Nuvoton NPCT75x TPM. The quote signature verified, Secure Boot was enabled, the
TPM-derived EK public key matched the EK certificate, and the EK certificate
chain validated to Nuvoton's NPCTxxx ECC521 RootCA.

This is hardware evidence, not a production appraisal. The local evidence is
stored outside the repository at:

`~/.local/state/beast/tpm-validation-latest.json`

The initial fail-closed blockers were AK activation and measurement-log replay.
AK activation is now complete:

- verifier-side MakeCredential runs offline in a pinned Debian 12 image;
- the physical TPM successfully recovers the verifier secret through
  ActivateCredential; and
- the evidence records the verifier image ID and hashes of the secret and
  credential blob without retaining the secret.

The staged firmware log parses successfully. PCRs `2,4,7,14` reconcile exactly.
The independent IMA stream replays PCR `10` exactly. Linux firmware replay does
not reconstruct PCR `0`, but HP's official V72 `01.11.00` SoftPaq history
publishes PCR0 as
`0886e6fc01b4b9c8fc427eb494c7fa477032d56991529621fe3e9865f532e92f`, which
matches the live TPM value exactly.

BEAST now treats that HP-published PCR0 as a vendor measurement source, not as a
waiver. The durable baseline is stored at:

`docs/evidence/tpm/vendor-baselines/hp-probook-450-g10-v72-01110000/`

The current local packet reports `eligible_for_commons: true` at the evidence
collector layer. It remains hardware evidence only; ARDA still has to issue a
separate appraisal before a node receives execution authority.

## Windows colleague protocol

Windows is a supported evidence source, not a separate trust model. The same
server-generated challenge, PCR policy, and appraisal gates apply.

1. The colleague establishes an authenticated transport identity. Internet
   exposure requires mTLS or an equivalently bound authenticated tunnel.
2. BEAST issues a short-lived challenge through
   `POST /edgek/control-plane/commons/attestation/challenges` with the exact
   node identity. Issuing a second active challenge supersedes the first.
3. A Windows attester obtains the EK certificate, creates or opens a
   non-exportable AK through Windows TPM Platform Crypto Provider/TBS, and
   sends only public enrollment material.
4. The verifier performs MakeCredential; the Windows TPM performs
   ActivateCredential. The recovered verifier secret binds the AK to the
   certified EK. A Boolean supplied by the Windows node is never accepted as
   evidence of this step.
5. The Windows TPM quotes SHA-256 PCRs `0,2,4,7,10,14` over the exact challenge
   nonce. The packet includes the quote, signature, AK public/name, selected
   PCR values, EK certificate, and measured-boot event log.
6. The independent verifier validates the EK manufacturer chain and
   revocation policy, AK activation, quote signature, nonce, PCR selection,
   freshness, Secure Boot policy, and event-log replay.
7. ARDA signs a short-lived, audience-bound node appraisal over the complete
   Commons advertisement. Only that appraisal can make the node eligible for
   Job Choir selection.

`Get-Tpm`, `Confirm-SecureBootUEFI`, and device-information utilities are useful
preflight signals on Windows, but their text output is not a TPM quote and must
not be promoted into an attestation.

## Required submission verifier

The next implementation must add a two-stage enrollment and quote verifier:

- persistent AK enrollment identities and Nuvoton/Intel/AMD manufacturer trust
  roots under change control;
- MakeCredential/ActivateCredential with verifier-generated secrets;
- Windows and Linux evidence adapters targeting one canonical bundle schema;
- event-log replay with exact PCR reconciliation and vendor-published firmware
  baselines where the firmware vendor publishes PCR values;
- revocation and firmware-baseline policy;
- transactional challenge consumption only after all cryptographic checks;
- ARDA appraisal issuance and a durable evidence-graph receipt;
- rejection tests for replay, wrong nonce, wrong node, stale quote, altered
  event log, untrusted EK, mismatched AK, and self-reported verification.

Until those checks exist, the challenge endpoint is intentionally the only live
remote TPM endpoint and no remote node is admitted.
