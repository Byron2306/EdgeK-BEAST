# BEAST Commons Enterprise Verification Report

Date: 2026-07-14

Scope: BEAST, Commons, ARDA appraisal binding, Seraph service registration,
desktop identity propagation, and workload admission. VAMP and Hivenance were
not included.

## Result

Focused enterprise contract suite: **PASS — 49 tests**.

The suite covered:

- persistent Commons registry, vault, chunks, and route damping;
- exact dataset digest and deterministic lineage;
- cryptographically verified, unexpired Commons-node selection and rejection
  of self-reported attestation state;
- Space authority and ARDA appraisal requirements;
- real Ed25519 signature verification and tamper rejection;
- signed ARDA decision binding to the exact canonical Space body;
- fail-closed behavior without verification configuration;
- workspace-identity-bound Commons API mutation;
- service registry validation and atomic config rendering;
- semantic tool bucket/lazy schema exposure;
- bounded resource-lane admission and exclusive keys;
- PSI/interference decisions;
- scheduler-to-executor pressure binding; and
- BEAST CLI compatibility after gateway port convergence.

Command:

```text
pytest -q tests/test_commons_enterprise_api.py tests/test_commons_enterprise_plane.py tests/test_commons_signature_verifier.py tests/test_commons_appraisal_verifier.py tests/test_commons_foundations.py tests/test_artifact_vault.py tests/test_chunk_store.py tests/test_dataset_river.py tests/test_commons_job_choir.py tests/test_space_forge.py tests/test_capability_plane.py tests/test_control_plane_foundations.py tests/test_interference_buckets.py tests/test_agent_scheduler_mission_cockpit.py::test_agent_scheduler_binds_pressure_to_resource_execution tests/test_agent_scheduler_mission_cockpit.py::test_agent_scheduler_escalates_for_low_confidence_implementation tests/test_beast_cli_script.py
```

Python compile gate: **PASS** for the gateway, Commons modules, service
registry, resource executor, Agent Scheduler, CapabilityPlane, and CLI.

Desktop RC4 smoke/visual gate: **PASS**.

- JavaScript files checked: 40
- JavaScript syntax failures: 0
- visual metric scenarios: 110
- visual metric failures: 0
- missing HTML references: 0
- duplicate DOM IDs: 0
- animation runtime: running

Enterprise desktop runtime contract gate: **PASS**.

- registry-owned gateway: `127.0.0.1:8101`
- legacy `8000–8020` compatibility scan: removed
- required control-plane route attestation: enabled
- Electron `gatewayRequest` IPC transport: enabled
- workspace identity header propagation: enabled
- Python interpreter probe includes FastAPI, Uvicorn, cryptography, and YAML

Live probes returned HTTP 200 for:

- `/edgek/control-plane/workspace-identity`
- `/edgek/control-plane/services`
- `/edgek/control-plane/tool-buckets?phase=Observe`
- `/edgek/control-plane/commons`
- `/edgek/control-plane/enterprise`

The live audit also found and fixed two deployment defects: an old `8001`
gateway passed the earlier IDE-only compatibility test, and Electron selected a
Python environment that had FastAPI but lacked `cryptography`. Compatibility
now requires the enterprise routes, and interpreter selection checks the full
gateway dependency boundary. Active-workspace identity uses its startup cache;
non-default Git discovery has a two-second subprocess ceiling so it cannot
freeze the Uvicorn event loop.

Generated registry digest:

```text
sha256:d9182646fb7cf9592cb06e9c3b8cfcb9411d326d6781a5be7c6cb1f58ba05b10
```

Generated configuration:

- `.beast/control-plane/generated/hosts.generated`
- `.beast/control-plane/generated/nginx.generated.conf`

## Honest production boundary

No private signing key was created or packaged. The current repository does
not claim that a production Commons authority trust store, live ARDA appraisal
issuer, administrator-installed hosts/NGINX configuration, cgroup sandbox, or
Seraph containment plane is provisioned. Without the public trust/appraisal
configuration, enterprise admission reports `configuration_required` and
fails closed. This is expected and verified behavior.
