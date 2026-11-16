# IDE model selection + Workspace/Monaco/Agent Coder legibility — 16 Nov 2026

Byron's priority: get model and provider selection right, and make the Workspace, Monaco, and Agent Coder screens legible. Live gateway `127.0.0.1:8101` was not restarted or killed. A current-code test gateway ran on `127.0.0.1:8199` and was stopped after the proof. No keys were printed. Backups are `*.before-ide-legibility-20261116`.

Renderer changes take effect after you close the IDE and run `./bin/beast ide`. The new inventory and route-probe endpoints are only on current code, so 8101 will keep serving the older discovery path until you restart it yourself. The pickers still show **Auto (BEAST governed)** in that fallback, plus live Ollama models.

## Pickers found

| Surface | Before | After |
|---|---|---|
| **Models page** | Registry of installed Ollama + one default model per credentialed provider. Store seeded fake `1.24s` / `94.7%` until refresh. "Stage as Primary" only patched `selectedId`. | Lists **Auto (BEAST governed)** first, then real lanes from `GET /edgek/ide/model-inventory` (registry + `provider_lanes` + `hf_router_lanes` + live TGI/Ollama). Only providers whose key exists (name only). Scorecard family ranks and "best at" chips. Staging writes the route through `selectModel` → `syncModel` → `/proxy` / agent-run body. |
| **Workspace toolbar** | Second full-width toolbar, Ollama + verified Nemotron only, placeholder "Choose a model". The extra row stole the editor's grid track (`grid-template-rows: auto auto 1fr` with four children). | Merged into the root toolbar. Shared picker (`BeastModelAgentBridge.fillModelSelect`) lists Auto + every selectable lane, including TGI, Fireworks, HF routes, etc. |
| **Agent Coder panel** | No model picker. Relied on the workspace toolbar. | Header select, same inventory and `selectModel` wiring as the workspace picker. |
| **Providers page** | Seeded demo rows (Ollama/NIM/OpenAI/Anthropic with invented 90–96% confidence and `94.7%` chronicle text) on API failure. `selectProvider` only synced a provider default_model. | On a live inventory response, lists Auto + credentialed providers from that inventory, confidence 0 unless the scorecard has a rate. Failure no longer falls back to demo seeds (demo mode still can). Choosing a provider pins its first selectable lane, or Auto. |
| **Settings** | Typography/density/atmosphere only. No model picker. | Left as-is. Model selection lives on Models, Workspace, Agent Coder, and Providers. |

Duplicate pickers were consolidated onto one helper and one store (`models.selectedId` / `selectedModel` / `selectedProvider`, plus `aiCoding.model` / `provider` / `governedAuto`). Empty or `auto` means Auto (BEAST governed). Fake store defaults (`qwen2.5-coder:7b`, `94.7`, `1.24s`) are gone.

## End-to-end selection proof (test gateway :8199)

Current code, flags on, isolated `BEAST_STATE_ROOT=/tmp/beast-ide-8199-20261116`. 8101 was not touched. Proof: `evidence/ide-polish-2026-11-16/e2e-proof-8199.json`.

`GET /edgek/ide/model-inventory` returned **38 lanes**, default **Auto (BEAST governed)**. No secret-leak markers. Providers present (keys exist, names only): `fal_llm`, `fireworks`, `hf`, `hyperbolic`, `nim`, `ollama`, `replicate`, `sambanova`, `tgi`.

Live state at the time of the probe:

- TGI on `:8090` up, model `Qwen/Qwen2.5-Coder-3B-Instruct-AWQ`
- Ollama on `:11434` up, models `granite3.2:2b`, `granite3.3:2b`, `qwen2.5-coder:7b`, `qwen3:4b`

`POST /edgek/ide/model-route` with Auto, family `rename`, `call=false`: router resolved to `nim` / `nvidia/nemotron-3.5-lightning-30b-a3b` (`via=capability_router`) from the scorecard aggregate. No model call, **$0**.

`POST /edgek/ide/model-route` with an explicit TGI pin, `call=true`: GovernedModelClient called **TGI**, `call_status=ok`, `accepted=true`, `matches_resolved=true`, latency **596 ms**, **$0.00**. The governed candidate id is still `tgi` (not the Hugging Face model name). The request asked for the live model name; the pin correctly stayed on the TGI lane and that is the lane that ran.

Paid lanes were resolved in inventory but not called (probe only calls local TGI/Ollama). Total spend for this pass: **$0.00** (under the $0.02 cap).

An Agent Coder send now posts `provider`, `model`, `governed_auto`, and `route_id` on `/edgek/agent-runs`. Auto sends `provider=beast`, `model=auto`. An explicit Fireworks pick sends that provider and model. The older agent-run planner still special-cases Ollama/NIM; Auto and new lanes are proven on the governed `/edgek/ide/model-route` path (and will be used once 8101 runs this code). Wiring the full agent-run cascade onto every new lane is still open.

## Legibility (Workspace, Monaco, Agent Coder)

No screenshots: Playwright/Electron was not launched, so Byron's running IDE was left alone. Fixes were made from the live CSS/DOM stack. The mounted shell still ends at `beast-studio-repair-r1.css`; the large unused sheets (`beast-hacker-coherence.css`, `beast-aesthetic-override.css`, `beast-production.css`, `beast-layout-authority.css`) are **not** in `index.html`. A new last sheet, `css/beast-ide-legibility-20261116.css`, is.

**What was wrong**

- Type in the explorer, tabs, status bar, and some Agent Coder chrome was 7–8px on a dark background.
- File rows repeated the filename in `<strong>` and `<small>`.
- Five explorer tabs were forced into a 3-column grid.
- A second model-picker toolbar consumed the only `1fr` row, shrinking the editor.
- Monaco default was 13px, line numbers `#405047` on `#020403`, minimap off in the Cortex editor (on in the unused workbench).
- Agent Coder diffs were plain `<pre>` with no before/after contrast; tool-call rows were cramped; the action footer had `max-height: 92px` and clipped buttons.

**What changed**

- Merged toolbars; editor keeps the flexible row.
- File tree 13px, one name, extension as the quiet meta, 11px status/pills.
- Explorer tabs wrap in a flex row at 11px.
- Monaco default **14px**, line-height **1.55×**, ligatures, brighter foreground `#e8f2ea`, stronger line numbers and selection, slim proportional minimap, sticky scroll. Zoom still updates line-height.
- Agent Coder: 13px/1.5 transcript, red/green before/after diffs, 12px tool-call rows, unclipped wrapping actions, readable cockpit, model select in the header.
- Ask/Edit/Agent shortcut buttons and the MODE `<select>` (which also has Review) both still work and share `api.setMode`. They are overlapping controls, not dead ones. Left both in place so Review stays reachable.

### Control / wiring inventory (Workspace + Agent Coder)

All of the following have handlers. None were left as dead buttons.

**Workspace header:** Choose Folder, Crystals (navigates to Crystallization), Governance (navigates to SourcePlan), Trust Workspace (native trust host), Refresh Index. The Agent Coder toggle is injected into this action row.

**Workspace toolbar:** model `<select>`, Refresh models, Verify Nemotron, status pills (files / models / dirty).

**Explorer:** Files / Outline / Recent tabs; Git and Search (read-only recovery views); filter; New file, New folder, Toggle tree/flat, Rename, Delete (Safety Governor + confirm).

**Editor chrome:** zoom −/+, Split, Revert, Draft SourcePlan, tab strip, status/position.

**Agent Coder:** model `<select>`, Focus, Close, Attach active file, Suggest context, Retry, New chat, Stop (shown while streaming), Isolate (worktree run), Run agent / Ask / Prepare edit / Review (label follows mode). Shortcut Ask/Edit/Agent buttons and the MODE select. In-message Inspect diff and SourcePlan actions.

## Tests

- `pytest tests/test_ide_model_inventory.py tests/test_crystal_reuse_gateway.py tests/test_durable_inference_storage.py` — 35 passed.
- `desktop-ide`: `npm run smoke` — 38/38.
- `node scripts/verify-live-page-contracts.js` — 4/4.
- `node scripts/verify-nim-picker.js` — 9/9 (hosted Nemotron still requires explicit verification; Auto is not inserted on the old discovery fallback used by this harness).
- `node scripts/verify-enterprise-runtime-contract.js` — still FAIL on many pre-existing checks. `no_unverified_default_model_route` now **passes**. Untouched failures include Mission/honest-boot copy and other pages outside this pass.

Spend: **$0.00**.

## What remains

- Restart 8101 yourself when you want the live IDE to use `/edgek/ide/model-inventory` and `/edgek/ide/model-route`. Until then, the renderer falls back to older discovery and still offers Auto in the picker.
- The default scorecard file currently exposes family evidence mainly under `gauntlet`. Today's rename/refguard Fireworks rankings will show once those cells live in `.beast/capability_scorecard.json`.
- TGI's governed candidate id is `tgi`, not `Qwen/Qwen2.5-Coder-3B-Instruct-AWQ`. Explicit TGI picks still hit TGI.
- Hyperbolic, Replicate, fal, and SambaNova appear when their key *names* are present, even if those accounts are out of credit or blocked. Inventory does not probe account health.
- The agent-run planner cascade is still Ollama/NIM-centric. Auto and new lanes are selected and posted, and are proven on the governed route probe; a full agent-loop through Fireworks/HF on `/edgek/agent-runs` is not proven in this pass.
- Review / SourcePlan GET / Mission placeholder copy from the earlier polish report are unchanged.
- Ask/Edit/Agent shortcuts still overlap the MODE select.

## Commands for Byron

Renderer changes only (does not restart 8101):

```bash
cd ~/GitHub/EdgeK-BEAST
# close the IDE window, then:
./bin/beast ide
```

Optional, already on the closure list — restart 8101 yourself when you want the new inventory on the live gateway. Follow `evidence/closure-2026-11-16/03-gateway-flags/REPORT.md`. I did not restart it. The 8199 test gateway used for the proof has been stopped.
