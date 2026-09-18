# BEAST Coding Agent Phase 4 — Termux / Android Acceptance

**Status:** PASS  
**Platform:** native Android / Termux  
**Android runtime branch:** `agent/beast-phase4-termux-runtime`  
**Android tested Git head:** `2ace317ebe5173254c7a64a2fa601fb5a9b6b15f`  
**Android:** 16  
**Architecture:** `aarch64`  
**Python:** 3.14.6  
**Ollama:** `0.33.1-termux`  
**Model:** `qwen2.5:0.5b`

## Result

The native Android Phase 4 gauntlet completed successfully and emitted:

```text
verified: true
backend_ready: true
BEAST Phase 4 Termux / Android Acceptance
Status: PASS
```

This was not a hosted emulation. The proof ran inside native Termux against
the local BEAST backend and the locally running Ollama/Qwen runtime.

## Verified gates

| Gate | State | Tests | Evidence digest |
|---|---|---:|---|
| `canonical_phase4` | PASS | 112 | `sha256:5ea9cf46e773037669b8f7461e1621d98910e8ef56dd9e8fb256b4db1bdb5460` |
| `live_durable_authority` | PASS | 6 | `sha256:e55a1cd75f2b75188a6ed4d34876f145fe1189e774d6819e0c24c53336e3ae0f` |
| `permission_modes` | PASS | 6 | `sha256:342e9e81574b5f99b32fd885740a43c45d4b6b521dc4390465771829b48e76f1` |
| `sensitive_external_controls` | PASS | 3 | `sha256:8aebdc22f4d509cda55e90e6a0c5401137065f204d4d5e1a973ded183ee7b938` |
| `phase3_regression` | PASS | 31 | `sha256:b5a8c8097dc35a16bb18810c4f903043a8ba1fcee8d3fb850a4a909ac655ffd5` |
| `desktop_renderer_ingress` | PASS | 1 | `sha256:a63b2c2932bf4fb34c8d520cb16fb5d9840319b01f8fad02f2b455ca19fac24b` |
| `live_local_ollama` | PASS | 1 | `sha256:d29c0544b624d99bd097fe7633a1b88993db84aeebe8dce861911a14cd77adea` |
| `planner_endurance` | PASS | 5 | `sha256:5733e11bbf06a7e614c6cd0a8f64059feb5944cea91e63f32f4d0f59c2c92a7f` |

## Native backend evidence

The live Termux gateway returned HTTP 200 for:

```text
/edgek/ide/system-snapshot
```

and reported:

- platform `Android 16`;
- architecture `aarch64`;
- CPython 3.14.6;
- local Ollama process active;
- BEAST gateway and MCP HTTP processes active;
- secret-like environment variables redacted;
- desktop compatibility contract available through the native gateway.

The Android acceptance receipt was written under:

```text
benchmarks/results/beast_phase4_termux_android/20260918T041512Z/
```

## Phase 4 meaning

The Android proof covers:

- durable approval contracts;
- restart-aware approval recovery;
- request-bound, one-use capability authority;
- reject/replan/revocation behavior;
- Review, Guided, Bounded Autonomy, Observe Only and Locked mode semantics;
- sensitive-data redaction;
- external-content admission controls;
- inherited Phase 3 least-authority, budget, stagnation and verification behavior;
- renderer-to-backend ingress;
- local Ollama/Qwen planner exchange;
- planner endurance.

## Boundary

This receipt proves the BEAST Phase 4 coding-agent backend and durable
authority controls on native Android/Termux.

It does **not** claim that stock Linux Electron runs natively under Android
Bionic. The desktop shell remains a separate Debian-proot + Termux:X11 UI
validation path.

It also does not claim Vulkan/GPU inference. The accepted model path is the
verified local Ollama runtime.

SourcePlan promotion remains outside model authority.
