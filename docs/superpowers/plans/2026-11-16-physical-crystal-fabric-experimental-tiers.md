# Physical Crystal Fabric — Experimental Tiers (second-last batch) — Plan

Grounding: IEI v0.9 §7.12 (Table 14 "Production runtime implementation plan and claim boundaries"),
§7.12.2 Local Adapter Compiler, §7.12.3 Defragmentation Daemon, §7.12.4 zero-copy KV transport, and the
runtime contract `adapter_can_execute=false | adapter_may_only_propose=true | crystal_may_only_propose=true |
beast_verifiers_decide=true | no_compute_saving_counts_unless_verification_quality_is_preserved=true`.

Existing code built on: `app/context/economizer.py`, `app/kernel/data_processing/cascade_output_compressor.py`
(RTK + exact-line post-check), `app/kernel/registry/tool_integrations.py` (rtk/sqz/longcodezip/reporelay
backends), `app/kernel/governance/governor_spine.py` (ComputeGovernorSpine admit/execute receipts),
`app/kernel/compute/coding_crystals.py` (CodingCrystalRegistry promote/receipt evidence_root),
`app/kernel/sensorium/episode_envelope.py` (verified envelopes), `app/kernel/agents/swarm_specialist.py`
(Ollama swarm runner), `app/kernel/crystal_bus/bus.py` (D4 consolidated bus, memfd + SCM_RIGHTS + custody),
`bpf/beast_x3_redirect.bpf.c` + `scripts/x3_af_xdp_*` (July 2026 AF_XDP lab: 10000/10000 echoed, p50 117 µs),
ARDA ring-0 BPF LSM (`/usr/lib/arda/src/arda_os/backend/services/bpf/arda_physical_lsm.c`, maps pinned under
`/sys/fs/bpf/arda`, live scoped_strict generation 12 per `/run/arda/ring0-restore.json`).

Constraints: everything default-off behind new `BEAST_*` flags; no host installs, no native oqs build, no
kernel loads/attaches, no HF pushes, local-only, Commons stays verify_only; every operation is a Compute Governor
proposal with a receipt; similarity nominates, never grants; savings only count when fidelity holds.

## Flags
| Flag | Default | Effect |
|---|---|---|
| `BEAST_COMPRESSION_TIERS` | off | Economizer applies repo-map / LongCodeZip tiers to messages explicitly marked `context_tier` |
| `BEAST_ADAPTER_COMPILER` | off | Allows compiling specialist packages (plan mode always; never trains) |
| `BEAST_DEFRAG_DAEMON` | off | Enables the defrag planner; `BEAST_DEFRAG_APPLY=1` additionally allows reversible apply |
| `BEAST_ZERO_COPY_KV` | off | Enables memfd KV handoff over the D4 bus (host-local only) |
| `BEAST_XDP_FASTPATH_SIM` | off | Enables the userspace XDP admitted-flow simulator (no BPF load) |

## Task 1 — Real context compression tiers (`app/context/compression_tiers.py`)
- Detection: rtk/sqz ready only if the binary is on PATH **and** a `--version` probe identifies it; native
  stand-ins report `ready=false, real_tool=false` (never falsely ready). LongCodeZip/RepoRelay tiers are BEAST
  native implementations labelled `real_tool=false, implementation=beast_native`.
- RepoRelay-style repo map: AST symbol map (classes, functions with signatures, line numbers) ranked by import
  in-degree + focus-term relevance, packed to a token budget. Fidelity: every listed symbol resolves to that
  line in the source.
- LongCodeZip-style: function-level coarse selection by query relevance within a budget; non-selected bodies
  become signature stubs; edit targets kept byte-exact. Fidelity: output parses, kept functions byte-exact, all
  top-level signatures retained, query identifiers preserved.
- Measurement: original/compressed tokens (chars/4 estimate, labelled), savings %, fidelity pass; savings are
  reported as 0 when fidelity fails. Each tier call is a Governor `deterministic_tool` proposal executed via
  `ComputeGovernorSpine.execute` (receipted). Economizer + Quality Cascade hooks behind the flag.

## Task 2 — Local Adapter Compiler (`app/kernel/compute/local_adapter_compiler.py`)
- Inputs: a CodingCrystalRegistry crystal with `status=promoted`, a promoted receipt with `structured=true` and
  `evidence_root`; EpisodeEnvelopeStore envelopes for the family. Only envelopes that validate (digest), state
  succeeded and `verification.passed` are used; everything else is counted and excluded (never trained on).
- Output package (local dir): `manifest.json` (crystal/evidence binding, episode digests, contract flags),
  Ollama `Modelfile` specialist prompt package (FROM a real installed base, SYSTEM = crystal step program +
  verified exemplars as digests/tool sequences only), `dataset.jsonl` (verified-only), `training_plan.json`
  (PEFT/LoRA plan, `mode=plan`, rejects random-init/diagnostic bases; peft is not installed so no training).
- Governor-admitted (`local_specialist` rung material, dry_run plan). Registration (`ollama create`) is an
  operator command.

## Task 3 — Defragmentation Daemon (`app/kernel/compute/defrag_daemon.py`)
- Plan (dry-run default): exact duplicates (same body modulo source run), near-duplicates (Jaccard over step
  programs ≥ threshold → nomination only; merge requires an injected proof verifier, e.g. held-out replay of the
  survivor on the victim's variants), stale (no reuse/promotion within max age, never with recent reuse), ledger
  compaction (VACUUM only; no rows deleted; proof receipts retained).
- Apply (`BEAST_DEFRAG_APPLY=1` + Governor admit): status overlay `superseded`/`retired_stale` with prior state in a
  hash-chained defrag ledger; `undo(receipt_id)` restores exactly. Receipts for every action.

## Task 4 — Zero-copy KV transport (`app/kernel/compute/kv_transport.py`)
- KV manifest per §7.12.4 (model identity, tokenizer hash, system-prompt hash, prefix hash, engine identity,
  privacy boundary `host_local`, `reuse_allowed=false` until a restore check passes, `publishable=false`).
- Producer writes the KV segment into a sealed memfd and hands it over the D4 ConsolidatedCrystalBus (AF_UNIX
  SEQPACKET, SCM_RIGHTS, one-use lease, custody receipt) after Governor admit; consumer mmaps read-only
  (no payload copy through the socket). Publication guard refuses any manifest/descriptor in Commons/HF paths.
- Measured: handoff latency vs pipe copy for a synthetic segment. Engine-native KV export/restore is **not**
  wired (no engine API); payload is synthetic — claim boundary stated.

## Task 5 — XDP admitted-flow fast path (plan + userspace simulation)
- Reuse, not parallel policy: the fast path consults ARDA's pinned maps (`lockdown_map`, `policy_state_map`,
  `active_generation_map`) plus one BEAST cache map `admitted_flows` whose entries are written only from a
  Guardian lease + Governor admit receipt and carry the ARDA generation/hash-prefix they were admitted under.
  Any ARDA change (lockdown, redline triggered, generation bump) instantly invalidates the fast path → XDP_PASS
  (normal stack). The fast path never drops; it only redirects admitted flows to the existing x3 XSK path.
- Deliverables: `bpf/beast_x6_admitted_fastpath.bpf.c` (compiled to `bpf/build/*.o` with clang only, never
  loaded), `app/kernel/networking/xdp_fastpath_sim.py` (identical decision function over map snapshots, ARDA
  snapshot read-only from `/run/arda/ring0-restore.json`), flow writer from Guardian/Governor decisions,
  measured simulated decision throughput, and operator commands (bpftool inspect, veth lab, load/attach, x3 echo).

## Exit
Targeted tests per task, a final targeted regression, ledger lines per task, ruff on new files, `git diff --check`.

## Follow-up (2026-11-16 04:35 SAST, Byron feedback)
- **Tools installed user-local**: rtk 1.2.0 (release install.sh, checksum-verified) and sqz 2.2.0 (`cargo install --locked sqz-cli`, ojuschugh1/sqz) in `~/.cargo/bin` (not on PATH by default). BEAST calls rtk with `RTK_TELEMETRY_DISABLED=1` (telemetry is opt-in and was never enabled) and sqz with a private `SQZ_DB_PATH` under /tmp and dedup off. sqz `--cmd` follows the cascade kind (test→pytest, lint→ruff, log→log).
- **Exact-line contract sees through ANSI colour**: coloured tool output used to hide every `file:line` diagnostic from the exact-line check, which made a 98.6% ruff "saving" look safe. Lines are now matched on their ANSI-stripped form.
- **Adapter compiler stays in plan mode.** One crystal exists today. The gauntlets will produce more, and LoRA training waits until a family has enough promoted, non-superseded crystals.
- **KV capsules ↔ crystal reuse proofs (design only)**: a memfd KV capsule is sealed (F_SEAL_WRITE|GROW|SHRINK) and hash-addressed, so its digest can act as the *state witness* for a crystal replay on an unknown workload. Flow:
  1. A crystal replay on a new workload records the capsule digest of the prefix KV it consumed.
  2. The verifier re-derives that prefix on a fresh engine and compares the digest. Only `reuse_allowed=true` after the restore check passes (IEI Table 14).
  3. The crystal's reuse receipt then cites `{crystal_id, capsule_digest, restore_check_receipt}`.

  The result is a reuse proof that does not depend on similarity: the bytes the engine actually used are the bytes that were verified. Still host-local; no capsule leaves the host; Commons stays verify_only.
- **Memory hull defrag** (`DefragDaemon(hull=MemoryHull)`, behind the same BEAST_DEFRAG_DAEMON / BEAST_DEFRAG_APPLY flags): `plan_hull` (dry run) verifies sidecars, finds exact-duplicate residue (content minus created_at/residue_id/markdown hash), and reports index drift and orphan markdown. `apply_hull` (Governor-admitted) moves duplicates into `<vault>/.defrag/<ts>-<id>/`, writing sha256 and original paths into the hash-chained ledger, then rebuilds the signed index. `undo` checks the hashes and moves the files back. Failed seals are reported for operator review/reseal and never moved, because the vault is operator-editable.
- **Lattice `superseded` state**: `CrystalLattice.supersede(node, by=, reason=)` and `restore()` are witnessed in the lattice ledger and the chain. They are same-family only, refused while an admitted composite contains the node, and apply no demotion and no clawback.
- **XDP X6 lab bundle**: `.beast/generated/xdp-x6/run-x6-lab.sh` uses absolute paths and works from any directory. Subcommands: precheck, up, load, attach, admit, traffic kernel|afxdp, stats (counters by name), detach, down, and sequence. July X3 baseline: p50 117.065 µs (AF_XDP copy echo, 512 B, 1000 pps, 10 s, generic XDP).
