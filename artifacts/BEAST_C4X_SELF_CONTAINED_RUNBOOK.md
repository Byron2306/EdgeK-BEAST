# BEAST C4-X physical truth 12-gate self-contained bundle

This bundle is a runnable proof package for the C4-X physical-truth 12-gate
certificate.

## What is included

- Minimal runnable `app/` runtime needed by the C4-X proof scripts:
  - `app/kernel/**`
  - `app/commons_node_main.py`
  - `app/__init__.py`
- One-shot 12-gate orchestrator:
  - `scripts/run_c4x_full_physical_truth_12_gate_gauntlet.py`
- Component gauntlets for:
  - C4-X physical certificate
  - Sensorium/BPF zero-provider witness
  - protocol/reuse/route
  - Commons ML-KEM
  - Commons replication
  - PQ transport
  - PSI governance
  - XDP scope
  - visual/cross-modal/generation/benchmark evidence paths
- Docker Compose and Commons Dockerfile with liboqs ML-KEM-768 + ML-DSA-65.
- Tests relevant to the certificate and C4-X proof stack.
- Evidence receipts required to verify and rerun the current 12/12 proof,
  including high-velocity AF_XDP receipts used by the XDP scope gate.

## What is intentionally excluded

- Python virtual environments.
- Docker volumes.
- `.git`, worktrees, caches, editor state, and huge local DB/log files.
- Secret-bearing files and likely secret material:
  - `.env`
  - `provider_secrets`
  - `vector.env`
  - `*.pem`
  - `*.key`
  - SQLite/DB runtime files

## Quick start

From the unzipped bundle root:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Start/rebuild Commons nodes:

```bash
docker compose -f docker-compose.commons-lab.yml up -d --build commons-node-a commons-node-b commons-node-c
```

Run the full 12-gate proof:

```bash
.venv/bin/python scripts/run_c4x_full_physical_truth_12_gate_gauntlet.py
```

Expected successful terminal summary:

```json
{
  "status": "passed",
  "green_count": 12,
  "red_gates": [],
  "public_credit_allowed": true
}
```

## Privileged harvest option

The normal one-shot command reuses the included privileged sidecar receipts.
To refresh privileged BPF/XDP/memfd/Guardian evidence on a real local Linux
terminal, prime sudo yourself and run:

```bash
sudo -v
.venv/bin/python scripts/run_c4x_full_physical_truth_12_gate_gauntlet.py \
  --include-sudo-harvest \
  --skip-sudo
```

Do not pass sudo passwords through command-line arguments, pipes, logs, or
automation transcripts.

## Verification-only path

If Docker is unavailable, you can still verify the certificate engine and
included final evidence:

```bash
.venv/bin/python -m pytest tests/test_c4x_physical_truth_certificate.py -q
.venv/bin/python scripts/run_c4x_physical_truth_certificate.py \
  --sidecar evidence/c4x-physical-truth-certificate/physical_truth_sidecar_harvested.json \
  --run-id local-verification-only
```

The full PQ/Commons gates require Docker and the Commons lab containers.

## Core claim boundary

The umbrella one-shot receipt does not override failed evidence. Authority
still comes from the component receipts and the final physical-truth
certificate. If any gate is missing or red, the one-shot runner exits non-zero.
