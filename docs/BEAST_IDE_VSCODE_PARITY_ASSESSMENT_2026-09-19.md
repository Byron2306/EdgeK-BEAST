# BEAST IDE ↔ VS Code Parity Assessment

Date: 2026-09-19
Status: repository assessment; runtime parity gauntlet still required

## Executive assessment

BEAST Desktop IDE is no longer a toy editor shell. The repository contains substantial VS Code-compatible infrastructure: extension package discovery/activation, command registration, tree/webview/status APIs, workspace state/secrets, language services, tasks, debugging/DAP, test explorer, notebooks, remote extension runtime and governed execution targets.

However, **BEAST Desktop IDE is not yet full VS Code parity**. The existing `verify-scoped-100-parity.js` name means 100% of a deliberately scoped contract, not 100% of VS Code. It currently aggregates twelve selected runtime contracts. That is useful proof, but it must not be represented as universal VS Code compatibility.

### Current parity bands

| Area | Repository assessment | Basis |
|---|---|---|
| Core editing/workspace shell | Strong | Monaco/workspace hosts, file/index hosts and parity verifiers exist |
| BEAST coding-agent governance | Strong and BEAST-specific | SourcePlan, Worktree Forge, Evidence Bus, agent sessions, policy/evidence surfaces |
| VS Code extension package compatibility | Strong but bounded | real-extension-host verifier exercises package.json discovery, activation, commands, trees, status, language and webviews |
| Language/navigation | Strong contract coverage | dedicated language/navigation verifier |
| Tasks/tests/debug | Strong contract coverage | IDE services, DAP and Test Explorer verifiers |
| Notebook runtime | Strong contract coverage | notebook MIME/trust/runtime/widget-state verifiers |
| Remote execution/extensions | Strong contract coverage | governed target and remote extension runtime verifiers |
| Marketplace/ecosystem breadth | Partial | compatibility host is not Microsoft's complete extension host/runtime |
| Complete VS Code API surface | Partial | many APIs are shimmed/emulated; no proof of exhaustive API compatibility |
| UI/UX parity | Partial by design | BEAST has its own operator cockpit and governance surfaces rather than cloning VS Code chrome |
| Real-world extension corpus compatibility | Unproven at broad scale | synthetic/selected workload contracts exist; broad corpus evidence is not established here |

## Important distinction

There are two different surfaces:

1. `vscode-extension/` is the BEAST extension intended to run **inside real VS Code/Cursor**.
2. `desktop-ide/` is BEAST's own Electron/Monaco IDE with a VS Code compatibility host.

Parity work should therefore use real VS Code as the reference oracle while preserving BEAST-native governance. The goal is API/workflow compatibility where useful, not visual cloning and not weakening BEAST's authority boundaries.

## Gap to close

The next parity programme should measure capabilities rather than one aggregate marketing number:

- editor/workspace/files/search
- extension lifecycle/API
- commands/views/webviews/status
- configuration/state/secrets
- language/navigation
- tasks
- debugging/DAP
- testing
- notebooks
- terminals
- SCM/Git
- remote targets
- coding-agent workflow
- extension corpus compatibility

Each capability must be labelled `verified`, `partial`, `missing`, or `not-applicable`, with a concrete verifier and artifact. A 100% claim is allowed only inside the named scope that the verifier actually exercises.

## BEAST advantage that should remain non-parity

VS Code parity must not erase BEAST's differentiated execution model. SourcePlan custody, isolated Worktree Forge mutation, current mutation epochs, fresh verifier receipts, Evidence Bus, Mission Crystal Lattice, Memory Hull and governed promotion are BEAST capabilities above the VS Code baseline, not incompatibilities to remove.
