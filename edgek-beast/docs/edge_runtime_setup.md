# Edge Runtime Setup

This is the operational path for turning BEAST's native probes into real packet
experiments and for contrasting cloud APIs against a local NIM deployment.

## 1. Install Native Libraries

```bash
sudo ./scripts/install_native_os_bypass_deps.sh
```

Verify detection:

```bash
PYTHONPATH=. python3 - <<'PY'
import json
from app.kernel.os_bypass import capabilities
print(json.dumps(capabilities(), indent=2))
PY
```

Expected readiness on a prepared Linux host:

- `supported_modes.dpdk: true`
- `supported_modes.af_xdp: true`
- DPDK libraries present: `rte_eal`, `rte_ethdev`, `rte_mempool`
- AF_XDP libraries present: `xdp`, `bpf`

## 2. Prepare Host Permissions

Dry-run first:

```bash
./scripts/configure_os_bypass_host.sh
```

Apply hugepages and process capabilities:

```bash
HUGEPAGES=1024 ./scripts/configure_os_bypass_host.sh --apply
```

To target a specific runtime binary, pass `PYTHON_BIN`:

```bash
PYTHON_BIN=./venv/bin/python HUGEPAGES=1024 ./scripts/configure_os_bypass_host.sh --apply
```

If `vm.nr_hugepages` is accepted but `/proc/meminfo` still reports
`HugePages_Total: 0`, the kernel could not reserve contiguous hugepage memory at
runtime. Reboot with a kernel command-line reservation such as
`default_hugepagesz=2M hugepagesz=2M hugepages=1024`, or reduce `HUGEPAGES` and
try again.

For DPDK packet IO, bind a non-management NIC by PCI address:

```bash
PCI_ADDR=0000:03:00.0 DRIVER=vfio-pci ./scripts/configure_os_bypass_host.sh --apply
```

Do not bind the interface carrying SSH, VPN, or desktop network access. DPDK
takes ownership of the NIC away from the kernel network stack.

Restore a NIC to its kernel driver with:

```bash
sudo dpdk-devbind.py --bind=r8169 0000:03:00.0
```

Replace `r8169` with the original driver shown by `dpdk-devbind.py --status`.

## 3. Probe BEAST Runtime

Start the gateway:

```bash
PYTHONPATH=. uvicorn app.main:app --host 0.0.0.0 --port 8005
```

Probe capabilities:

```bash
curl -sS http://127.0.0.1:8005/edgek/os-bypass/capabilities | python3 -m json.tool
curl -sS -X POST http://127.0.0.1:8005/edgek/os-bypass/dpdk/probe -H 'Content-Type: application/json' -d '{}' | python3 -m json.tool
curl -sS -X POST http://127.0.0.1:8005/edgek/os-bypass/af-xdp/probe -H 'Content-Type: application/json' -d '{"interface":"lo"}' | python3 -m json.tool
```

Interpretation:

- DPDK `opened: true` means EAL initialized. `available_ethdev_ports: 0` means no
  usable DPDK ethdev was discovered. That can mean no NIC is bound, the NIC is
  unsupported by the loaded PMDs, IOMMU is not enabled, or hugepages were not
  reserved.
- AF_XDP `opened: true` means libxdp/libbpf and interface lookup are ready. Full
  packet IO still requires an XDP-capable interface and privileges.

On the current lab host, AF_PACKET TPACKET_V3 opens successfully on `lo`.
DPDK EAL initializes and common PMDs are loaded, but the available RTL8111 NIC
does not appear as a DPDK ethdev; use an Intel i40e/ixgbe/igc or Mellanox mlx5
class NIC for the real DPDK dataplane round.

## 4. Deploy Local NIM On Edge GPU

Run a NIM container on the Jetson or edge GPU host according to the model's NIM
container instructions. Expose its OpenAI-compatible API, commonly as:

```text
http://<edge-gpu-host>:8000/v1
```

From the BEAST host:

```bash
curl -sS http://<edge-gpu-host>:8000/v1/models | python3 -m json.tool
```

The local NIM endpoint is the acceleration layer. BEAST remains the governance
and traffic-management layer in front of it.

## 5. Compare Cloud APIs vs Local NIM

Configure any combination of providers:

```bash
export NVIDIA_API_KEY='...'
export NVIDIA_MODEL='meta/llama-3.1-8b-instruct'
export OPENROUTER_API_KEY='...'
export OPENROUTER_MODEL='meta-llama/llama-3.1-8b-instruct'
export LOCAL_NIM_BASE_URL='http://<edge-gpu-host>:8000/v1'
export LOCAL_NIM_MODEL='<model-served-by-local-nim>'
```

Dry-run payload shaping without provider calls:

```bash
PYTHONPATH=. python3 benchmarks/provider_edge_compare.py --dry-run
```

Live run:

```bash
PYTHONPATH=. python3 benchmarks/provider_edge_compare.py --repeats 3
```

Outputs:

- `benchmarks/results/provider_edge_compare.json`
- `benchmarks/results/provider_edge_compare.md`

The report compares:

- Raw application payloads vs BEAST-governed payloads
- Prompt token reduction from Isolation Forest filtering, context economy, and
  AST/structural compression
- Provider latency and usage for NVIDIA hosted NIM, OpenRouter, and local NIM
- Estimated cloud fee reduction where a per-token fee is configured

## 6. The Argument This Demonstrates

NVIDIA NIM gives accelerated inference. It does not, by itself, decide which
telemetry is redundant, which agent loop should be interrupted, which tool call
should be skipped, or how to reshape high-frequency payloads before they cross a
WAN or hit a model context window.

BEAST sits before NIM or cloud APIs and supplies:

- Isolation Forest outlier filtering
- AST/schema-row compression
- Context economy
- Tool laziness learning
- Circuit breakers
- Budget and forensic records

That is the useful contrast: cloud APIs and stock local NIM are inference
engines; BEAST is the governed edge traffic manager around them.

## 7. Tool Laziness Tuning

Tool laziness should not mean "always skip." It learns per `tool_name` and
`scenario`:

- `skip`: repeated low-value calls with low learned usefulness
- `call`: frequently useful calls
- `call`: rare but high-value calls when a success has a high `value_score`

Record live outcomes with a value signal:

```bash
curl -sS -X POST http://127.0.0.1:8005/edgek/tool-laziness/record \
  -H 'Content-Type: application/json' \
  -d '{
    "tool_name": "provider_call",
    "scenario": "nvidia_telemetry_triage",
    "called": true,
    "useful": true,
    "tokens_spent": 320,
    "cost_usd": 0.00012,
    "latency_ms": 900,
    "value_score": 0.9
  }' | python3 -m json.tool
```

Use `value_score: 0.0` for redundant or throwaway calls and values closer to
`1.0` for calls that prevent mistakes, catch anomalies, or materially improve
the result.
