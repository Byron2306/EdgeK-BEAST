# EdgeK BEAST Metrics Benchmark

Generated at: `2026-06-12T09:06:10Z`

## Implementation Boundary

- Runtime circuit breaker: implemented and measured.
- Context economizer / semantic compression: implemented and measured.
- Zero-copy memory mapping: local `mmap`, AF_PACKET mmap, and native DPDK/AF_XDP probes are implemented.
- AST compression engine: implemented for lossless JSON schema rows, reconstructive Python AST canonicalization, and semantic Python AST summaries.
- Isolation Forest: implemented as a deterministic pure-Python edge outlier filter.

## Latency

- Traditional median: `7.29376 ms`
- mmap median: `4.379386 ms`
- Median reduction: `39.9571%`
- OS-bypass status: `native_backends_available`
- DPDK ready: `True`
- AF_XDP ready: `True`
- Missing DPDK libs: `none`
- Missing AF_XDP libs: `none`

## Bandwidth

- Telemetry raw bytes: `2803883`
- Telemetry schema bytes: `1604004`
- Telemetry reduction: `42.7935%`
- Agentic raw bytes: `54979`
- Agentic AST semantic-summary bytes: `9118`
- Agentic reduction: `83.4155%`

## Loop Protection

- Time to interruption: `6.414101 ms`
- Accepted failures before interrupt: `5`
- Uncontrolled loop rate: `12367858.22 iterations/s`

## Cost Efficiency

- Raw estimated tokens: `770241`
- Filtered/compressed estimated tokens: `402636`
- Token reduction: `47.726%`
- Estimated OpenRouter fee before: `$0.02041139`
- Estimated OpenRouter fee after: `$0.01066985`
- Fee reduction: `$0.00974153` / `47.726%`

## Tool Laziness Learning

- Final decision: `skip`
- Final reason: `low learned usefulness`
- Rare critical decision: `call`
- Rare critical reason: `rare critical success observed`
- Projected 100-call tokens avoided: `6180.0`
- Projected 100-call cost avoided: `$0.0618`
- High-token static total: `2941497`
- High-token lazy total: `210627`
- High-token reduction: `92.8395%`
- High-token skipped calls: `34`
- High-token latency avoided: `32980.0 ms`

## Swarm

- Runs: `48`
- Status counts: `{'approval_required': 4, 'succeeded': 40, 'needs_revision': 4}`
- Role event counts: `{'conductor': 48, 'sentinel': 48, 'supervisor': 48, 'cartographer': 44, 'compressor': 44, 'archivist': 44, 'critic': 4}`
- Estimated tokens saved: `667200.0`
- Avoided model calls: `4.0`
- Blocked risk events: `4.0`
- Average expected value score: `0.6175`
