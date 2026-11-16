# BEAST Commons, independent witness and Windows TPM evidence

Collected 2026-10-10. This folder preserves the validation receipts, scripts, logs and Windows public TPM artifacts from this session. Results describe the recorded verification time; they are not a claim that expiring challenges or services remain current indefinitely.

## Overall result

Commons A/B/C were started and lattice-attested, the desktop was packaged, and local inference worked. The independent HF software witness verified successfully. A fresh Windows TPM quote and five boot-log PCRs verified. Full hardware-backed Commons execution trust remains incomplete. The broader backend test suite also has unresolved failures.

## Containers, dependencies and runtime

- Started the three Commons containers using `docker-compose.commons-lab.yml` and `.beast/remote-commons-lab/docker-compose.ports.yml`. Host endpoints are loopback ports 8121, 8122 and 8123.
- Started the sibling Metatron ARDA fabric with validation roots and host-port overrides. Recorded 14 running containers across Commons and ARDA. Docker access for the Debian user was corrected.
- Installed project Python requirements, CPU PyTorch, Node 22.23.3/npm 10.9.9, desktop dependencies and supporting services/tools. Python dependency consistency passed.
- Verified gateway 8101, Commons gateway 8601, MCP HTTP 8765, LiteLLM 4000 and nginx 8080. Direct Ollama and governed proxy inference returned BEAST_OK using local Qwen models.
- Evidence: `validation/containers.json`, `validation/runtime-probes.json`, and `validation/REPORT.md`. These are recorded observations rather than a new health check performed during packaging.

## Commons attestation and ML-KEM correction

The failing admission was caused by the advertised subject changing after ML-KEM key initialization. Kept the canonical six-field node subject stable and put the ML-KEM public-key digest outside that subject in the signed descriptor. This preserved subject binding while retaining the key digest. Thirteen targeted node tests passed.

Rebuilt the nodes, refreshed signed attestations with `scripts/attest_remote_commons_lab.py`, then discovered, challenged, registered and probed them with `scripts/bootstrap_remote_commons_lab.py`, from the repository root using its `.venv/bin/python`. The lattice ledger verified 13 checkpoints, head `sha256:45de93005b57756bccfd341426e794ca25ab66e2a360220c288b13f29b0406a4`. All three nodes reported lattice trust. This is signed metadata/history and endpoint-key possession, not proof of hardware-backed workload execution.

Evidence: `validation/attest_remote_commons_lab.json` and `validation/bootstrap_remote_commons_lab.json`.

## Desktop IDE and enterprise wiring

Fixed portable Python selection, stylesheet inclusion, versioned shell-storage validation, debug IPC audit contracts, and duplicate pytest module collection. Existing user changes were preserved.

Desktop smoke and visual-contract checks passed; target smoke had 30 passes and 3 skips. Live parity checks passed 92/93, with panel resizing still disabled. Electron launched against the backend under Xvfb. Linux AppImage and Debian packages built successfully using repository packaging commands. The npm audit reported 22 findings (10 moderate, 12 high). The bounded backend suite recorded 1,923 passes, 86 failures and 8 skips.

Configured local-lab artifact, appraisal and witness signing/verifier settings for Job Choir and Space Forge. Sixteen targeted tests passed; signed wiring and tampering checks passed. READY means configuration readiness. No real execution job or Space was launched, and storage-node lattice trust does not authorize CPU execution. Private signing keys remain outside this evidence bundle.

Evidence: `validation/enterprise-wiring.json`, `validation/electron-live.json`, test logs/XML, and the historical detailed `validation/REPORT.md`.

## Actual admission proof and identified gap

Fresh honest hardware-unavailable evidence for A/B/C was refused (HTTP 403). An isolated test with a temporary key and ledger demonstrated that caller-supplied eligibility and verifier-result flags could be accepted by the appraisal issuer without raw quote, certificate, activation or event-log proof. Its signed result passed SignedNodeAttestationVerifier and Job Choir selection; replay was refused. No live node received that synthetic successful appraisal.

This exposes an issuer input trust-boundary gap. Independent authenticated verification of raw evidence, bound to the exact subject and challenge, must precede issuance. This session did not repair that gap. Evidence: `validation/attestation-proof.json` and `validation/prove-enterprise-attestation.py`.

## Hugging Face independent witness

Recovered the deleted witness reference from `github/rescue/pre-purge-2026-10-03` into isolated evidence directories. The user restarted `Byron230686/dio-phase2-semantic-witness`. Health, identity and manifest endpoints returned 200; root 404 is expected for the API-only service.

The recovered verifier completed a fresh run with verified=true against pinned identity/build metadata at Hub commit `544a229085182448daa74c099b296d28a851fb9e`. Its authority is remote_signed_software_witness_only. It is not a TPM appraisal service, and separate administrative custody of its signing authority was not established.

Evidence: `validation/hf-witness-live.json`, `validation/hf-witness-recovery/`, and `validation/recovered-witness-reference/`.

## Windows TPM quote and boot evidence

The administrator-run preflight confirmed TPM 2.0 present, ready, enabled and activated; Secure Boot enabled; MSFT firmware 6.4.1.383; one EK manufacturer certificate. The certificate identifies Microsoft Pluton.

Prepared a native Windows quote collector using Microsoft TSS.MSR at pinned commit `52cb9f432318e8e95cdfeaf98b824ece89370744`. The user ran it. It obtained a fresh BEAST server challenge, bound current Commons identities, created a transient restricted signing key, quoted SHA256 PCRs 0,2,4,7,10,14 and flushed that key.

Independent verification passed all 13 quote checks and three tampering controls at verification time, including signature, challenge, expiry, canonical subject binding, key names and PCR digest. This does not establish EK-to-AK identity binding. The captured challenge has since expired; the receipt documents its original verification time.

`tpm2_eventlog` replay matched quoted PCRs 0,2,4,7,14. PCR10 was zero and absent from the supplied log, so complete six-PCR reconciliation was not established.

Evidence: `windows-tpm-public/nonce-bound-quote.json`, `windows-tpm-public/SRTMBoot.dat`, and `validation/windows-quote/quote-verification.json`, `boot-replay-verification.json`, `windows-boot-replay.yaml`, collector/verifier scripts and upstream provenance.

## EK certificate chain investigation

Windows chain building initially reported PartialChain, RevocationStatusUnknown and OfflineRevocation. Downloaded Microsoft's published TrustedTpm.cab; Windows Authenticode reported Valid, signer Microsoft Corporation. Extracted certificates without changing trust stores. The bundle did not supply the exact per-device issuer. Get-TpmEndorsementKeyInfo.AdditionalCertificates returned zero.

Read public TPM NV metadata, then exported only standard public certificate indices: 0x01c00002 (959-byte RSA EK leaf), 0x01c0000a (756-byte ECC EK leaf), and 0x01c00100 (1,215-byte device intermediate). The recovered intermediate cryptographically verified the RSA leaf signature. Its issuer is AMD Pluton Factory DEVICE EK ICA DFID0001, which was not located in the downloaded bundle.

The final check covers signatures and rendered issuer names; it is not complete X509 path validation. A certificate name-encoding difference prevented strict direct-issuer matching; the limited check is explicitly recorded. The chain does not yet reach an authenticated root, revocation is unverified, and EK-to-AK credential activation was not performed.

Evidence: `windows-tpm-public/nv-certificate-*.bin`, `nv-public-metadata.json`, `ek-manufacturer-0.cer`, `TrustedTpm.cab`, extracted `TrustedTpm/`, and `validation/windows-quote/ek-chain-from-nv.json`. Earlier failed-chain receipt is retained separately.

## Remaining requirements

- Obtain and validate the missing AMD Pluton factory issuer chain to an authenticated trust anchor, with revocation and full certificate-path checks.
- Prove EK-to-AK binding using credential activation and collect a fresh challenge-bound quote.
- Define and validate an explicit Windows PCR baseline/policy; resolve the missing PCR10 reconciliation.
- Authenticate independent verifier results before ARDA appraisal issuance, and close the demonstrated caller-supplied-result gap.
- Establish host-to-container workload assurance for Commons execution claims.
- Resolve the 86 backend failures, disabled IDE panel resizing and dependency audit findings before claiming the whole system passes.

## Evidence integrity and handling

`manifest-sha256.json` lists byte sizes and SHA256 hashes of all bundled files except itself. `repository-state.txt` records the current commit and working-tree changes. `validation/REPORT.md` is preserved as a chronological report: earlier pending/failed statements are superseded by later entries and this summary. Public TPM evidence includes host diagnostics and registry exports and should be reviewed before publishing. Private signing keys and credentials were not copied from the live trust configuration.
