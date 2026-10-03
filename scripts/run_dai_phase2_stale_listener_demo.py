#!/usr/bin/env python3
"""Run the Phase-2 DAI stale-listener whole-creature demo.

The demo is self-contained and local:

1. start a disposable stale listener and an unrelated control listener;
2. acquire a world lease over the exact live state;
3. retire the stale listener and start a replacement on the same port;
4. prove the unrelated control listener was unchanged;
5. attempt stale lease replay and prove deterministic refusal with zero effect.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import canonical_json, sha256_digest
from app.kernel.dai.contracts import ArtifactReceipt, DAIOrgan
from app.kernel.dai.phase2_acquisition import (
    phase2_acquisition_receipt,
    stale_listener_candidate_from_sophia_examples,
    write_phase2_acquisition_receipt,
)
from app.kernel.dai.phase2_commons_quorum import (
    bind_phase2_commons_quorum,
    load_ml_kem_receipt,
    write_phase2_commons_quorum_packet,
)
from app.kernel.dai.phase2_harmonic import (
    score_stale_listener_harmonic_transfer,
    write_phase2_harmonic_report,
)
from app.kernel.dai.phase2_seraph import (
    run_stale_listener_seraph_injections,
    write_phase2_seraph_report,
)
from app.kernel.dai.phase2_sensorium_bpf import (
    build_phase2_sensorium_bpf_witness,
    capture_phase2_cgroup_snapshot,
    write_phase2_sensorium_bpf_report,
)
from app.kernel.dai.phase2_stale_listener import (
    acquire_phase2_world_lease,
    attempt_stale_world_replay,
    execute_phase2_stale_listener_replacement,
    start_phase2_stale_listener_lab,
    write_phase2_receipt,
)


DEFAULT_OUT = ROOT / "evidence/dai-diode/phase2-stale-listener-001"
DEFAULT_SOPHIA_EXAMPLES = ROOT / "fixtures/dai_phase2/stale_listener_acquisition_examples.json"
DEFAULT_ML_KEM = ROOT / "evidence/commons-ml-kem/physical-truth-commons-mlkem-live-container-helper-001.json"
DEFAULT_BPF_SIDECAR = ROOT / "evidence/c4x-physical-truth-certificate/physical_truth_sidecar_harvested.json"


def run(*, out: Path, run_id: str, sophia_examples: Path, ml_kem_receipt_path: Path, bpf_sidecar_path: Path) -> dict[str, object]:
    out.mkdir(parents=True, exist_ok=True)
    copied_examples = out / "phase2_sophia_stale_listener_examples.json"
    shutil.copy2(sophia_examples, copied_examples)
    sophia_receipt = ArtifactReceipt.from_file(
        copied_examples,
        organ=DAIOrgan.SOPHIA,
        artifact_schema="dai.phase2.sophia_stale_listener_examples.v1",
        summary={"phase": "DAI-Diode-Phase-2", "domain": "stale_listener_conflict"},
    )
    candidate, acquisition_summary = stale_listener_candidate_from_sophia_examples(
        copied_examples,
        source_receipt=sophia_receipt,
    )
    acquisition_payload = phase2_acquisition_receipt(candidate, acquisition_summary)
    write_phase2_acquisition_receipt(out / "phase2_sophia_acquisition_receipt.json", candidate, acquisition_summary)
    harmonic_report = score_stale_listener_harmonic_transfer(
        copied_examples,
        candidate_digest=candidate.candidate_digest,
        source_receipt_digest=sha256_digest(acquisition_payload),
        source_artifact_digest=sophia_receipt.artifact_digest,
    )
    write_phase2_harmonic_report(out / "phase2_harmonic_transfer_report.json", harmonic_report)
    seraph_report = run_stale_listener_seraph_injections(
        candidate_digest=candidate.candidate_digest,
        source_receipt_digest=sha256_digest(acquisition_payload),
    )
    write_phase2_seraph_report(str(out / "phase2_seraph_injection_report.json"), seraph_report)

    lab = start_phase2_stale_listener_lab(run_id=run_id)
    try:
        lease = acquire_phase2_world_lease(lab)
        before_cgroups = capture_phase2_cgroup_snapshot(lab, phase="before_replacement")
        replacement_receipt = execute_phase2_stale_listener_replacement(lab, lease)
        after_cgroups = capture_phase2_cgroup_snapshot(lab, phase="after_replacement")
        replay_receipt = attempt_stale_world_replay(lab, lease)

        lease_payload = {
            "lease": lease,
            "lease_digest": lease.lease_digest,
        }
        (out / "phase2_world_lease.json").write_text(
            canonical_json(lease_payload) + "\n",
            encoding="utf-8",
        )
        write_phase2_receipt(out / "phase2_live_replacement_receipt.json", replacement_receipt)
        write_phase2_receipt(out / "phase2_stale_world_replay_receipt.json", replay_receipt)
        proposal_digest = sha256_digest({
            "phase": "DAI-Diode-Phase-2",
            "candidate_digest": candidate.candidate_digest,
            "harmonic_transfer_report_digest": harmonic_report.report_digest,
            "seraph_injection_report_digest": seraph_report.report_digest,
            "world_state_digest": replacement_receipt.world_state_digest,
            "capability_digest": replacement_receipt.capability_digest,
            "authority": "commons_quorum_approval_only_no_execution_authority",
        })
        commons_admission, quorum_decision, commons_report = bind_phase2_commons_quorum(
            ml_kem_receipt=load_ml_kem_receipt(ml_kem_receipt_path),
            phase2_world_state_digest=replacement_receipt.world_state_digest,
            proposal_digest=proposal_digest,
            evidence_digests={
                "sophia_acquisition": sha256_digest(acquisition_payload),
                "harmonic_transfer": harmonic_report.report_digest,
                "seraph_injections": seraph_report.report_digest,
                "live_replacement": replacement_receipt.receipt_digest,
                "stale_world_replay": replay_receipt.receipt_digest,
            },
        )
        sensorium_bpf_report = build_phase2_sensorium_bpf_witness(
            phase2_world_state_digest=replacement_receipt.world_state_digest,
            proposal_digest=proposal_digest,
            live_replacement_receipt_digest=replacement_receipt.receipt_digest,
            before_cgroups=before_cgroups,
            after_cgroups=after_cgroups,
            bpf_sidecar_path=bpf_sidecar_path,
        )
        write_phase2_sensorium_bpf_report(out / "phase2_sensorium_bpf_witness_report.json", sensorium_bpf_report)
        write_phase2_commons_quorum_packet(
            out / "phase2_commons_quorum_packet.json",
            admission=commons_admission,
            quorum=quorum_decision,
            report=commons_report,
        )

        summary = {
            "beast_object_type": "dai_phase2_stale_listener_demo_summary",
            "run_id": run_id,
            "phase": "DAI-Diode-Phase-2",
            "identity": "Whole-creature stale-listener replacement and stale-world veto",
            "sophia_examples_artifact_digest": sophia_receipt.artifact_digest,
            "sophia_candidate_digest": candidate.candidate_digest,
            "sophia_acquisition_receipt_digest": sha256_digest(acquisition_payload),
            "harmonic_transfer_report_digest": harmonic_report.report_digest,
            "seraph_injection_report_digest": seraph_report.report_digest,
            "commons_quorum_report_digest": commons_report.report_digest,
            "sensorium_bpf_witness_report_digest": sensorium_bpf_report.report_digest,
            "sensorium_bpf_authority_level": sensorium_bpf_report.authority_level,
            "sensorium_exact_phase2_kernel_events_bound": sensorium_bpf_report.exact_phase2_kernel_events_bound,
            "world_lease_digest": lease.lease_digest,
            "proposal_digest": proposal_digest,
            "live_replacement_receipt_digest": replacement_receipt.receipt_digest,
            "stale_world_replay_receipt_digest": replay_receipt.receipt_digest,
            "green": bool(
                candidate.candidate_id == "sophia:phase2:stale-listener-conflict:v1"
                and candidate.maximum_authority.value == "candidate_only"
                and candidate.promotion_state.value == "quarantined_candidate"
                and harmonic_report.passed
                and harmonic_report.provider_calls_used == 0
                and seraph_report.passed
                and seraph_report.provider_calls_used == 0
                and commons_report.passed
                and commons_report.provider_calls_used == 0
                and sensorium_bpf_report.passed
                and sensorium_bpf_report.provider_calls_used == 0
                and replacement_receipt.executed
                and not replacement_receipt.red_gates
                and replay_receipt.refused
                and replay_receipt.zero_effect
                and not replay_receipt.red_gates
                and replacement_receipt.provider_calls_used == 0
                and replay_receipt.provider_calls_used == 0
            ),
            "provider_calls_used": 0,
            "production_authority_allowed": False,
            "claim_boundary": {
                "claims": [
                    "real disposable localhost listener was retired",
                    "replacement listener became healthy on the same port",
                    "unrelated control listener remained unchanged",
                    "stale world-state lease replay was refused with zero effect",
                    "Commons ML-KEM nodes admitted and role-diverse quorum approved the exact Phase-2 world digest",
                    "Sensorium/BPF authority sidecar and live Phase-2 child cgroup snapshots were bound",
                ],
                "nonclaims": [
                    "production service authority",
                    "host-wide process authority",
                    "exact Phase-2 kernel ring-buffer events unless sensorium_exact_phase2_kernel_events_bound is true",
                    "Commons execution authority",
                    "external three-machine Commons quorum",
                    "Sophia/Seraph/Harmonic live acquisition authority",
                ],
            },
        }
        summary["summary_digest"] = sha256_digest(summary)
        (out / "phase2_summary.json").write_text(canonical_json(summary) + "\n", encoding="utf-8")
        return summary
    finally:
        lab.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--run-id", default="dai-phase2-stale-listener-local-001")
    parser.add_argument("--sophia-examples", type=Path, default=DEFAULT_SOPHIA_EXAMPLES)
    parser.add_argument("--ml-kem-receipt", type=Path, default=DEFAULT_ML_KEM)
    parser.add_argument("--bpf-sidecar", type=Path, default=DEFAULT_BPF_SIDECAR)
    args = parser.parse_args()
    summary = run(
        out=args.out,
        run_id=args.run_id,
        sophia_examples=args.sophia_examples,
        ml_kem_receipt_path=args.ml_kem_receipt,
        bpf_sidecar_path=args.bpf_sidecar,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["green"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
