"""Experimental Task 5: ARDA-admitted XDP fast path — userspace simulation (nothing is loaded into the kernel)."""
from __future__ import annotations

import json
import os
import random
import re
import shutil
import struct
import subprocess
from pathlib import Path

import pytest

from app.kernel.governance.governor_spine import ComputeGovernorSpine
from app.kernel.networking.xdp_fastpath_sim import (
    PASS,
    REDIRECT,
    SIM_ENV,
    AdmittedFlowWriter,
    ArdaSnapshot,
    FastPathSimulator,
    operator_commands,
    udp_frame,
)

ROOT = Path(__file__).resolve().parents[1]
ON = {SIM_ENV: "1"}
ARDA_SRC = Path("/usr/lib/arda/src/arda_os/backend/services/bpf/arda_physical_lsm.c")
FLOW = ("10.203.0.1", "10.203.0.2", 40000, 9999)


def snapshot(**over):
    base = {"lockdown": 0, "projection_flags": 1, "generation_hash_prefix": 13745055897814023361,
                "active_generation": {3144: 12}, "source": "test"}
    base.update(over)
    return ArdaSnapshot(**base)


def lease(cgroup_id=3144, generation=5):
    return {"verified": True, "cgroup_id": cgroup_id, "lease_generation": generation, "lease_id": "lease-1"}


def world(snap=None, env=ON, governor=None, now=1_000):
    sim = FastPathSimulator(snapshot=snap or snapshot(), env=env, xsk_queues={0}, clock_ns=lambda: now)
    writer = AdmittedFlowWriter(sim, governor=governor or ComputeGovernorSpine(enforce=True),
                                lease_verifier=lambda lease: dict(lease), env=env, clock_ns=lambda: now)
    return sim, writer


def test_flag_default_off():
    with pytest.raises(PermissionError, match=SIM_ENV):
        FastPathSimulator(snapshot=snapshot(), env={})


def test_admitted_flow_redirects_and_unknown_flow_passes():
    sim, writer = world()
    entry = writer.admit(*FLOW, lease=lease(), ttl_s=30)
    assert entry["governor"]["outcome"] == "admit" and entry["arda_generation"] == 12
    assert sim.decide(udp_frame(*FLOW)) == (REDIRECT, "admitted")
    assert sim.decide(udp_frame("10.203.0.1", "10.203.0.2", 40001, 9999)) == (PASS, "miss")
    assert sim.decide(b"\x00" * 10) == (PASS, "not_udp_ipv4")


@pytest.mark.parametrize("change, reason", [
    ({"lockdown": 1}, "arda_lockdown"),
    ({"projection_flags": 3}, "arda_redline_triggered"),
    ({"active_generation": {3144: 13}}, "arda_generation_mismatch"),
    ({"active_generation": {}}, "arda_generation_mismatch"),
    ({"generation_hash_prefix": 1}, "arda_policy_prefix_mismatch"),
])
def test_arda_policy_changes_fall_back_to_kernel_stack(change, reason):
    sim, writer = world()
    writer.admit(*FLOW, lease=lease(), ttl_s=30)
    sim.snapshot = snapshot(**change)
    assert sim.decide(udp_frame(*FLOW)) == (PASS, reason)


def test_expiry_and_missing_xsk_pass():
    sim, writer = world()
    writer.admit(*FLOW, lease=lease(), ttl_s=1)
    sim.clock_ns = lambda: 1_000 + 2 * 10**9
    assert sim.decide(udp_frame(*FLOW)) == (PASS, "expired")
    sim2, writer2 = world()
    writer2.admit(*FLOW, lease=lease(), ttl_s=30)
    sim2.xsk_queues = set()
    assert sim2.decide(udp_frame(*FLOW)) == (PASS, "no_xsk")


def test_writer_requires_verified_lease_arda_admitted_cgroup_and_governor():
    _sim, writer = world()
    with pytest.raises(PermissionError, match="lease"):
        writer.admit(*FLOW, lease={**lease(), "verified": False}, ttl_s=30)
    with pytest.raises(PermissionError, match="ARDA active generation"):
        writer.admit(*FLOW, lease=lease(cgroup_id=999), ttl_s=30)
    _sim, locked = world(snap=snapshot(lockdown=1))
    with pytest.raises(PermissionError, match="lockdown"):
        locked.admit(*FLOW, lease=lease(), ttl_s=30)

    class Refuse(ComputeGovernorSpine):
        def admit(self, episode, proposal):
            from dataclasses import replace
            return replace(super().admit(episode, proposal), outcome="refuse", reasons=("operator_refused",))

    sim, refusing = world(governor=Refuse(enforce=True))
    with pytest.raises(PermissionError, match="refuse"):
        refusing.admit(*FLOW, lease=lease(), ttl_s=30)
    assert sim.flows == {}


def test_never_drops_under_fuzz():
    sim, writer = world()
    writer.admit(*FLOW, lease=lease(), ttl_s=30)
    rng = random.Random(7)
    frames = [bytes(rng.getrandbits(8) for _ in range(rng.randint(0, 80))) for _ in range(2000)]
    frames += [udp_frame(*FLOW)] * 50
    actions = {sim.decide(frame)[0] for frame in frames}
    assert actions <= {PASS, REDIRECT}


def test_flow_entry_bytes_match_c_layout_and_commands_are_operator_only():
    _sim, writer = world()
    entry = writer.admit(*FLOW, lease=lease(), ttl_s=30)
    assert len(bytes.fromhex(entry["key_hex"])) == 16 and len(bytes.fromhex(entry["value_hex"])) == 48
    saddr, daddr, sport, dport, proto = struct.unpack("!4s4sHHB", bytes.fromhex(entry["key_hex"])[:13])
    assert (sport, dport, proto) == (40000, 9999, 17)
    commands = "\n".join(operator_commands())
    assert "sudo" in commands and "map name arda_lockdown_map pinned /sys/fs/bpf/arda/lockdown_map" in commands
    assert "xdpgeneric" in commands and "beast-x3-rx" in commands
    assert entry["bpftool_update"].startswith("sudo bpftool map update pinned /sys/fs/bpf/beast/x6/beast_admitted_flows")


def test_c_source_reuses_arda_map_definitions_verbatim():
    source = (ROOT / "bpf" / "beast_x6_admitted_fastpath.bpf.c").read_text()
    if not ARDA_SRC.exists():
        pytest.skip("ARDA source not present on this host")
    arda = ARDA_SRC.read_text()

    def block(text, name):
        match = re.search(r"struct \{(?:(?!\} ).)*?\} " + name + r" SEC\(\"\.maps\"\);", text, re.S)
        assert match, name
        return re.sub(r"\s+", " ", match.group(0))

    for name in ("arda_active_generation_map", "arda_policy_state_map", "arda_lockdown_map"):
        assert block(source, name) == block(arda, name)
    assert "bpf_map_update_elem(&arda" not in source and "bpf_map_delete_elem(&arda" not in source
    assert "XDP_DROP" not in source


@pytest.mark.skipif(not shutil.which("clang") and not os.path.exists("/usr/bin/clang"), reason="clang missing")
def test_c_source_compiles_to_bpf_object(tmp_path):
    out = tmp_path / "x6.o"
    done = subprocess.run(["/usr/bin/clang", "-g", "-O2", "-target", "bpf", "-D__TARGET_ARCH_x86",
                           f"-I{ROOT / 'bpf' / 'build'}", "-c", str(ROOT / "bpf" / "beast_x6_admitted_fastpath.bpf.c"),
                           "-o", str(out)], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert b"beast_admitted_flows" in out.read_bytes()


def test_live_arda_snapshot_is_read_only(tmp_path):
    path = Path("/run/arda/ring0-restore.json")
    if not path.exists():
        pytest.skip("ARDA ring0 restore state not present")
    before = path.stat().st_mtime_ns
    snap = ArdaSnapshot.from_restore_json(path)
    assert snap.generation_hash_prefix > 0 and snap.active_generation
    assert snap.lockdown_inferred is True
    assert path.stat().st_mtime_ns == before


# --- Operator bundle (Byron feedback 2026-11-16 04:35: commands must work from any directory) -------------------
def test_operator_commands_use_absolute_paths_only():
    from app.kernel.networking.xdp_fastpath_sim import REPO_ROOT

    commands = [c for c in operator_commands() if not c.startswith("#")]
    text = "\n".join(commands)
    assert str(REPO_ROOT) in text
    for token in text.split():
        if token.startswith(("scripts/", "bpf/", "./", "docs/")):
            raise AssertionError(f"relative path in operator command: {token}")
    assert "bpf/build/beast_x6_admitted_fastpath.bpf.o" in text and f"{REPO_ROOT}/bpf/build" in text


def test_bundle_writes_run_md_and_safe_script(tmp_path):
    from app.kernel.networking.xdp_fastpath_sim import write_operator_bundle

    out = write_operator_bundle(tmp_path / "xdp-x6")
    script = Path(out["script"])
    body = script.read_text()
    assert os.access(script, os.X_OK) and "set -euo pipefail" in body and 'cd "$REPO"' in body
    for sub in ("precheck)", "up)", "load)", "attach)", "flow)", "stats)", "down)"):
        assert sub in body
    for line in body.splitlines():
        if "/sys/fs/bpf/arda" in line or "$ARDA_PINS" in line:
            assert not re.search(r"\b(rm|mv|unlink|update|delete|pin )\b", line.replace("map update pinned \"$X6", "")), line
    assert subprocess.run(["bash", "-n", str(script)], capture_output=True).returncode == 0
    run_md = Path(out["run_md"]).read_text()
    assert str(script) in run_md and "sudo" in run_md


def test_snapshot_from_bpftool_dumps_btf_and_hex():
    from app.kernel.networking.xdp_fastpath_sim import ArdaSnapshot

    active = '[{"key": 3144, "value": 12}, {"key": 1209451, "value": 12}]'
    policy = '[{"key": 0, "value": {"generation_hash_prefix": 13745055897814023361, "redline_rule_count": 7, "projection_flags": 1}}]'
    lockdown = '[{"key": 0, "value": 0}]'
    snap = ArdaSnapshot.from_bpftool_dumps(active, policy, lockdown)
    assert snap.active_generation == {3144: 12, 1209451: 12} and snap.lockdown == 0 and not snap.lockdown_inferred
    assert snap.generation_hash_prefix == 13745055897814023361 and snap.projection_flags == 1
    hex_active = '[{"key": ["0x48","0x0c","0x00","0x00","0x00","0x00","0x00","0x00"], "value": ["0x0c","0x00","0x00","0x00","0x00","0x00","0x00","0x00"]}]'
    prefix = (13745055897814023361).to_bytes(8, "little") + (7).to_bytes(4, "little") + (3).to_bytes(4, "little")
    hex_policy = json.dumps([{"key": ["0x00"] * 4, "value": [f"0x{b:02x}" for b in prefix]}])
    snap2 = ArdaSnapshot.from_bpftool_dumps(hex_active, hex_policy, '[{"key":["0x00","0x00","0x00","0x00"],"value":["0x01","0x00","0x00","0x00"]}]')
    assert snap2.active_generation == {3144: 12} and snap2.projection_flags == 3 and snap2.lockdown == 1


def test_bundle_has_admit_traffic_named_stats_and_full_sequence(tmp_path):
    import subprocess

    from app.kernel.networking.xdp_fastpath_sim import STAT_NAMES, X3_BASELINE, write_operator_bundle

    assert STAT_NAMES[1][0] == "redirect" and STAT_NAMES[8][0] == "no_xsk" and len(STAT_NAMES) == 9
    assert X3_BASELINE["p50_latency_us"] == 117.065
    out = write_operator_bundle(tmp_path / "xdp-x6")
    script = Path(out["script"]).read_text()
    for sub in ("  admit|flow)", "  traffic)", "  stats)", "  detach)", "  sequence)"):
        assert sub in script
    # the measured flow is the admitted flow: sender binds the admitted sport and targets the X3 echo port
    assert "10.203.0.1 10.203.0.2 40000 45678" in script and "bind((saddr, sport))" in script
    # AF_XDP lane shares the admitted-flow and stats maps with the operator instance
    assert '--reuse-pin=beast_admitted_flows="$X6/beast_admitted_flows"' in script
    assert "x3_af_xdp_echo_20260720T113948Z.json" in script
    sequence = script.split("  sequence)")[1].split(";;")[0]
    assert "trap cleanup_lab EXIT" in sequence  # any failure tears the lab down
    sequence = "\n".join(line for line in sequence.splitlines() if "cleanup_lab" not in line)
    order = [sequence.index(s) for s in ('"$0" up', '"$0" load', 'traffic kernel', '"$0" attach', '"$0" admit',
                                         '"$0" stats', '"$0" detach', '"$0" down')]
    assert order == sorted(order)
    assert subprocess.run(["bash", "-n", out["script"]]).returncode == 0
    run_md = Path(out["run_md"]).read_text()
    assert "117" in run_md and "sequence" in run_md


ACTIVE_DUMP = '[{"key": 3144, "value": 12}, {"key": 1209451, "value": 12}]'
POLICY_DUMP = '[{"key": 0, "value": {"generation_hash_prefix": 13745055897814023361, "redline_rule_count": 7, "projection_flags": 1}}]'
LOCKDOWN_DUMP = '[{"key": 0, "value": 0}]'


def test_cgroup_check_reports_missing_consumer_and_suggests_arda_measured_scope():
    from app.kernel.networking.xdp_fastpath_sim import ArdaSnapshot, check_cgroup

    snap = ArdaSnapshot.from_bpftool_dumps(ACTIVE_DUMP, POLICY_DUMP, LOCKDOWN_DUMP)
    ok = check_cgroup(snap, 3144, source="explicit")
    assert ok["eligible"] is True and ok["generation"] == 12
    miss = check_cgroup(snap, 1238415, source="consumer:beast-beast-guardian-consumer.service", arda_measured=3144)
    assert miss["eligible"] is False and miss["active_entries"] == 2
    assert "--cgroup arda-measured" in miss["suggestion"] and "3144" in miss["suggestion"]
    assert "revocation" in miss["note"]


def test_cgroup_check_cli_exit_codes(tmp_path, capsys):
    from app.kernel.networking.xdp_fastpath_sim import _main

    for name, body in (("a", ACTIVE_DUMP), ("p", POLICY_DUMP), ("l", LOCKDOWN_DUMP)):
        (tmp_path / f"{name}.json").write_text(body)
    base = ["cgroup-check", "--active", str(tmp_path / "a.json"), "--policy", str(tmp_path / "p.json"),
            "--lockdown", str(tmp_path / "l.json"), "--source", "explicit"]
    assert _main([*base, "--cgroup", "1209451"]) == 0
    assert _main([*base, "--cgroup", "1241599"]) == 65
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["eligible"] is False


def test_script_resolves_cgroup_from_consumer_unit_not_the_sudo_shell(tmp_path):
    import subprocess

    from app.kernel.networking.xdp_fastpath_sim import write_operator_bundle

    out = write_operator_bundle(tmp_path / "xdp-x6")
    script = Path(out["script"]).read_text()
    assert "/proc/$$/cgroup" not in script  # the sudo shell's cgroup is never the default
    assert 'CONSUMER_UNIT="${CONSUMER_UNIT:-beast-beast-guardian-consumer.service}"' in script
    assert "systemctl --user show -p ControlGroup --value" in script and "XDG_RUNTIME_DIR=/run/user/" in script
    seq = script.split("  sequence)")[1].split(";;")[0]
    assert seq.index('"$0" cgroup-check') < seq.index('"$0" up')  # refuse before building the lab
    assert '"$0" admit "${cg_args[@]}"' in seq and "trap cleanup_lab EXIT INT TERM" in seq
    run = lambda *a: subprocess.run(["bash", out["script"], "resolve-cgroup", *a], capture_output=True, text=True)  # noqa: E731
    assert run("--cgroup", "3144").stdout.split() == ["3144", "explicit"]
    assert run("--cgroup=/").stdout.split()[1] == "path:/"
    bad = run("--cgroup", "nonsense;rm")
    assert bad.returncode == 64
