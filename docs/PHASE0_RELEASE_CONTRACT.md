# BEAST Phase 0 Release Contract Foundation

**Started:** 2026-07-18  
**Scope:** Truth freeze, generated identity, parity contract, support matrices, verifier repair, and canonical import protection.

## Implemented in this slice

1. `contracts/beast-parity-contract.v1.yaml` defines the measurable BEAST parity claim.
2. Versioned execution-target, extension, language, debugger, testing, and agent-tool matrices define published support boundaries.
3. `release/RELEASE_VERSION.json` is the single declared version source; `scripts/phase0/generate_build_identity.py` expands it into identities for backend, Electron, renderer, evidence, and packaging.
4. `app/kernel/build_identity.py` exposes the same identity to the gateway without making version metadata a policy authority.
5. `scripts/phase0/check_canonical_imports.py` blocks new production imports from deprecated compatibility facades.
6. `scripts/phase0/generate_release_contract.py` creates `build/PHASE0_STATUS.json` with current checks and explicit not-run states.
7. Enterprise timeout validation now checks a bounded behavioural policy instead of one historical source literal.
8. The AI lifecycle fixture accepts the current semantic mutating mode rather than fossilising one old mode label.
9. The detailed parity guide no longer carries a future date or manually maintained assertion totals.
10. The environment-independent parity foundation now reports 89/89, including live disposable Git, extension-host, and AI proposal lifecycles while LSP/DAP/kernel probes are explicitly marked skipped.

## Commands

```bash
python3 scripts/phase0/generate_build_identity.py
python3 scripts/phase0/verify_phase0.py
cd desktop-ide && npm run smoke:parity:foundation
cd desktop-ide && npm run smoke:targets
cd ..
python3 scripts/phase0/generate_release_contract.py
```

Run the provisioned LSP/DAP/kernel matrix only on a machine with those runtimes installed:

```bash
cd desktop-ide
BEAST_VERIFY_LSP=1 BEAST_VERIFY_DAP=1 BEAST_VERIFY_KERNEL=1 npm run smoke:parity
```

## Current boundary

This is the beginning of Phase 0, not its final closure. Repository hygiene, CI publication of the generated contract, release-bundle signing, evidence retention policy, and full environment matrices remain subsequent Phase 0 work.
