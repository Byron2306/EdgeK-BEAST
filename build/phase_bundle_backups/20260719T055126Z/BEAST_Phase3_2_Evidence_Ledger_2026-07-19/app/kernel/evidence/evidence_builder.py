"""Crystallize a promoted AgentRun into an immutable evidence object."""
from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.evidence.evidence_digest import sha256_digest
from app.kernel.evidence.evidence_models import EvidenceArtifact, EvidenceObject
from app.kernel.evidence.evidence_store import EvidenceStore
from app.kernel.evidence.evidence_verify import verify_evidence_object


class EvidenceBuilder:
    VERSION = "3.1"

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.engine = AgentRunEngine(self.workspace_root)
        self.store = EvidenceStore(self.workspace_root)

    def _eligible_run(self, run_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        run = self.engine.store.get_run(run_id)
        if not run:
            raise KeyError(f"unknown agent run: {run_id}")
        checkpoint = dict(run.get("checkpoint") or {})
        promotion = dict(checkpoint.get("promotion") or {})
        candidate = dict(checkpoint.get("commit_candidate") or {})
        if promotion.get("status") != "promoted" or not candidate.get("commit"):
            raise PermissionError("evidence crystallization requires a promoted commit candidate")
        if candidate.get("applied_to_operator_workspace") is not False:
            raise PermissionError("commit candidate isolation provenance is invalid")
        chain = self.engine.store.verify_chain(run_id)
        if not chain.get("ok") or not chain.get("head_matches"):
            raise PermissionError("AgentRun event chain is invalid")
        return run, checkpoint

    def crystallize(self, run_id: str) -> dict[str, Any]:
        existing = self.store.get_by_run(run_id)
        if existing:
            return existing
        run, checkpoint = self._eligible_run(run_id)
        events = self.engine.store.events(run_id, after=0, limit=100000)
        observations = [event for event in events if str(event.get("event_type") or "").startswith("agent.tool.")]
        verification_events = [event for event in events if str(event.get("event_type") or "").startswith("agent.verification.")]
        approvals = self.engine.store.approvals(run_id)
        promotion = dict(checkpoint.get("promotion") or {})
        candidate = dict(checkpoint.get("commit_candidate") or {})
        sourceplan = dict(checkpoint.get("sourceplan") or {})
        verification = dict(checkpoint.get("verification") or {})
        planner = dict(checkpoint.get("planner") or {})

        artifact_values = {
            "event_chain": events,
            "observations": observations,
            "sourceplan": sourceplan,
            "receipts": {"verification": verification, "promotion": promotion, "commit_candidate": candidate},
            "approvals": approvals,
        }
        evidence_id = f"crystal-{uuid.uuid4().hex[:24]}"
        artifacts = tuple(
            EvidenceArtifact(
                artifact_id=f"{evidence_id}-{kind}",
                kind=kind,
                digest=sha256_digest(value),
                metadata={"records": len(value) if isinstance(value, list) else 1},
            )
            for kind, value in artifact_values.items()
        )
        created_at = time.time()
        worktree = {
            "task_id": checkpoint.get("worktree_task_id"),
            "branch": checkpoint.get("worktree_branch"),
            "base_commit": checkpoint.get("worktree_base_commit"),
            "commit": candidate.get("commit"),
            "mutation_epoch": checkpoint.get("worktree_mutation_epoch"),
        }
        task = {
            "objective": run.get("objective"),
            "mode": run.get("mode"),
            "provider": run.get("provider"),
            "model": run.get("model"),
            "planner_turns": planner.get("turn", 0),
            "repair_cycles": planner.get("repair_cycles", 0),
            "task_fingerprint": sha256_digest({"objective": run.get("objective"), "mode": run.get("mode"), "sourceplan_operations": sourceplan.get("operations", [])}),
        }
        environment = {
            "workspace_root_name": self.workspace_root.name,
            "base_commit": checkpoint.get("worktree_base_commit"),
            "branch": checkpoint.get("worktree_branch"),
            "environment_fingerprint": sha256_digest(worktree),
        }
        provenance = {
            "run_id": run_id,
            "session_id": run.get("session_id"),
            "event_count": len(events),
            "event_chain_head": events[-1]["event_hash"] if events else "",
            "agent_run_created_at": run.get("created_at"),
            "crystallized_at": created_at,
        }
        authority = {
            "promotion_approval_id": candidate.get("approval_id"),
            "approved_by": candidate.get("approved_by"),
            "promotion_receipt_digest": candidate.get("receipt_digest"),
            "operator_workspace_applied": candidate.get("applied_to_operator_workspace"),
        }
        draft = EvidenceObject(
            evidence_id=evidence_id,
            version=self.VERSION,
            kind="verified_sourceplan_commit_candidate",
            created_at=created_at,
            run_id=run_id,
            task=task,
            environment=environment,
            transformation={"sourceplan_id": sourceplan.get("plan_id"), "candidate_id": candidate.get("candidate_id"), "commit": candidate.get("commit"), "worktree": worktree},
            verification=verification,
            promotion=promotion,
            provenance=provenance,
            authority=authority,
            reuse_constraints={"mode": "adapt_and_reverify", "fresh_verification_required": True, "phase2_governance_bypass_allowed": False},
            artifacts=artifacts,
            evidence_digest="",
        )
        core = draft.core_dict()
        evidence = EvidenceObject(**{**draft.__dict__, "evidence_digest": sha256_digest(core)}).as_dict()
        stored = self.store.put(evidence)
        for artifact in artifacts:
            self.store.put_artifact(evidence_id, artifact.artifact_id, artifact.kind, artifact_values[artifact.kind])
        self.engine.emit(run_id, "agent.evidence.crystallized", {"evidence_id": evidence_id, "evidence_digest": evidence["evidence_digest"]})
        return stored

    def verify(self, evidence_id: str) -> dict[str, Any]:
        evidence = self.store.get(evidence_id)
        if not evidence:
            raise KeyError(f"unknown evidence crystal: {evidence_id}")
        artifacts: dict[str, Any] = {}
        import json, sqlite3
        with sqlite3.connect(self.store.db_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute("SELECT kind,object_path FROM evidence_artifacts WHERE evidence_id=?", (evidence_id,)).fetchall()
        for row in rows:
            artifacts[str(row["kind"])] = json.loads(Path(str(row["object_path"])).read_text(encoding="utf-8"))
        return verify_evidence_object(evidence, artifacts)
