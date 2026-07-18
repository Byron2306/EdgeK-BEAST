# Windows discovery-agnostic receiver

This bundle is the independent receiver experiment. It is deliberately not a
claim that a TPM makes crystallized compute true: TPM evidence only raises the
identity/isolation confidence of the receiver.

1. Copy the repository bundle to a fresh Windows checkout. Do not copy BEAST
   state, caches, private keys, or prior receipts.
2. Place the ARDA appraisal public key at `keys\arda-public-key.pem`.
3. Set `BEAST_RECEIVER_VERIFY_COMMAND` to a command that reproduces the sealed
   task in the receiver checkout and returns exit code 0 only after its own
   tests pass.
4. Run PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup_beast_windows_discovery_receiver.ps1
```

The output receipt is valid for discovery-agnostic reuse only when its signed
node appraisal, local verifier output, and clean-workspace provenance are
reviewed. With TPM, attach the TPM quote/PCR and ARDA appraisal artifacts. A
software identity or ordinary VM is acceptable for a portability rehearsal but
must be labeled `hardware_attestation=unavailable`.
