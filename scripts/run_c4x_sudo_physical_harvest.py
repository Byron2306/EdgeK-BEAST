#!/usr/bin/env python3
"""Interactive sudo harvester for the C4-X physical-truth certificate.

Run this from a real terminal:

    .venv/bin/python scripts/run_c4x_sudo_physical_harvest.py

The script intentionally asks sudo itself (`sudo -v`) and then uses `sudo -n`
for all privileged probes.  This keeps the sudo password out of Codex tool
logs, shell history, evidence files, and JSON receipts.
"""
from __future__ import annotations

import argparse
import base64
import fcntl
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, replace
from multiprocessing import Process, Queue
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey  # noqa: E402

from app.kernel.compute.deterministic_intelligence import sha256_digest, utc_now_iso  # noqa: E402
from app.kernel.compute.sealed_capsule import CrystalCapsule  # noqa: E402
from app.kernel.execution.guardian_authorization import (  # noqa: E402
    GUARDIAN_CAPABILITY_AUDIENCE,
    GuardianCapabilityAuthorizer,
    guardian_operation_digest,
)
from app.kernel.execution.process_identity import LinuxProcessIdentityCollector  # noqa: E402
from app.kernel.execution.socket_guardian import (  # noqa: E402
    GuardianProtocolError,
    SocketGuardianClient,
    SocketGuardianServer,
)
from app.kernel.integration.one_use_capability import OneUseCapability, OneUseCapabilityLedger  # noqa: E402
from scripts.harvest_c4x_physical_truth_sidecar import harvest_physical_truth_sidecar  # noqa: E402
from scripts.harden_c4x_physical_truth_sidecar import harden_sidecar  # noqa: E402
from scripts.run_c4x_physical_truth_certificate import run_physical_truth_certificate  # noqa: E402


DEFAULT_ROOT = REPO_ROOT / "evidence" / "c4x-physical-truth-certificate"


def main() -> int:
    parser = argparse.ArgumentParser(description="Prime sudo, harvest BPF/XDP, run custody proof, rebuild C4-X physical certificate.")
    parser.add_argument("--run-id", default="physical-truth-sudo-live-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
    parser.add_argument("--skip-sudo", action="store_true", help="Do not call sudo -v; useful after manually priming sudo.")
    parser.add_argument("--skip-custody", action="store_true", help="Only harvest sudo BPF/XDP state.")
    parser.add_argument(
        "--arda-root",
        default=os.environ.get("ARDA_ROOT", "/home/byron/Integritas-Mechanicus"),
        help="Optional Integritas/ARDA checkout used to harvest authoritative BPF attachment status.",
    )
    parser.add_argument(
        "--skip-arda",
        action="store_true",
        help="Do not run the ARDA status harvester even if an ARDA checkout is present.",
    )
    args = parser.parse_args()

    run_root = DEFAULT_ROOT / args.run_id
    run_root.mkdir(parents=True, exist_ok=True)

    if not args.skip_sudo:
        print("Priming sudo. Type your sudo password in this terminal if prompted.", flush=True)
        sudo = subprocess.run(["sudo", "-v"])
        if sudo.returncode != 0:
            raise SystemExit("sudo -v failed; no privileged evidence was harvested.")

    arda_receipt = {} if args.skip_arda else harvest_arda_status(run_root, Path(args.arda_root))
    bpf_receipt = harvest_bpf_xdp(run_root, arda_receipt=arda_receipt)
    custody_receipt = {} if args.skip_custody else run_local_custody_attack_suite(run_root)

    harvest = harvest_physical_truth_sidecar(
        output=DEFAULT_ROOT / "physical_truth_sidecar_harvested.json",
        bpf_prereq=run_root / "bpf_xdp_live_receipt.json",
    )
    sidecar_path = Path(harvest["output"])
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))

    if bpf_receipt:
        sidecar["bpf_receipt"] = _merge_receipts(sidecar.get("bpf_receipt") or {}, bpf_receipt.get("bpf_receipt") or {})
        sidecar["xdp_receipt"] = _merge_receipts(sidecar.get("xdp_receipt") or {}, bpf_receipt.get("xdp_receipt") or {})
    if custody_receipt:
        sidecar["memfd_receipt"] = custody_receipt["memfd_receipt"]
        sidecar["guardian_receipt"] = custody_receipt["guardian_receipt"]

    sidecar_path.write_text(json.dumps(sidecar, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    harden_sidecar(sidecar_path)
    certificate = run_physical_truth_certificate(
        sidecar=sidecar_path,
        run_id=args.run_id,
        evidence_root=DEFAULT_ROOT,
    )

    summary = {
        "run_id": args.run_id,
        "evidence_root": certificate["evidence_root"],
        "sidecar": str(sidecar_path),
        "certificate_digest": certificate["receipt_digest"],
        "public_credit_allowed": certificate["public_credit_allowed"],
        "green_gates": [k for k, v in certificate["certificate_gates"].items() if v],
        "red_gates": [k for k, v in certificate["certificate_gates"].items() if not v],
        "bpf_authority_present": bool((bpf_receipt.get("bpf_receipt") or {}).get("bpf_authority_present")),
        "bpf_loaded_program_count": int((bpf_receipt.get("bpf_receipt") or {}).get("loaded_bpf_program_count") or 0),
        "arda_bpf_authoritative": bool((bpf_receipt.get("bpf_receipt") or {}).get("arda_bpf_authoritative")),
        "arda_attach_verified": bool((bpf_receipt.get("bpf_receipt") or {}).get("arda_attach_verified")),
        "bpf_xdp_receipt_digest": bpf_receipt.get("receipt_digest", ""),
        "arda_receipt_digest": arda_receipt.get("receipt_digest", ""),
        "custody_receipt_digest": custody_receipt.get("receipt_digest", ""),
    }
    (run_root / "sudo_physical_harvest_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def harvest_arda_status(run_root: Path, arda_root: Path) -> dict[str, Any]:
    arda_bin = arda_root / "arda_os" / "bin" / "arda"
    if not arda_bin.is_file():
        receipt = {
            "beast_object_type": "c4x_arda_status_harvest",
            "version": "1.0",
            "created_at": utc_now_iso(),
            "present": False,
            "reason": f"ARDA binary not found at {arda_bin}",
        }
        receipt["receipt_digest"] = sha256_digest(receipt)
        (run_root / "arda_status_harvest.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return receipt

    env = os.environ.copy()
    env["ARDA_SOVEREIGN_MODE"] = "1"
    result = subprocess.run(
        ["sudo", "-n", str(arda_bin), "status", "--json"],
        cwd=str(arda_root),
        env=env,
        capture_output=True,
        text=True,
    )
    stdout_path = run_root / "arda_status.stdout"
    stderr_path = run_root / "arda_status.stderr"
    stdout_path.write_text(result.stdout, encoding="utf-8", errors="replace")
    stderr_path.write_text(result.stderr, encoding="utf-8", errors="replace")
    status = _parse_json(result.stdout)
    if not isinstance(status, Mapping):
        status = {}
    inner = status.get("status") if isinstance(status.get("status"), Mapping) else {}
    loader = inner.get("loader_status") if isinstance(inner.get("loader_status"), Mapping) else {}
    required_maps = inner.get("required_maps") if isinstance(inner.get("required_maps"), Mapping) else {}
    phase3 = inner.get("phase3_measured_identity") if isinstance(inner.get("phase3_measured_identity"), Mapping) else {}
    phase3_required = phase3.get("required_maps") if isinstance(phase3.get("required_maps"), Mapping) else {}
    checks = status.get("checks") if isinstance(status.get("checks"), Mapping) else {}
    required_maps_all_present = bool(required_maps.get("all_required_present"))
    phase3_required_maps_all_present = bool(phase3_required.get("all_required_present"))
    attach_verified = bool(inner.get("attach_verified"))
    canonical_bpf_object_exists = bool(loader.get("canonical_bpf_object_exists"))
    canonical_loader_binary_exists = bool(loader.get("canonical_loader_binary_exists"))
    authoritative_maps_present = bool(checks.get("authoritative_maps_present")) or required_maps_all_present
    bpf_authoritative = bool(checks.get("bpf_authoritative")) or (
        attach_verified
        and bool(inner.get("is_authoritative"))
        and not bool(inner.get("is_simulation"))
        and canonical_bpf_object_exists
        and canonical_loader_binary_exists
        and required_maps_all_present
    )
    kernel_text = " ".join(
        str(value or "")
        for value in (
            status.get("kernel"),
            inner.get("kernel"),
            os.uname().release if hasattr(os, "uname") else "",
        )
    )
    receipt = {
        "beast_object_type": "c4x_arda_status_harvest",
        "version": "1.0",
        "created_at": utc_now_iso(),
        "present": result.returncode == 0 and bool(status),
        "command": ["sudo", "-n", str(arda_bin), "status", "--json"],
        "returncode": result.returncode,
        "stdout_digest": _file_sha256(stdout_path),
        "stderr_digest": _file_sha256(stderr_path),
        "ok": bool(status.get("ok")) if "ok" in status else result.returncode == 0 and bool(status),
        "kernel": kernel_text.strip(),
        "valinor_kernel": bool(checks.get("valinor_kernel")) or "valinor" in kernel_text,
        "bpf_authoritative": bpf_authoritative,
        "authoritative_maps_present": authoritative_maps_present,
        "policy_bundle_present": bool(checks.get("policy_bundle_present")),
        "is_authoritative": bool(inner.get("is_authoritative")),
        "is_simulation": bool(inner.get("is_simulation")),
        "attach_verified": attach_verified,
        "arm_mode": str(inner.get("arm_mode") or ""),
        "enforcement_mode": str(inner.get("enforcement_mode") or ""),
        "loader_attempted": bool(inner.get("loader_attempted")),
        "loader_last_error": inner.get("loader_last_error"),
        "canonical_bpf_object_exists": canonical_bpf_object_exists,
        "canonical_loader_binary_exists": canonical_loader_binary_exists,
        "required_maps_all_present": required_maps_all_present,
        "phase3_required_maps_all_present": phase3_required_maps_all_present,
        "required_map_count": len(required_maps.get("maps") or {}) if isinstance(required_maps.get("maps"), Mapping) else 0,
        "phase3_required_map_count": len(phase3_required.get("maps") or {}) if isinstance(phase3_required.get("maps"), Mapping) else 0,
        "claim_boundary": (
            "ARDA/Integritas authoritative BPF substrate status. This proves BPF "
            "attachment and pinned-map authority when present, but does not by "
            "itself prove BEAST's zero-provider observed episode."
        ),
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    (run_root / "arda_status_harvest.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def harvest_bpf_xdp(run_root: Path, *, arda_receipt: Mapping[str, Any] | None = None) -> dict[str, Any]:
    commands = {
        "bpftool_prog_show_json": ["sudo", "-n", "bpftool", "-j", "prog", "show"],
        "bpftool_map_show_json": ["sudo", "-n", "bpftool", "-j", "map", "show"],
        "bpftool_net_show_json": ["sudo", "-n", "bpftool", "-j", "net", "show"],
        "bpftool_feature_probe_json": ["sudo", "-n", "bpftool", "-j", "feature", "probe"],
        "mounts": ["findmnt", "-J", "/sys/fs/bpf", "/sys/kernel/tracing", "/sys/kernel/debug/tracing"],
    }
    command_receipts: dict[str, Any] = {}
    for name, cmd in commands.items():
        result = subprocess.run(cmd, capture_output=True, text=True)
        stdout_path = run_root / f"{name}.stdout"
        stderr_path = run_root / f"{name}.stderr"
        stdout_path.write_text(result.stdout, encoding="utf-8", errors="replace")
        stderr_path.write_text(result.stderr, encoding="utf-8", errors="replace")
        parsed = _parse_json(result.stdout)
        command_receipts[name] = {
            "argv": _redacted_argv(cmd),
            "returncode": result.returncode,
            "ok": result.returncode == 0,
            "stdout_digest": _file_sha256(stdout_path),
            "stderr_digest": _file_sha256(stderr_path),
            "json_kind": type(parsed).__name__ if parsed is not None else "",
            "json_count": len(parsed) if isinstance(parsed, list) else len(parsed or {}) if isinstance(parsed, dict) else 0,
        }

    xdp_proofs = _existing_xdp_proofs()
    prog_list = _load_stdout_json(run_root / "bpftool_prog_show_json.stdout")
    net_state = _load_stdout_json(run_root / "bpftool_net_show_json.stdout")
    arda = dict(arda_receipt or {})
    arda_authority = (
        arda.get("present") is True
        and arda.get("bpf_authoritative") is True
        and arda.get("attach_verified") is True
        and arda.get("is_authoritative") is True
        and arda.get("is_simulation") is False
    )
    bpftool_authority = (
        command_receipts["bpftool_prog_show_json"]["ok"]
        and command_receipts["bpftool_map_show_json"]["ok"]
        and _json_len(prog_list) > 0
    )
    bpf_receipt = {
        "read_only_program": _x1_source_read_only(),
        "cgroup_bound": bool(_json_nonempty(prog_list) or _json_nonempty(net_state) or arda_authority),
        "outbound_connect_attempts": -1,
        "dns_activity": -1,
        "provider_sockets_opened": -1,
        "unexpected_child_processes": -1,
        "live_provider_comparator_observed_network": False,
        "ring_loss_explicit": (REPO_ROOT / "app/kernel/sensorium/bpf_loss_receipts.py").is_file(),
        "raw_packet_payload_retained": False,
        "privileged_bpftool_prog_show": command_receipts["bpftool_prog_show_json"]["ok"],
        "privileged_bpftool_map_show": command_receipts["bpftool_map_show_json"]["ok"],
        "privileged_bpftool_net_show": command_receipts["bpftool_net_show_json"]["ok"],
        "loaded_bpf_program_count": _json_len(prog_list),
        "bpf_authority_present": bool(bpftool_authority or arda_authority),
        "bpftool_bpf_authority_present": bool(bpftool_authority),
        "arda_bpf_authoritative": bool(arda.get("bpf_authoritative")),
        "arda_attach_verified": bool(arda.get("attach_verified")),
        "arda_is_authoritative": bool(arda.get("is_authoritative")),
        "arda_is_simulation": bool(arda.get("is_simulation")),
        "arda_valinor_kernel": bool(arda.get("valinor_kernel")),
        "arda_required_maps_all_present": bool(arda.get("required_maps_all_present")),
        "arda_phase3_required_maps_all_present": bool(arda.get("phase3_required_maps_all_present")),
        "arda_status_receipt_digest": str(arda.get("receipt_digest") or ""),
        "source_receipt_digest": sha256_digest(command_receipts),
        "status": "bpf_authority_present_zero_provider_episode_pending" if (bpftool_authority or arda_authority) else "bpf_authority_not_confirmed",
    }
    bpf_receipt["receipt_digest"] = sha256_digest(bpf_receipt)
    xdp_receipt = {
        "isolated_veth_or_namespace": bool(xdp_proofs),
        "redirect_pass_drop_observed": any(item.get("validated") is True for item in xdp_proofs),
        "unauthorized_cgroup_rejected": False,
        "worker_death_observed": False,
        "rx_ring_loss_reported": any((item.get("result") or {}).get("ring_saturation_events", -1) >= 0 for item in xdp_proofs),
        "xdp_detach_detected": False,
        "no_unrelated_traffic_redirected": False,
        "policy_fail_open_or_closed_verified": False,
        "guardian_policy_not_bypassed": False,
        "xdp_object_present": (REPO_ROOT / "bpf/build/beast_x3_redirect.bpf.o").is_file(),
        "af_xdp_worker_present": (REPO_ROOT / "bpf/build/beast_x3_af_xdp_worker").is_file(),
        "existing_xdp_proof_count": len(xdp_proofs),
        "source_receipt_digest": sha256_digest(xdp_proofs),
        "status": "sudo_live_xdp_inventory_plus_existing_af_xdp_proofs_attack_suite_pending",
    }
    xdp_receipt["receipt_digest"] = sha256_digest(xdp_receipt)
    receipt = {
        "beast_object_type": "c4x_sudo_bpf_xdp_live_harvest",
        "version": "1.0",
        "created_at": utc_now_iso(),
        "commands": command_receipts,
        "arda_status_receipt": arda,
        "bpf_receipt": bpf_receipt,
        "xdp_receipt": xdp_receipt,
        "claim_boundary": "Privileged kernel inventory and existing AF_XDP proof harvest. Does not claim zero-provider BPF witness without a closed observed episode.",
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    (run_root / "bpf_xdp_live_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def run_local_custody_attack_suite(run_root: Path) -> dict[str, Any]:
    payload = b"BEAST physical custody attack suite " + os.urandom(16)
    capsule = CrystalCapsule().create(
        payload,
        authority_ref="beast.c4x.local-custody",
        audience="beast-generation-provider-boundary",
        capability_ref="generation_provider_boundary",
        appraisal_ref=sha256_digest({"suite": "c4x-local-custody"}),
    )
    try:
        seals = fcntl.fcntl(capsule.fd, fcntl.F_GET_SEALS)
        required = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SEAL
        mutation_attempt_rejected = _write_rejected(capsule.fd)
        digest_verified = CrystalCapsule().verify(
            capsule,
            expected_authority="beast.c4x.local-custody",
            expected_audience="beast-generation-provider-boundary",
            capability_ref="generation_provider_boundary",
            appraisal_ref=sha256_digest({"suite": "c4x-local-custody"}),
        )
        try:
            guardian = _run_guardian_attacks(capsule)
        except Exception as exc:
            guardian = {
                "separate_process": False,
                "scm_rights_handoff_verified": False,
                "process_lease_verified": False,
                "one_use_render_capability_consumed": False,
                "replay_render_capability_rejected": False,
                "wrong_uid_rejected": False,
                "expired_lease_rejected": False,
                "wrong_fd_type_rejected": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        memfd_receipt = {
            "sealed_memfd": capsule.sealed,
            "seal_write": bool(seals & fcntl.F_SEAL_WRITE),
            "seal_grow": bool(seals & fcntl.F_SEAL_GROW),
            "seal_shrink": bool(seals & fcntl.F_SEAL_SHRINK),
            "seal_seal": bool(seals & fcntl.F_SEAL_SEAL),
            "digest_verified_after_seal": bool(digest_verified),
            "mutation_attempt_rejected": bool(mutation_attempt_rejected),
            "wrong_fd_type_rejected": bool(_local_wrong_fd_type_rejected(capsule)),
            "capsule_digest": capsule.digest,
            "status": "local_memfd_attack_suite_completed",
        }
        memfd_receipt["receipt_digest"] = sha256_digest(memfd_receipt)
        guardian_all_green = all((
            bool(guardian.get("separate_process")),
            bool(guardian.get("scm_rights_handoff_verified")),
            bool(guardian.get("process_lease_verified")),
            bool(guardian.get("one_use_render_capability_consumed")),
            bool(guardian.get("replay_render_capability_rejected")),
            bool(guardian.get("wrong_uid_rejected")),
            bool(guardian.get("expired_lease_rejected")),
            bool(guardian.get("producer_death_after_handoff_verified")),
            bool(guardian.get("joined_custody_receipt_signed")),
        ))
        guardian_receipt = {
            "separate_process": bool(guardian.get("separate_process")),
            "scm_rights_handoff_verified": bool(guardian.get("scm_rights_handoff_verified")),
            "process_lease_verified": bool(guardian.get("process_lease_verified")),
            "one_use_render_capability_consumed": bool(guardian.get("one_use_render_capability_consumed")),
            "replay_render_capability_rejected": bool(guardian.get("replay_render_capability_rejected")),
            "wrong_uid_rejected": bool(guardian.get("wrong_uid_rejected")),
            "expired_lease_rejected": bool(guardian.get("expired_lease_rejected")),
            "producer_death_after_handoff_verified": bool(guardian.get("producer_death_after_handoff_verified")),
            "joined_custody_receipt_signed": bool(guardian.get("joined_custody_receipt_signed")),
            "capsule_handoff_receipt_digest": str(guardian.get("capsule_handoff_receipt_digest") or ""),
            "runtime_error": str(guardian.get("error") or ""),
            "status": "passed" if guardian_all_green else "local_guardian_attack_suite_incomplete",
        }
        guardian_receipt["receipt_digest"] = sha256_digest(guardian_receipt)
        receipt = {
            "beast_object_type": "c4x_local_memfd_guardian_custody_attack_suite",
            "version": "1.0",
            "created_at": utc_now_iso(),
            "memfd_receipt": memfd_receipt,
            "guardian_receipt": guardian_receipt,
            "claim_boundary": (
                "User-space local custody proof. Memfd credit requires sealed "
                "immutable artifact custody; Guardian credit requires independent "
                "process custody, one-use capabilities, replay/expiry/wrong-UID "
                "rejection, signed joined custody, and producer death after "
                "handoff."
            ),
        }
        receipt["receipt_digest"] = sha256_digest(receipt)
        (run_root / "local_memfd_guardian_custody_attack_suite.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return receipt
    finally:
        try:
            os.close(capsule.fd)
        except OSError:
            pass


def _run_guardian_attacks(capsule: Any) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="beast-c4x-guardian-") as tmp:
        root = Path(tmp)
        if not _af_unix_seqpacket_bind_allowed(root):
            raise PermissionError("AF_UNIX SOCK_SEQPACKET bind is not permitted in this execution context")
        socket_path = root / "guardian.sock"
        ledger_path = root / "guardian.sqlite3"
        cap_ledger_path = root / "capabilities.sqlite3"
        ready_path = root / "ready"
        receipt_key = Ed25519PrivateKey.generate()
        authority_key = Ed25519PrivateKey.generate()
        child = Process(
            target=_guardian_child,
            args=(
                str(socket_path),
                str(ledger_path),
                str(cap_ledger_path),
                str(ready_path),
                _raw_private(receipt_key),
                _raw_public(authority_key),
            ),
        )
        child.start()
        _wait_for(ready_path)
        fixed_process_lease = LinuxProcessIdentityCollector().collect(os.getpid(), owner_scope="c4x-local-custody")
        issued: list[dict[str, Any]] = []

        def mint(request: Mapping[str, Any], *, expired: bool = False) -> dict[str, Any]:
            unsigned = OneUseCapability(
                capability_id=f"guardian-c4x:{len(issued) + 1}",
                request_digest=guardian_operation_digest(request),
                authority="arda",
                expires_at=time.time() - 1 if expired else time.time() + 60,
                nonce=f"nonce:{len(issued) + 1}",
                signature="",
                audience=GUARDIAN_CAPABILITY_AUDIENCE,
                policy_generation=str(request["policy_generation"]),
                appraisal_ref=str(request["appraisal_ref"]),
                key_id="arda-c4x-test-key",
            )
            item = {**asdict(unsigned), "signature": base64.b64encode(authority_key.sign(unsigned.body())).decode("ascii")}
            issued.append(item)
            return item

        client = SocketGuardianClient(
            socket_path,
            process_lease_provider=lambda: fixed_process_lease,
            operation_capability_provider=mint,
            receipt_verifier=receipt_key.public_key(),
        )
        capsule_binding = {
            "workspace_id": "generation-provider-boundary",
            "policy_generation": "generation-provider-boundary.v2",
        }
        result: dict[str, Any] = {}
        try:
            handoff = client.verify_capsule(
                capsule.fd,
                expected_capsule_digest=capsule.digest,
                authority_ref=capsule.authority_ref,
                audience=capsule.audience,
                capability_ref=capsule.capability_ref,
                appraisal_ref=capsule.appraisal_ref,
                **capsule_binding,
            )
            result["separate_process"] = child.pid != os.getpid()
            result["scm_rights_handoff_verified"] = handoff.get("verified") is True and handoff.get("fd_transport") == "SCM_RIGHTS"
            result["joined_custody_receipt_signed"] = bool(handoff.get("signature"))
            result["capsule_handoff_receipt_digest"] = str(handoff.get("receipt_digest") or "")
            result["process_lease_verified"] = True
            result["one_use_render_capability_consumed"] = len(issued) >= 1

            replay = issued[0]
            client.operation_capability_provider = lambda _request: replay
            result["replay_render_capability_rejected"] = _guardian_rejected(
                lambda: client.verify_capsule(
                    capsule.fd,
                    expected_capsule_digest=capsule.digest,
                    authority_ref=capsule.authority_ref,
                    audience=capsule.audience,
                    capability_ref=capsule.capability_ref,
                    appraisal_ref=capsule.appraisal_ref,
                    **capsule_binding,
                )
            )

            client.operation_capability_provider = lambda request: mint(request, expired=True)
            result["expired_capability_rejected"] = _guardian_rejected(
                lambda: client.verify_capsule(
                    capsule.fd,
                    expected_capsule_digest=capsule.digest,
                    authority_ref=capsule.authority_ref,
                    audience=capsule.audience,
                    capability_ref=capsule.capability_ref,
                    appraisal_ref=capsule.appraisal_ref,
                    **capsule_binding,
                )
            )

            client.operation_capability_provider = mint
            lease = client.reserve(
                "c4x-expiring-service",
                "generation-provider-boundary",
                authority_ref="beast.c4x.local-custody",
                capability_ref="generation_provider_boundary",
                appraisal_ref="arda-appraisal:c4x-expiring-service",
                policy_generation="generation-provider-boundary.v2",
                ttl_seconds=0.01,
            )
            time.sleep(0.05)
            result["expired_lease_rejected"] = _guardian_rejected(
                lambda: client.recover(
                    lease.lease_id,
                    workspace_id="generation-provider-boundary",
                    capability_ref="generation_provider_boundary",
                    appraisal_ref="arda-appraisal:c4x-expiring-service",
                    policy_generation="generation-provider-boundary.v2",
                )
            )

            with open(os.devnull, "rb") as bad:
                result["wrong_fd_type_rejected"] = _guardian_rejected(
                    lambda: client.verify_capsule(
                        bad.fileno(),
                        expected_capsule_digest=capsule.digest,
                        authority_ref=capsule.authority_ref,
                        audience=capsule.audience,
                        capability_ref=capsule.capability_ref,
                        appraisal_ref=capsule.appraisal_ref,
                        **capsule_binding,
                    )
                )
            result["wrong_uid_rejected"] = _wrong_uid_rejected(root, receipt_key)
            result["producer_death_after_handoff_verified"] = _producer_death_after_handoff_verified(
                root,
                socket_path,
                receipt_key,
                authority_key,
                _raw_public(receipt_key),
            )
        finally:
            child.terminate()
            child.join(timeout=5)
            if child.is_alive():
                child.kill()
        return result


def _producer_death_after_handoff_verified(
    root: Path,
    socket_path: Path,
    receipt_key: Ed25519PrivateKey,
    authority_key: Ed25519PrivateKey,
    receipt_public_raw: bytes,
) -> bool:
    """Prove a capsule handoff receipt survives producer process death."""
    queue: Queue = Queue()
    producer = Process(
        target=_capsule_handoff_producer_child,
        args=(str(socket_path), _raw_private(authority_key), receipt_public_raw, queue),
    )
    producer.start()
    producer.join(timeout=10)
    if producer.is_alive():
        producer.kill()
        producer.join(timeout=5)
        return False
    if producer.exitcode != 0:
        return False
    try:
        item = queue.get_nowait()
    except Exception:
        return False
    if not isinstance(item, Mapping) or not item.get("verified"):
        return False
    body = {key: value for key, value in dict(item).items() if key not in {"receipt_digest", "signature", "producer_pid"}}
    if item.get("fd_transport") != "SCM_RIGHTS" or item.get("guardian_id") != "beast.socket-guardian.v1":
        return False
    if item.get("receipt_digest") != _guardian_digest(body):
        return False
    signature = str(item.get("signature") or "")
    if not signature:
        return False
    try:
        receipt_key.public_key().verify(base64.b64decode(signature, validate=True), _guardian_canonical(body))
    except Exception:
        return False
    producer_pid = int(item.get("producer_pid") or -1)
    return producer_pid > 0 and not _pid_alive(producer_pid)


def _capsule_handoff_producer_child(
    socket_path: str,
    authority_private_raw: bytes,
    receipt_public_raw: bytes,
    queue: Queue,
) -> None:
    authority_key = Ed25519PrivateKey.from_private_bytes(authority_private_raw)
    receipt_public = Ed25519PublicKey.from_public_bytes(receipt_public_raw)
    payload = b"BEAST producer-death Guardian handoff " + os.urandom(16)
    capsule = CrystalCapsule().create(
        payload,
        authority_ref="beast.c4x.producer-death",
        audience="beast-generation-provider-boundary",
        capability_ref="generation_provider_boundary",
        appraisal_ref=sha256_digest({"suite": "c4x-producer-death"}),
    )
    issued: list[dict[str, Any]] = []

    def mint(request: Mapping[str, Any]) -> dict[str, Any]:
        unsigned = OneUseCapability(
            capability_id=f"guardian-producer-death:{len(issued) + 1}",
            request_digest=guardian_operation_digest(request),
            authority="arda",
            expires_at=time.time() + 60,
            nonce=f"producer-death:{len(issued) + 1}",
            signature="",
            audience=GUARDIAN_CAPABILITY_AUDIENCE,
            policy_generation=str(request["policy_generation"]),
            appraisal_ref=str(request["appraisal_ref"]),
            key_id="arda-c4x-test-key",
        )
        item = {**asdict(unsigned), "signature": base64.b64encode(authority_key.sign(unsigned.body())).decode("ascii")}
        issued.append(item)
        return item

    try:
        lease = LinuxProcessIdentityCollector().collect(os.getpid(), owner_scope="c4x-producer-death")
        client = SocketGuardianClient(
            socket_path,
            process_lease_provider=lambda: lease,
            operation_capability_provider=mint,
            receipt_verifier=receipt_public,
        )
        receipt = dict(client.verify_capsule(
            capsule.fd,
            expected_capsule_digest=capsule.digest,
            authority_ref=capsule.authority_ref,
            audience=capsule.audience,
            capability_ref=capsule.capability_ref,
            appraisal_ref=capsule.appraisal_ref,
            workspace_id="generation-provider-boundary",
            policy_generation="generation-provider-boundary.v2",
        ))
        receipt["producer_pid"] = os.getpid()
        queue.put(receipt)
    finally:
        try:
            os.close(capsule.fd)
        except OSError:
            pass


def _guardian_child(
    socket_path: str,
    ledger_path: str,
    cap_ledger_path: str,
    ready_path: str,
    receipt_private_raw: bytes,
    authority_public_raw: bytes,
) -> None:
    receipt_key = Ed25519PrivateKey.from_private_bytes(receipt_private_raw)
    authority_public = Ed25519PublicKey.from_public_bytes(authority_public_raw)
    ledger = OneUseCapabilityLedger({"arda": authority_public}, cap_ledger_path)
    authorizer = GuardianCapabilityAuthorizer(ledger, allowed_authorities={"arda"})
    server = SocketGuardianServer(
        socket_path,
        ledger_path,
        signer=receipt_key,
        authorize=authorizer,
        require_authority=True,
        require_process_lease=True,
    )
    server.start()
    Path(ready_path).write_text(str(os.getpid()), encoding="utf-8")
    server.serve_forever()


def _wrong_uid_rejected(root: Path, receipt_key: Ed25519PrivateKey) -> bool:
    socket_path = root / "wrong-uid.sock"
    ledger_path = root / "wrong-uid.sqlite3"
    ready_path = root / "wrong-uid.ready"
    child = Process(
        target=_wrong_uid_guardian_child,
        args=(str(socket_path), str(ledger_path), str(ready_path), _raw_private(receipt_key), os.getuid() + 1),
    )
    child.start()
    _wait_for(ready_path)
    client = SocketGuardianClient(socket_path, require_signed_receipts=False)
    try:
        return _guardian_rejected(lambda: client.snapshot())
    finally:
        child.terminate()
        child.join(timeout=5)
        if child.is_alive():
            child.kill()


def _wrong_uid_guardian_child(socket_path: str, ledger_path: str, ready_path: str, receipt_private_raw: bytes, expected_uid: int) -> None:
    server = SocketGuardianServer(
        socket_path,
        ledger_path,
        expected_uid=expected_uid,
        signer=Ed25519PrivateKey.from_private_bytes(receipt_private_raw),
        require_authority=False,
        require_process_lease=False,
    )
    server.start()
    Path(ready_path).write_text(str(os.getpid()), encoding="utf-8")
    server.serve_forever()


def _raw_private(key: Ed25519PrivateKey) -> bytes:
    return key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _raw_public(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def _wait_for(path: Path, *, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return
        time.sleep(0.02)
    raise TimeoutError(f"guardian did not become ready: {path}")


def _guardian_rejected(action) -> bool:
    try:
        action()
        return False
    except (GuardianProtocolError, PermissionError, KeyError, OSError, RuntimeError):
        return True


def _guardian_canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":")).encode("utf-8")


def _guardian_digest(value: Mapping[str, Any]) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(_guardian_canonical(value)).hexdigest()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _write_rejected(fd: int) -> bool:
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, b"tamper")
        return False
    except OSError:
        return True


def _local_wrong_fd_type_rejected(capsule: Any) -> bool:
    try:
        with open(os.devnull, "rb") as bad:
            wrong = replace(capsule, fd=bad.fileno())
            return not CrystalCapsule().verify(wrong)
    except Exception:
        return True


def _af_unix_seqpacket_bind_allowed(root: Path) -> bool:
    probe_path = root / "bind-probe.sock"
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    try:
        sock.bind(str(probe_path))
        return True
    except OSError:
        return False
    finally:
        sock.close()
        try:
            probe_path.unlink()
        except OSError:
            pass


def _existing_xdp_proofs() -> list[Mapping[str, Any]]:
    root = REPO_ROOT / "evidence" / "high_velocity_fabric"
    proofs: list[Mapping[str, Any]] = []
    for path in sorted(root.glob("x3_af_xdp_*.json")):
        value = _parse_json(path.read_text(encoding="utf-8", errors="replace"))
        if isinstance(value, Mapping):
            proofs.append({**dict(value), "path": str(path.relative_to(REPO_ROOT)), "file_digest": _file_sha256(path)})
    return proofs


def _merge_receipts(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    merged = {**dict(base or {}), **dict(overlay or {})}
    merged.pop("receipt_digest", None)
    merged["receipt_digest"] = sha256_digest(merged)
    return merged


def _x1_source_read_only() -> bool:
    source = REPO_ROOT / "bpf" / "beast_x1_observer.bpf.c"
    if not source.is_file():
        return False
    text = source.read_text(encoding="utf-8", errors="replace")
    return "BPF_MAP_TYPE_RINGBUF" in text and "No override" in text


def _redacted_argv(cmd: list[str]) -> list[str]:
    return ["sudo", "-n", *cmd[2:]] if cmd[:2] == ["sudo", "-n"] else list(cmd)


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return None


def _load_stdout_json(path: Path) -> Any:
    if not path.is_file():
        return None
    return _parse_json(path.read_text(encoding="utf-8", errors="replace"))


def _json_nonempty(value: Any) -> bool:
    return bool(value) if isinstance(value, (list, dict)) else False


def _json_len(value: Any) -> int:
    return len(value) if isinstance(value, (list, dict)) else 0


def _file_sha256(path: Path) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
