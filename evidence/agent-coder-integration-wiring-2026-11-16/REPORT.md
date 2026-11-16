# Agent Coder integration wiring proof

This is a controlled coordinator proof, not a claim that every optional backend
was live on the host. The production `CoderIntegrationCoordinator` was invoked
with deterministic bounded adapters so every branch could be exercised without
provider, kernel, or network side effects. `proof.jsonl` retains the redacted
normalized receipts emitted by that run.

The proof covers RepoRelay, LongCodeZip, RTK, SQZ, Vector RAG, Memory Hull
recall/seal, crystal reuse, family-crystal lookup, coding-crystal readiness and
candidate production, Crystal Bus eligibility, and swarm selection. The
postflight proof first records the unverified refusal, then the verified seal
and `verified_awaiting_operator_promotion` result. No automatic promotion,
ML-KEM load, XDP/eBPF load, or X7 LSM/ARDA load occurred.

Command:

```text
.venv/bin/python -m pytest -q -s -o log_cli=true --log-cli-level=INFO \
  tests/kernel/agents/test_coder_integrations.py::test_preflight_invokes_every_coding_path_and_emits_redacted_normalized_events \
  tests/kernel/agents/test_coder_integrations.py::test_postflight_seals_memory_and_produces_only_an_unpromoted_crystal_candidate
```

Result: `2 passed in 0.06s`.
