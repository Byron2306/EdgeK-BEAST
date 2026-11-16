# Step 4 — Close bypasses (closure 2026-11-16)

## A. Direct model call sites → governed egress shims
- `app/kernel/compute/governed_egress.py` (new):
  - Shims: `post(client, caller, url, **kw)`, `apost(...)`, `astream(client, caller, method, url, **kw)`, `urlopen(caller, request, timeout=)`.
  - **Flags off (default): the exact original call.** Same client, same args, no added headers, no receipts.
  - With `BEAST_GOVERNED_INTERCEPTION=1`:
    - each call is admitted by the Compute Governor as `Proposal(kind="cloud", provider="egress:<host>", tool_id="egress:<caller>")`;
    - the request carries `X-BEAST-Admit: <receipt prefix>` and `X-BEAST-Caller`;
    - a hash-chained `model_egress` receipt (host, path, status, latency, token usage; no prompt, no keys) goes to
      `.beast/governed-egress/receipts.jsonl` (`BEAST_GOVERNED_EGRESS_RECEIPTS` overrides the path).
  - A refusal only blocks when `BEAST_GOVERNED_EGRESS_ENFORCE=1`; otherwise it is receipted and the call proceeds.
  - `BEAST_ARDA_EGRESS_ADMIT=1` queues the admit for the X7 token writer (below).
  - I chose these instead of routing each site through GovernedModelClient.complete. Those call sites have heterogeneous payloads and
    streaming semantics, and rewriting them into schema-forced completions would not preserve behaviour. The shims put every egress
    under the same governor, receipts and kernel admit-token path without changing a single response.
- **Converted 53 call lines in 33 files**:
  - 20 app modules: inference_engine_fabric, adapters/providers (stream+post), nim/ollama planners, swarm_specialist, nim_live_probe,
    nim_picker, ollama_kv_manager, ollama_scout, generation_provider_adapters, milestone11_*, scientific_uplift, provider_tournament,
    final_boss/hard_coding gauntlets, crystallized_compute_proof, adapter_comparison, coder_client's direct-Ollama fallback,
    deployment keepalive ping;
  - 13 scripts: gauntlet_large, gauntlet_memfd_replay, proof/*, benchmarks, milestones.
  - Exact lines: `converted-lines.json`; full diff: `egress-shim-conversion.diff`. The deployment.py hunk also contains step 2's nginx changes.
  - Every file is backed up as `*.before-closure-20261116`.
  - When a script is run directly, its import falls back to inserting the repo root on sys.path.
- **Deliberately not converted** (already governed, or not model egress):
  - the /proxy and adapter route handlers (`@router.post`; that is the gateway itself);
  - execute.py (canonical governed execution);
  - governed_client / gpu_scheduler (the governor's own lanes);
  - cli/api.py and coder_client's gateway calls (they go to BEAST, which governs them);
  - main.py control-plane routes;
  - constrained_output, provider_adapters, full_spectrum, reason, provider_registry and sensorium (only endpoint strings or docs, no live call).
  - So the "43" from this morning's inventory resolves to 53 concrete call lines once multi-call files are counted line by line.
    No remaining direct egress was found outside the gateway/governed modules.
- Tests:
  - `tests/test_governed_egress.py` **6/6**: flags-off exact passthrough; flags-on headers + receipts with no prompt or key leakage;
    async post and stream passthrough; refusal only under ENFORCE; ARDA admit queue; no raw `.post(` left in key modules.
  - `tests/test_x7_admit_writer.py` **2/2**.
  - Deployment-adjacent tests: 35/35.
  - Adjacent suites (44 files touching converted modules): the 16 failures are **not caused by the shims**:
    - 4 in tests/proof/test_ollama_planner_provider.py fail identically on the original files (verified by swapping the originals back in;
      restored and checked afterwards);
    - test_modularized_route_families (route ownership app.main vs app.routes.commons), test_coder_tli (command list) and
      mammoth (integration_count 7 < 9) are drift in other modules;
    - 8 IDE-agent-session tests hit the 120 s pytest timeout both with and without the conversion (the baseline run hung at the same test).

## B. ARDA / X7 admit-token enforcement (written, compiled; NOT loaded)
- `bpf/beast_x7_model_egress_lsm.bpf.c` → `bpf/build/beast_x7_model_egress_lsm.bpf.o` (clang only; nothing loaded or attached; /sys/fs/bpf/arda untouched).
  - Hook: `lsm/socket_connect`.
  - **Reuses ARDA's maps read-only** with byte-identical definitions, bound at load time to ARDA's pins:
    `active_generation_map` (cgroup → generation; this IS the measured set), `policy_state_map`, `lockdown_map`.
  - Decision:
    - not in ARDA's measured set → allow;
    - destination not in `beast_model_egress_dst` → allow;
    - ARDA lockdown → deny;
    - no `beast_admit_tokens[{tgid, dst}]` → deny;
    - token expired / ARDA generation changed / ARDA policy prefix changed → deny.
  - "Deny" means -EPERM only when `beast_x7_mode=1`; the default 0 is audit (count and allow). Per-reason counters live in `beast_x7_stats`.
- `scripts/beast_x7_admit_writer.py`:
  - reads Governor admits from the egress admit queue;
  - resolves model hosts and fills `model_egress_dst` + `admit_tokens`, with the ARDA generation of the caller's cgroup and the ARDA
    policy prefix read from ARDA's pinned maps; tokens have a 30 s TTL;
  - dry run (prints bpftool commands) by default; `--apply` refuses without root.
- ARDA policy reuse:
  - the consumer is added to ARDA's measured set through ARDA's own flow (`arda_build_measured_manifest.py` →
    `stage_measured_manifest` → `activate_staged_measured_manifest` → `project_staged_measured_manifest`, the same as arda-enroll step 30);
  - consumer executables are added through ARDA's own `arda_harmony_addendum.json` (proposed category in
    `deploy/closure-2026-11-16/arda-addendum-beast-consumer.json`).
- **Important caveat for Byron:**
  - Under `ARDA_MODE_SCOPED_STRICT`, ARDA's existing `bprm_check_security` hook enforces exec measurement for every cgroup in
    `active_generation_map`. Adding the consumer cgroup therefore also means **only measured executables can run in it**.
  - Only the `critical-host` profile exists, and it does not list node/codex/claude/code/tmux. Merge the addendum first or agents will
    fail to exec.
  - Also: ARDA keys on the exact leaf cgroup, so agents must run inside the single persistent `beast-consumer.service` cgroup
    (tmux server), not in per-launch scopes.
  - Known limitation: destinations are IP-based. CDN IP rotation needs the writer to re-resolve (it does, per admit). Direct hard-coded
    IPs not in the dst map are not covered.

## Commands Byron must run
`deploy/closure-2026-11-16/x7-operator-commands.sh`. It has an `exit 0` guard; run it block by block:
1. install/enable `beast-consumer.service` and read its cgroup id;
2. merge the addendum into ARDA's harmony addendum (back it up first);
3. as root, move a shell into the consumer cgroup and run ARDA's builder plus stage/activate/project; verify with
   `bpftool map lookup pinned /sys/fs/bpf/arda/active_generation_map`;
4. `bpftool prog load … type lsm map name arda_* pinned /sys/fs/bpf/arda/* pinmaps /sys/fs/bpf/beast/x7 autoattach` (audit mode);
5. start the admit writer `--follow --apply`, and launch agents with `BEAST_GOVERNED_INTERCEPTION=1 BEAST_ARDA_EGRESS_ADMIT=1`;
6. after the audit counters look right, set `beast_x7_mode=1`.
Rollback is in the script. The load line was written against bpftool v7.5.0 (installed) but has **not been executed**; it is untested on this kernel.

## Spend
$0 (no model calls in this step).
