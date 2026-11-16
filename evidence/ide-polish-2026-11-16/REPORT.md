# IDE polish (Delivery 8) — 16 Nov 2026 13:19 SAST

Delivery 8 of `docs/superpowers/plans/2026-11-15-physical-crystal-fabric-roadmap.md`: IDE observability for topology/custody, episode/budget, candidate/replay/promotion/reuse with savings, and Commons publication. No keys or pins are rendered. Credits must not be shown as money. Refusals and clawbacks are first-class.

Live gateway `127.0.0.1:8101` was probed read-only and was **not** restarted. It is still running older code, so new inventory fields land only after you restart it. Renderer changes take effect on the next `beast ide` launch.

## Hidden / legacy layers

**Mounted (live tree):** `desktop-ide/renderer/index.html` loads `beast-phase9-app.js`, which registers 31 routes against the `renderer/js/pages/*` modules and the Phase 8 utility pages in `beast-phase8-pages.js`. Data is filled by the bridge modules (`beast-map-crystal-bridge.js`, `beast-utility-orchestration-bridge.js`, `beast-restored-route-bridge.js`, and siblings).

**Not mounted (dead application shells):**

- `renderer/js/beast-phase7-app.js` — older 15-page registrar
- `renderer/js/beast-phase8-app.js` — older 23-page registrar
- `renderer/js/beast-release-app.js` — later shell with the same page list as Phase 9, but it is not in `index.html`

Those files are leftover iterations. They do not run. Historical CSS (`beast-phase6-*` through `beast-phase9-*`) still loads for visuals only. Root-level `desktop-ide/beast-workspace-page.js` and backup trees (`.beast-studio-repair-r1-backup-*`) are also unused by the current shell.

**Store gap:** `beast-store.js` still initialises only the Phase 7 keys. Later surfaces (`economy`, `commons`, `liveFabric`, `computeFabric`, `control`, `platform`, `reality`, `grandClosure`, `sensorium`) were created on the fly. `ensureFabricState()` now seeds them so those pages do not crash before the first refresh.

## Page status

Probed against live `http://127.0.0.1:8101` (older process) plus the current renderer/bridge source. Status is for the current UI tree, after today's fixes, once the IDE is relaunched.

| Page | Status | Root cause | Layer |
|---|---|---|---|
| Studio | works | Overview of other surfaces; health comes from `refreshStudio()` after utility refresh | `beast-phase8-pages.js` + utility bridge |
| Workspace | works | Local editor/workbench; not a fabric scorecard surface | `beast-workspace-page.js` |
| IDE Compatibility | works, incomplete | `/edgek/control-plane/desktop-compatibility` returns `status=incomplete` on 8101 | compatibility page + desktop contract |
| SourcePlan | partial | Lifecycle is POST-only (`GET /edgek/ide/sourceplan/lifecycle` → 405). Draft/verify/apply still use POST routes | `beast-sourceplan-page.js` + editor cortex |
| Mission | stale copy | Hardcoded Phase 7/8 “transplant” mission text and demo progress (82–88%) in the store / `ensureState` | `beast-store.js`, utility `ensureState` |
| Models | works after refresh | Initial store still seeds fake latency/confidence (`1.24s`, `94.7`) until a models refresh | models page + store defaults |
| Compute Fabric | works | Filled from `/edgek/ide/phase-evidence` (`selectedRoute`, routes, decision trace) | compute-fabric page + restored-route bridge |
| Live Evidence Fabric | works, historical | Same phase-evidence payload. BPF/XDP `live` flags are often `null`; counters come from older receipts, honestly labelled as repository evidence | live-fabric page + restored-route bridge |
| Compute Control | works | `/edgek/interception/transparent/state`, `/edgek/crystal-reuse`, `/edgek/control-plane/services`, cgroup, reboot, host-enforcement | compute-control page + restored-route bridge |
| Agents | works (inferred) | `/edgek/swarm/state`, `/edgek/swarm/runs`, agent-session routes exist and return 200 | agents page + model-agent bridge |
| Review | broken / empty for Zero Review | `/edgek/zero/review-board` and `/edgek/zero/reviews` return **503** “Desktop Review workspace is not configured” | review page + review-evidence / zero-review board |
| Grand Closure | works | Phase-evidence `grandClosure.gates` G1–G9 with receipt digests | grand-closure page + restored-route bridge |
| Trust | works (inferred) | Trust/memory security endpoints return 200 | trust page + trust-memory bridge |
| Memory | works | Covered by existing live-page contract (nullable truth stores, no invented records) | memory page + trust-memory bridge |
| Evidence | works | `/edgek/evidence-bus/query` returns 200 | evidence page + review-evidence bridge |
| Crystallization | **fixed** | Was showing demo candidates and fake Phase 4/5 artifacts because `/edgek/crystal-reuse` has no `candidates` list on 8101 and the bridge fell back to `DEMO_CANDIDATES`. Now maps `credits` (current code) or synthesises from `storage.*` metrics, loads chain blocks, and shows witness refusals | crystallization page + map-crystal bridge |
| Commons | works, degraded remote | `/edgek/control-plane/commons` is ready; `/edgek/control-plane/commons/remote/health` is `degraded`. Publication/credits are non-financial | commons page |
| Map | works | `/edgek/workspace/graph` (or `/edgek/ide/snapshot` fallback) | map page + map-crystal bridge |
| Terminal | works (inferred) | Local/doctor tooling path; no 8000 dependency after the fallback fix | terminal page + doctor/tooling bridge |
| Testing | thin / likely empty | 55-line page; no Delivery 8 episode list wired yet | testing page |
| Tooling | works | `/edgek/ide/actions/manifest` (54 actions), MCP/plugin routes 200 | tooling page + doctor/tooling bridge |
| Doctor | works | Live scan of root-info/snapshot/actions/system/MCP/plugins. Default gateway fallback was `:8000`; now `:8101` | doctor page + doctor/tooling bridge |
| Reality Matrix | works, historical | Phase-evidence reality receipts; `live` often null | reality page + restored-route bridge |
| Providers | works after refresh | `/edgek/providers/state` and registry return 200. Demo seed no longer shows `R0.00` | phase8 providers + utility bridge |
| System | works (inferred) | Ports/processes from system snapshot / control-plane | phase8 system + utility bridge |
| Systems Atlas | works (inferred) | Platform snapshot + phase-evidence | atlas page + utility/restored bridges |
| Worktrees | works (inferred) | Present in IDE snapshot payload | phase8 worktrees + utility bridge |
| Deploy | unproven | Relies on release-readiness / runbook routes; not live-clicked this pass | phase8 deploy + utility bridge |
| Chronicle | works | `/edgek/chronicle?limit=20` returns 200 with events | phase8 chronicle + utility/trust bridges |
| Compute Economy | **fixed** | Bridge looked for `tokens_saved` / `calls_displaced` / `cost_avoided`, which `/edgek/commons-economy` does not ship. Real figures live at `crystal-reuse.storage.total_avoided_tokens` (6780), `total_reuse_count` (7), `active_credits` (16). Page also showed `R0` / demo `R18,420` (money). Now uses storage + phase-evidence and labels savings as non-financial token credits | phase8 economy + utility bridge |
| Settings | works | Local renderer settings | phase8 settings |

## Endpoint mismatches found

Live 8101 (older process):

- `GET /edgek/crystal-reuse` — 200, but inventory is metrics + integrations only (no credit rows). Current tree now also returns redacted `credits`.
- `GET /edgek/commons-economy` — 200, `mode=non_financial_simulation`, no `tokens_saved` / `cost_avoided`.
- `GET /edgek/crystal-chain?include_blocks=true&limit=25` — 200, 5 valid blocks. Head is 15 Nov 2026, not today’s durable-inference chain (`app/data/durable_inference/crystal_chain.jsonl`, 37 entries). Two different ledgers.
- `GET /edgek/crystal-lattice` — 200, 18 valid checkpoints.
- `GET /edgek/crystal-chain/witness` — 200. Audit verdict **`quarantine`**, `promotion_allowed=false`, reason `rollback_detected`. This was not shown in the IDE before.
- `GET /edgek/crystal-lattice/spine` — **404** on 8101; route exists in current `app/main.py`.
- `GET /edgek/zero/review-board`, `/edgek/zero/reviews` — **503**.
- `GET /edgek/workspace/context-header`, `/edgek/ide/sourceplan/lifecycle`, `/edgek/forge/scorecard` — **405** (wrong method).
- Doctor/tooling fallback URL was `http://127.0.0.1:8000`. Store default and health checks already use **8101**.

## What changed

Backups are `*.before-ide-polish-20261116` next to each edited file.

1. `app/kernel/storage/durable_inference_storage.py` — added `list_credit_summaries(limit=40)`. Rows are redacted: no metadata, prompts, responses, or request payloads.
2. `app/kernel/compute/crystal_reuse_gateway.py` — `/edgek/crystal-reuse` inventory now includes `credits`.
3. `desktop-ide/renderer/js/beast-map-crystal-bridge.js` — crystallisation no longer invents demo candidates or fake Phase 4/5 artifacts when live data exists; fetches chain blocks and witness; quality gates now use chain, lattice, reusable credits, and witness refusals; savings (tokens avoided, reuse count) are stored and listed.
4. `desktop-ide/renderer/js/beast-utility-orchestration-bridge.js` — economy maps `storage.total_avoided_tokens`, `total_reuse_count`, `active_credits`, and phase-evidence `economy.*`. `costAvoided` is a token/non-financial label, never Rand or USD. No fake 70/30 provider mix when the API has none.
5. `desktop-ide/renderer/js/beast-terminal-tooling-doctor-bridge.js` — default gateway fallback is `http://127.0.0.1:8101`.
6. `desktop-ide/renderer/js/beast-restored-route-bridge.js` — `ensureFabricState()` seeds later-page store keys so Live Fabric / Control / Commons / Reality do not read `undefined`.
7. `tests/test_crystal_reuse_gateway.py` — inventory lists redacted credit summaries and must not leak secrets.

## Tests

- `pytest tests/test_crystal_reuse_gateway.py tests/test_durable_inference_storage.py` — 31 passed.
- `desktop-ide`: `npm run smoke` — 38 checks ok.
- `node scripts/verify-live-page-contracts.js` — 4/4 passed (after making `ensureFabricState` work with the test’s `patch`-only store mock).
- `npm run smoke:parity:foundation` — failed with `REFUSE: requested model 'test-model' is unavailable; no provider fallback is authorized.` This is in the existing parity harness / coding-route resolver, not in the files edited here. Left untouched.

No model API spend. 8101, 8131, 8765, ARDA, seraph, TGI, Ollama, and LiteLLM were not restarted or killed.

## What remains

- **Restart the IDE** to load the renderer fixes. The live 8101 process will keep serving the old inventory (no `credits` array) until you restart the gateway with current code; until then the crystallisation page still shows real `storage` totals and chain/witness data, not demo residue.
- **Review** stays empty until a Desktop Review workspace is configured.
- **SourcePlan** lifecycle GET is still the wrong method.
- **Mission** copy is still the old Phase 7/8 transplant text.
- **Delivery 8 episode/budget:** `/edgek/ide/phase-evidence` `sensorium.episodes` is currently `closed_count=0` / no open missions, so there is no live episode envelope to render. Tightening that is backend evidence work, not a field-mismatch fix.
- **Two crystal ledgers:** Commons chain (`data/commons_spaces/.crystal_chain`, 5 blocks) vs durable inference (`app/data/durable_inference/crystal_chain.jsonl`, 37 entries, including today’s runs). The IDE now shows the gateway’s Commons chain + durable-inference credits. Unifying those ledgers is still open.
- **`/edgek/crystal-lattice/spine`** will 404 until 8101 runs current code.
- Line-anchored edit tool and live agent-loop verification are still the other open closures, not IDE pages.

## Commands for Byron

Renderer changes only take effect after relaunching the IDE (this does not restart 8101):

```bash
cd ~/GitHub/EdgeK-BEAST
# if an IDE window is already open, close it, then:
./bin/beast ide
```

Optional, already on the closure list — restart 8101 yourself when you want the new `credits` inventory and `/edgek/crystal-lattice/spine`. Follow `evidence/closure-2026-11-16/03-gateway-flags/REPORT.md`. I did not restart it.

No other host or kernel commands are required for this polish.
