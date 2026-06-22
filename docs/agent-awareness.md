# BEAST Agent Awareness

Every attached agent can begin with `beast_session_handshake`. The packet tells the agent which local systems BEAST already provides, which work should remain local, which tool calls have low learned value, and when cloud inference is justified.

OpenClaw and Nemoclaw plans embed the same handshake and a measured `beast_local_preflight` artifact containing:

- Tool Laziness call/skip recommendations
- Provider Economist role selection
- Ollama scout output or an explicit budget-skip reason
- phase timings and total elapsed time
- suppressed actions
- preflight and scout budget verdicts

Defaults are `500 ms` for total preflight and `300 ms` for scout work. Optional phases are skipped before the deadline when insufficient budget remains. Ollama discovery and generation receive bounded HTTP timeouts.

## Capability Exchange

The Capability Exchange is disabled by default. Enable it explicitly with:

```bash
export BEAST_CAPABILITY_EXCHANGE_OPT_IN=1
export BEAST_CAPABILITY_EXCHANGE_ENDPOINT=https://your-exchange.example
```

Optional settings:

```bash
export BEAST_CAPABILITY_EXCHANGE_NODE_ID=anonymous-local-alias
export BEAST_CAPABILITY_EXCHANGE_SIGNING_KEY=local-signing-secret
```

Exchange evidence is allowlisted aggregate metadata only. It excludes prompts, source code, paths, and secrets. Submission requires opt-in, explicit approval, and `dry_run=false`. Rankings are scoped by task class, role, capability version, and schema hash; global evidence is a prior rather than a universal leaderboard.

## TUI Intelligence Workspace

Press `j` in the BEAST TUI, or select **Intelligence** from the command palette,
to inspect the active handshake, preflight and scout budgets, Tool Laziness
recommendations, Provider Economist decision, contextual Meta Tool Commons
rankings, Capability Exchange posture, OpenTelemetry configuration, and installed
plugin manifests.

TUI refresh is read-only. It cannot ingest shared evidence, export telemetry,
install a plugin, or adopt a Commons candidate. Those operations retain their
normal explicit approval gates.

## Compute Awareness

Phase 1 of the Inference Compute Governor runs beside provider execution in
shadow mode. The TUI Intelligence workspace and `beast_compute_shadow` expose
its plans and receipts. Agents should treat recommended rungs and avoidable-token
figures as observations only; no call may be skipped until a later rollout phase
passes behavior-preserving ablation gates.
