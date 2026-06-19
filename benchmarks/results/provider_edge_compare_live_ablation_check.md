# Provider Edge Compare

Generated at: `2026-06-18T10:54:41Z`

Cloud APIs and local NIM are compared as OpenAI-compatible inference endpoints; BEAST impact is measured as edge preprocessing/governance around those endpoints.

## Scenario Token Shaping

- `industrial_telemetry_anomaly_triage` raw `5603` tokens, BEAST `3325` tokens, reduction `40.6568%`
- `long_context_redundant_agent_state` raw `3809` tokens, BEAST `45` tokens, reduction `98.8186%`
- `agentic_tool_surface_summary` raw `1000` tokens, BEAST `262` tokens, reduction `73.8%`

## Provider Summary

### nvidia_cloud_nim
- Raw successes: `3/3`; median latency `2951.35 ms`; tokens `11390`; cost `$0.0`
- BEAST successes: `3/3`; median latency `1911.559 ms`; tokens `6514`; cost `$0.0`
- Observed token reduction: `42.8095%`
- Observed cost reduction: `0.0%`
- Median latency delta: `-1039.791 ms`

### openrouter
- Raw successes: `3/3`; median latency `5113.623 ms`; tokens `11573`; cost `$0.00030668`
- BEAST successes: `3/3`; median latency `5022.56 ms`; tokens `5195`; cost `$0.00013767`
- Observed token reduction: `55.111%`
- Observed cost reduction: `55.1096%`
- Median latency delta: `-91.063 ms`
