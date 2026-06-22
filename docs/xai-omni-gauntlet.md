# xAI Omni-Gauntlet

The xAI Omni-Gauntlet evaluates Grok as a governed component inside BEAST. It
does not treat system rescue as provider-clean success.

## Surface

- 24 full-BEAST live coding trials with visible and hidden tests
- 4 matched raw-provider controls
- 13 local subsystem probe groups
- 13 architecture coverage layers
- Action IR validation, local compilation, pytest verification, repair evidence,
  latency, tokens, route fitness, and integrity hashes

The live tasks cover provider routing, multi-file fixes, async streaming, TUI
state, rollback, malformed output, refs-only actions, stale hashes, agent latency
budgets, Provider Economist routing, Tool Laziness, Meta Tool Commons approval,
plugin permissions, OTEL redaction, network diagnosis, GitHub PR envelopes,
multilingual quality checks, MCP schema pins, Chronicle evidence, deployment
resolution, and vector context deduplication.

## Run

Preflight without provider calls:

```bash
.venv/bin/python benchmarks/beast_xai_omni_gauntlet.py \
  --output beast_xai_omni_gauntlet_preflight
```

Live run:

```bash
.venv/bin/python benchmarks/beast_xai_omni_gauntlet.py \
  --live \
  --output beast_xai_omni_gauntlet_live \
  --max-tokens 1400 \
  --timeout 240
```

The script loads `.beast/provider_secrets.env` through `SecretVault`; secret
values are never written into benchmark artifacts.

## Claim Boundary

- **System completion** means provider output plus BEAST reached passing visible
  and hidden tests.
- **Provider clean** means no canonicalization, schema repair, or local verifier
  repair was used.
- **Provider rescued** means BEAST repaired or replaced imperfect output before
  verification.
- **Local probes** validate BEAST itself and are not credited to Grok.

Cost ranking is excluded unless xAI returns first-party request cost evidence.
