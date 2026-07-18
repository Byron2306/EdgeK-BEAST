# Tiny Llama Crystal Amplification Gauntlet

Generated: `2026-06-21T20:46:26.391839+00:00`
Passed: `True`
Tiny model: `llama3.2:1b`
Big model reference: `nvidia_nim_nemotron_super_120b`
Crystals: `8`
Pack hash: `sha256:f3d9761ff0a21ac8db2030941fdd0ec4af3591a718868f23ba46eb69861b73dc`
Fused crystal: `fused_crystal_65c5ecddc035039fbd55`
Crystal credit units: `61`
Seal provider: `liboqs`
Report hash: `sha256:a36b8fcf573ab90db9f98dcf9064f0463abfb99fd1a45d27c246fd4f829e672e`

## Comparison

| Lane | Model | Score | Crystal Hits |
| --- | --- | ---: | ---: |
| `tiny_raw` | `llama3.2:1b` | `0.34` | `0` |
| `tiny_openclaw_zeroclaw` | `llama3.2:1b` | `0.5` | `0` |
| `tiny_crystal_amplified` | `llama3.2:1b` | `0.94` | `8` |
| `big_model_raw` | `nvidia_nim_nemotron_super_120b` | `0.86` | `0` |
| `big_model_beast` | `nvidia_nim_nemotron_super_120b` | `0.97` | `8` |

## Boundary

A tiny model is evaluated as part of a BEAST system equipped with verified defensive crystals. This does not claim the base tiny model has frontier general intelligence.

## Live Big-Model Anchor

- Artifact: `benchmarks/results/beast_definitive_mega_test_nim_live_reuse_plane_o1_o10`
- Provider: `nvidia_nim`
- Model: `n/a`
- Controlled rows: `15`
- Full BEAST success rate: `100%`
- Compute Governor receipts: `2`
- Provider call receipts: `13`

Safety: defensive cyber hardening and analysis only; no exploit payloads or offensive automation.
