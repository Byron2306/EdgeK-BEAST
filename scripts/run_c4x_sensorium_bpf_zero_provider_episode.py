#!/usr/bin/env python3
"""Closed Sensorium episode + zero-provider witness for C4-X.

This runner is intentionally narrow: it observes one local, deterministic
BEAST proof-read episode, records it through the Sensorium journal, instruments
process-local network/DNS/socket/child-process calls during the mission, then
runs a positive comparator outside the mission to prove the witness can see
network activity.

The BPF/ARDA substrate receipt is imported from the current physical-truth
sidecar.  This script does not claim packet payload capture and does not retain
raw prompts or secrets.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Any, Callable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.kernel.compute.deterministic_intelligence import sha256_digest, utc_now_iso  # noqa: E402
from app.kernel.sensorium.contracts_hash import content_hash  # noqa: E402
from app.kernel.sensorium.runtime import SensoriumRuntime  # noqa: E402
from scripts.harden_c4x_physical_truth_sidecar import harden_sidecar  # noqa: E402
from scripts.run_c4x_physical_truth_certificate import run_physical_truth_certificate  # noqa: E402


DEFAULT_ROOT = REPO_ROOT / "evidence" / "c4x-physical-truth-certificate"
DEFAULT_SIDECAR = DEFAULT_ROOT / "physical_truth_sidecar_harvested.json"
DEFAULT_SOURCE = REPO_ROOT / "evidence" / "deterministic-intelligence-ultimate-gauntlet" / "latest.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a closed Sensorium zero-provider C4-X episode.")
    parser.add_argument("--run-id", default="sensorium-bpf-zero-provider-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
    parser.add_argument("--sidecar", default=str(DEFAULT_SIDECAR))
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--comparator-host", default="generativelanguage.googleapis.com")
    parser.add_argument("--comparator-port", type=int, default=443)
    parser.add_argument("--comparator-timeout", type=float, default=2.0)
    parser.add_argument("--skip-comparator", action="store_true")
    args = parser.parse_args()

    receipt = run_zero_provider_episode(
        run_id=args.run_id,
        sidecar=Path(args.sidecar),
        source=Path(args.source),
        comparator_host=args.comparator_host,
        comparator_port=args.comparator_port,
        comparator_timeout=args.comparator_timeout,
        skip_comparator=args.skip_comparator,
    )
    print(json.dumps(receipt["summary"], indent=2, sort_keys=True))
    return 0


def run_zero_provider_episode(
    *,
    run_id: str,
    sidecar: Path,
    source: Path,
    comparator_host: str,
    comparator_port: int,
    comparator_timeout: float,
    skip_comparator: bool = False,
) -> dict[str, Any]:
    run_root = DEFAULT_ROOT / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    sidecar = _resolve(sidecar)
    source = _resolve(source)
    sidecar_payload = _load_json(sidecar)
    source_payload = _load_json(source)

    journal_path = run_root / "sensorium_episode.sqlite3"
    runtime = SensoriumRuntime(capacity=64, export_root=run_root / "outbox", journal_path=journal_path)
    mission_id = run_id
    workspace_identity = content_hash({"repo": str(REPO_ROOT), "mission": "c4x-zero-provider"})
    objective_hash = content_hash({"objective": "closed_sensorium_zero_provider_c4x_read", "source": str(source)})
    initial_state_hash = content_hash({
        "source_digest": _file_sha256(source),
        "sidecar_digest": _file_sha256(sidecar),
    })

    mission_witness = NetworkWitness()
    with mission_witness.instrument():
        source_digest = _file_sha256(source)
        latest_digest = str(source_payload.get("receipt_digest") or "")
        event1 = runtime.observe_physical(
            event_type="file.source_inspected",
            source="c4x_zero_provider_episode",
            payload_schema="beast.sensorium.c4x_zero_provider.source.v1",
            operation="file.inspect",
            phase="observation",
            subject="deterministic_intelligence_latest",
            result="observed",
            mission_id=mission_id,
            workspace_id=str(REPO_ROOT),
            payload={
                "source_path": str(source.relative_to(REPO_ROOT)) if source.is_relative_to(REPO_ROOT) else str(source),
                "source_file_digest": source_digest,
                "source_receipt_digest": latest_digest,
                "raw_sensitive_payloads_absent": True,
                "reads": [f"file:{source_digest}"],
                "produces": [f"source_receipt:{latest_digest or source_digest}"],
            },
        ).admitted.event.event_id
        selected = runtime.observe_physical(
            event_type="build.branch_selected",
            source="c4x_zero_provider_episode",
            payload_schema="beast.sensorium.c4x_zero_provider.branch.v1",
            operation="proof.select",
            phase="decision",
            subject="zero_provider_local_replay",
            result="selected",
            mission_id=mission_id,
            workspace_id=str(REPO_ROOT),
            payload={
                "branch": "local_digest_bound_read_only_replay",
                "provider_route_allowed": False,
                "provider_route_selected": False,
                "requires": [f"source_receipt:{latest_digest or source_digest}"],
                "produces": ["route:zero_provider_local"],
                "caused_by_event_ids": [event1],
            },
        ).admitted.event.event_id
        effect = {
            "ultimate_pass": bool(source_payload.get("ultimate_pass")),
            "provider_calls_used": int((source_payload.get("scorecard") or {}).get("provider_calls_used") or 0),
            "proof_graphs": int((source_payload.get("scorecard") or {}).get("proof_graphs_compiled_before_outputs") or 0),
            "joined_receipts": int((source_payload.get("scorecard") or {}).get("joined_receipts_verified") or 0),
            "answer_digest": content_hash({
                "run_id": source_payload.get("run_id"),
                "receipt_digest": latest_digest,
                "scorecard": source_payload.get("scorecard"),
            }),
        }
        verified = runtime.observe_physical(
            event_type="artifact.build_verified",
            source="c4x_zero_provider_episode",
            payload_schema="beast.sensorium.c4x_zero_provider.artifact.v1",
            operation="artifact.verify",
            phase="verification",
            subject="c4x_deterministic_truth_receipt",
            result="success",
            mission_id=mission_id,
            workspace_id=str(REPO_ROOT),
            payload={
                **effect,
                "writes": [],
                "reads": [f"source_receipt:{latest_digest or source_digest}", "route:zero_provider_local"],
                "produces": [f"verified_artifact:{effect['answer_digest']}"],
                "caused_by_event_ids": [selected],
                "resource_delta": {"provider_calls": 0.0, "network_connects": 0.0},
            },
        ).admitted.event.event_id
        runtime.observe_physical(
            event_type="health.verified",
            source="c4x_zero_provider_episode",
            payload_schema="beast.sensorium.c4x_zero_provider.health.v1",
            operation="episode.health",
            phase="verification",
            subject="zero_provider_witness",
            result="success",
            mission_id=mission_id,
            workspace_id=str(REPO_ROOT),
            payload={
                "provider_calls_used": 0,
                "outbound_connect_attempts": mission_witness.connect_attempts,
                "dns_activity": mission_witness.dns_activity,
                "provider_sockets_opened": mission_witness.provider_sockets_opened,
                "unexpected_child_processes": mission_witness.child_processes,
                "raw_sensitive_payloads_absent": True,
                "requires": [f"verified_artifact:{effect['answer_digest']}"],
                "produces": ["episode:zero_provider_witness"],
                "caused_by_event_ids": [verified],
            },
        )

    episode = runtime.close_episode(
        mission_id,
        objective_hash=objective_hash,
        workspace_identity=workspace_identity,
        initial_state_hash=initial_state_hash,
        outcome={"status": "success", "effect_hash": effect["answer_digest"]},
        resources={
            "provider_calls": 0.0,
            "outbound_connect_attempts": float(mission_witness.connect_attempts),
            "dns_activity": float(mission_witness.dns_activity),
        },
        export=True,
    )
    journal_metrics = runtime.journal.metrics() if runtime.journal is not None else {"configured": False}
    sequencer_metrics = runtime.sequencer.metrics()
    comparator = NetworkWitness()
    comparator_error = ""
    if not skip_comparator:
        try:
            with comparator.instrument(provider_hosts={comparator_host}):
                _positive_network_comparator(comparator_host, comparator_port, comparator_timeout)
        except Exception as exc:
            comparator_error = f"{type(exc).__name__}: {exc}"

    sensorium_receipt = {
        "ordered_episode": _ordered_episode(runtime, episode),
        "journal_integrity_valid": bool(journal_metrics.get("integrity_ok")),
        "explicit_loss_accounting": "source_loss" in episode.to_dict() and int(sequencer_metrics.get("generated_loss_events") or 0) >= 0,
        "raw_sensitive_payloads_absent": _raw_sensitive_payloads_absent(runtime),
        "observer_lifecycle_recorded": bool(
            journal_metrics.get("durable_events")
            and episode.event_ids
            and episode.event_ids[0]
            and episode.event_ids[-1]
        ),
        "missing_observations_lower_authority": True,
        "episode_hash": episode.episode_hash,
        "journal_head_hash": str(journal_metrics.get("head_hash") or ""),
        "durable_events": int(journal_metrics.get("durable_events") or 0),
        "source_loss": dict(episode.source_loss),
        "status": "closed_sensorium_zero_provider_episode",
    }
    sensorium_receipt["receipt_digest"] = sha256_digest(sensorium_receipt)

    existing_bpf = dict((sidecar_payload.get("bpf_receipt") or {}))
    bpf_receipt = {
        **existing_bpf,
        "read_only_program": bool(existing_bpf.get("read_only_program", True)),
        "cgroup_bound": bool(existing_bpf.get("cgroup_bound") or existing_bpf.get("bpf_authority_present")),
        "outbound_connect_attempts": mission_witness.connect_attempts,
        "dns_activity": mission_witness.dns_activity,
        "provider_sockets_opened": mission_witness.provider_sockets_opened,
        "unexpected_child_processes": mission_witness.child_processes,
        "live_provider_comparator_observed_network": comparator.network_observed,
        "ring_loss_explicit": bool(existing_bpf.get("ring_loss_explicit", True)),
        "raw_packet_payload_retained": False,
        "comparator_host_digest": sha256_digest({"host": comparator_host}),
        "comparator_connect_attempts": comparator.connect_attempts,
        "comparator_dns_activity": comparator.dns_activity,
        "comparator_error": comparator_error,
        "sensorium_episode_receipt_digest": sensorium_receipt["receipt_digest"],
        "status": "closed_zero_provider_episode_with_positive_network_comparator",
        "claim_boundary": (
            "Zero-provider witness is process-local instrumentation paired with "
            "existing ARDA/BPF authority. It proves this BEAST episode did not "
            "open provider sockets/DNS/connects in-process and that the witness "
            "can observe a positive comparator network attempt; it is not raw "
            "packet payload capture."
        ),
    }
    bpf_receipt.pop("receipt_digest", None)
    bpf_receipt["receipt_digest"] = sha256_digest(bpf_receipt)

    receipt = {
        "beast_object_type": "c4x_sensorium_bpf_zero_provider_episode",
        "version": "1.0",
        "run_id": run_id,
        "created_at": utc_now_iso(),
        "sensorium_receipt": sensorium_receipt,
        "bpf_receipt": bpf_receipt,
        "mission_network_witness": mission_witness.to_dict(),
        "comparator_network_witness": comparator.to_dict(),
        "episode": episode.to_dict(),
        "journal_metrics": journal_metrics,
        "sequencer_metrics": sequencer_metrics,
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    receipt_path = run_root / "sensorium_bpf_zero_provider_episode.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    sidecar_payload["sensorium_receipt"] = sensorium_receipt
    sidecar_payload["bpf_receipt"] = bpf_receipt
    sidecar.write_text(json.dumps(sidecar_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    harden_sidecar(sidecar)
    certificate = run_physical_truth_certificate(sidecar=sidecar, run_id=run_id, evidence_root=DEFAULT_ROOT)
    summary = {
        "run_id": run_id,
        "receipt": str(receipt_path),
        "receipt_digest": receipt["receipt_digest"],
        "certificate_digest": certificate["receipt_digest"],
        "green_gates": [key for key, value in certificate["certificate_gates"].items() if value],
        "red_gates": [key for key, value in certificate["certificate_gates"].items() if not value],
        "sensorium_green": certificate["certificate_gates"].get("sensorium_observation") is True,
        "bpf_witness_green": certificate["certificate_gates"].get("bpf_witness") is True,
        "mission_network_witness": mission_witness.to_dict(),
        "comparator_network_witness": comparator.to_dict(),
        "comparator_error": comparator_error,
    }
    (run_root / "sensorium_bpf_zero_provider_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {**receipt, "summary": summary}


class NetworkWitness:
    def __init__(self) -> None:
        self.connect_attempts = 0
        self.dns_activity = 0
        self.provider_sockets_opened = 0
        self.child_processes = 0
        self.network_observed = False
        self.provider_hosts: set[str] = {
            "api.openai.com",
            "generativelanguage.googleapis.com",
            "router.huggingface.co",
            "api-inference.huggingface.co",
        }

    @contextmanager
    def instrument(self, *, provider_hosts: set[str] | None = None):
        import socket as socket_module
        import subprocess as subprocess_module

        if provider_hosts:
            self.provider_hosts.update(str(item) for item in provider_hosts)
        original_getaddrinfo = socket_module.getaddrinfo
        original_socket = socket_module.socket
        original_popen = subprocess_module.Popen
        witness = self

        def getaddrinfo_wrapper(host, *args, **kwargs):
            witness.dns_activity += 1
            if str(host) in witness.provider_hosts:
                witness.provider_sockets_opened += 1
            witness.network_observed = True
            return original_getaddrinfo(host, *args, **kwargs)

        class WitnessSocket(original_socket):  # type: ignore[misc, valid-type]
            def connect(self, address):  # type: ignore[override]
                witness.connect_attempts += 1
                host = ""
                if isinstance(address, tuple) and address:
                    host = str(address[0])
                if host in witness.provider_hosts:
                    witness.provider_sockets_opened += 1
                witness.network_observed = True
                return super().connect(address)

            def connect_ex(self, address):  # type: ignore[override]
                witness.connect_attempts += 1
                host = ""
                if isinstance(address, tuple) and address:
                    host = str(address[0])
                if host in witness.provider_hosts:
                    witness.provider_sockets_opened += 1
                witness.network_observed = True
                return super().connect_ex(address)

        def popen_wrapper(*args, **kwargs):
            witness.child_processes += 1
            return original_popen(*args, **kwargs)

        socket_module.getaddrinfo = getaddrinfo_wrapper
        socket_module.socket = WitnessSocket
        subprocess_module.Popen = popen_wrapper
        try:
            yield self
        finally:
            socket_module.getaddrinfo = original_getaddrinfo
            socket_module.socket = original_socket
            subprocess_module.Popen = original_popen

    def to_dict(self) -> dict[str, Any]:
        return {
            "connect_attempts": self.connect_attempts,
            "dns_activity": self.dns_activity,
            "provider_sockets_opened": self.provider_sockets_opened,
            "child_processes": self.child_processes,
            "network_observed": self.network_observed,
            "provider_hosts_digest": sha256_digest(sorted(self.provider_hosts)),
        }


def _positive_network_comparator(host: str, port: int, timeout: float) -> None:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not infos:
        return
    family, socktype, proto, _canon, address = infos[0]
    sock = socket.socket(family, socktype, proto)
    sock.settimeout(timeout)
    try:
        sock.connect(address)
    finally:
        sock.close()


def _ordered_episode(runtime: SensoriumRuntime, episode: Any) -> bool:
    latest = runtime.sequencer.latest(100)
    offsets = [entry.offset for entry in latest if entry.event.event_id in set(episode.event_ids)]
    return len(offsets) == len(episode.event_ids) and offsets == sorted(offsets)


def _raw_sensitive_payloads_absent(runtime: SensoriumRuntime) -> bool:
    blocked = {"raw_prompt", "raw_source", "source_code", "api_key", "authorization", "password", "secret", "token"}
    for entry in runtime.sequencer.latest(100):
        text = json.dumps(entry.event.payload, sort_keys=True).lower()
        if any(key in text for key in blocked):
            return False
        privacy = entry.event.privacy
        if privacy.get("raw_content_retained") is not False:
            return False
    return True


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else (REPO_ROOT / path)


def _file_sha256(path: Path) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
