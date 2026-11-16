"""Experimental Task 5: ARDA-admitted XDP fast path — userspace simulation (default-off, BEAST_XDP_FASTPATH_SIM).

Mirrors bpf/beast_x6_admitted_fastpath.bpf.c decision-for-decision over map *snapshots*, so the policy can be
tested without root. Nothing here loads, attaches, reads or writes a BPF program or map: the ARDA snapshot comes
from ARDA's own read-only restore record (/run/arda/ring0-restore.json) and the flow writer only emits the
``bpftool map update`` command for the operator.

Policy is ARDA's, not a parallel one: a flow takes the fast path only while ARDA is not in lockdown, no redline is
triggered, the consumer cgroup still holds the ARDA active generation it was admitted under, and ARDA's policy
generation prefix is unchanged. Any change falls back to the kernel stack (XDP_PASS). Nothing is ever dropped.
"""
from __future__ import annotations

import ipaddress
import json
import os
import struct
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SIM_ENV = "BEAST_XDP_FASTPATH_SIM"
PASS, REDIRECT = "XDP_PASS", "XDP_REDIRECT"
LOCKDOWN_DENY_ALL = 1
REDLINE_TRIGGERED = 2
KEY = struct.Struct("!4s4sHHB3x")          # struct beast_flow_key (wire order, as copied from the packet)
VALUE = struct.Struct("<QQQQQQ")            # struct beast_flow_admission (host little-endian u64s)
PIN_ARDA = "/sys/fs/bpf/arda"
PIN_X6 = "/sys/fs/bpf/beast/x6"
REPO_ROOT = Path(__file__).resolve().parents[3]
OBJECT = str(REPO_ROOT / "bpf" / "build" / "beast_x6_admitted_fastpath.bpf.o")
NETNS_SCRIPT = str(REPO_ROOT / "scripts" / "x3_lab_netns.sh")
WORKER = str(REPO_ROOT / "bpf" / "build" / "beast_x3_af_xdp_worker")
ARDA_REUSE = (("arda_lockdown_map", "lockdown_map"), ("arda_policy_state_map", "policy_state_map"),
              ("arda_active_generation_map", "active_generation_map"))
# libbpf map-reuse compatibility: (bpftool type, key bytes, value bytes, max_entries, flags) from the ARDA object.
ARDA_EXPECTED = {"lockdown_map": ("array", 4, 4, 1, 0), "policy_state_map": ("array", 4, 16, 1, 0),
                 "active_generation_map": ("hash", 8, 8, 1024, 0)}


def sim_enabled(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return str(env.get(SIM_ENV, "")).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class ArdaSnapshot:
    lockdown: int
    projection_flags: int
    generation_hash_prefix: int
    active_generation: dict[int, int]
    source: str = ""
    lockdown_inferred: bool = False

    @classmethod
    def from_restore_json(cls, path: str | Path = "/run/arda/ring0-restore.json") -> ArdaSnapshot:
        data = json.loads(Path(path).read_text(encoding="utf-8"))  # read-only
        policy = data.get("policy_state") or {}
        active = data.get("active_generation") or {}
        generations = {int(active["cgroup_kernel_id"]): int(active["generation"])} if active else {}
        # The restore record carries no lockdown value: treat lockdown as DENY_ALL unless ARDA reported ok.
        return cls(lockdown=0 if data.get("ok") is True else LOCKDOWN_DENY_ALL,
                   projection_flags=int(policy.get("projection_flags") or 0),
                   generation_hash_prefix=int(policy.get("generation_hash_prefix") or 0),
                   active_generation=generations, source=str(path), lockdown_inferred=True)


def _dump_rows(text: str) -> list[tuple[Any, Any]]:
    rows = json.loads(text) if text.strip() else []
    return [(row.get("key"), row.get("value")) for row in rows if isinstance(row, Mapping)]


def _as_int(value: Any) -> int:
    if isinstance(value, list):  # bpftool without BTF: little-endian byte list ["0x48", ...]
        return int.from_bytes(bytes(int(str(b), 16) for b in value), "little")
    return int(value)


def _policy(value: Any) -> tuple[int, int]:
    if isinstance(value, list):
        raw = bytes(int(str(b), 16) for b in value)
        return int.from_bytes(raw[0:8], "little"), int.from_bytes(raw[12:16], "little")
    return int(value["generation_hash_prefix"]), int(value["projection_flags"])


def _snapshot_from_dumps(active_json: str, policy_json: str, lockdown_json: str) -> ArdaSnapshot:
    active = {_as_int(k): _as_int(v) for k, v in _dump_rows(active_json)}
    policy_rows = _dump_rows(policy_json)
    lockdown_rows = _dump_rows(lockdown_json)
    prefix, flags = _policy(policy_rows[0][1]) if policy_rows else (0, REDLINE_TRIGGERED)
    lockdown = _as_int(lockdown_rows[0][1]) if lockdown_rows else LOCKDOWN_DENY_ALL
    return ArdaSnapshot(lockdown=lockdown, projection_flags=flags, generation_hash_prefix=prefix,
                        active_generation=active, source="bpftool map dump (operator)", lockdown_inferred=False)


ArdaSnapshot.from_bpftool_dumps = staticmethod(_snapshot_from_dumps)  # type: ignore[attr-defined]


def udp_frame(saddr: str, daddr: str, sport: int, dport: int, payload: bytes = b"beast") -> bytes:
    eth = b"\x02" * 6 + b"\x04" * 6 + b"\x08\x00"
    udp = struct.pack("!HHHH", sport, dport, 8 + len(payload), 0) + payload
    ip = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + len(udp), 0, 0, 64, 17, 0,
                     ipaddress.IPv4Address(saddr).packed, ipaddress.IPv4Address(daddr).packed)
    return eth + ip + udp


def flow_key(saddr: str, daddr: str, sport: int, dport: int) -> bytes:
    return KEY.pack(ipaddress.IPv4Address(saddr).packed, ipaddress.IPv4Address(daddr).packed, sport, dport, 17)


@dataclass
class FastPathSimulator:
    snapshot: ArdaSnapshot
    env: Mapping[str, str] | None = None
    xsk_queues: set[int] = field(default_factory=lambda: {0})
    clock_ns: Callable[[], int] = time.monotonic_ns   # same clock as bpf_ktime_get_ns (CLOCK_MONOTONIC)
    flows: dict[bytes, tuple[int, ...]] = field(default_factory=dict)
    stats: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not sim_enabled(self.env):
            raise PermissionError(f"XDP fast-path simulation is disabled (set {SIM_ENV}=1)")

    def _count(self, reason: str, action: str) -> tuple[str, str]:
        self.stats[reason] = self.stats.get(reason, 0) + 1
        return action, reason

    def decide(self, frame: bytes, rx_queue: int = 0) -> tuple[str, str]:
        """Same parse offsets and branch order as beast_x6_admitted_fastpath."""
        if len(frame) < 14 or frame[12] != 0x08 or frame[13] != 0x00:
            return PASS, "not_udp_ipv4"
        if len(frame) < 34:
            return PASS, "not_udp_ipv4"
        ihl = (frame[14] & 0x0F) * 4
        if ihl < 20 or 14 + ihl + 8 > len(frame) or frame[23] != 17:
            return PASS, "not_udp_ipv4"
        snap = self.snapshot
        if snap.lockdown == LOCKDOWN_DENY_ALL:
            return self._count("arda_lockdown", PASS)
        if snap.projection_flags & REDLINE_TRIGGERED:
            return self._count("arda_redline_triggered", PASS)
        udp = 14 + ihl
        key = frame[26:30] + frame[30:34] + frame[udp:udp + 2] + frame[udp + 2:udp + 4] + b"\x11\x00\x00\x00"
        flow = self.flows.get(key)
        if flow is None:
            return self._count("miss", PASS)
        cgroup_id, generation, prefix, _lease_gen, _receipt, expires_ns = flow
        if self.clock_ns() > expires_ns:
            return self._count("expired", PASS)
        live = snap.active_generation.get(cgroup_id)
        if not live or live != generation:
            return self._count("arda_generation_mismatch", PASS)
        if snap.generation_hash_prefix != prefix:
            return self._count("arda_policy_prefix_mismatch", PASS)
        if rx_queue not in self.xsk_queues:
            return self._count("no_xsk", PASS)
        return self._count("admitted", REDIRECT)


ARDA_MEASURED_FALLBACK = 3144  # /run/arda/ring0-restore.json current_cgroup_kernel_id = system.slice/arda-ring0.service


def check_cgroup(snapshot: ArdaSnapshot, cgroup_id: int, *, source: str = "",
                 arda_measured: int | None = None) -> dict[str, Any]:
    """Is this cgroup eligible for a fast-path admission? ARDA's active_generation_map is the only authority."""
    generation = snapshot.active_generation.get(int(cgroup_id))
    out: dict[str, Any] = {"cgroup_id": int(cgroup_id), "source": source, "eligible": bool(generation),
                           "generation": generation or 0, "active_entries": len(snapshot.active_generation)}
    if not generation:
        measured = int(arda_measured or ARDA_MEASURED_FALLBACK)
        in_map = measured in snapshot.active_generation
        out["suggestion"] = (f"cgroup {cgroup_id} ({source}) is not in ARDA's active_generation_map. For the lab, re-run "
                             f"with --cgroup arda-measured ({measured}, ARDA's measured scope"
                             f"{'' if in_map else '; NOT in the map either'}) or register the consumer with ARDA.")
        out["note"] = ("The cgroup in an admission is a revocation handle, not a packet filter: XDP sees no cgroup at "
                       "ingress. Binding to ARDA's measured scope means any ARDA regeneration/rotation of that scope "
                       "revokes the flow, but it attests ARDA's own service, not the consumer workload; production "
                       "admissions should bind the consumer's cgroup once ARDA measures it.")
    return out


class AdmittedFlowWriter:
    """The only writer of beast_admitted_flows: verified Guardian lease + ARDA-admitted cgroup + Governor admit."""

    def __init__(self, sim: FastPathSimulator, *, governor: Any, lease_verifier: Callable[[Any], Mapping[str, Any]],
                 env: Mapping[str, str] | None = None, clock_ns: Callable[[], int] = time.monotonic_ns):
        if not sim_enabled(env):
            raise PermissionError(f"XDP fast-path simulation is disabled (set {SIM_ENV}=1)")
        self.sim, self.governor, self.lease_verifier, self.clock_ns = sim, governor, lease_verifier, clock_ns

    def admit(self, saddr: str, daddr: str, sport: int, dport: int, *, lease: Any, ttl_s: float) -> dict[str, Any]:
        from app.kernel.governance.governor_spine import Episode, Proposal

        verified = dict(self.lease_verifier(lease) or {})
        if verified.get("verified") is not True:
            raise PermissionError("XDP fast path requires a verified Guardian lease")
        snap = self.sim.snapshot
        if snap.lockdown == LOCKDOWN_DENY_ALL or snap.projection_flags & REDLINE_TRIGGERED:
            raise PermissionError("ARDA lockdown/redline active; fast path admission refused")
        cgroup_id = int(verified.get("cgroup_id") or 0)
        generation = snap.active_generation.get(cgroup_id)
        if not generation:
            raise PermissionError(f"cgroup {cgroup_id} holds no ARDA active generation; refusing fast path")
        key = flow_key(saddr, daddr, sport, dport)
        proposal = Proposal(kind="deterministic_tool", tool_id="xdp_fastpath:admit_flow", targets=(key.hex(),),
                            signature_material={"flow": key.hex(), "cgroup": cgroup_id, "generation": generation,
                                                "lease": str(verified.get("lease_id") or "")},
                            estimate={"tool_calls": 1.0})
        decision = self.governor.admit(Episode(run_id=f"xdp-flow:{key.hex()}"), proposal)

        def run() -> dict[str, Any]:
            receipt_prefix = int((decision.receipt_hash or "sha256:" + "0" * 16).split(":", 1)[-1][:16], 16)
            value = (cgroup_id, generation, snap.generation_hash_prefix, int(verified.get("lease_generation") or 0),
                     receipt_prefix, self.clock_ns() + int(ttl_s * 1e9))
            self.sim.flows[key] = value
            value_hex = VALUE.pack(*value).hex()
            return {"key_hex": key.hex(), "value_hex": value_hex, "cgroup_id": cgroup_id,
                    "arda_generation": generation, "generation_hash_prefix": snap.generation_hash_prefix,
                    "expires_ns": value[-1],
                    "governor": {"outcome": decision.outcome, "receipt_id": decision.receipt_id},
                    "bpftool_update": (f"sudo bpftool map update pinned {PIN_X6}/beast_admitted_flows key hex "
                                       f"{_spaced(key.hex())} value hex {_spaced(value_hex)} any")}

        return self.governor.run_admitted(decision, proposal, run)


# Counter keys of the X6 `stats` PERCPU_ARRAY (enum order in bpf/beast_x6_admitted_fastpath.bpf.c).
STAT_NAMES: tuple[tuple[str, str], ...] = (
    ("seen", "IPv4/UDP frames evaluated by the gate (= redirect + all PASS reasons below)"),
    ("redirect", "FAST PATH: admitted, ARDA-current flow redirected to the AF_XDP socket"),
    ("lockdown", "fallback PASS: ARDA lockdown deny-all (or lockdown map unreadable)"),
    ("redline", "fallback PASS: ARDA policy redline triggered (or policy map unreadable)"),
    ("miss", "PASS: flow not admitted -> normal kernel stack"),
    ("expired", "PASS: admission TTL expired"),
    ("generation", "PASS: cgroup absent from ARDA active generation, or generation moved"),
    ("hash_prefix", "PASS: ARDA generation hash prefix changed since admission"),
    ("no_xsk", "PASS: admitted + ARDA-current but no AF_XDP socket on this RX queue (load+attach without worker)"),
)
# July X3 AF_XDP echo receipt (generic XDP, copy mode, 512 B, 1000 pps, 10 s, 10000/10000 echoed).
X3_BASELINE = {"receipt": "evidence/high_velocity_fabric/x3_af_xdp_echo_20260720T113948Z.json",
               "p50_latency_us": 117.065, "p95_latency_us": 268.057, "p99_latency_us": 314.496,
               "packet_size": 512, "packets_per_second": 1000, "duration_s": 10, "mode": "af_xdp_copy_echo"}
LAB_FLOW = ("10.203.0.1", "10.203.0.2", 40000, 45678)  # X3 echo port; the sender binds the admitted sport

_ECHO_RX_PY = r"""import json,socket,sys,time
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.bind((sys.argv[1],int(sys.argv[2]))); s.settimeout(.2)
end=time.monotonic()+float(sys.argv[3]); n=0
while time.monotonic()<end:
    try:
        d,a=s.recvfrom(65535); n+=1; s.sendto(d,a)
    except TimeoutError: pass
print(json.dumps({"kernel_echoed":n}))"""

_ECHO_TX_PY = r"""import json,socket,sys,time
saddr,daddr=sys.argv[1],sys.argv[2]; sport,dport=int(sys.argv[3]),int(sys.argv[4])
sec,pps,size=float(sys.argv[5]),float(sys.argv[6]),int(sys.argv[7])
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
s.bind((saddr, sport)); s.settimeout(.5)
payload=b"B"*size; interval=1.0/pps; end=time.monotonic()+sec; nxt=time.monotonic(); sent=got=0; lat=[]
while time.monotonic()<end:
    t=time.perf_counter_ns(); s.sendto(payload,(daddr,dport)); sent+=1
    try:
        s.recvfrom(65535); got+=1; lat.append((time.perf_counter_ns()-t)/1000)
    except TimeoutError: pass
    nxt+=interval; d=nxt-time.monotonic()
    if d>0: time.sleep(d)
lat.sort()
def q(p): return round(lat[min(len(lat)-1,int((len(lat)-1)*p))],3) if lat else 0
print(json.dumps({"flow":[saddr,daddr,sport,dport],"packet_size":size,"packets_per_second":pps,"duration_s":sec,
  "packets_sent":sent,"packets_echoed":got,"echo_drops":sent-got,
  "p50_latency_us":q(.50),"p95_latency_us":q(.95),"p99_latency_us":q(.99)}))"""

_STATS_PY = r"""import json,sys
names=json.loads(sys.argv[1]); rows=json.load(sys.stdin)
def num(v):
    if isinstance(v,dict): v=v.get("formatted",v.get("value",0))
    if isinstance(v,bool): return int(v)
    if isinstance(v,int): return v
    if isinstance(v,list): return int.from_bytes(bytes(int(x,16) for x in v),"little")
    return int(v,0) if isinstance(v,str) else 0
tot={}
for r in rows:
    r=r.get("formatted",r)
    vals=r.get("values",[])
    tot[num(r["key"])]=sum(num(c.get("value",c)) for c in vals) if isinstance(vals,list) else num(vals)
for i,(n,meaning) in enumerate(names):
    print(f"  {i} {n:<12}{tot.get(i,0):>12}  {meaning}")
seen=tot.get(0,0); fast=tot.get(1,0); passed=sum(tot.get(i,0) for i in range(2,len(names)))
inv="ok" if seen==fast+passed else "MISMATCH"
print(f"  fastpath={fast} fallback_or_pass={passed} seen={seen} invariant(seen==fastpath+pass)={inv}")
print(json.dumps({"seen":seen,"fastpath":fast,"fallback_or_pass":passed,"by_name":{n:tot.get(i,0) for i,(n,_) in enumerate(names)}}))"""

_COMPARE_PY = r"""import json,sys
r=json.loads(sys.argv[1]); base=json.loads(sys.argv[2]); r["mode"]=sys.argv[3]; r["label"]=sys.argv[4]
r["baseline_x3_july"]=base; r["p50_delta_vs_x3_us"]=round(r["p50_latency_us"]-base["p50_latency_us"],3)
r["like_for_like"]=sys.argv[3]=="afxdp" and r["packet_size"]==base["packet_size"] and r["packets_per_second"]==base["packets_per_second"]
r["claim_boundary"]=("AF_XDP echo through the ARDA-gated X6 program; comparable to the July X3 AF_XDP echo" if r["like_for_like"] else
  "kernel UDP echo (X6 gate PASSes admitted flow: no_xsk); measures gate overhead on the kernel path, not AF_XDP redirect")
print(json.dumps(r,indent=2,sort_keys=True))"""


def _spaced(hexstr: str) -> str:
    return " ".join(hexstr[i:i + 2] for i in range(0, len(hexstr), 2))


def operator_commands(repo: Path | str = REPO_ROOT) -> list[str]:
    """Privileged steps for Byron (run by hand; BEAST never runs them). Absolute paths: works from any directory."""
    script = f"{Path(repo)}/.beast/generated/xdp-x6/run-x6-lab.sh"
    obj = f"{Path(repo)}/bpf/build/beast_x6_admitted_fastpath.bpf.o"
    reuse = " ".join(f"map name {name} pinned {PIN_ARDA}/{pin}" for name, pin in ARDA_REUSE)
    return [
        "# 0. bpftool is not installed on this host; install it (distro bpftool / linux-tools) first",
        f"make -C {Path(repo)}/bpf beast-x6-object   # unprivileged; object already built",
        f"sudo {script} precheck    # read-only: ARDA pins + map-reuse compatibility",
        f"sudo {script} up          # = sudo {Path(repo)}/scripts/x3_lab_netns.sh up",
        f"sudo {script} load        # = sudo bpftool prog loadall {obj} {PIN_X6}/progs type xdp {reuse} pinmaps {PIN_X6}",
        f"sudo {script} attach      # nsenter --net=/var/run/netns/beast-x3-rx bpftool net attach xdpgeneric ...",
        f"sudo {script} cgroup-check   # consumer unit's cgroup in ARDA active_generation_map? (else suggests arda-measured)",
        f"sudo {script} admit       # --cgroup consumer (default) | arda-measured | /path | ID; lab flow 10.203.0.1:40000 -> 10.203.0.2:45678",
        f"sudo {script} traffic kernel 10 1000 512   # X3-shaped echo RTT on the admitted flow",
        f"sudo {script} stats       # per-key counters by name (fastpath vs fallback PASS reasons)",
        f"sudo {script} detach",
        f"sudo {script} down        # detach, rm -rf {PIN_X6} only, netns down; never touches {PIN_ARDA}",
        f"sudo {script} sequence [kernel|afxdp]   # full run: precheck up load baseline attach admit traffic stats "
        "detach down (cleanup on error)",
    ]


def _script(repo: Path) -> str:
    reuse_bpftool = " ".join(f'map name {name} pinned "$ARDA_PINS/{pin}"' for name, pin in ARDA_REUSE)
    reuse_worker = " ".join(f'--reuse-pin={name}="$ARDA_PINS/{pin}"' for name, pin in ARDA_REUSE)
    expected = json.dumps({k: list(v) for k, v in ARDA_EXPECTED.items()})
    lab_s, lab_d, lab_sp, lab_dp = LAB_FLOW
    echo_rx, echo_tx, stats_py, compare = _ECHO_RX_PY, _ECHO_TX_PY, _STATS_PY, _COMPARE_PY
    stat_names = json.dumps([list(x) for x in STAT_NAMES])
    baseline_receipt, baseline_json = X3_BASELINE["receipt"], json.dumps(X3_BASELINE)
    fallback = ARDA_MEASURED_FALLBACK
    for embedded in (echo_rx, echo_tx, stats_py, compare, stat_names, baseline_json):
        assert "'" not in embedded, "embedded helpers are single-quoted in bash"
    return f"""#!/usr/bin/env bash
# BEAST X6 ARDA-admitted XDP fast path: operator lab driver (generated; run with sudo, from any directory).
# Reads ARDA's pinned maps only; every write/removal is confined to $X6. Never touches $ARDA_PINS beyond read/reuse.
set -euo pipefail
REPO="${{REPO:-{repo}}}"
readonly ARDA_PINS=/sys/fs/bpf/arda
readonly X6=/sys/fs/bpf/beast/x6
OBJ="$REPO/bpf/build/beast_x6_admitted_fastpath.bpf.o"
NETNS=beast-x3-rx
NETNS_PATH=/var/run/netns/$NETNS
BPFTOOL="${{BPFTOOL:-bpftool}}"
PY="$REPO/.venv/bin/python"
RUN_AS="${{SUDO_USER:-$(id -un)}}"
cd "$REPO"   # python -m and relative tooling resolve from the repo root regardless of the caller's cwd

need_root() {{ [[ $EUID -eq 0 ]] || {{ echo "run with sudo" >&2; exit 77; }}; }}
need_bpftool() {{ command -v "$BPFTOOL" >/dev/null || {{ echo "bpftool not found (install distro bpftool)" >&2; exit 69; }}; }}
as_user() {{ if [[ $EUID -eq 0 && "$RUN_AS" != root ]]; then sudo -u "$RUN_AS" -- "$@"; else "$@"; fi; }}
CONSUMER_UNIT="${{CONSUMER_UNIT:-beast-beast-guardian-consumer.service}}"
ARDA_RESTORE=/run/arda/ring0-restore.json

# --cgroup consumer (default) | arda-measured | /cgroup/path | numeric id   (env CGROUP= also works)
parse_cgroup_args() {{
  CG_CHOICE="${{CGROUP:-consumer}}"; REST=()
  while (($#)); do
    case "$1" in
      --cgroup) CG_CHOICE="${{2:?--cgroup needs a value}}"; shift 2 ;;
      --cgroup=*) CG_CHOICE="${{1#--cgroup=}}"; shift ;;
      *) REST+=("$1"); shift ;;
    esac
  done
}}
arda_measured_id() {{ python3 -c 'import json,sys; print(int(json.load(open(sys.argv[1]))["current_cgroup_kernel_id"]))' "$ARDA_RESTORE" 2>/dev/null || echo {fallback}; }}
resolve_cgroup() {{  # prints "ID SOURCE"; never the sudo shell's own cgroup
  local choice="$1" path uid
  case "$choice" in
    consumer)
      uid="$(id -u "$RUN_AS")"
      path="$(as_user env XDG_RUNTIME_DIR=/run/user/$uid systemctl --user show -p ControlGroup --value "$CONSUMER_UNIT" 2>/dev/null || true)"
      if [[ -z "$path" || ! -d "/sys/fs/cgroup$path" ]]; then
        echo "cannot resolve $CONSUMER_UNIT for $RUN_AS; choose explicitly: --cgroup arda-measured | /cgroup/path | ID" >&2; return 66
      fi
      echo "$(stat -c %i "/sys/fs/cgroup$path") consumer:$CONSUMER_UNIT" ;;
    arda-measured) echo "$(arda_measured_id) arda-measured:system.slice/arda-ring0.service" ;;
    /*)
      if [[ "$choice" == *..* || ! -d "/sys/fs/cgroup$choice" ]]; then echo "no such cgroup path: $choice" >&2; return 64; fi
      echo "$(stat -c %i "/sys/fs/cgroup$choice") path:$choice" ;;
    *)
      [[ "$choice" =~ ^[0-9]+$ ]] || {{ echo "--cgroup must be consumer|arda-measured|/cgroup/path|numeric id" >&2; return 64; }}
      echo "$choice explicit" ;;
  esac
}}
dump_arda() {{  # read-only map dumps into $1
  "$BPFTOOL" -j map dump pinned "$ARDA_PINS/active_generation_map" > "$1/active.json"
  "$BPFTOOL" -j map dump pinned "$ARDA_PINS/policy_state_map" > "$1/policy.json"
  "$BPFTOOL" -j map dump pinned "$ARDA_PINS/lockdown_map" > "$1/lockdown.json"
  chmod 644 "$1"/*.json
}}
cgroup_gate() {{  # $1 dir $2 id $3 source: refuse (65) unless the id is in ARDA's active_generation_map
  as_user env BEAST_XDP_FASTPATH_SIM=1 HOME="$REPO/.beast/tmp-home" "$PY" -m app.kernel.networking.xdp_fastpath_sim cgroup-check \
    --active "$1/active.json" --policy "$1/policy.json" --lockdown "$1/lockdown.json" \
    --cgroup "$2" --source "$3" --arda-measured "$(arda_measured_id)"
}}

cmd="${{1:-help}}"; shift || true
case "$cmd" in
  precheck)
    need_root; need_bpftool
    [[ -f "$OBJ" ]] || as_user make -C "$REPO/bpf" beast-x6-object
    ls -l "$ARDA_PINS"
    for pin in lockdown_map policy_state_map active_generation_map; do
      "$BPFTOOL" -j map show pinned "$ARDA_PINS/$pin" > "/tmp/beast-x6-$pin.show.json"
    done
    python3 - '{expected}' <<'PY'
import json, sys
expected = json.loads(sys.argv[1]); ok = True
for pin, (kind, key, value, entries, flags) in expected.items():
    got = json.load(open(f"/tmp/beast-x6-{{pin}}.show.json"))
    have = (got.get("type"), got.get("bytes_key"), got.get("bytes_value"), got.get("max_entries"), got.get("flags", 0))
    match = have == (kind, key, value, entries, flags); ok &= match
    print(f"{{pin}}: pinned={{have}} x6={{(kind, key, value, entries, flags)}} {{'MATCH' if match else 'MISMATCH'}}")
sys.exit(0 if ok else 65)
PY
    ;;
  up)
    need_root; "$REPO/scripts/x3_lab_netns.sh" up ;;
  load)
    need_root; need_bpftool
    [[ -f "$OBJ" ]] || as_user make -C "$REPO/bpf" beast-x6-object
    mkdir -p "$X6"
    "$BPFTOOL" prog loadall "$OBJ" "$X6/progs" type xdp {reuse_bpftool} pinmaps "$X6"
    "$BPFTOOL" prog show pinned "$X6/progs/beast_x6_admitted_fastpath" ;;
  attach)
    need_root; need_bpftool
    nsenter --net="$NETNS_PATH" "$BPFTOOL" net attach xdpgeneric pinned "$X6/progs/beast_x6_admitted_fastpath" dev eth0
    nsenter --net="$NETNS_PATH" ip -d link show dev eth0 | grep -i xdp || true ;;
  resolve-cgroup)
    parse_cgroup_args "$@"; resolve_cgroup "$CG_CHOICE" ;;
  cgroup-check)
    need_root; need_bpftool
    parse_cgroup_args "$@"
    res="$(resolve_cgroup "$CG_CHOICE")"; read -r cgid src <<< "$res"
    tmp="$(mktemp -d)"; chmod 755 "$tmp"; trap 'rm -rf "$tmp"' EXIT
    dump_arda "$tmp"; cgroup_gate "$tmp" "$cgid" "$src" ;;
  admit|flow)
    need_root; need_bpftool
    parse_cgroup_args "$@"; set -- "${{REST[@]}}"
    saddr="${{1:-{lab_s}}}"; daddr="${{2:-{lab_d}}}"; sport="${{3:-{lab_sp}}}"; dport="${{4:-{lab_dp}}}"; ttl="${{5:-120}}"
    res="$(resolve_cgroup "$CG_CHOICE")"; read -r cgid src <<< "$res"
    tmp="$(mktemp -d)"; chmod 755 "$tmp"; trap 'rm -rf "$tmp"' EXIT
    dump_arda "$tmp"
    cgroup_gate "$tmp" "$cgid" "$src"
    # fresh AdmittedFlowWriter entry (Governor-admitted, ARDA generation + hash prefix read now)
    update="$(as_user env BEAST_XDP_FASTPATH_SIM=1 HOME="$REPO/.beast/tmp-home" "$PY" -m app.kernel.networking.xdp_fastpath_sim flow \
      --active "$tmp/active.json" --policy "$tmp/policy.json" --lockdown "$tmp/lockdown.json" \
      --cgroup "$cgid" --flow "$saddr" "$daddr" "$sport" "$dport" --ttl "$ttl")"
    echo "admitting $saddr:$sport -> $daddr:$dport for ${{ttl}}s (cgroup $cgid, $src): $update"
    case "$update" in "sudo bpftool map update pinned $X6/beast_admitted_flows "*) ;; *) echo "refusing unexpected command" >&2; exit 65 ;; esac
    eval "${{update#sudo }}"
    "$BPFTOOL" map dump pinned "$X6/beast_admitted_flows" ;;
  traffic)
    need_root
    mode="${{1:-kernel}}"; sec="${{2:-10}}"; pps="${{3:-1000}}"; size="${{4:-512}}"; label="${{5:-$mode}}"
    read -r saddr daddr sport dport <<< "${{FLOW:-{lab_s} {lab_d} {lab_sp} {lab_dp}}}"
    case "$mode" in
      kernel)
        ip netns exec beast-x3-rx python3 -c '{echo_rx}' "$daddr" "$dport" "$((sec + 2))" > /tmp/beast-x6-rx.json &
        helper=$! ;;
      afxdp)
        need_bpftool
        [[ -e "$X6/beast_admitted_flows" ]] || {{ echo "run load + admit first" >&2; exit 66; }}
        as_user make -C "$REPO/bpf" beast-x3-worker
        if ldd "$REPO/bpf/build/beast_x3_af_xdp_worker" | grep -q "not found"; then
          echo "worker cannot run: libxdp missing (sudo apt install libxdp-dev, then re-run)" >&2; exit 69
        fi
        nsenter --net="$NETNS_PATH" "$BPFTOOL" net detach xdpgeneric dev eth0 2>/dev/null || true
        nsenter --net="$NETNS_PATH" "$REPO/bpf/build/beast_x3_af_xdp_worker" --interface eth0 --object "$OBJ" \
          --program beast_x6_admitted_fastpath --generic-xdp --echo --duration "$((sec + 2))" \
          {reuse_worker} --reuse-pin=beast_admitted_flows="$X6/beast_admitted_flows" --reuse-pin=stats="$X6/stats" \
          > /tmp/beast-x6-worker.json &
        helper=$! ;;
      *) echo "traffic mode must be kernel|afxdp" >&2; exit 64 ;;
    esac
    sleep 0.5
    result="$(ip netns exec beast-x3-tx python3 -c '{echo_tx}' "$saddr" "$daddr" "$sport" "$dport" "$sec" "$pps" "$size")"
    wait "$helper" || true
    baseline="$(python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); print(json.dumps({{k: r["result"][k] for k in ("p50_latency_us","p95_latency_us","p99_latency_us")}} | {{"receipt": sys.argv[1], "packet_size": 512, "packets_per_second": 1000}}))' \
      "$REPO/{baseline_receipt}" 2>/dev/null || echo '{baseline_json}')"
    runs="$REPO/.beast/generated/xdp-x6/runs"; as_user mkdir -p "$runs"
    out="$runs/x6-$label-$(date -u +%Y%m%dT%H%M%SZ).json"
    python3 -c '{compare}' "$result" "$baseline" "$mode" "$label" | as_user tee "$out"
    echo "receipt: $out" ;;
  worker)
    need_root; duration="${{1:-10}}"
    [[ -x "$REPO/bpf/build/beast_x3_af_xdp_worker" ]] || {{ echo "worker not built (needs libxdp-dev)" >&2; exit 69; }}
    mkdir -p "$X6/worker"
    nsenter --net="$NETNS_PATH" "$REPO/bpf/build/beast_x3_af_xdp_worker" --interface eth0 --object "$OBJ" \
      --program beast_x6_admitted_fastpath --generic-xdp --echo --duration "$duration" \
      {reuse_worker} --pin-dir "$X6/worker" --pin-map beast_admitted_flows ;;
  stats)
    need_root; need_bpftool
    echo "X6 stats (summed over CPUs):"
    "$BPFTOOL" -j map dump pinned "$X6/stats" | python3 -c '{stats_py}' '{stat_names}'
    echo "admitted flows:"; "$BPFTOOL" map dump pinned "$X6/beast_admitted_flows" || true ;;
  detach)
    need_root; need_bpftool
    nsenter --net="$NETNS_PATH" "$BPFTOOL" net detach xdpgeneric dev eth0 || true
    nsenter --net="$NETNS_PATH" ip -d link show dev eth0 | grep -i xdp || echo "eth0: no XDP attached" ;;
  sequence)
    need_root; need_bpftool
    parse_cgroup_args "$@"
    mode="${{REST[0]:-kernel}}"; cg_args=(--cgroup "$CG_CHOICE")
    cleanup_lab() {{ trap - EXIT INT TERM; echo "sequence aborted: tearing the X6 lab down" >&2; "$0" down || true; }}
    trap cleanup_lab EXIT INT TERM
    "$0" precheck
    "$0" cgroup-check "${{cg_args[@]}}"
    "$0" up
    "$0" load
    "$0" traffic kernel 10 1000 512 baseline-no-xdp
    "$0" attach
    "$0" admit "${{cg_args[@]}}"
    "$0" traffic kernel 10 1000 512 x6-gate-kernel
    "$0" stats
    if [[ "$mode" == afxdp ]]; then
      "$0" admit "${{cg_args[@]}}"
      "$0" traffic afxdp 10 1000 512 x6-afxdp
      "$0" stats
    fi
    "$0" detach
    trap - EXIT INT TERM
    "$0" down ;;
  down)
    need_root
    if [[ -e "$NETNS_PATH" ]] && command -v "$BPFTOOL" >/dev/null; then
      nsenter --net="$NETNS_PATH" "$BPFTOOL" net detach xdpgeneric dev eth0 || true
    fi
    [[ "$X6" == /sys/fs/bpf/beast/x6 ]] && rm -rf -- "$X6"
    "$REPO/scripts/x3_lab_netns.sh" down
    echo "X6 lab down: XDP detached, $X6 removed, beast-x3 netns deleted; $ARDA_PINS untouched" ;;
  *)
    echo "usage: sudo $0 {{precheck|up|load|attach|admit [--cgroup C] [SADDR DADDR SPORT DPORT TTL]|cgroup-check [--cgroup C]|resolve-cgroup [--cgroup C]|traffic [kernel|afxdp] [SEC PPS SIZE LABEL]|stats|detach|down|sequence [kernel|afxdp] [--cgroup C]|worker [SEC]}}" >&2
    exit 64 ;;
esac
"""


def write_operator_bundle(out_dir: Path | str | None = None, repo: Path | str = REPO_ROOT) -> dict[str, str]:
    repo = Path(repo)
    out = Path(out_dir) if out_dir else repo / ".beast" / "generated" / "xdp-x6"
    out.mkdir(parents=True, exist_ok=True)
    script = out / "run-x6-lab.sh"
    script.write_text(_script(repo), encoding="utf-8")
    script.chmod(0o755)
    commands = operator_commands(repo)
    commands = [c.replace(f"{repo}/.beast/generated/xdp-x6/run-x6-lab.sh", str(script)) for c in commands]
    run_md = out / "RUN.md"
    run_md.write_text(
        "# BEAST X6 ARDA-admitted XDP fast path: operator run sheet\n\n"
        f"Repo: `{repo}`. Every path is absolute; run from any directory. BEAST never runs these.\n\n"
        "```bash\n" + "\n".join(commands) + "\n```\n\n"
        "Notes:\n"
        f"- `{PIN_ARDA}` is only read (map show/dump) and reused read-only at load; teardown removes `{PIN_X6}` only.\n"
        f"- `load` uses bpftool `pinmaps {PIN_X6}`, which also adds extra pins of the three reused ARDA maps under "
        f"`{PIN_X6}` (same kernel maps, removed by `down`; ARDA's own pins are untouched).\n"
        "- `attach`/`down` use `nsenter --net` (not `ip netns exec`, which remounts /sys and hides bpffs pins).\n"
        "- `flow` admits only if the cgroup is in ARDA's active_generation_map and ARDA is not in lockdown/redline.\n"
        "- `admit` writes a fresh AdmittedFlowWriter entry for the lab flow 10.203.0.1:40000 -> 10.203.0.2:45678 "
        "(the X3 echo port); `traffic` binds that sport so the measured packets are the admitted flow.\n"
        "- `--cgroup` (admit/cgroup-check/sequence): default `consumer` = the invoking user's "
        "beast-beast-guardian-consumer.service ControlGroup inode (`systemctl --user show -p ControlGroup`). It must be in "
        "ARDA's active_generation_map or admission is refused before the lab is built. `arda-measured` = "
        "/run/arda/ring0-restore.json current_cgroup_kernel_id (3144, system.slice/arda-ring0.service): a revocation "
        "handle tied to ARDA's own scope, not an attestation of the consumer.\n"
        "- `traffic kernel`: kernel UDP echo; with X6 attached the admitted flow counts as `no_xsk` and PASSes "
        "(gate overhead on the kernel path). `traffic afxdp`: X3 AF_XDP echo worker running the X6 program, reusing "
        "ARDA maps plus X6's beast_admitted_flows/stats pins: the like-for-like comparison with July's X3 p50 "
        f"{X3_BASELINE['p50_latency_us']} us ({X3_BASELINE['receipt']}). Needs `sudo apt install libxdp-dev`.\n"
        "- `stats` sums the per-CPU counters by name: redirect = fast path; lockdown/redline = ARDA fallback PASS; "
        "miss/expired/generation/hash_prefix/no_xsk = PASS reasons. Invariant: seen = redirect + all PASS keys.\n"
        "- `sequence [kernel|afxdp]`: precheck, up, load, baseline traffic (no XDP), attach, admit, traffic, stats, "
        "[afxdp lane], detach, down; on any error it runs `down`. Receipts land in .beast/generated/xdp-x6/runs/.\n"
        "- `worker` is the AF_XDP echo path (X3 worker with --program/--reuse-pin); it needs libxdp "
        "(`sudo apt install libxdp-dev`) and replaces load+attach (it loads and attaches its own instance).\n",
        encoding="utf-8")
    return {"script": str(script), "run_md": str(run_md)}


def _main(argv: list[str] | None = None) -> int:
    import argparse

    from app.kernel.governance.governor_spine import ComputeGovernorSpine

    parser = argparse.ArgumentParser(prog="xdp_fastpath_sim")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("bundle")
    flow = sub.add_parser("flow")
    flow.add_argument("--active", required=True)
    flow.add_argument("--policy", required=True)
    flow.add_argument("--lockdown", required=True)
    flow.add_argument("--cgroup", type=int, required=True)
    flow.add_argument("--flow", nargs=4, required=True, metavar=("SADDR", "DADDR", "SPORT", "DPORT"))
    flow.add_argument("--ttl", type=float, default=60.0)
    check = sub.add_parser("cgroup-check")
    for name in ("--active", "--policy", "--lockdown"):
        check.add_argument(name, required=True)
    check.add_argument("--cgroup", type=int, required=True)
    check.add_argument("--source", default="")
    check.add_argument("--arda-measured", type=int, default=None)
    args = parser.parse_args(argv)
    if args.cmd == "bundle":
        print(json.dumps(write_operator_bundle()))
        return 0
    snap = _snapshot_from_dumps(Path(args.active).read_text(), Path(args.policy).read_text(),
                                Path(args.lockdown).read_text())
    if args.cmd == "cgroup-check":
        result = check_cgroup(snap, args.cgroup, source=args.source, arda_measured=args.arda_measured)
        if not result["eligible"]:
            print(f"REFUSED: {result['suggestion']}\nNOTE: {result['note']}", file=sys.stderr)
        print(json.dumps(result))
        return 0 if result["eligible"] else 65
    sim = FastPathSimulator(snapshot=snap)
    # Lab admission: the operator running this command attests the consumer (no Guardian lease in the netns lab).
    writer = AdmittedFlowWriter(sim, governor=ComputeGovernorSpine(enforce=True),
                                lease_verifier=lambda lease: lease)
    saddr, daddr, sport, dport = args.flow
    entry = writer.admit(saddr, daddr, int(sport), int(dport), ttl_s=args.ttl,
                         lease={"verified": True, "cgroup_id": args.cgroup, "lease_generation": 0,
                                "lease_id": "operator-lab-attestation"})
    print(entry["bpftool_update"])
    return 0


def benchmark(sim: FastPathSimulator, frames: list[bytes], rounds: int = 5) -> dict[str, Any]:
    best = float("inf")
    for _ in range(rounds):
        start = time.perf_counter()
        for frame in frames:
            sim.decide(frame)
        best = min(best, time.perf_counter() - start)
    return {"frames": len(frames), "best_seconds": best, "decisions_per_second": len(frames) / best if best else 0.0,
            "claim_boundary": "Python simulation of decision logic; not XDP throughput"}


__all__ = ["ARDA_MEASURED_FALLBACK", "LAB_FLOW", "PASS", "REDIRECT", "REPO_ROOT", "SIM_ENV", "STAT_NAMES", "X3_BASELINE", "check_cgroup", "AdmittedFlowWriter", "ArdaSnapshot", "FastPathSimulator",
           "benchmark", "flow_key", "operator_commands", "sim_enabled", "udp_frame", "write_operator_bundle"]


if __name__ == "__main__":
    raise SystemExit(_main())
