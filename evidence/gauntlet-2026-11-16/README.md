# Gauntlet 2026-11-16 — crystallization + sealed-memfd replay

Run: `scripts/gauntlet_memfd_replay.py --approve-by Byron` (run 4, 2026-11-16 SAST). All BEAST_* flags set in-process only.
State lives in `.beast/gauntlets/2026-11-16/` (isolated registry; main crystal registry untouched). No commits.

## Task family `fix-failing-config-constant`
Synthetic-but-realistic Python repos where a unittest contract fails on `AssertionError: X != Y` against a module constant.
Deterministic verifier: `/usr/bin/python3 -m unittest <contract>` (returncode 0, tests_run 2) + target sha256.
- cold: billing `INVOICE_RETRY_LIMIT 3→5`
- held-out (promotion): scheduler MAX_WORKERS, auth TOKEN_TTL_MINUTES, cache CACHE_MAX_ENTRIES
- warm hits: ingest BATCH_SIZE, notify MAX_EMAILS_PER_HOUR
- near-miss: pricing `vat()` logic 0.14→0.15 (sim 0.88); far: parser ZeroDivisionError (sim 0.38)

## Models actually called (model_calls.json)
| # | tier | model | tokens | latency | result |
|---|---|---|---|---|---|
| 1 | provider (cold) | NIM nvidia/nemotron-3.5-lightning-30b-a3b | 801 (341p/460c, 428 reasoning) | 3.5 s | edit accepted |
| 2 | specialist (near-miss) | Ollama qwen3:4b | 1339 | 125.8 s | prose, no JSON → verifier refused |
| 3 | provider fallback (near-miss) | NIM nemotron | 1169 | 6.1 s | verified pass |
| 4 | provider (far) | NIM nemotron | 2393 (2048 reasoning, finish=length) | 13.5 s | no edit → verifier refused, task failed |

## Cold vs warm
| episode | similarity | route | model calls | tokens | wall | passed |
|---|---|---|---|---|---|---|
| cold-billing | 0 | provider_fallback | 1 | 801 | 3799 ms | yes |
| warm-ingest | 1.0 | crystal_replay | 0 | 0 | 188 ms | yes |
| warm-notify | 1.0 | crystal_replay | 0 | 0 | 194 ms | yes |
| near-miss-pricing | 0.88 | local_specialist_adapter | 2 | 2508 | 132.2 s | yes (via NIM) |
| far-parser | 0.38 | provider_fallback | 1 | 2393 | 13.6 s | no |
Similarity only nominates; every execution needed a Governor admit and a passing verifier.

## Crystal + promotion (crystal_promotion.json)
`coding-crystal:4720e3bdaa55dd552f88cdad`, digest sha256:4720e3bd…25e3, status promoted, approved_by Byron,
held-out 3/3, evidence_root sha256:eed87888…31a3, record_digest sha256:8c7c61aa…3e3d.

## memfd receipt (memfd_receipt.json, receipt_digest sha256:e7e318f7…4b6d)
- capsule 3699 B (header 444 + payload 3255); payload sha256:9409f38e…3e08 matched in child; manifest sha256:59521100…c68b
- seals 15 = SEAL|SHRINK|GROW|WRITE read back in parent and child; write-after-seal → EPERM
- copies: 2 write() into memfd (3699 B), 1 SCM_RIGHTS fd pass (202 socket B, 0 payload B), 1 read-only mmap, 0 read() syscalls, 3255 B userland JSON parse; pipe baseline 7398 B → 3699 transport bytes saved
- replay child pid in `unshare -rn` empty netns: lo 0 B, inet sockets/connects/DNS/http sends all 0; parent model calls during replay 0
- child wall 138.5 ms (hydrate 0.43, replay 94.5); parent hydrate+handoff+replay 444.3 ms vs cold 3799 ms → 27.4×, 3660 ms saved
- postcondition: child + parent independent check passed (rc 0, 2 tests, target sha256:f538f060…3162)
- avoided 1 model call / 801 tokens; PGEC eq.6 V_K = 1.938489 − (0.501385 + 0 + 0.05) = 1.387103; shadow credit 1.387103 non-transferable, non-redeemable
- Governor admit gov_eb83d71944248479974fac5e (one-use, echoed by child); chain 7 receipts valid

## Negative controls (negative_controls.json)
- tampered payload → refused `capsule payload digest mismatch` (no replay)
- unsealed memfd → refused `capsule is not sealed (seals=[])`
- wrong postcondition → replay ran, refused `postcondition_failed:target_sha256_after`, credit 0

## Real vs simulated
Real: NIM + Ollama calls/token counts, unittest verifiers, memfd/seals/fd passing/mmap, unshare netns, Governor + hash-chained receipts, registry promotion.
Not real/limited: applicability matcher is a local deterministic feature matcher (not embeddings); repos are synthetic; capsule transport is a direct socketpair, not the D4 bus; L4/Chronicle not wired; pipe end-to-end ms is not comparable to memfd end-to-end (latter includes unshare + replay + 2 unittest runs) — compare bytes.
Earlier aborted runs (not in this evidence): run 1 two NIM calls returned empty content (400-token budget consumed by reasoning); debug probes (4 NIM calls); run 2 one NIM cold call then a make_repo bug; run 3 completed (4 calls), superseded by run 4 after raising specialist max_tokens 300→1024 and fixing the negative-control label.

## Reproduce
```
cd /data/byron/dio-wsl-restored-20261015/home/byron/GitHub/EdgeK-BEAST
.venv/bin/python scripts/gauntlet_memfd_replay.py --approve-by Byron   # live: ~4 model calls, ~2.5 min
env HOME=$PWD/.beast/tmp-home .venv/bin/python -m pytest -p no:cacheprovider -o addopts="" -q tests/test_crystal_memfd_capsule.py tests/test_gauntlet_memfd_replay.py
```
