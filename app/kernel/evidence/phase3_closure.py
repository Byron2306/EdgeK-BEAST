"""BEAST Phase 3.13 end-to-end proof closure and canonical regression gate."""
from __future__ import annotations

import json
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Optional

SCHEMA_VERSION = "3.13"
REQUIRED_PHASES = tuple(f"3.{n}" for n in range(1, 13))
RECEIPT_CONTRACTS = {
    "3.5": ("beast_evidence_compatibility_receipt", {"EXACT", "ADAPTABLE"}),
    "3.6": ("beast_evidence_reuse_receipt", {"PREPARED_EXACT_REPLAY", "PREPARED_ADAPTATION_SEED"}),
    "3.7": ("beast_evidence_reuse_outcome_receipt", {"VERIFIED_EQUIVALENT", "VERIFIED_ADAPTED"}),
    "3.8": ("beast_evidence_sourceplan_handoff_receipt", {"SOURCEPLAN_REVIEW_READY"}),
    "3.9": ("beast_evidence_operator_approval_receipt", {"OPERATOR_APPROVED"}),
    "3.10": ("beast_evidence_capability_consumption_receipt", {"SOURCEPLAN_APPLIED"}),
    "3.11": ("beast_evidence_post_apply_promotion_gate_receipt", {"PROMOTION_ELIGIBLE"}),
    "3.12": ("beast_evidence_promotion_closure_receipt", {"PROMOTION_COMPLETED"}),
}
MODULES = {
    "3.1": "evidence_builder.py", "3.2": "evidence_ledger.py", "3.3": "fingerprint_engine.py",
    "3.4": "evidence_retrieval.py", "3.5": "compatibility_engine.py", "3.6": "reuse_engine.py",
    "3.7": "equivalence_engine.py", "3.8": "sourceplan_handoff.py", "3.9": "operator_approval.py",
    "3.10": "capability_consumption.py", "3.11": "post_apply_gate.py", "3.12": "promotion_closure.py",
}

class Phase3ClosureError(ValueError):
    pass

def _canonical(v: Any) -> bytes:
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()

def digest_object(v: Any) -> str:
    return "sha256:" + sha256(_canonical(v)).hexdigest()

def digest_file(path: Path) -> str:
    h = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()

def verify_receipt_digest(receipt: Mapping[str, Any]) -> bool:
    return isinstance(receipt.get("receipt_digest"), str) and receipt["receipt_digest"] == digest_object(
        {k: v for k, v in receipt.items() if k != "receipt_digest"}
    )

@dataclass(frozen=True)
class ClosurePolicy:
    minimum_regression_tests: int = 63
    require_all_regression_tests_pass: bool = True
    require_python_compilation: bool = True
    require_architecture_checks: bool = True
    require_operational_proof: bool = True
    def __post_init__(self) -> None:
        if not 1 <= self.minimum_regression_tests <= 100000:
            raise Phase3ClosureError("invalid minimum regression count")
    @classmethod
    def from_mapping(cls, value: Optional[Mapping[str, Any]]) -> "ClosurePolicy":
        if not value:
            return cls()
        unknown = set(value) - set(cls.__dataclass_fields__)
        if unknown:
            raise Phase3ClosureError(f"unknown closure policy controls: {sorted(unknown)}")
        return cls(**dict(value))

class Phase3EndToEndProofClosure:
    def close(
        self, *, root_path: str, phase_evidence: Mapping[str, Any], receipt_chain: Mapping[str, Any],
        regression_report: Mapping[str, Any], policy_controls: Optional[Mapping[str, Any]] = None,
        output_directory: Optional[str] = None, created_at: Optional[str] = None,
    ) -> dict[str, Any]:
        root = Path(root_path).resolve()
        policy = ClosurePolicy.from_mapping(policy_controls)
        now = datetime.fromisoformat(created_at.replace("Z", "+00:00")) if created_at else datetime.now(timezone.utc)
        blockers: list[str] = []
        phase_records: list[dict[str, Any]] = []
        source_records: list[dict[str, Any]] = []

        if not root.is_dir():
            blockers.append("repository_root_missing")
        evidence_kernel = root / "app/kernel/evidence"
        for phase in REQUIRED_PHASES:
            evidence = phase_evidence.get(phase)
            if not isinstance(evidence, Mapping):
                blockers.append(f"phase_evidence_missing:{phase}")
                continue
            artifact_digest = evidence.get("artifact_digest")
            if not isinstance(artifact_digest, str) or not artifact_digest.startswith("sha256:"):
                blockers.append(f"phase_artifact_digest_invalid:{phase}")
            if evidence.get("status") != "PASS":
                blockers.append(f"phase_evidence_not_passed:{phase}")
            if policy.require_operational_proof and evidence.get("verification_class") not in {"local-live", "external-live", "operational"}:
                blockers.append(f"phase_operational_proof_missing:{phase}")
            phase_records.append({"phase": phase, **dict(evidence)})
            module = evidence_kernel / MODULES[phase]
            if not module.is_file():
                blockers.append(f"phase_module_missing:{phase}:{MODULES[phase]}")
            else:
                source_records.append({"phase": phase, "path": module.relative_to(root).as_posix(), "digest": digest_file(module)})

        for phase, (object_type, dispositions) in RECEIPT_CONTRACTS.items():
            receipt = receipt_chain.get(phase)
            if not isinstance(receipt, Mapping):
                blockers.append(f"receipt_missing:{phase}")
                continue
            if receipt.get("version") != phase or receipt.get("beast_object_type") != object_type:
                blockers.append(f"receipt_contract_invalid:{phase}")
            if not verify_receipt_digest(receipt):
                blockers.append(f"receipt_digest_invalid:{phase}")
            if receipt.get("disposition", receipt.get("verdict")) not in dispositions:
                blockers.append(f"receipt_terminal_disposition_invalid:{phase}")
            if receipt.get("phase2_governance_bypass_allowed") is True:
                blockers.append(f"governance_bypass_detected:{phase}")
            if phase != "3.12" and receipt.get("promotion_authorized") is True:
                blockers.append(f"premature_promotion_authority:{phase}")

        self._verify_bindings(receipt_chain, blockers)
        passed = int(regression_report.get("passed", 0) or 0)
        failed = int(regression_report.get("failed", 0) or 0)
        if passed < policy.minimum_regression_tests:
            blockers.append("regression_test_count_below_policy")
        if policy.require_all_regression_tests_pass and failed != 0:
            blockers.append("regression_failures_present")
        if policy.require_python_compilation and regression_report.get("python_compilation") != "PASS":
            blockers.append("python_compilation_not_passed")
        if policy.require_architecture_checks:
            arch = regression_report.get("architecture_checks") or {}
            if arch.get("passed") != arch.get("total") or not arch.get("total"):
                blockers.append("architecture_checks_not_all_passed")

        phase_records.sort(key=lambda x: tuple(map(int, x["phase"].split("."))))
        source_records.sort(key=lambda x: tuple(map(int, x["phase"].split("."))))
        chain_summary = [
            {"phase": p, "receipt_digest": receipt_chain[p].get("receipt_digest"),
             "disposition": receipt_chain[p].get("disposition", receipt_chain[p].get("verdict"))}
            for p in RECEIPT_CONTRACTS if isinstance(receipt_chain.get(p), Mapping)
        ]
        core = {
            "version": SCHEMA_VERSION,
            "beast_object_type": "beast_phase3_end_to_end_closure_receipt",
            "disposition": "PHASE3_CLOSED" if not blockers else "PHASE3_CLOSURE_BLOCKED",
            "phase3_complete": not blockers,
            "authority": "historical_proof_closure_only",
            "further_mutation_authorized": False,
            "promotion_authorized": False,
            "phase2_governance_bypass_allowed": False,
            "required_phases": list(REQUIRED_PHASES),
            "phase_evidence": phase_records,
            "receipt_chain": chain_summary,
            "source_manifest": source_records,
            "regression_report": dict(regression_report),
            "policy_digest": digest_object(asdict(policy)),
            "blockers": sorted(set(blockers)),
            "created_at": now.astimezone(timezone.utc).isoformat(),
        }
        receipt = {**core, "receipt_digest": digest_object(core)}
        if output_directory and not blockers:
            receipt["proof_bundle"] = self._write_bundle(Path(output_directory), receipt)
            unsigned = {k: v for k, v in receipt.items() if k != "receipt_digest"}
            receipt["receipt_digest"] = digest_object(unsigned)
        return receipt

    @staticmethod
    def _verify_bindings(chain: Mapping[str, Any], blockers: list[str]) -> None:
        pairs = [
            ("3.6", "compatibility_receipt_digest", "3.5"),
            ("3.7", "reuse_receipt_digest", "3.6"),
            ("3.8", "outcome_receipt_digest", "3.7"),
            ("3.9", "handoff_receipt_digest", "3.8"),
            ("3.10", "approval_receipt_digest", "3.9"),
            ("3.11", "consumption_receipt_digest", "3.10"),
            ("3.12", "eligibility_receipt_digest", "3.11"),
        ]
        for child, field, parent in pairs:
            c, p = chain.get(child), chain.get(parent)
            if not isinstance(c, Mapping) or not isinstance(p, Mapping):
                continue
            if c.get(field) != p.get("receipt_digest"):
                blockers.append(f"receipt_parent_binding_invalid:{child}:{field}")
        binding_keys = ("evidence_id", "plan_id", "worktree_id", "sourceplan_digest", "operations_digest")
        for key in binding_keys:
            values = {str(r.get(key)) for p, r in chain.items() if p in RECEIPT_CONTRACTS and isinstance(r, Mapping) and r.get(key) is not None}
            if len(values) > 1:
                blockers.append(f"cross_phase_binding_drift:{key}")

    @staticmethod
    def _write_bundle(output: Path, receipt: Mapping[str, Any]) -> dict[str, Any]:
        output.mkdir(parents=True, exist_ok=True)
        manifest = output / "PHASE3_CLOSURE_MANIFEST.json"
        manifest.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        sums = output / "SHA256SUMS"
        sums.write_text(f"{digest_file(manifest).split(':',1)[1]}  {manifest.name}\n", encoding="utf-8")
        archive = output.with_suffix(".zip")
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(manifest, manifest.name)
            zf.write(sums, sums.name)
        return {"directory": str(output), "archive": str(archive), "archive_digest": digest_file(archive)}
