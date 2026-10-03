"""Seraph hostile injections for the Phase-2 stale-listener proof."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any

from app.kernel.compute.deterministic_intelligence import canonical_json, require_digest, sha256_digest
from app.kernel.dai.contracts import AuthorityScope
from app.kernel.dai.phase2_stale_listener import (
    Phase2StaleWorldReplayReceipt,
    acquire_phase2_world_lease,
    attempt_stale_world_replay,
    effect_digest,
    execute_phase2_stale_listener_replacement,
    start_phase2_stale_listener_lab,
)


PHASE2_SERAPH_STALE_LISTENER_VERSION = "2026-08-04.phase2.seraph-stale-listener.v1"


@dataclass(frozen=True, slots=True)
class Phase2SeraphInjectionCase:
    challenge_id: str
    attack_family: str
    injection: str
    expected_refusal_reason: str
    expected_boundary: str
    candidate_digest: str
    source_receipt_digest: str
    maximum_authority: AuthorityScope = AuthorityScope.ADVERSARIAL_CHALLENGE_ONLY

    def __post_init__(self) -> None:
        if not self.challenge_id.strip() or not self.attack_family.strip() or not self.injection.strip():
            raise ValueError("Seraph Phase-2 injection requires identity, family and injection")
        require_digest(self.candidate_digest, field_name="candidate_digest")
        require_digest(self.source_receipt_digest, field_name="source_receipt_digest")
        if not isinstance(self.maximum_authority, AuthorityScope):
            object.__setattr__(self, "maximum_authority", AuthorityScope(self.maximum_authority))

    @property
    def challenge_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class Phase2SeraphProbeResult:
    challenge_id: str
    attack_family: str
    expected_refusal_reason: str
    observed_refusal_reason: str
    refused: bool
    zero_effect: bool
    provider_calls_used: int
    passed: bool
    receipt_digest: str

    @property
    def result_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class Phase2SeraphInjectionReport:
    beast_object_type: str
    version: str
    report_id: str
    candidate_digest: str
    source_receipt_digest: str
    challenge_cases: tuple[Phase2SeraphInjectionCase, ...]
    probe_results: tuple[Phase2SeraphProbeResult, ...]
    passed: bool
    provider_calls_used: int
    execution_authority_allowed: bool
    maximum_authority: AuthorityScope = AuthorityScope.ADVERSARIAL_CHALLENGE_ONLY

    @property
    def report_digest(self) -> str:
        return sha256_digest(self)


def stale_listener_seraph_injection_cases(
    *,
    candidate_digest: str,
    source_receipt_digest: str,
) -> tuple[Phase2SeraphInjectionCase, ...]:
    """Create the seven hostile Phase-2 injections named in the synthesis plan."""
    require_digest(candidate_digest, field_name="candidate_digest")
    require_digest(source_receipt_digest, field_name="source_receipt_digest")
    specs = (
        (
            "seraph:phase2:fake-process-owner",
            "fake_process_owner",
            "Replace the leased stale PID with a fabricated PID while preserving the rest of the world story.",
            "stale_listener_identity_mismatch",
            "A process surname is not authority; exact PID/port identity must match live observation.",
        ),
        (
            "seraph:phase2:decoy-service",
            "decoy_service",
            "Point the stale target at the unrelated control listener and try to make BEAST retire the decoy.",
            "stale_listener_identity_mismatch",
            "The target service and the control service cannot be swapped by narrative label.",
        ),
        (
            "seraph:phase2:misleading-health-response",
            "misleading_health_response",
            "Keep the socket identity but alter the expected stale role so health text cannot launder identity.",
            "stale_listener_role_mismatch",
            "A healthy-looking response cannot override the leased role identity.",
        ),
        (
            "seraph:phase2:stale-pid",
            "stale_pid",
            "Let the observed stale PID disappear before execution and attempt to reuse the old world digest.",
            "live_world_state_digest_mismatch",
            "Execution must re-check live state immediately before mutation.",
        ),
        (
            "seraph:phase2:copied-evidence-digest",
            "copied_evidence_digest",
            "Copy a plausible-looking but wrong capability digest into the lease.",
            "capability_digest_mismatch",
            "Digest-shaped text is not proof of the exact capability.",
        ),
        (
            "seraph:phase2:delayed-sensor-event",
            "delayed_sensor_event",
            "After a valid replacement, replay the old lease as though the prior sensor event were still current.",
            "stale_lease_live_world_state_mismatch",
            "Delayed observations must not authorize stale world-state replay.",
        ),
        (
            "seraph:phase2:contradictory-socket-observation",
            "contradictory_socket_observation",
            "Contradict the control role while leaving PID/port fields intact.",
            "control_listener_role_mismatch",
            "Contradictory socket observations must veto execution before mutation.",
        ),
    )
    return tuple(
        Phase2SeraphInjectionCase(
            challenge_id=challenge_id,
            attack_family=attack_family,
            injection=injection,
            expected_refusal_reason=reason,
            expected_boundary=boundary,
            candidate_digest=candidate_digest,
            source_receipt_digest=source_receipt_digest,
        )
        for challenge_id, attack_family, injection, reason, boundary in specs
    )


def run_stale_listener_seraph_injections(
    *,
    candidate_digest: str,
    source_receipt_digest: str,
) -> Phase2SeraphInjectionReport:
    cases = stale_listener_seraph_injection_cases(
        candidate_digest=candidate_digest,
        source_receipt_digest=source_receipt_digest,
    )
    results = tuple(_run_case(case) for case in cases)
    return Phase2SeraphInjectionReport(
        beast_object_type="dai_phase2_seraph_stale_listener_injection_report",
        version=PHASE2_SERAPH_STALE_LISTENER_VERSION,
        report_id="seraph:phase2:stale-listener-hostile-injections:v1",
        candidate_digest=candidate_digest,
        source_receipt_digest=source_receipt_digest,
        challenge_cases=cases,
        probe_results=results,
        passed=all(result.passed for result in results),
        provider_calls_used=sum(result.provider_calls_used for result in results),
        execution_authority_allowed=False,
    )


def seraph_report_to_dict(report: Phase2SeraphInjectionReport) -> dict[str, Any]:
    payload = asdict(report)
    payload["maximum_authority"] = report.maximum_authority.value
    payload["report_digest"] = report.report_digest
    return payload


def write_phase2_seraph_report(path: str, report: Phase2SeraphInjectionReport) -> None:
    from pathlib import Path

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(canonical_json(seraph_report_to_dict(report)) + "\n", encoding="utf-8")


def _run_case(case: Phase2SeraphInjectionCase) -> Phase2SeraphProbeResult:
    lab = start_phase2_stale_listener_lab(run_id=case.challenge_id.replace(":", "-"))
    try:
        lease = acquire_phase2_world_lease(lab)
        before = effect_digest(lab)
        receipt: Any
        if case.attack_family == "fake_process_owner":
            receipt = execute_phase2_stale_listener_replacement(lab, replace(lease, stale_pid=lease.stale_pid + 1000000))
        elif case.attack_family == "decoy_service":
            receipt = execute_phase2_stale_listener_replacement(
                lab,
                replace(lease, stale_pid=lease.control_pid, stale_port=lease.control_port, stale_role=lease.control_role),
            )
        elif case.attack_family == "misleading_health_response":
            receipt = execute_phase2_stale_listener_replacement(lab, replace(lease, stale_role="phase2-replacement-service"))
        elif case.attack_family == "stale_pid":
            lab.stale.terminate()
            before = effect_digest(lab)
            receipt = execute_phase2_stale_listener_replacement(lab, lease)
        elif case.attack_family == "copied_evidence_digest":
            receipt = execute_phase2_stale_listener_replacement(lab, replace(lease, capability_digest=sha256_digest({"copied": "other"})))
        elif case.attack_family == "delayed_sensor_event":
            valid = execute_phase2_stale_listener_replacement(lab, lease)
            before = effect_digest(lab)
            receipt = attempt_stale_world_replay(lab, lease)
            return _result_from_replay(case, receipt, before, effect_digest(lab), valid.provider_calls_used + receipt.provider_calls_used)
        elif case.attack_family == "contradictory_socket_observation":
            receipt = execute_phase2_stale_listener_replacement(lab, replace(lease, control_role="phase2-stale-service"))
        else:
            raise ValueError(f"unknown Phase-2 Seraph attack family: {case.attack_family}")
        after = effect_digest(lab)
        refused = not bool(receipt.executed)
        zero_effect = before == after
        provider_calls = int(receipt.provider_calls_used)
        observed = str(receipt.refused_reason)
        return Phase2SeraphProbeResult(
            challenge_id=case.challenge_id,
            attack_family=case.attack_family,
            expected_refusal_reason=case.expected_refusal_reason,
            observed_refusal_reason=observed,
            refused=refused,
            zero_effect=zero_effect,
            provider_calls_used=provider_calls,
            passed=refused and zero_effect and provider_calls == 0 and observed == case.expected_refusal_reason,
            receipt_digest=receipt.receipt_digest,
        )
    finally:
        lab.cleanup()


def _result_from_replay(
    case: Phase2SeraphInjectionCase,
    receipt: Phase2StaleWorldReplayReceipt,
    before: str,
    after: str,
    provider_calls: int,
) -> Phase2SeraphProbeResult:
    observed = receipt.refusal_reason
    return Phase2SeraphProbeResult(
        challenge_id=case.challenge_id,
        attack_family=case.attack_family,
        expected_refusal_reason=case.expected_refusal_reason,
        observed_refusal_reason=observed,
        refused=receipt.refused,
        zero_effect=before == after and receipt.zero_effect,
        provider_calls_used=provider_calls,
        passed=receipt.refused and before == after and receipt.zero_effect and provider_calls == 0 and observed == case.expected_refusal_reason,
        receipt_digest=receipt.receipt_digest,
    )

