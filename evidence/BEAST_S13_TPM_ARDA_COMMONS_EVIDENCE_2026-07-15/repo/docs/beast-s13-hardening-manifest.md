# BEAST S13 hardening and audit-bundle closure

This manifest is the dependency-closure index for the S13 handoff. It lists
the runtime modules, tests, and documentation required to reproduce the
hardening work. Secrets, private keys, tokens, mutable runtime data, and
`node_modules` are intentionally excluded.

The bundle is sourced from the BEAST working tree represented by the release
manifest in the archive (no absolute workstation paths are retained). The
focused pytest bootstrap dependency `app/kernel/governance/reason.py` and its
direct factory/perception/workspace-graph dependencies are included; the
archive is not a byte-for-byte clone of the full repository.

## Runtime surfaces

- `app/kernel/commons/route_damping.py`
- `app/kernel/sensorium/socket_reconciler.py`
- `app/kernel/compute/crystal_bus.py`
- `app/kernel/compute/sealed_capsule.py`
- `app/kernel/compute/port_conflict_crystal.py`
- `app/kernel/integration/one_use_capability.py`
- `app/kernel/integration/arda_metatron_bridge.py`
- `app/kernel/evidence/control_graph.py`
- `app/kernel/networking/service_registry.py`
- `app/kernel/capability/tool_buckets.py`
- `app/kernel/compute/resource_executor.py`
- `app/kernel/commons/enterprise_plane.py`
- `app/kernel/commons/signature_verifier.py`
- `app/kernel/commons/appraisal_verifier.py`
- `app/kernel/commons/evidence_bridge.py`
- `app/kernel/execution/socket_guardian.py`
- `app/kernel/execution/guardian_authorization.py`
- `app/kernel/execution/socket_guardian_daemon.py`
- `app/kernel/execution/guardian_uvicorn.py`
- `app/kernel/execution/port_lease_broker.py`
- `app/kernel/commons/service_boundary.py`
- `app/commons_main.py`
- `bin/beast`
- `scripts/generate_socket_guardian_units.py`
- `scripts/provision_guardian_validation.py`
- `scripts/check_guardian_authority.py`
- `scripts/accept_guardian_runtime.py`
- `app/kernel/sensorium/journal.py`

## Verification surfaces

- `tests/test_commons_foundations.py`
- `tests/test_socket_reconciler.py`
- `tests/test_crystal_bus_capsule.py`
- `tests/test_port_conflict_crystal.py`
- `tests/test_port_conflict_heldout_matrix.py`
- `tests/test_port_conflict_fixture.py`
- `tests/test_arda_metatron_bridge.py`
- `tests/test_control_evidence_graph.py`
- `tests/test_control_plane_foundations.py`
- `tests/test_capability_plane.py`
- `tests/test_commons_enterprise_plane.py`
- `tests/test_commons_signature_verifier.py`
- `tests/test_commons_appraisal_verifier.py`
- `tests/test_commons_enterprise_api.py`
- `tests/test_socket_guardian.py`
- `tests/test_socket_guardian_production_boundary.py`
- `tests/test_socket_guardian_daemon.py`
- `tests/test_guardian_uvicorn.py`
- `tests/test_commons_service_boundary.py`
- `tests/test_sensorium_journal.py`
- `tests/test_commons_sensorium_integration.py`

The acceptance command is:

```text
pytest -q tests/test_crystal_bus_capsule.py tests/test_arda_metatron_bridge.py tests/test_port_conflict_crystal.py tests/test_commons_foundations.py
```

The enterprise Commons closure is reproduced with:

```text
pytest -q tests/test_commons_enterprise_api.py tests/test_commons_enterprise_plane.py tests/test_commons_signature_verifier.py tests/test_commons_appraisal_verifier.py tests/test_control_plane_foundations.py tests/test_capability_plane.py
```

The restart-safe broker and durable evidence closure is reproduced with:

```text
pytest -q tests/test_socket_guardian.py tests/test_port_lease_broker.py tests/test_sensorium_journal.py tests/test_commons_sensorium_integration.py
```

The server-consumer and retained-listener restart proof is reproduced with:

```text
pytest -q tests/test_guardian_uvicorn.py tests/test_commons_service_boundary.py tests/test_socket_guardian_daemon.py tests/test_socket_guardian_production_boundary.py
```

That focused family completed with 13 passing tests. The broader Guardian,
Sensorium, Commons, evidence, and ARDA bridge selection completed with 66.

The installed host-local validation later completed with 76 BEAST tests and 8
Metatron ARDA authority tests. Live consumer and Guardian replacement receipts
and their hashes are documented in
`docs/beast-guardian-live-validation-2026-07-15.md`.

The expanded Commons/Sensorium family completed with 144 passing tests. The
Socket Guardian tests require permission to create local UNIX/IPv4/IPv6
sockets and inspect `SO_PEERCRED`; they do not require root for the configured
high ports.

The live Electron checklist is maintained separately in
`desktop-ide/docs/LIVE_ELECTRON_RUNTIME_ACCEPTANCE.md`.

The enterprise runtime adds
`desktop-ide/scripts/verify-enterprise-runtime-contract.js`. It rejects legacy
port scanning, missing control-plane route attestation, absent IPC gateway
transport, missing workspace identity propagation, and dependency-incomplete
Python interpreter selection.
