# Windows Discovery-Agnostic Receiver Runbook

This bundle tests a clean Windows receiver. It does not import Linux caches,
private keys, promoted crystals, database files, or workspace copies.

## Trust mode

The receiver supports two honest modes:

- `signed_clean_room`: Ed25519/ARDA-signed node identity plus fresh clean
  environment and local verification. This is the mode for the TPM-less laptop.
- `hardware_attested`: an additional fresh TPM/vTPM/remote-attestation evidence
  chain. Do not claim this mode unless the evidence is actually collected and
  verified.

The scientific replication result may be valid in `signed_clean_room` mode.
The stronger host/boot-posture claim requires `hardware_attested` mode.

## Before copying the bundle

On Linux/origin, prepare a sealed scenario and an ARDA node public key. The
scenario must contain only privacy-safe digests, candidate contracts, expected
admission outcomes, and paired economics. It must not contain source code,
prompts, credentials, private keys, or an executable command supplied by the
origin.

On Windows, create a fresh workspace checkout for the held-out corpus. It must
not share the Linux worktree, BEAST state root, Ollama cache, or prior receiver
result directory.

Create `verifier-plan.json` locally on Windows:

```json
{
  "timeout_seconds": 180,
  "contracts": {
    "sha256:<sealed-semantic-contract-digest>": ["py", "-3", "-m", "pytest", "-q"]
  }
}
```

Only local Windows operators define this plan. The origin artifact cannot add
or replace a verifier command.

## Run

Extract the bundle. From PowerShell in the extracted directory:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup_beast_windows_discovery_receiver.ps1 `
  -Scenario C:\path\scenario.json `
  -ArdaPublicKey C:\path\arda-node-public.pem `
  -Workspace C:\clean\heldout-corpus `
  -VerifierPlan C:\clean\verifier-plan.json `
  -ForceClean
```

The script creates a fresh virtual environment, uses only loopback Ollama,
runs the receiver corpus, and independently validates the result before
creating its manifest.

## Return package

Return these files unchanged:

- `discovery-agnostic-corpus-receipt.json`
- `receiver-manifest.json`
- `scenario.json`
- `verifier-plan.json`

Linux verifies the corpus receipt with:

```bash
python3 scripts/verify_discovery_agnostic_receipt.py discovery-agnostic-corpus-receipt.json
```

## Claim gate

The run advances the discovery-agnostic claim only if the returned receipt has
zero unsafe admissions, expected held-out admissions, provider-free verified
reuse, and measured net economics after every local overhead. A clean Windows
run remains a signed clean-room replication unless hardware-attestation
evidence is separately supplied and verified.
