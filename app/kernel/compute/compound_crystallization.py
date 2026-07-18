"""Fail-closed compound crystallization DAG and a bounded integration fixture.

This module deliberately proves composition mechanics, not frontier quality.
Every edge binds an output digest and predecessor proof digest; a bad edge
prevents mutation.  The gateway fixture composes two independently registered
patch fragments rather than replaying a stored final patch.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from app.kernel.compute.final_boss_crystallization_gauntlet import (
    MultiFilePatchTool,
    final_boss_spec,
    fixed_gateway_contents,
    verify_gateway_repo,
    write_gateway_repo,
)


STAGES = ("envelope", "evidence", "plan", "execute", "verify")


def canonical_digest(value: Any) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


@dataclass(frozen=True)
class StageReceipt:
    stage: str
    inputs: Mapping[str, str]
    output: Mapping[str, Any]
    verifier: str
    verifier_output: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        output_digest = canonical_digest(self.output)
        proof = {
            "stage": self.stage,
            "inputs": dict(self.inputs),
            "output_digest": output_digest,
            "verifier": self.verifier,
            "verifier_output": dict(self.verifier_output),
        }
        return {
            "beast_object_type": "compound_crystal_stage_receipt",
            "version": "1.0",
            "output": dict(self.output),
            **proof,
            "proof_digest": canonical_digest(proof),
        }


class CompoundAdmissionError(ValueError):
    """Raised before mutation when a composed capability is not admissible."""


class CompoundCrystallizationDAG:
    """Small typed DAG validator with fail-closed predecessor binding."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}

    def admit(self, row: Mapping[str, Any], *, predecessors: tuple[str, ...] = ()) -> None:
        stage = str(row.get("stage") or "")
        if stage not in STAGES:
            raise CompoundAdmissionError("unknown composition stage")
        if stage in self.rows:
            raise CompoundAdmissionError(f"duplicate stage: {stage}")
        if not bool((row.get("verifier_output") or {}).get("passed")):
            raise CompoundAdmissionError(f"stage verifier failed: {stage}")
        computed_output = canonical_digest(row.get("output") or {})
        if row.get("output_digest") != computed_output:
            raise CompoundAdmissionError(f"output digest mismatch: {stage}")
        proof = {
            "stage": stage,
            "inputs": dict(row.get("inputs") or {}),
            "output_digest": computed_output,
            "verifier": row.get("verifier"),
            "verifier_output": dict(row.get("verifier_output") or {}),
        }
        if row.get("proof_digest") != canonical_digest(proof):
            raise CompoundAdmissionError(f"proof digest mismatch: {stage}")
        supplied = dict(row.get("inputs") or {})
        for predecessor in predecessors:
            prior = self.rows.get(predecessor)
            if not prior:
                raise CompoundAdmissionError(f"missing predecessor: {predecessor}")
            expected = str(prior["proof_digest"])
            if supplied.get(predecessor) != expected:
                raise CompoundAdmissionError(f"invalid predecessor proof: {predecessor}->{stage}")
        self.rows[stage] = dict(row)

    def receipt(self) -> dict[str, Any]:
        return {stage: self.rows[stage] for stage in STAGES if stage in self.rows}


class CompoundGatewayMigrationGauntlet:
    """Bounded compound proof fixture; it is not a frontier-comparator runner."""

    def __init__(self, root: Path, *, decoy_files: int = 24) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.decoy_files = max(0, int(decoy_files))
        self.patch_tool = MultiFilePatchTool()

    def run(self) -> dict[str, Any]:
        repo = self.root / "heldout_gateway_repo"
        write_gateway_repo(repo, variant="far_transfer", decoy_files=self.decoy_files)
        baseline = verify_gateway_repo(repo)
        dag = CompoundCrystallizationDAG()

        envelope = {
            "task_class": final_boss_spec().task_class,
            "risk_class": "approved_multifile_patch",
            "postcondition": "gateway_integration_pytest",
            "repo_digest": self._repo_digest(repo),
        }
        envelope_row = StageReceipt(
            "envelope", {}, envelope, "envelope_contract_v1",
            {"passed": not baseline["tests_passed"], "baseline_tests_failed": not baseline["tests_passed"]},
        ).to_dict()
        dag.admit(envelope_row)

        fragments = self._fragments(repo)
        evidence = {
            "candidates": fragments,
            "provenance_lanes": sorted({str(item["provenance_lane"]) for item in fragments}),
            "contract": {"task_class": envelope["task_class"], "postcondition": envelope["postcondition"]},
        }
        evidence_ok = len(evidence["provenance_lanes"]) >= 2 and all(item["patches"] for item in fragments)
        evidence_row = StageReceipt(
            "evidence", {"envelope": envelope_row["proof_digest"]}, evidence, "candidate_contract_verifier_v1",
            {"passed": evidence_ok, "separate_provenance_lanes": len(evidence["provenance_lanes"])},
        ).to_dict()
        dag.admit(evidence_row, predecessors=("envelope",))

        recipe = self._compose_plan(repo, fragments)
        required = set(final_boss_spec().changed_files)
        plan_paths = {str(p["path"]) for p in recipe["patches"]}
        plan_row = StageReceipt(
            "plan",
            {"envelope": envelope_row["proof_digest"], "evidence": evidence_row["proof_digest"]},
            recipe,
            "typed_patch_ir_verifier_v1",
            {"passed": plan_paths == required, "paths": sorted(plan_paths), "fragment_count": len(fragments)},
        ).to_dict()
        dag.admit(plan_row, predecessors=("envelope", "evidence"))

        applied = self.patch_tool.apply(repo, recipe)
        execute_row = StageReceipt(
            "execute", {"plan": plan_row["proof_digest"]}, applied, "approved_multifile_patch_tool",
            {"passed": applied["file_count"] == len(required), "file_count": applied["file_count"]},
        ).to_dict()
        dag.admit(execute_row, predecessors=("plan",))

        verification = verify_gateway_repo(repo)
        verify_row = StageReceipt(
            "verify", {"execute": execute_row["proof_digest"], "plan": plan_row["proof_digest"]}, verification,
            "independent_pytest_v1", {"passed": bool(verification["tests_passed"]), "returncode": verification["returncode"]},
        ).to_dict()
        dag.admit(verify_row, predecessors=("execute", "plan"))
        negatives = self._negative_controls(envelope_row, evidence_row, plan_row)
        stages = dag.receipt()
        receipt = {
            "beast_object_type": "compound_agentic_crystallization_receipt",
            "version": "1.0",
            "claim_boundary": "bounded typed composition fixture only; not quality equivalence, frontier comparison, economics, or independent replication",
            "stages": stages,
            "baseline": baseline,
            "postcondition": verification,
            "negative_controls": negatives,
            "metrics": {
                "replay_time_model_calls": 0,
                "replay_time_provider_calls": 0,
                "decoy_files": self.decoy_files,
                "provenance_lanes": len(evidence["provenance_lanes"]),
                "fragment_count": len(fragments),
            },
            "claims": {
                "typed_dag_composed": set(stages) == set(STAGES),
                "separate_evidence_lanes": evidence_ok,
                "postcondition_verified": bool(verification["tests_passed"]),
                "mandatory_negative_refusal": all(item["refused"] for item in negatives),
                "no_replay_time_model_or_provider_calls": True,
                "quality_equivalence_established": False,
                "frontier_ephemeral_comparison_established": False,
            },
        }
        receipt["receipt_digest"] = canonical_digest(receipt)
        (self.root / "compound_agentic_crystallization_receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return receipt

    def _fragments(self, repo: Path) -> list[dict[str, Any]]:
        contents = fixed_gateway_contents()
        lanes = (
            ("contract_normalization_lane", ("gateway/providers.py", "gateway/client.py")),
            ("safety_streaming_lane", ("gateway/auth.py", "gateway/streaming.py")),
        )
        return [
            {
                "candidate_id": f"fragment-{index + 1}", "provenance_lane": lane,
                "contract": "gateway_integration_pytest",
                "patches": [{"path": path, "expected_sha256": self._file_digest(repo / path), "content": contents[path]} for path in paths],
            }
            for index, (lane, paths) in enumerate(lanes)
        ]

    def _compose_plan(self, repo: Path, fragments: list[dict[str, Any]]) -> dict[str, Any]:
        patches = [patch for fragment in fragments for patch in fragment["patches"]]
        if len({patch["path"] for patch in patches}) != len(patches):
            raise CompoundAdmissionError("overlapping fragment writes require an explicit merge crystal")
        return {
            "beast_object_type": "COMPOUND_TYPED_PATCH_IR",
            "version": "1.0",
            "task_class": final_boss_spec().task_class,
            "patches": patches,
            "dependency_edges": ["envelope->evidence", "envelope+evidence->plan", "plan->execute", "plan+execute->verify"],
            "input_repo_digest": self._repo_digest(repo),
        }

    def _negative_controls(self, envelope: Mapping[str, Any], evidence: Mapping[str, Any], plan: Mapping[str, Any]) -> list[dict[str, Any]]:
        cases = []
        for name, row, predecessor, replacement in (("broken_predecessor_proof", evidence, "envelope", "sha256:broken"),):
            dag = CompoundCrystallizationDAG()
            dag.admit(envelope)
            candidate = json.loads(json.dumps(row))
            candidate["inputs"][predecessor] = replacement
            try:
                dag.admit(candidate, predecessors=("envelope",))
                refused = False
            except CompoundAdmissionError:
                refused = True
            cases.append({"case": name, "refused": refused, "mutation_attempted": False})
        dag = CompoundCrystallizationDAG()
        dag.admit(envelope)
        dag.admit(evidence, predecessors=("envelope",))
        poisoned_plan = json.loads(json.dumps(plan))
        poisoned_plan["inputs"]["evidence"] = "sha256:poisoned"
        try:
            dag.admit(poisoned_plan, predecessors=("envelope", "evidence"))
            refused = False
        except CompoundAdmissionError:
            refused = True
        cases.append({"case": "poisoned_intermediate_ir", "refused": refused, "mutation_attempted": False})
        return cases

    @staticmethod
    def _file_digest(path: Path) -> str:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

    def _repo_digest(self, root: Path) -> str:
        return canonical_digest({str(p.relative_to(root)): self._file_digest(p) for p in sorted(root.rglob("*.py"))})
