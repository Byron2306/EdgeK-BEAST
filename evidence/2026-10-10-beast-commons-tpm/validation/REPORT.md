# BEAST validation ? 2026-10-10

BEAST is runnable, but the complete system is not verified green. The complete bounded backend run produced **1,923 passed, 86 failed, 8 skipped** (2,017 tests, 631.76 seconds). See pytest-bounded.xml, pytest-bounded.log and failed-tests.json. Live/manual marked tests were excluded. A 30-second per-test timeout prevented the unbounded planner stall seen in the first partial run (489 passed, 26 failed, 4 skipped before interrupt). Some failures reference obsolete desktop layouts; others affect active runtime contracts. They need individual triage rather than blanket expectation changes.

## Containers and VS Code

All 14 requested Commons and ARDA lab containers are running; configured Docker health checks pass. See containers.json. Several lattice roles are intentionally sleep-infinity lab containers, so running status does not prove an executable production witness workflow. Docker is the native Debian daemon at unix:///var/run/docker.sock. Windows VS Code opened the repository through a UNC path and does not automatically inspect that daemon. The byron user was added to the docker group and new WSL sessions can list containers.

In VS Code, run **WSL: Reopen Folder in WSL**, choose Debian, then ensure **Container Tools** is installed in that WSL window (extension panel: Install in WSL: Debian), and refresh Containers. The local Windows extension install does not establish a remote install.

Commons compose: docker-compose.commons-lab.yml plus .beast/remote-commons-lab/docker-compose.ports.yml; container endpoints 127.0.0.1:8121?8123 preserve existing non-container services on 8111?8113.
ARDA compose: ../Metatron/live_arda_fabric/docker-compose.yml plus docker-compose.validation-roots.yml and .beast/validation-2026-10-10/docker-compose.arda-hostports.yml. Ollama 127.0.0.1:11434; ARDA 127.0.0.1:18401. Validation keys are in /tmp/metatron-recovery-roots-validation; these are lab keys, not production trust roots.

## Installed and running

Node 22.23.3/npm 10.9.9 installed from checksum-verified official Node distribution; desktop npm ci completed. Python requirements installed jointly: core, Commons node, LiteLLM, integrations, desktop IDE tools, semantic. CPU PyTorch installed. pip check passes. PostgreSQL 17, nginx, Electron system libraries, Xvfb and Go tooling installed. GitHub remains unconfigured without GITHUB_TOKEN; no cloud-provider requests were verified. Optional Rust/C++/LLDB/Delve and externally configured remote debugging targets remain unverified.

BEAST up reports ready for gateway, proxy, MCP gateway, MCP HTTP, LiteLLM, Ollama and nginx. Final HTTP receipts are in runtime-probes.json. Gateway 8101; MCP HTTP 8765; LiteLLM 4000; nginx 8080; Commons gateway 8601. Local qwen2.5-coder:1.5b and qwen2.5:0.5b were downloaded. Direct Ollama and governed /proxy/ollama/v1/chat/completions inference returned BEAST_OK. Commons enterprise admission still reports configuration_required: production signature/appraisal/attestation verification is not configured.

## Desktop verification and builds

- npm run smoke: PASS (24 static checks, renderer release validation, 39 runtime contract checks).
- npm run check:visual-contract: PASS, 31 routes.
- npm run smoke:targets: 30 passed, 3 skipped, with project venv on PATH.
- npm run smoke:parity with live DAP and Jupyter enabled: 92/93 passed. Remaining failure: middle-workbench panel resizing is explicitly disabled in source. LSP, debugpy DAP/restart, persistent Jupyter kernel, Git and extension sandbox checks passed. Optional external/absent tools were skipped.
- Selected actual Electron visual audit routes: PASS, no renderer console errors. The audit uses fixture IPC data; it does not prove live route functionality for every page. Preserved artifacts are under generated/desktop-ide/visual-audit.
- Actual desktop main process launch against the running backend: PASS, renderer loaded, desktop bridge loaded, no console errors, clean process exit. See electron-live.json. Run under virtual X display with --no-sandbox for this WSL validation environment; native interactive desktop use remains untested.
- npm run package:dir and final npm run package:linux: PASS. Packages: desktop-ide/dist/BEAST Desktop IDE-0.1.2.AppImage and desktop-ide/dist/beast-desktop-ide_0.1.2_amd64.deb. There is no npm build script; these are the repository packaging commands.
- npm ci reported 22 dependency audit findings (10 moderate, 12 high); dependency upgrades were not applied automatically.

## Repository changes

Fixed portable Python selection in renderer/VERIFY_BEAST_IDE_RC4.sh, included the existing layout-authority stylesheet in renderer/tools/validate_release.py, allowed current versioned shell storage in scripts/verify-ide-parity-foundation.js, and registered real debug IPC contracts in the visual-audit harness. pytest.ini uses importlib mode to resolve duplicate test-module basenames. Generated tracked receipts/screenshots were preserved here and restored to their prior committed contents.

Existing user edits in app/kernel/agents/verification_repair_loop.py, app/kernel/sensorium/journal.py, and tests/test_socket_guardian_daemon.py were preserved. The backend failures were measured against the current working tree including those edits; their origin has not been assigned.

## Remaining work

Triage the 86 backend failures, including planner/verification flows, compatibility gateway routes, MCP contracts, compute/production trust and port-lease lifecycle. Complete real production trust configuration and GitHub credentials. Decide how to implement supported panel resizing without restoring the disabled layout-breaking control injection. Address npm dependency audit findings with compatibility verification. A build and successful local inference do not establish production readiness.

## Enterprise wiring follow-up

Configured local-lab Commons artifact trust, pinned the existing ARDA validation public key with a durable local copy of its matching appraisal signing key, and provisioned dedicated artifact and witness keys under .beast/remote-commons-lab/trust-commons (private files mode 0600). app/main.py loads enterprise-config.json when environment settings are absent; explicit environment settings take precedence. Job Choir witness signing is now wired to an explicit Ed25519 authority. Both gateways were restarted and report admission.ready=true, all three enterprise verifiers configured, signed_witnesses=true and submission_verifier_live=true.

16 targeted tests passed. Active-key wiring checks validated correctly signed Space and job advertisements, rejected tampered/unsigned submissions, verified witness signatures and rejected incomplete TPM evidence. Receipt: enterprise-wiring.json. These were configuration test inputs, not real hardware appraisals. No job was executed or Space launched. Remote lattice-trusted storage nodes do not automatically become CPU execution nodes. Real job advertisements and Space manifests still need valid, fresh, subject-bound authority evidence. Space Forge currently uses the in-process port broker. This remains a local lab configuration, not production hardware assurance.

## Hardware-backed admission proof attempt

The requested independent ARDA hardware chain is NOT proven. Debian exposes neither /dev/tpm0 nor /dev/tpmrm0, has no tpm2_quote tool, and the running ARDA service exposes authorization endpoints only. Windows Get-Tpm requires administrator privileges; no Windows quote was obtained. Historical hardware packets were not reused for fresh challenges.

Fresh live challenges were issued for A/B/C. Honest hardware-unavailable evidence was refused with HTTP 403 for each. Isolated adversarial execution with a fresh temporary key/ledger showed TpmNodeAppraisalIssuer accepting caller-supplied eligibility/reconciliation/verifier-fact flags with no quote, EK certificate, AK activation proof, or event log. Its signed advertisement then passed SignedNodeAttestationVerifier and Job Choir selection. Replay was refused. No live node received a synthetic successful appraisal; no jobs ran.

The isolated acceptance demonstrates an issuer input trust-boundary gap, not an independently verified hardware identity. app/main.py forwards request evidence directly to the issuer; the issuer treats verifier-produced results as trusted without authenticating their provenance. Required next work is an independently authenticated verifier result over cryptographically checked raw evidence and exact challenge/subject, with restricted issuer submission and adversarial rejection tests. READY remains configuration readiness only. Receipt: attestation-proof.json. Reproducer: prove-enterprise-attestation.py.

## Recovered independent witness reference

The rescue ref github/rescue/pre-purge-2026-10-03 retains the DIO HF witness deployment and verification code removed from the current tree. Space Byron230686/dio-phase2-semantic-witness exists; Hub API currently reports PAUSED at commit 544a229085182448daa74c099b296d28a851fb9e; live /health returns 503. It independently signs software witness/proposal evidence, explicitly remote_signed_software_witness_only, not hardware/execution/production authority. Read-only reference copies and provenance are under recovered-witness-reference. No deployment, restoration into active source, or Space restart was performed.

Historical TPM records document a Nuvoton physical TPM and successful July Linux evidence collection. The earlier Debian device-access finding must not be read as evidence that the laptop has no TPM. Current Windows TPM access is denied to this process even outside the filesystem sandbox; fresh host evidence remains uncollected. Metatron/.github/workflows/arda-windows-tpm-secureboot.yml is a Windows platform readiness probe on GitHub-hosted windows-latest, not a fresh attestation of this laptop.

## Resumed HF witness and Windows TPM preflight

The resumed HF service returns HTTP 200 for /health, /identity and /manifest. Root / returns 404 because it is an API service. The recovered verifier completed a fresh challenge/vote/autonomous packet run with verified=true against the pinned identity and build. Receipt: hf-witness-live.json. It remains signed software witness authority, not hardware appraisal.

Administrator-run Windows preflight confirms TPM 2.0 present/ready/enabled/activated, manufacturer MSFT, Secure Boot enabled, attestation capable/ready, and one public EK manufacturer certificate. The host reports Microsoft TPM; the preflight does not establish discrete physical TPM provenance. Public host artifacts are under C:/Users/buntb/Documents/BEAST-TPM-Proof.

Prepared Windows quote collector under windows-quote/collect_quote.py using Microsoft's TSS.MSR pinned to commit 52cb9f432318e8e95cdfeaf98b824ece89370744; provenance hashes are in windows-quote/upstream.json. Windows import/template serialization self-check passed. The collector requires administrator execution, obtains a fresh BEAST challenge and binds current Commons identities, creates a transient NULL-hierarchy signing key, quotes SHA256 PCRs 0,2,4,7,10,14, saves public quote/signature/PCR material, and flushes its own key. It does not enroll an AK, prove EK-to-AK binding, launch jobs or mark nodes eligible. Real TPM execution remains pending user run.

## Fresh Windows quote verification

The administrator-run quote collector completed. Debian independently validated the RSA-SHA256 quote signature, TPM attestation format, canonical challenge/Commons subject binding, exact durable server challenge, active TTL, key Name/qualified signer, SHA256 PCR selection and digest. All 13 quote checks and three tampering controls passed at verification time. Receipt: windows-quote/quote-verification.json. Source quote remains in C:/Users/buntb/Documents/BEAST-TPM-Proof/nonce-bound-quote.json.

Independent tpm2_eventlog 5.7 replay of SRTMBoot.dat exactly matches PCRs 0,2,4,7,14. PCR10 is quoted as zero and absent from the supplied log; the six-PCR policy is therefore not fully reconciled. Receipt: windows-quote/boot-replay-verification.json. Windows-specific policy/baseline must be explicit rather than silently waive PCR10.

The EK certificate identifies Microsoft Pluton. Windows default chain check returned PartialChain/RevocationStatusUnknown/OfflineRevocation. Downloaded Microsoft TrustedTpm.cab from the official published URL; Windows Authenticode verification returned Valid, signer Microsoft Corporation. Extracted it into the proof directory without installing certificates or altering trust stores. Of 2,532 parsed certificates, none supplied the exact per-device issuer CN=02210BE837ACADE766EB3FEACF82620B00, OU=DEVICE EKICA DFID0001. The manufacturer chain and revocation remain unverified. Receipt: windows-quote/ek-chain-verification.json.

This improves the proof beyond preflight, but no EK-to-AK activation was performed, and the transient key was flushed. Independent ARDA issuance over authenticated verifier results and host-to-container workload assurance also remain missing. Nodes were not admitted for hardware-backed execution.
