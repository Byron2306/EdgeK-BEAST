# Step 6 — Loose ends (closure 2026-11-16)

## 6.1 All 69 MCP tools exposed (was 36)
- Cause: the stdio / JSON-RPC server (`app/mcp/stdio_server.py`, also behind `bin/beast mcp-http` POST /mcp) answered `tools/list` from a
  hand-maintained 36-entry `TOOL_DEFINITIONS`. The runtime, `GET /mcp/tools/list` and 8101 already had 69.
- Fix:
  - `tools/list` now returns `_listed_tools()`. With the default profile that is a generated snapshot `app/mcp/tool_definitions.json`
    (69 tools; kept in parity with `BeastToolRuntime._raw_tool_definitions()` by the new `tests/test_mcp_tool_parity.py`), so listing still
    doesn't warm the kernel.
  - With any `BEAST_MCP_TOOLS` profile or allow/deny list, the runtime applies the same visibility rules as tools/call.
  - If both paths fail, it falls back to the old 36.
- Live: POST /mcp on :8765 (pid 1646367, started 08:53 SAST) still answers 36 until it is restarted. I did not restart it.
  Byron: `kill -TERM 1646367; cd ~/GitHub/EdgeK-BEAST && nohup .venv/bin/python bin/beast mcp-http --port 8765 >/dev/null 2>&1 &`
  Then check: `curl -s -XPOST localhost:8765/mcp -H 'content-type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python3 -c 'import json,sys;print(len(json.load(sys.stdin)["result"]["tools"]))'` → 69.

## 6.2 The 4 failing tests in tests/test_mcp_runtime_v2.py: fixed (`app/mcp/runtime.py`, backup kept)
- Cause:
  - the least-authority mutation gate ran **before** the profile check, and treated 3 mixed tools as always-mutating;
  - so read and dry-run calls (`beast_capability_exchange` prepare/rank, `beast_otel_export` without approval, `beast_tool_laziness_record`)
    came back as `least_authority_mutation_block`.
- Fix:
  - the profile block is decided first (a readonly profile returns `beast_mcp_tool_profile_block` with `profile`);
  - new `_mutation_requested()` makes the gate action-aware:
    - capability_exchange is gated only for `submit` with `dry_run=false`;
    - otel_export only when `approved=true` (a real export);
    - tool_laziness_record is not gated (local learning ledger, no workspace or network effect);
    - every other mutating tool is unchanged.
  - The handlers keep their own approval checks.
  - **Semantics note for Byron:** laziness_record is now allowed without approval. Re-add it to the gate if you consider ledger writes mutations.
- Results:
  - test_mcp_runtime_v2 + the parity test + the other tests/test_mcp_*: **40/40**;
  - least-authority conductor, stdio framing, streamable HTTP, capability plane: **17/17**.

## 6.3 seraph-backend image digest pin (change made in BEAST; live compose left to Byron)
- The live image is `seraph-backend:latest` = `sha256:a42de2079b075a0e4f57026d9d1a50e47e4d25bfe5daa230c75e201a91183af9`
  (built 2026-11-15 08:26 SAST). It is used by `seraph-backend` (Metatron compose) and `beast-arda-guardian-arda-authorizer-1`.
  `docker image inspect seraph-backend@sha256:a42de…` resolves locally.
- Change:
  - `scripts/provision_guardian_validation.py`: `DEFAULT_ARDA_IMAGE = seraph-backend@sha256:a42de…`, overridable only explicitly via `BEAST_ARDA_IMAGE`;
  - `tests/test_guardian_phase3.py` asserts the digest form. **25/25** pass. Both files are backed up.
- Commands for Byron. They recreate the authorizer, so I didn't run them; I also didn't edit ~/.config/beast:
```
sed -i.bak 's#image: seraph-backend:latest#image: seraph-backend@sha256:a42de2079b075a0e4f57026d9d1a50e47e4d25bfe5daa230c75e201a91183af9#' ~/.config/beast/arda-guardian-compose.yaml
docker compose -f ~/.config/beast/arda-guardian-compose.yaml -p beast-arda-guardian up -d arda-authorizer
# optional, Metatron's own stack:
sed -i.bak 's#seraph-backend:latest#seraph-backend@sha256:a42de2079b075a0e4f57026d9d1a50e47e4d25bfe5daa230c75e201a91183af9#' ~/Metatron/docker-compose.seraph-fixed.yml
```

## 6.4 Memory-hull duplicate: deduped, with backup
- Dry run (DefragDaemon.plan_hull) over all vaults:
  - repo `.beast/vault` had **one duplicate group**: `residue_3e79043dea6a32a2a2da` (2026-10-10) plus 4 byte-identical copies;
  - `~/.beast/vault`, commons-enterprise and crystal_runtime vaults were clean.
- The copies are **test residue**: provider `local-test`, "Crystallized inference for chat_completion", written by the mammoth/gateway tests
  at 00:21 SAST (Nov 16), 10:04, 11:16 and 11:34 SAST. The last two came from my own adjacent test runs today.
- Backup: `.beast/backups/vault-before-closure-20261116.tar.gz` (sha256 `aa5c2ef79fd5e42e011b8fd73edfda263390a898d46f0f4041c2e4290d3fd16b`).
- Applied with BEAST's own `DefragDaemon.apply_hull`:
  - governor admit `gov_b379d5e963ccf0297f696b76`;
  - 4 residues **quarantined reversibly** under `.beast/vault/.defrag/` (nothing deleted), then reindexed;
  - ledger `.beast/defrag/hull-ledger.jsonl` valid (5 entries);
  - afterwards: 1 verified residue, 0 duplicates, no index drift (`hull_dedupe.json`).
  - Undo: `DefragDaemon.undo(<receipt_id>)`.
- Root cause fixed: `tests/conftest.py` now also sets `BEAST_STATE_ROOT` to the temp dir. That covers the vault, trace ledger, semantic cache
  and route optimizer. After mammoth/gateway/plugin/guardian tests, the live state sha256 was unchanged.

## 6.5 Provider keys re-importable from disk (NAMES ONLY; no values read out)
- `.beast/provider_secrets.env`: FAL_KEY, FIREWORKS_API_KEY, HYPERBOLIC_API_KEY, NVIDIA_API_KEY, REPLICATE_API_TOKEN, SAMBANOVA_API_KEY
- `~/.cache/huggingface/token`: HF_TOKEN (token file)
- `~/Metatron/backend/.env`: OPENAI_API_KEY
- `~/Metatron/.env`: ANTHROPIC_API_KEY
- (not a provider key) `/data/byron/lilith-local/.../worker/.env`: LILITH_WORKER_TOKEN
- Names BEAST lanes read that have no on-disk source: GEMINI_API_KEY/GOOGLE_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY, XAI_API_KEY,
  DEEPINFRA_API_KEY, CEREBRAS_API_KEY, COHERE_API_KEY, NOVITA, NSCALE, FEATHERLESS, OVHCLOUD.

## Spend
$0.
