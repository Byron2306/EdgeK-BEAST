from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.agents.run_state import AgentRunState, normalize_state

from .capability_issuer import RequestBoundCapabilityIssuer
from .digests import canonical_json, canonicalize, semantic_payload, sha256_digest, verify_digest
from .models import ApprovalContractFactory

RUNTIME_VERSION = "4.7"
RECEIPT_OBJECT_TYPE = "beast_capability_consumption_resume_receipt"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_time(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError("timestamp is required")
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class CapabilityConsumptionResumeReceipt:
    consumption_id: str
    capability_id: str
    capability_digest: str
    approval_id: str
    request_digest: str
    run_id: str
    step_id: str
    tool_id: str
    tool_version: str
    workspace_id: str
    execution_target: str
    policy_generation: str
    call_identity_digest: str
    consumed_at: str
    resume_state: str
    run_resumed: bool
    tool_execution_started: bool
    capability_consumed: bool = True
    replay_allowed: bool = False
    authority: str = "consumed_exact_step_resume_only"
    workspace_mutation_authorized: bool = False
    promotion_authorized: bool = False
    phase2_governance_bypass_allowed: bool = False
    version: str = RUNTIME_VERSION
    beast_object_type: str = RECEIPT_OBJECT_TYPE
    receipt_digest: str = ""

    def semantic_dict(self) -> dict[str, Any]:
        return canonicalize(semantic_payload(asdict(self), exclude={"receipt_digest"}))

    def to_dict(self) -> dict[str, Any]:
        payload = canonicalize(asdict(self))
        payload["receipt_digest"] = self.receipt_digest or sha256_digest(self.semantic_dict())
        return payload


class CapabilityConsumptionStore:
    """Durable one-use ledger for Phase 4 tool capabilities.

    Consumption is committed before AgentRun state is changed. A crash may leave a
    burned capability awaiting recovery, but can never make the capability reusable.
    """

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.db_path = self.workspace_root / ".beast" / "approvals" / "capability_consumption.sqlite3"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, timeout=30.0)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS capability_consumptions (
                    capability_id TEXT PRIMARY KEY,
                    capability_digest TEXT NOT NULL,
                    approval_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    request_digest TEXT NOT NULL,
                    status TEXT NOT NULL,
                    consumed_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    receipt_json TEXT
                )
                """
            )
            db.execute("CREATE INDEX IF NOT EXISTS idx_capability_run_step ON capability_consumptions(run_id, step_id)")

    def consume_pending(self, capability: Mapping[str, Any], *, consumed_at: datetime) -> dict[str, Any]:
        row = {
            "capability_id": str(capability["capability_id"]),
            "capability_digest": str(capability["capability_digest"]),
            "approval_id": str(capability["approval_id"]),
            "run_id": str(capability["run_id"]),
            "step_id": str(capability["step_id"]),
            "request_digest": str(capability["request_digest"]),
            "status": "CONSUMED_PENDING_RESUME",
            "consumed_at": _iso(consumed_at),
            "updated_at": _iso(consumed_at),
        }
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                existing = db.execute(
                    "SELECT * FROM capability_consumptions WHERE capability_id=?",
                    (row["capability_id"],),
                ).fetchone()
                if existing:
                    raise ValueError("capability_already_consumed")
                db.execute(
                    """
                    INSERT INTO capability_consumptions(
                        capability_id, capability_digest, approval_id, run_id,
                        step_id, request_digest, status, consumed_at, updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    """,
                    tuple(row.values()),
                )
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return row

    def finalize(self, capability_id: str, *, status: str, receipt: Mapping[str, Any]) -> None:
        now = _iso(_utcnow())
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                changed = db.execute(
                    "UPDATE capability_consumptions SET status=?,updated_at=?,receipt_json=? WHERE capability_id=?",
                    (str(status), now, canonical_json(receipt), str(capability_id)),
                ).rowcount
                if changed != 1:
                    raise KeyError(f"unknown consumed capability: {capability_id}")
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise

    def get(self, capability_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM capability_consumptions WHERE capability_id=?",
                (str(capability_id),),
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["receipt"] = json.loads(result.pop("receipt_json")) if result.get("receipt_json") else None
        return result

    def pending_recovery(self, *, run_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM capability_consumptions WHERE status='CONSUMED_PENDING_RESUME'"
        params: tuple[Any, ...] = ()
        if run_id:
            sql += " AND run_id=?"
            params = (str(run_id),)
        sql += " ORDER BY consumed_at"
        with self._connect() as db:
            return [dict(row) for row in db.execute(sql, params).fetchall()]


class ExactStepResumeRuntime:
    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.issuer = RequestBoundCapabilityIssuer()
        self.contracts = ApprovalContractFactory()
        self.consumptions = CapabilityConsumptionStore(self.workspace_root)
        self.engine = AgentRunEngine(self.workspace_root)

    def _validate_bindings(
        self,
        capability: Mapping[str, Any],
        request: Mapping[str, Any],
        *,
        now: datetime,
    ) -> dict[str, Any]:
        if not self.issuer.verify(capability, now=now, require_unexpired=True):
            raise ValueError("capability is invalid, tampered, or expired")
        self.contracts.validate_request(request)
        bindings = {
            "approval_id": "approval_id",
            "request_digest": "request_digest",
            "run_id": "run_id",
            "step_id": "step_id",
            "tool_id": "tool_id",
            "tool_version": "tool_version",
            "workspace_id": "workspace_id",
            "execution_target": "execution_target",
            "policy_generation": "policy_generation",
        }
        for capability_field, request_field in bindings.items():
            if str(capability.get(capability_field)) != str(request.get(request_field)):
                raise ValueError(f"capability {capability_field} binding mismatch")
        if capability.get("audience") != "beast-tool-runtime":
            raise ValueError("capability audience mismatch")
        run = self.engine.store.get_run(str(capability["run_id"]))
        if not run:
            raise KeyError(f"unknown agent run: {capability['run_id']}")
        if normalize_state(str(run.get("state") or "")) != AgentRunState.WAITING_FOR_APPROVAL:
            raise ValueError("agent run is not waiting for approval")
        checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), dict) else {}
        suspended = checkpoint.get("suspended_step") if isinstance(checkpoint.get("suspended_step"), dict) else {}
        suspended_step_id = str(suspended.get("step_id") or checkpoint.get("suspended_step_id") or capability["step_id"])
        if suspended_step_id != str(capability["step_id"]):
            raise ValueError("capability does not target the suspended run step")
        suspended_approval = str(suspended.get("approval_id") or checkpoint.get("suspended_approval_id") or capability["approval_id"])
        if suspended_approval != str(capability["approval_id"]):
            raise ValueError("capability does not target the suspended approval")
        return run

    def consume_and_resume(
        self,
        *,
        capability: Mapping[str, Any],
        request: Mapping[str, Any],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or _utcnow()
        from .revocation import RevocationPolicyStore
        revocations = RevocationPolicyStore(self.workspace_root)
        revocations.assert_active(capability)
        revocations.assert_active(request)
        self._validate_bindings(capability, request, now=now)
        self.consumptions.consume_pending(capability, consumed_at=now)

        receipt: dict[str, Any]
        try:
            self.engine.merge_checkpoint(
                str(capability["run_id"]),
                {
                    "approval_resume": {
                        "capability_id": str(capability["capability_id"]),
                        "capability_digest": str(capability["capability_digest"]),
                        "approval_id": str(capability["approval_id"]),
                        "step_id": str(capability["step_id"]),
                        "tool_id": str(capability["tool_id"]),
                        "tool_version": str(capability["tool_version"]),
                        "request_digest": str(capability["request_digest"]),
                        "consumed_at": _iso(now),
                        "status": "READY_FOR_EXACT_TOOL_EXECUTION",
                    }
                },
            )
            self.engine.store.transition(str(capability["run_id"]), AgentRunState.EXECUTING_TOOL)
            self.engine.emit(
                str(capability["run_id"]),
                "agent.approval.capability_consumed",
                {
                    "approval_id": str(capability["approval_id"]),
                    "capability_id": str(capability["capability_id"]),
                    "step_id": str(capability["step_id"]),
                    "tool_id": str(capability["tool_id"]),
                    "tool_version": str(capability["tool_version"]),
                    "request_digest": str(capability["request_digest"]),
                    "capability_digest": str(capability["capability_digest"]),
                },
            )
            receipt = CapabilityConsumptionResumeReceipt(
                consumption_id=f"consume_{uuid4().hex}",
                capability_id=str(capability["capability_id"]),
                capability_digest=str(capability["capability_digest"]),
                approval_id=str(capability["approval_id"]),
                request_digest=str(capability["request_digest"]),
                run_id=str(capability["run_id"]),
                step_id=str(capability["step_id"]),
                tool_id=str(capability["tool_id"]),
                tool_version=str(capability["tool_version"]),
                workspace_id=str(capability["workspace_id"]),
                execution_target=str(capability["execution_target"]),
                policy_generation=str(capability["policy_generation"]),
                call_identity_digest=str(capability["call_identity_digest"]),
                consumed_at=_iso(now),
                resume_state=AgentRunState.EXECUTING_TOOL.value,
                run_resumed=True,
                tool_execution_started=False,
            ).to_dict()
            self.consumptions.finalize(str(capability["capability_id"]), status="RESUMED", receipt=receipt)
            return receipt
        except Exception as exc:
            failure = CapabilityConsumptionResumeReceipt(
                consumption_id=f"consume_{uuid4().hex}",
                capability_id=str(capability["capability_id"]),
                capability_digest=str(capability["capability_digest"]),
                approval_id=str(capability["approval_id"]),
                request_digest=str(capability["request_digest"]),
                run_id=str(capability["run_id"]),
                step_id=str(capability["step_id"]),
                tool_id=str(capability["tool_id"]),
                tool_version=str(capability["tool_version"]),
                workspace_id=str(capability["workspace_id"]),
                execution_target=str(capability["execution_target"]),
                policy_generation=str(capability["policy_generation"]),
                call_identity_digest=str(capability["call_identity_digest"]),
                consumed_at=_iso(now),
                resume_state="RECOVERY_REQUIRED",
                run_resumed=False,
                tool_execution_started=False,
            ).to_dict()
            failure["error"] = str(exc)
            failure["receipt_digest"] = sha256_digest(semantic_payload(failure, exclude={"receipt_digest"}))
            self.consumptions.finalize(str(capability["capability_id"]), status="RECOVERY_REQUIRED", receipt=failure)
            raise

    @staticmethod
    def verify_receipt(receipt: Mapping[str, Any]) -> bool:
        if receipt.get("beast_object_type") != RECEIPT_OBJECT_TYPE or str(receipt.get("version")) != RUNTIME_VERSION:
            return False
        if receipt.get("authority") != "consumed_exact_step_resume_only":
            return False
        if receipt.get("capability_consumed") is not True or receipt.get("replay_allowed") is not False:
            return False
        for field in ("workspace_mutation_authorized", "promotion_authorized", "phase2_governance_bypass_allowed"):
            if receipt.get(field) is not False:
                return False
        required = (
            "consumption_id", "capability_id", "capability_digest", "approval_id",
            "request_digest", "run_id", "step_id", "tool_id", "tool_version",
            "workspace_id", "execution_target", "policy_generation",
            "call_identity_digest", "consumed_at", "resume_state",
        )
        if any(not str(receipt.get(field) or "").strip() for field in required):
            return False
        try:
            _parse_time(receipt.get("consumed_at"))
        except (TypeError, ValueError):
            return False
        return verify_digest(
            semantic_payload(receipt, exclude={"receipt_digest"}),
            str(receipt.get("receipt_digest") or ""),
        )
