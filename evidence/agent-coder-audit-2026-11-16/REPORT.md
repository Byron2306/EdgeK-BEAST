# Agent Coder subsystem audit — 16 November 2026 (Africa/Johannesburg)

Isolated test gateway `:8199`. Live `:8101` was not restarted and was not used for this audit run.

This report is the source of record for:

1. The post-heal Agent Coder max-output-tokens failure and the model-aware `max_tokens` + auto-continue fix.
2. One real Agent Coder run on `:8199` (`implementer-c17b0faf-6287242d2187`).
3. A complete inventory of every system, delivery and integration defined in **all 16** `docs/superpowers` plans and specs, plus the additional repo systems Byron named that those docs do not cover.

Nothing listed in those 16 docs is omitted. Rows use three columns:

- **Backend works** — module present and/or unit/E2E evidence (not “it exists so it must be live”).
- **IDE wiring** — which Desktop IDE screen or flow actually references it (or CLI/TLI only).
- **Fires in a real Agent Coder run** — yes/no against the `:8199` run below, with event or probe evidence. “No” is an honest answer, not a promise.

Inventory source: every `*.md` under `docs/superpowers` (14 plans + 2 specs). Extracted headings and module paths are also saved as `superpowers-inventory.json`.

---

## 1. Max-output-tokens incident and fix

### What Byron saw after heal

Context-budget precheck passed. Agent Coder run `implementer-0a9e4ce2-32c3e28615f7` on live `:8101` (Fireworks `accounts/fireworks/models/kimi-k3`, packet `pkt_597c66ef016620da`, raid `raid_1c70e66b89dbf1030213`) failed with:

> provider stream incomplete: provider reached max output tokens before a natural stop

Evidence from `.beast/agent_runs/agent_runs.sqlite3` (live state, read-only): provider fireworks, client `max_tokens=16000`, state=failed, `chars=0`, 41 events, ~45s Fireworks egress HTTP 200, **no continuation events**. Hidden reasoning can consume the output budget while visible text stays empty.

### Root cause (not context budget)

Three independent clamps, all still true after the context-budget commit `f3bf852b`:

1. `pair_programmer_limits` hard-capped Fireworks / generic providers at **3072** output tokens (NIM 4096, compact Ollama 1024). The Agent Coder client could request 16000, but the stream path still used the pair-programmer cap.
2. `agent_run_stream` set `max_continuations: 0` for non-chat Agent Coder runs, so `finish_reason=length` never auto-continued.
3. Continuation also required non-empty **visible** text. Kimi K3 can spend the entire budget on hidden `reasoning_content` / `reasoning` / `thinking` (`chars=0`) and still never continue.

Provider-lane `max_tokens: 2048` in `provider_lanes.json` is a cost default and must not be used as the model output cap (same rule as the input-budget fix).

### Fix (this change)

- New `resolve_output_budget` / `output_token_budget` in `app/context/budget.py`. Coding default **16384**, hard cap **32768**. Family caps: kimi / deepseek / glm / gpt-oss **32768**; llama-3.3 / qwen **16384**. Compact local still **1024**. Headroom = window minus known input. Never use the provider-lane 2048 as the cap.
- `pair_programmer_limits` uses that helper. Large-window models also get up to 50000 context chars / 5 files. Compact Ollama stays 1024 / 2400 chars / 3 files.
- `provider_stream_max_tokens` uses `output_token_budget` (dropped the 2000 default and 16000 hard cap). `provider_stream_continuations` default **3**.
- Stream loop tracks `reasoning_chars` and **continues on `finish_reason=length` even if visible text is empty**. Hidden reasoning is extracted and never treated as the visible answer.
- `continuation_user_message`: empty-visible Action IR asks for JSON only; partial output continues from the next character.
- Agent Coder stream options: `max_continuations` is **3** for agent runs, **1** for chat.
- Prompt / repair guidance prefers line-anchored minimal-span `old`/`new` plus `anchor_line` / `anchor_ref`. Whole-file `new` only when the change is essentially a rewrite.

Backups (gitignored): `*.before-maxtok-20261116`.

### Tests

35 passed:

```
tests/test_output_budget.py
tests/test_context_budget.py
tests/routes/test_ide_support_common.py
tests/test_budget_governance.py
tests/test_context_economizer.py
```

Key assertions: Fireworks kimi/glm/deepseek and HF gpt-oss ≥16384 and greater than the old 2048/3072 caps; compact `qwen2.5:3b` still (1024, 2400, 3); unknown `openai/coder` beats 3072 and stays ≤16384 (policy-default window can yield 8000). Continuation helpers and reasoning extract are covered.

---

## 2. Isolated Agent Coder audit run (`:8199`)

- Gateway pid `2162080`, `BEAST_STATE_ROOT=/tmp/beast-audit-8199-20261116`, workspace `/tmp/beast-audit-ws-20261116`, flags from `deploy/closure-2026-11-16/beast-gateway.env`. Family-crystal DB pointed at the live closure file (read-only reuse). Live `:8101` stayed up.
- Run id: `implementer-c17b0faf-6287242d2187`. Auto-approved capability `cap_bb3a0f0d6d73`. Model: TGI `Qwen/Qwen2.5-Coder-3B-Instruct-AWQ`. 43 events. **Spend $0.00**. Artifacts: `mission-8199.json`, `events-8199.json`, `audit_8199.py`.
- The max-tokens fix **did fire** on this run. Stream event text:

  > `provider stream: tgi model=Qwen/Qwen2.5-Coder-3B-Instruct-AWQ max_tokens=16384 continuations=3`

- The run then failed with LiteLLM HTTP 400: invalid model name for that TGI model when proxied through LiteLLM. **Not a max-tokens failure.** TGI itself is up on `:8090`. This routing bug is pre-existing and was not changed in this commit.
- Events that **did** fire before the LiteLLM 400: Code Cortex, approved workspace search and related-file read, pathfinder preflight `route_quality_live_coding`, semantic RAID `raid_d489c97de9ced63d8bda`, packet `pkt_a4fcb032a4faad75`, crystal-reuse preflight `crystal_reuse_2fb2b79fb00cbf` / `no_reusable_crystal_found`, PREC perceive / reason / economize, handoff ready, compute `budget_source=model_family` `input_budget=28672` (history 1003 tokens), then the provider-stream options line above.
- Events that **did not** fire: swarm specialist, crystal bus publication, socket guardian (the process may be listening, but this run did not call `:8131`), GPU scheduler, ML-KEM, XDP, ForgeKV write, coding-crystal promotion, RTK/SQZ compression of the prompt, memory-hull seal, Adaptive Router execution grant (proposal-only by design).

A completed generation was not required to inventory “did this subsystem execute on the Agent Coder path.” Where a subsystem only has probe evidence (health/MCP/inventory), that is labelled as a probe, not as an in-run fire.

### Probes on `:8199` (not the Agent Coder stream)

All HTTP 200 unless noted:

- `/health`, `/proxy/health` — 29 providers including fireworks, sambanova, huggingface, hyperbolic, fal, replicate, ollama, tgi, nvidia_nim.
- `/mcp/health`, `/mcp/tools/list` — **69** tools including `beast_symbol_surgeon_plan`. Live MCP `:8765` also listed 69.
- `/edgek/ide/model-inventory` — 38 models; `providers_present` fal_llm / fireworks / hf / hyperbolic / nim / ollama / replicate / sambanova / tgi; `blocked_providers` fal_llm / hyperbolic / replicate / sambanova; live tgi + ollama up.
- Auto rename via capability router → fireworks `glm-5p3-flash`.
- Crystal-reuse / lattice / chain, commons-economy, memory-security, ide/system/tooling snapshots, chronicle — API present.
- `:8131` HTTP 200 returned a payload that looked like `edgek-beast-gateway` health (pids 2128583 / 2128582). **Do not claim Agent Coder called it.**
- `lsmod` showed no `arda` / `x7` LSM loaded (compiled, not loaded — expected).

---

## 3. Spend

**$0.00** on the `:8199` audit run. No paid Fireworks / SambaNova / Hyperbolic / Replicate / fal calls were made for this audit. The live `:8101` Kimi failure earlier in the day is not part of this audit spend.

---

## 4. Audit table — every system, delivery and integration in `docs/superpowers`

Cite column is the defining plan or spec (path under `docs/`). Overlapping deliveries are listed once under their detailed plan and cross-cited to the roadmap rather than silently dropped.

Legend for column 3:

- **Yes** — observed in run `implementer-c17b0faf-6287242d2187` (or a named event from that run).
- **No (path reached earlier, this stage not entered)** — Agent Coder can reach it in principle, but this run stopped before or never entered that stage.
- **No (not on the Agent Coder path)** — backend may work; this run has no hook.
- **No (default OFF / proposal-only / compiled not loaded)** — present by design but not active.

### 4.1 BEAST Coder TLI

Defined in `superpowers/plans/2026-10-28-beast-coder-tli.md` and `superpowers/specs/2026-10-28-beast-coder-tli-design.md`.

| System / delivery / integration | Backend works | IDE wiring | Fires in a real Agent Coder run |
|---|---|---|---|
| CoderRuntimeClient + RuntimeEvent projection (`app/cli/coder_client.py`) | Yes — module + `tests/test_coder_client.py` | **CLI / Textual TLI only**, not the Desktop IDE Agent Coder panel | No (not on the Desktop IDE Agent Coder path). Desktop uses `desktop-ide/renderer/js/ai/agent-client.js` instead |
| Persistent Coder state: CoderSettings, ConversationStore, SlashCommand (`app/cli/coder_state.py`) | Yes — module + `tests/test_coder_state.py` | CLI / TLI only | No (CLI state, not the IDE run store) |
| Focused Textual UI / BeastCoderApp (`app/cli/coder.py`) | Yes — module + `tests/test_coder_tli.py` | CLI / TLI only (`bin/beast`) | No |
| Default launcher switch and rollback (`bin/beast`, `tests/test_beast_cli_script.py`) | Yes — `bin/beast` ships TLI + heal/ide subcommands | CLI. Desktop IDE is a separate Electron app | No |
| Design components AgentPlannerRuntime, AgentToolRegistry, AgentRunEngine (spec) | Yes — planner/runtime and tool registry exist under `app/kernel/agents` and `app/cli`; Agent Coder uses `app/routes/ide_routes/agent_run_stream.py` + run store | Desktop Agent Coder panel: `beast-workspace-agent-panel.js`, `agent-client.js`, `operations-console-client.js`, `approval-cards.js` | **Yes** — the `:8199` run executed the IDE AgentRun / planner path (Code Cortex, approvals, PREC, packet, RAID) until the LiteLLM 400 |

### 4.2 Physical Crystal Fabric spine (spec)

Defined in `superpowers/specs/2026-11-15-physical-crystal-fabric-spine-design.md`. Concrete deliveries are expanded in the phase plans below; these are the spec-level integrations that must appear as rows.

| System / delivery / integration | Backend works | IDE wiring | Fires in a real Agent Coder run |
|---|---|---|---|
| Fabric architecture (control plane + Commons nodes + guardian-owned listeners) | Partial — modules for topology, remote Commons, guardian exist; live fabric is optional and lab-oriented | Commons page `beast-commons-page.js` shows health/topology evidence | No (audit gateway is a local process, not a multi-node fabric join) |
| Trust and identity (signed candidates, custody, verify_only) | Yes — remote client + health + custody paths used by Commons lab tests | Commons page | No |
| Topology contract (`AF_UNIX` / `SOCK_SEQPACKET`, `SCM_RIGHTS` as specified) | Yes — `app/kernel/networking/fabric_topology.py`, `tests/test_fabric_topology.py` | Commons / scripts, not Agent Coder | No |
| Crystal authority classes (local / promoted / published / quarantined) | Yes — coding crystals + family crystals + publication/quarantine plans implemented in compute/commons | Crystal reuse map / utility / narration in the IDE; Commons page for publication | Partial: family/coding **reuse preflight ran** (`crystal_reuse_2fb2b79fb00cbf`, `no_reusable_crystal_found`). Promotion/publication did not run. `family_crystals_enabled` was False in the process that imported the module for this report; the `:8199` process was started with `BEAST_FAMILY_CRYSTALS_DB` pointed at the closure DB |
| Delivery sequence D3–D8 (spec) | See rows in §§4.3–4.9 (roadmap + phase plans). Nothing from the sequence is omitted | — | — |

### 4.3 Phase 1 — registry, signed candidates, operator API, live recovery

Defined in `superpowers/plans/2026-11-15-physical-crystal-fabric-phase1.md`.

| System / delivery / integration | Backend works | IDE wiring | Fires in a real Agent Coder run |
|---|---|---|---|
| Atomic registry endpoint reconciliation (`reconcile_endpoint`, `app/kernel/commons/remote_client.py`) | Yes — module + `tests/test_remote_commons_gateway.py` | Commons page `beast-commons-page.js` | No (not on Agent Coder stream) |
| Signed candidate verification (`verify_only`) | Yes — remote client + lab scripts (`scripts/provision_remote_commons_lab.py`) | Commons page | No |
| Local operator API and topology contract (`app/routes/commons_remote.py`, `app/main.py`, `build_remote_commons_router`) | Yes — router mounted; lab compose `docker-compose.commons-lab.yml` | Commons page | No |
| Live recovery and verification | Yes — recovery helpers exist on the remote-client / guardian path | Commons page | No |

### 4.4 Phase 2 — signed health, fabric health, discovery supersession, IDE evidence

Defined in `superpowers/plans/2026-11-15-physical-crystal-fabric-phase2-health.md`.

| System / delivery / integration | Backend works | IDE wiring | Fires in a real Agent Coder run |
|---|---|---|---|
| Signed container health verifier (`app/kernel/commons/node_health.py`, `scripts/check_remote_commons_health.py`) | Yes — module + `tests/test_remote_commons_health.py` | Commons page; also `desktop-ide/scripts/smoke-desktop-ide.js` | No |
| Control-plane fabric health | Yes — healthcheck path on remote client / commons routes | Commons page | No |
| Discovery supersession (`app/kernel/commons/discovery.py`, `superseded_candidate`) | Yes — module present | Commons page | No |
| Live health and IDE evidence | Yes — Commons page is the IDE evidence surface named by the plan | **Wired: Commons page** | No (this audit did not open the Commons page as part of the Agent Coder stream) |

### 4.5 Phase 3 / Delivery 3 — socket guardian, topology, custody

Defined in `superpowers/plans/2026-11-15-physical-crystal-fabric-phase3-guardian.md` and roadmap Delivery 3 in `superpowers/plans/2026-11-15-physical-crystal-fabric-roadmap.md`.

| System / delivery / integration | Backend works | IDE wiring | Fires in a real Agent Coder run |
|---|---|---|---|
| Fabric topology contract (`app/kernel/networking/fabric_topology.py`, `ServiceRegistry`, `topology_digest`, `scripts/check_fabric_topology.py`) | Yes — module + `tests/test_fabric_topology.py` | Commons page (topology evidence), not Agent Coder | No |
| Topology-bound guardian daemon with host roots (`app/kernel/execution/socket_guardian_daemon.py`, `scripts/generate_socket_guardian_units.py`) | Yes — module + `tests/test_socket_guardian_daemon.py`. `:8131` probe on this host returned HTTP 200 looking like gateway health (pids 2128583 / 2128582) | Not a Desktop IDE screen. Operated via `bin/beast` / units | **No.** Probe only. Agent Coder run did not call `:8131` |
| Guardian-owned gateway listener (`app/kernel/execution/guardian_uvicorn.py`, `recover_named_listener`) | Yes — module + `tests/test_guardian_uvicorn.py`. Live `:8101` is the production listener (not restarted here). Audit used a plain `:8199` process, not a guardian-owned bind | Heal / Commons operational surfaces, not the Agent Coder editor | **No** on the `:8199` audit process (it was started directly for isolation) |
| Commons signed custody records and live verification (D3.3) | Yes — remote client + gateway tests | Commons page | No |

### 4.6 Delivery 4 — consolidated crystal bus

Defined in `superpowers/plans/2026-11-16-physical-crystal-fabric-d4-crystal-bus.md` and roadmap Delivery 4.

| System / delivery / integration | Backend works | IDE wiring | Fires in a real Agent Coder run |
|---|---|---|---|
| Consolidated Crystal Bus (`app/kernel/compute/crystal_bus.py`, `app/kernel/crystal_bus/bus.py`) | Yes — both modules present; lattice / chain snapshots served by IDE APIs | Crystal reuse map, utility, and narration bridges in the renderer | **No.** Reuse **preflight** ran (`no_reusable_crystal_found`). The bus itself (publish / subscribe / consolidated transfer) did not emit an event on this run |
| `ConsolidatedCrystalBus`, `OneUseAuthority`, `CustodyChain`, `verify_custody_chain`, `strict_peer_credentials`, `content_digest`, `crystal_bus_from_environment` (D4 GREEN tasks) | Yes — implemented in `app/kernel/crystal_bus/bus.py` and re-exported; plan requires flag **default-off**, receipts, chain verification, tamper detection, durable one-use authority | Not a dedicated Agent Coder control; crystal / chain snapshots only | **No (default OFF / no transfer this run)** |
| Crystal-bus regression surface (`tests/test_consolidated_crystal_bus.py`, `tests/test_crystal_bus_capsule.py`) | Backend tests exist as named in the plan | n/a | No (tests are not the Agent Coder path) |

### 4.7 Delivery 5 / Phase 5 — episode envelope and planner wiring

Defined in `superpowers/plans/2026-11-15-physical-crystal-fabric-phase5-episode-envelope.md` and roadmap Delivery 5.

| System / delivery / integration | Backend works | IDE wiring | Fires in a real Agent Coder run |
|---|---|---|---|
| Budget tracker and episode envelope contract (`app/kernel/sensorium/episode_envelope.py`) | Yes — module present; used by planner / governor paths | Not a dedicated IDE screen. Budget UI is `budget-view.js` (economizer / context budget), which is related but not the envelope object itself | No named envelope event in the `:8199` event log |
| Planner runtime wiring (`app/kernel/agents/planner_runtime.py`) | Yes — module present; Agent Coder / pathfinder preflight uses the planner stack | Agent Coder panel (preflight / pathfinder) | **Yes** — pathfinder preflight `route_quality_live_coding` fired |

### 4.8 Delivery 6 / Phase 6 — coding crystal loop

Defined in `superpowers/plans/2026-11-15-physical-crystal-fabric-phase6-crystal-loop.md` and roadmap Delivery 6.

| System / delivery / integration | Backend works | IDE wiring | Fires in a real Agent Coder run |
|---|---|---|---|
| Reviewed coding opcodes and resolver (`app/kernel/compute/coding_crystals.py`) | Yes — module present | Crystal reuse / utility narration | No opcode execution on this run (no reusable crystal; coding crystals production wiring is default OFF) |
| Extraction, negative evidence and registry | Yes — registry + negative-evidence path in the crystal loop | Indirectly via crystal / review evidence bridges | **No** — run failed before a completed patch, so nothing was extracted or registered |
| Held-out replay, promotion and planning-time reuse | Yes — family/coding promotion DBs exist (live closure `family-crystal:a54695a14f648efdd70f6620` is a promoted rename crystal). This run’s preflight was `no_reusable_crystal_found` (task was not a rename) | Crystal reuse map | Preflight **Yes**; hit / promotion **No** |
| Closed-loop acceptance test | Backend test coverage exists for the loop; this audit is not that test | n/a | No |
| Enabling coding crystals (production wiring, **default OFF**) | Code present, flag default off (plan requirement) | Not exposed as an Agent Coder toggle in the panel scanned | **No (default OFF)** |

### 4.9 Delivery 7 / Phase 7 — Commons publication, quarantine, reproduction, shadow economy

Defined in `superpowers/plans/2026-11-15-physical-crystal-fabric-phase7-crystal-publication.md` and roadmap Delivery 7 (ForgeKV / Commons publication).

| System / delivery / integration | Backend works | IDE wiring | Fires in a real Agent Coder run |
|---|---|---|---|
| Publication bundle + privacy filter (`crystal_publication.py`; manifest, compatibility, proofs, Xet 4 KiB chunks, Ed25519 signature, `.beast-space.zip`) | Yes — `app/kernel/compute/crystal_publication.py` + `tests/test_crystal_publication.py` | Commons page | No |
| Commons Space + `verify_only` bucket revision + witness quorum + quarantined import (`crystal_commons.py`; nodes 8111–8113 through the 8101 control plane; `CommonsEnterprisePlane` custody) | Yes — `app/kernel/compute/crystal_commons.py` + `tests/test_crystal_commons.py` | Commons page | No. Audit did not talk to 8111–8113 |
| ML-KEM channel + client signing key stay inside the gateway (phase-7 flow; also `ml_kem.py` / `forge_kv_ml_kem_transport.py`) | Yes — modules present | None in Agent Coder | **No** |
| Node-signed receipts as witnesses / quorum (all nodes) | Yes — publication / commons path | Commons / review | **No** witness-quorum write this run |
| Local held-out reproduction (≥3 variants, zero model calls) + CLI `scripts/coding_crystals.py publish\|pull\|reproduce\|ledger` (offline default; `--live` loopback only) | Yes — script present | CLI, not the Agent Coder panel | **No** |
| Promotion sovereignty on the production path (`tests/test_coding_crystal_wiring.py`) | Yes — tests/wiring exist; production enablement still default OFF (phase 6) | Crystal reuse map | **No** |
| Shadow economy (`crystal_economy.py`; hook after `agent.episode.sealed`) | Yes — `app/kernel/compute/crystal_economy.py` + `tests/test_crystal_economy.py`. Commons-economy snapshot API 200 on `:8199` | Commons / economy surfaces | **No** as a write (episode never sealed). Snapshot probe only |
| Credit model details: `credit = max(0, V_K)`, token/tool/wall weights, `C_maintenance`, `C_risk`, `tokens_estimated` excluded, `local_envelope` / `publisher_signed_envelope` baselines, ratings 0.5x–1.5x, sybil/`aggregate_federated`, `false_reuse` + `clawback`, receipts on Space revision (`economy/reduction_receipts.json`, `economy/shadow_ledger.json`) | Encoded in `crystal_economy.py` / ledger types (plan + operator rulings 23:41 / 23:47) | Commons economy, not Agent Coder | **No** credit/rating/clawback this run |

### 4.10 Delivery 8 — IDE observability

Defined in `superpowers/plans/2026-11-15-physical-crystal-fabric-roadmap.md` (Delivery 8).

| System / delivery / integration | Backend works | IDE wiring | Fires in a real Agent Coder run |
|---|---|---|---|
| IDE observability for the fabric / crystal loop (snapshots, chronicle, tooling) | Yes — ide / system / tooling snapshots and chronicle APIs returned 200 on `:8199` | Wired across Agent Coder (`operations-console-client.js`), Models, Commons, review/trust bridges | Partial: Agent Coder SSE / operations console **did** stream this run’s events to the client. Fabric-health / publication observability did not have anything to show because those stages did not run |

### 4.11 Compute governor spine (PREC), memory contract, RTK addendum

Defined in `superpowers/plans/2026-11-16-physical-crystal-fabric-compute-governor-spine.md`.

| System / delivery / integration | Backend works | IDE wiring | Fires in a real Agent Coder run |
|---|---|---|---|
| Compute governor spine / PREC admit (`app/kernel/governance/governor_spine.py`, `ComputeGovernor.evaluate`; perceive → reason → economize → compute) | Yes — governor spine + `app/kernel/governance/reason.py` + economizer | Agent Coder / budget-view; not a separate “PREC” page | **Yes** — PREC perceive / reason / economize and handoff-ready all fired |
| Decision order in `admit` (execute-command behind admit; proposal cannot run without admit) | Yes — admit path is in the spine | Not surfaced as its own IDE control | Admit / handoff ran as part of PREC. Adaptive-router execution grant is proposal-only (see §4.14) |
| Task Envelope → D5 seal binding | Yes — spine wiring named in the plan | None as a dedicated screen | No named D5 seal event (run failed before episode seal) |
| D7 settlement requiring governor receipts (opt-in) | Yes — opt-in path in spine / economy | Commons economy | **No (opt-in, episode not sealed)** |
| Skill Tree promotion through D6 (enforced mode) | Code path present | Crystal / review | **No** |
| L4 / Chronicle receipt sinks | Chronicle API returned 200 on `:8199` | Operations / chronicle views | Probe yes; no new chronicle receipt attributed to this failed run in the event log |
| Eviction dry-run via admit (capsule governor; PSI/PRISM wrapper) | Code path present | None | **No** |
| RTK / SQZ readiness fix (governor-spine task 4; economizer refuse semantics) | Yes — compression_tiers + economizer tests | Budget view | Economizer **Yes**; RTK/SQZ binaries/tiers **No** this run |
| Swarm specialist (addendum; also §4.15) | Yes — `app/kernel/agents/swarm_specialist.py` | Swarm is mentioned in the store / `agent-client.js`, not a dedicated live swarm console for this run | **No** |
| RTK cascade compression (addendum; `app/kernel/data_processing/cascade_output_compressor.py`) | Yes — module present; used on swarm / cascade output, not on every chat token | Not an IDE screen | **No** (swarm/cascade not entered; no `rtk` event) |
| Memory contract (`app/kernel/governance/memory_contract.py`) | Yes — module present | Trust / memory bridge (`beast-trust-memory-bridge.js`) is the closest IDE surface | No named memory-contract event in the `:8199` log |
| Promotion evidence (addendum) | Yes — family-crystal promotion DB exists from earlier closure work | Crystal reuse map | **No** promotion this run |

### 4.12 Experimental tiers

Defined in `superpowers/plans/2026-11-16-physical-crystal-fabric-experimental-tiers.md` (including the 2026-11-16 04:35 SAST follow-up).

| System / delivery / integration | Backend works | IDE wiring | Fires in a real Agent Coder run |
|---|---|---|---|
| Real context compression tiers (`app/context/compression_tiers.py`) — native stand-ins for **RTK (Rust Token Killer)**, **SQZ** (Byron also said SGZ; the code and `deployment_integrations` spell this compressor **sqz** / SQZ), longcodezip, reporelay. Real binaries optional | Yes — module present; economizer can call tiers when flagged | No dedicated IDE screen. Economizer / `budget-view.js` is the related UI | **No.** This run’s economize step used the context-budget / summarise path (`budget_source=model_family`, `input_budget=28672`). No RTK/SQZ/longcodezip/reporelay tier event |
| Local Adapter Compiler (`app/kernel/compute/local_adapter_compiler.py`) | Yes — module present | Not in the Agent Coder panel | No |
| Defragmentation daemon (`app/kernel/compute/defrag_daemon.py`) | Yes — module present | Not in the Agent Coder panel | No |
| Zero-copy KV transport (plan file `app/kernel/compute/kv_transport.py`) | **Gap:** the exact path named in the plan is **missing**. Related ForgeKV stack exists (`forge_kv_*.py`, including `forge_kv_ml_kem_transport.py`) | Commons / ForgeKV, not Agent Coder | No |
| XDP admitted-flow fast path (plan + userspace sim `app/kernel/networking/xdp_fastpath_sim.py`) | Userspace simulator present; not a loaded XDP program on this host | None | No |
| Follow-up wiring of tiers into economizer / governor / crystal bus / swarm / tool integrations (04:35 addendum) | Modules listed in the plan exist (`economizer.py`, `governor_spine.py`, `crystal_bus/bus.py`, `swarm_specialist.py`, `tool_integrations.py`, `coding_crystals.py`, `episode_envelope.py`, `cascade_output_compressor.py`) | Indirect (budget, crystals, tools) | Only the economizer / PREC portion fired. Tiers, compiler, defrag, KV transport, XDP did not |

### 4.13 Lattice spine

Defined in `superpowers/plans/2026-11-16-physical-crystal-fabric-lattice-spine.md`.

| System / delivery / integration | Backend works | IDE wiring | Fires in a real Agent Coder run |
|---|---|---|---|
| Governed composition graph / `CrystalLattice` (`crystal_lattice_spine.py`; persist, hypergraph validation, witnessing, `compose()`, digest-stable empty composites) | Yes — `app/kernel/compute/crystal_lattice_spine.py`; lattice snapshot API 200 on `:8199` | Crystal / lattice views in the IDE | **No** as an admit/compose step. Snapshot probe only |
| `admit_composite` admission (PGEC §2.4, §8.1(4); two-child admission, authority intersection, one-child wrapper refused) | Yes — admission lives on the lattice spine | Not a dedicated control | No lattice-admission event in the run log |
| `demote` cascade (IEI §7.13.1) plus clawback | Backend path exists | Not in Agent Coder | No |
| Composite credits: `account_composite_reuse`, `rate_composite`, V_L cap, child pro-rata, premium S, self-composition earns no premium, ratings 0.5x–1.5x, shadow ledger non-financial | Encoded in lattice / economy modules | Commons / economy | No write |
| Router pointed at the lattice spine (D9) | Yes — `app/kernel/compute/adaptive_router.py` | Models / capability surfaces | Proposal-only; no execution grant this run (see next section) |

### 4.14 Delivery 9 — unified adaptive router (proposal-only)

Defined in `superpowers/plans/2026-11-16-physical-crystal-fabric-phase9-adaptive-router.md`.

| System / delivery / integration | Backend works | IDE wiring | Fires in a real Agent Coder run |
|---|---|---|---|
| Unified Adaptive Router (`app/kernel/compute/adaptive_router.py`: `RouteKind`, `RouteDecision`, `classify_band`, `AdaptiveRouter.route()`, `coding_crystal_fingerprints()`), **proposal-only** | Yes — module present. Capability scorecard / Auto rename probe on `:8199` routed to fireworks `glm-5p3-flash` via the **capability router** (related, not necessarily this D9 object) | Models page `beast-models-page.js`; capability / inventory bridges | **No D9 execution grant** (plan is proposal-only). Capability-router Auto rename was a **probe**, not an event inside `implementer-c17b0faf-6287242d2187` |
| Decision bands (Table 15) | Encoded in the router (`classify_band`) | Models page may show scores; not verified as Table 15 labels in the UI this turn | No |
| D6/D5 fingerprints for coding crystals | Fingerprint fields exist on the crystal / lattice path | Crystal views | No (no crystal hit) |
| Close the `execute.py` leak: dispatcher output is a `RouteDecision` at `ir.metadata["adaptive_route"]`; no model/provider rewrite; no `adaptive_route_executed` | Plan requires this; module present. Not re-verified by reading `execute.py` in this audit | None | **No** `adaptive_route` / `adaptive_route_executed` in the run log |
| Subordinate `CrystalReuseGateway`: semantic hit is a proposal unless `semantic_verifier` returns True; exact durable replay / KV checks unchanged | Yes — `crystal_reuse_gateway.py` preflight ran on this path | Crystal reuse narration | Preflight **Yes** (`execute_local_cpu` / `no_reusable_crystal_found` style). No semantic proposal payload this run |
| Router wired behind `BEAST_ADAPTIVE_ROUTER=1` (**default off**); `crystal_planner` / `crystal_replay` lane only when flag on; legacy `crystal_match` when off | Code present; default off matches the plan | Not an Agent Coder toggle | **No (default OFF)** |

### 4.15 Swarm specialist cascade

Defined in `superpowers/plans/2026-11-16-physical-crystal-fabric-swarm-specialist-cascade.md` (and the governor-spine addendum).

| System / delivery / integration | Backend works | IDE wiring | Fires in a real Agent Coder run |
|---|---|---|---|
| Ollama swarm specialist runner (`OllamaSwarmRunner`, `app/kernel/agents/swarm_specialist.py`) | Module present. Plan documents that local Ollama swarm runners were broken and how to fix them; this audit did not re-run that install | Swarm mentions in store / `agent-client.js` only | **No** |
| SwarmSpecialistDispatch / cascade-gated admit (`BEAST_SWARM_SPECIALIST`, `execution_granted`) | Code present; gated | Not a live Agent Coder default | **No** |
| PSI shrink (`pressure_factor` on interceptor / governor) | Code present on `InferenceComputeInterceptor` / `RuntimeGovernor` | None | No PSI event in the run log |
| RTK cascade output compression (`cascade_output_compressor.compress_cascade_output`) | Yes — module present | None | **No** |
| QualityCascade.run hook | Code present | None | No |

---

## 5. Additional repo systems Byron named that the 16 superpowers docs do not define as a primary delivery

These stay in the table so the earlier audit request is not dropped. They are **not** substitutes for any row in §4.

| System / delivery / integration | Backend works | IDE wiring | Fires in a real Agent Coder run |
|---|---|---|---|
| Governed interception / inference interceptor (`app/kernel/compute/inference_interceptor.py`) | Yes | Not a named IDE screen; errors surface in Agent Coder SSE | Interceptor/PREC path **Yes** (perceive/reason/economize). No separate “interception” event name |
| Streaming interceptor (`app/kernel/compute/streaming_interceptor.py`) | Yes | Agent Coder SSE is the user-visible stream; this module is gateway-side | Provider stream **started** (`max_tokens=16384 continuations=3`) then died on LiteLLM 400, so a full streamed completion was **not** observed |
| Constrained JSON / constrained output (`app/kernel/compute/constrained_output.py`) | Yes | Implicit in Action IR / pair-programmer JSON | Prompt asked for Action IR; the model never returned a body (LiteLLM 400) |
| Context economizer / input compression (`app/context/economizer.py`) | Yes — tests in `tests/test_context_economizer.py` | `budget-view.js` | **Yes** — economize + handoff ready |
| Context budget / model-aware input window (`app/context/budget.py`, shipped in `f3bf852b`, extended here for output) | Yes — `tests/test_context_budget.py` + `tests/test_output_budget.py` | Budget view + structured SSE errors in `agent-client.js` (`parseGovernedExecutionError`) | **Yes** — `budget_source=model_family` `input_budget=28672`; output `max_tokens=16384` |
| Provider lanes: Fireworks, SambaNova, HF router, Ollama, TGI, NIM, Hyperbolic, Replicate, fal | Yes — `/proxy/health` listed 29 providers including all of these | Models page / model inventory (`beast-model-agent-bridge.js`, `beast-utility-orchestration-bridge.js`, `beast-models-page.js`). SambaNova / Hyperbolic / Replicate / fal_llm were **blocked** on this inventory | This run selected **TGI**. It then failed because the proxy path sent the TGI model name through **LiteLLM** (HTTP 400). Other lanes did not fire |
| Capability scorecard / capability router | Yes — Auto rename probe routed to fireworks `glm-5p3-flash` | Models page | Probe yes; **not** an event inside the audit Agent Coder run (that run used the already-selected TGI model) |
| Family crystals / lattices (`app/kernel/compute/family_crystals.py`, `crystal_reuse_gateway.py`) | Yes — preflight hook; promoted rename crystal exists in the closure DB | Crystal reuse map / narration | Preflight **Yes**, hit **No** (`no_reusable_crystal_found`; task was not a rename) |
| Memory hull (`app/kernel/storage/memory_hull.py`) + residue seal (`app/kernel/security/residue_seal.py`) | Yes — modules present; memory-security snapshot 200 | `beast-trust-memory-bridge.js` | **No** hull/seal event in the run log |
| GPU scheduler (`app/kernel/compute/gpu_scheduler.py`) | Yes — module present | None found in the renderer scan | **No** |
| Process lifecycle (`app/kernel/execution/process_lifecycle.py`) | Yes | Heal / `bin/beast`, not Agent Coder | **No** |
| Heal (`heal_restart.py` / `heal_guard.py`, `./bin/beast heal`) | Yes — default is a full BEAST-stack restart (`d51a7ddd`); `--dry-run` / `--selective` remain. `beast ide` stays dry-run + selective | Commons page references heal; CLI is the actuator | **No** — this audit must not and did not run heal. **Byron should run** `cd ~/GitHub/EdgeK-BEAST && ./bin/beast heal` to put the max-tokens fix on live `:8101` |
| Governed egress shims (`app/kernel/compute/governed_egress.py`) | Yes — live run earlier had receipt `gov_2f067850cee2cf4d885096ea`. Audit run died before a successful paid egress | Not a screen | **No** successful egress on the `:8199` run (LiteLLM 400 first) |
| X7 LSM / ARDA (`app/kernel/transport/x7_*.py`) | Compiled userspace present | None | **No (compiled, not loaded)** — `lsmod` had no arda/x7 |
| MCP tool surface (69 tools) including `beast_symbol_surgeon_plan` | Yes — `/mcp/tools/list` count 69 on `:8199` and `:8765` | Tooling snapshot in the IDE | Tools were **available**. The audit run used approved search/read (Code Cortex), not a full 69-tool exercise. No evidence it called `code.rename_symbol` |
| `code.rename_symbol` / symbol surgeon | Yes — MCP tool listed; earlier closure promoted a rename family crystal | No renderer hit for the exact name `code.rename_symbol`; Models Auto-rename is a different flow | **No** (audit task was not a rename) |
| Line-anchored edits (`anchor_line` / `anchor_ref`, `apply_one_edit`) | Yes — `agent_run_stream` prompt now requires them; earlier `:8199` IDE E2E exercised `apply_one_edit` | Agent Coder apply path (not a separate page) | **Prompt Yes** on this run. **Apply No** — no model body, so no edit was applied |
| Semantic RAID (`app/kernel/data_processing/semantic_raid.py`) | Yes | No renderer hit for the name; packet/raid ids appear in Agent Coder / operations events | **Yes** — `raid_d489c97de9ced63d8bda`, packet `pkt_a4fcb032a4faad75` |
| Witness / ledgers | Yes — receipts / run store / chronicle | Review + operations console | Partial: run-store events and approvals **Yes**. A separate “witness ledger” write was not named in the event log |
| Trust / review / SourcePlan | Yes | `beast-review-evidence-bridge.js`, `beast-trust-memory-bridge.js`, `beast-phase9-app.js` (SourcePlan) | Approvals **Yes**. SourcePlan UI was not the driver of this run |
| IDE model inventory | Yes — 38 models on `/edgek/ide/model-inventory` | Models page | Used to **select** TGI for the run (inventory probe). Not an in-stream subsystem |
| Vector RAG (`app/kernel/adapters/vector_adapters.py`, `vector_memory.py`, `crystal_vector_bridge.py`) | Yes — modules present | Not found as a named Agent Coder toggle | **No** vector-RAG event in the run log |
| ML-KEM post-quantum crypto (`app/kernel/commons/ml_kem.py`, `forge_kv_ml_kem_transport.py`) | Yes — modules present | None in Agent Coder | **No** |
| Socket guardian — see §4.5 | — | — | **No** (repeated here only as a named ask; evidence is in §4.5) |

---

## 6. Low-risk gaps — what was and was not wired

Wired in this change (Agent Coder path, low risk):

- Model-aware output `max_tokens` and auto-continue on `finish_reason=length` (including empty visible text).
- Line-anchored edit prompting so a continued stream is less likely to emit a whole-file `new`.

Not wired (not low-risk, or already default-off / proposal-only). Honest list of what would be needed for each to fire inside Agent Coder:

- **Crystal bus / coding-crystal production enablement** — flag is default OFF by plan. Turning it on is an operator decision, not a drive-by hook.
- **Swarm specialist / cascade / PSI / RTK-on-cascade** — gated by `BEAST_SWARM_SPECIALIST`; local Ollama swarm runners have a known breakage history. Not enabled on this audit.
- **Compression tiers (RTK / SQZ / longcodezip / reporelay)** — need the economizer flag / real binaries. Native stand-ins exist but did not run.
- **Socket guardian-owned bind** — `:8199` was started as a plain process on purpose (isolated state). Live ownership stays with `:8101` after Byron heals.
- **ML-KEM, ForgeKV publication, XDP, defrag, local adapter compiler, kv_transport.py (missing exact module)** — not on the Agent Coder generate path.
- **TGI-through-LiteLLM 400** — pre-existing proxy routing bug. Fixing it would make a full generation possible on this Qwen TGI lane, but it is not part of the max-tokens change and was left alone to keep spend and blast radius at zero.

---

## 7. Commit and live-gateway reminder

Commit contents (intended): `app/context/budget.py`, `app/cli/api.py`, `app/routes/ide_support/common.py`, `app/routes/ide_routes/agent_run_stream.py`, `tests/test_output_budget.py`, `tests/routes/test_ide_support_common.py`, and `evidence/agent-coder-audit-2026-11-16/**`. Not committed: `benchmarks/results/**`, `deploy/generated/**`, gitignored `*.before-*` backups.

The max-tokens fix is on this branch and was observed on isolated `:8199`. It is **not** on live `:8101` until Byron runs:

```
cd ~/GitHub/EdgeK-BEAST && ./bin/beast heal
```

This audit did not run heal and did not touch `:8101`.
