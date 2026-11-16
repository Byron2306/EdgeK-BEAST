"""Compute Governor spine: the single Reason-phase arbiter of the PREC loop.

``ComputeGovernorSpine.admit(episode, proposal)`` combines typed inputs (L0 rules on every path, one unified
budget, the D9 route / Pathfinder nomination, lattice admission, the MCP vault allowed set, PSI pressure,
runtime circuits and Safety classification) into exactly one outcome: admit, refuse, revalidate, escalate or
defer. Every decision is written to a hash-chained receipt log; downstream consumers (L4 forensic archive,
Chronicle, D7 settlement) read those receipts.

Paper anchors (IEI v0.9): §4 places the compute governor between provider handoff and the provider/local route;
Table 3 makes false suppression a redline that must remain zero, so ambiguity escalates and pressure, budget and
circuits defer instead of refusing; §7.12.1 / Table 15 keep the router a proposal; §7.13.1-7.13.3 settle credits
only from witnessed receipts. PGEC §2.4 promotion sovereignty and eq. 3 authority envelopes bound L3 and lattice
inputs. Enforcement is default-off (``BEAST_GOVERNOR_ENFORCE``): shadow decisions are receipted, never blocking.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import inspect
import json
import os
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ENFORCE_ENV = "BEAST_GOVERNOR_ENFORCE"
ADMIT, REFUSE, REVALIDATE, ESCALATE, DEFER = "admit", "refuse", "revalidate", "escalate", "defer"
OUTCOMES = (ADMIT, REFUSE, REVALIDATE, ESCALATE, DEFER)
RUNGS = ("crystal", "local_specialist", "deterministic_tool", "cloud")  # cost ladder, cheapest first
PROPOSAL_KINDS = frozenset(RUNGS) | {"command", "eviction"}
PROTECTED_LANES = frozenset({"operator", "security"})
APPROVAL_DECISIONS = frozenset({"warn", "require_approval", "sandbox/worktree_only"})
HARD_REASONS = ("l0:", "lattice_component_not_admitted", "lattice_node_not_admitted", "loop_detected")
PRESSURE_FACTORS = {"preserve": 1.0, "admit": 1.0, "admit_reduced": 0.5, "delay": 0.5, "suppress": 0.25}
SESSION_KEYS = {"requests": "cloud_calls", "tokens": "tokens_total", "estimated_cost_usd": "cost_usd"}
ROUTE_FOR_RUNG = {"crystal": "crystal_replay", "local_specialist": "local_specialist_adapter"}
CLAIM_BOUNDARY = ("Typed, fail-closed admission arbiter with receipts; enforcement default-off; shadow mode never "
                  "suppresses; no realized-savings claim (IEI §4, Table 3).")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def _sha(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def enforcement_enabled(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return str(env.get(ENFORCE_ENV) or "").strip().lower() in {"1", "true", "yes", "on"}


def unified_limits(compute_budget: Any = None, limits: Mapping[str, float] | None = None) -> dict[str, float]:
    """One budget: the tightest of explicit run/session limits and the plan's ComputeBudget."""
    merged = {k: float(v) for k, v in (limits or {}).items() if v is not None}
    if compute_budget is not None:
        plan = {"cloud_calls": getattr(compute_budget, "cloud_calls", None),
                "tokens_total": (getattr(compute_budget, "input_tokens", 0) or 0)
                + (getattr(compute_budget, "output_tokens", 0) or 0) or None,
                "wall_ms": getattr(compute_budget, "latency_ms", None),
                "cost_usd": getattr(compute_budget, "cost_usd", None)}
        for key, value in plan.items():
            if value is not None:
                merged[key] = min(float(value), merged.get(key, float(value)))
    return merged


@dataclass(frozen=True)
class Proposal:
    kind: str
    lane: str = "agent"
    crystal_id: str = ""
    component_ids: tuple[str, ...] = ()
    provider: str = ""
    tool_id: str = ""
    command: str = ""
    mcp_tool: str = ""
    route_decision: Mapping[str, Any] | None = None
    pathfinder: Mapping[str, Any] | None = None
    safety: Mapping[str, Any] | None = None
    approved: bool = False
    quality_cascade: Mapping[str, Any] | None = None
    estimate: Mapping[str, float] = field(default_factory=dict)
    ambiguous: bool = False
    signature_material: Mapping[str, Any] | None = None
    dry_run: bool = False
    targets: tuple[str, ...] = ()
    memory: Mapping[str, Any] | None = None  # memory_contract.MemoryReadResult.admission_inputs()

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "lane": self.lane, "crystal_id": self.crystal_id,
                "component_ids": list(self.component_ids), "provider": self.provider, "tool_id": self.tool_id,
                "command": self.command, "mcp_tool": self.mcp_tool,
                "route_decision": dict(self.route_decision) if self.route_decision else None,
                "pathfinder": dict(self.pathfinder) if self.pathfinder else None,
                "safety_decision": str((self.safety or {}).get("decision") or "") if self.safety else None,
                "approved": self.approved, "quality_cascade": dict(self.quality_cascade or {}) or None,
                "estimate": dict(self.estimate), "ambiguous": self.ambiguous,
                "signature_material": dict(self.signature_material or {}), "dry_run": self.dry_run,
                "targets": list(self.targets)}

    def digest(self) -> str:
        return _sha(self.to_dict())

    def signature(self) -> str:
        """L1 signature: what is being attempted, independent of budget/approval noise."""
        return "l1:" + _sha({"kind": self.kind, "crystal_id": self.crystal_id, "provider": self.provider,
                             "tool_id": self.tool_id, "command": self.command, "mcp_tool": self.mcp_tool,
                             "material": dict(self.signature_material or {})})[7:31]


@dataclass(frozen=True)
class Episode:
    run_id: str
    task_envelope: Mapping[str, Any] | None = None
    run_budget_used: Mapping[str, float] = field(default_factory=dict)   # D5 RunBudgetTracker merge_budget
    session_used: Mapping[str, float] = field(default_factory=dict)      # Reasoner BudgetLedger.daily_totals
    limits: Mapping[str, float] = field(default_factory=dict)            # unified_limits(...)
    available_rungs: tuple[str, ...] = ()
    attempted_rungs: tuple[str, ...] = ()
    signatures: tuple[str, ...] = ()                                     # L1 history for loop detection
    psi_samples: Mapping[str, Any] | None = None

    def used(self) -> dict[str, float]:
        used: dict[str, float] = {}
        for key, value in self.run_budget_used.items():
            used[key] = used.get(key, 0.0) + float(value or 0.0)
        for key, value in self.session_used.items():
            target = SESSION_KEYS.get(key, key)
            used[target] = used.get(target, 0.0) + float(value or 0.0)
        return used


def pressure_factor(lane: str, samples: Mapping[str, Any] | None, psi: Any = None) -> float:
    """The single pressure policy: PSI can only shrink a budget (0.25-1.0), never deny on its own."""
    if lane in PROTECTED_LANES or not samples:
        return 1.0
    from app.kernel.governance.psi_governor import PsiGovernor

    decision = (psi or PsiGovernor()).decide(lane, samples)
    return PRESSURE_FACTORS.get(decision.action, 0.25)


# -- Quality Cascade attestations: only server-run cascade reports can open the cloud rung ----------------
CASCADE_SKIP_ENV = "BEAST_QUALITY_CASCADE_SKIP"
CASCADE_TTL_SECONDS = 3600.0


CASCADE_ATTESTATIONS_ENV = "BEAST_CASCADE_ATTESTATIONS"


def _default_attestation_path() -> Path:
    override = str(os.environ.get(CASCADE_ATTESTATIONS_ENV) or "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / ".beast" / "governor" / "cascade_attestations.jsonl"


def cascade_report_digest(report: Mapping[str, Any]) -> str:
    return _sha({k: v for k, v in dict(report).items() if k != "attestation"})


def attest_quality_cascade(report: Mapping[str, Any], path: str | Path | None = None) -> str:
    """Record a report produced by QualityCascade.run in this trusted process; returns its digest."""
    digest = cascade_report_digest(report)
    target = Path(path) if path is not None else _default_attestation_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    record = {"digest": digest, "status": str(report.get("status") or ""),
              "verification_accepted": report.get("verification_accepted") is True,
              "task_id": str(report.get("task_id") or ""), "at": time.time()}
    with open(target, "a", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.write(json.dumps(record, sort_keys=True) + "\n")
        fcntl.flock(handle, fcntl.LOCK_UN)
    return digest


def _attestation(digest: str, path: Path, ttl: float) -> dict[str, Any] | None:
    if not digest or not path.exists():
        return None
    found = None
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if record.get("digest") == digest:
            found = record
    if found is None or time.time() - float(found.get("at") or 0) > ttl:
        return None
    return found


def cascade_admission_input(metadata: Mapping[str, Any] | None, *, env: Mapping[str, str] | None = None,
                            path: str | Path | None = None,
                            ttl: float = CASCADE_TTL_SECONDS) -> dict[str, Any] | None:
    """Map request metadata to the governor's cascade input. Client claims never count: a report must carry an
    attestation recorded by a server-side QualityCascade.run, and a skip must come from the server environment."""
    env = os.environ if env is None else env
    skip = str(env.get(CASCADE_SKIP_ENV) or "").strip()
    if skip:
        return {"skipped": f"operator:{skip}"}
    metadata = metadata or {}
    target = Path(path) if path is not None else _default_attestation_path()
    report = metadata.get("quality_cascade")
    digest = ""
    if isinstance(report, Mapping) and report.get("beast_object_type") == "quality_cascade_report":
        digest = cascade_report_digest(report)
    elif isinstance(metadata.get("quality_cascade_digest"), str):
        digest = metadata["quality_cascade_digest"]
    record = _attestation(digest, target, ttl)
    if record is None:
        return {"unattested": True} if (report or digest) else None
    return {"passed": bool(record.get("verification_accepted")), "attested_digest": digest,
            "status": record.get("status")}


@dataclass(frozen=True)
class GovernorDecision:
    outcome: str
    reasons: tuple[str, ...]
    rung: str
    recommended_rung: str
    enforced: bool
    pressure_factor: float
    effective_limits: Mapping[str, float]
    proposal_digest: str
    receipt_id: str = ""
    receipt_hash: str = ""
    suppressed: bool = False

    def permits(self) -> bool:
        return self.outcome == ADMIT or not self.enforced

    def gate_decision(self) -> str:
        """Map onto ComputeGateDecision routes; anything but admit escalates (never a silent suppression)."""
        return "" if self.outcome == ADMIT else "escalate"

    def to_dict(self) -> dict[str, Any]:
        return {"outcome": self.outcome, "reasons": list(self.reasons), "rung": self.rung,
                "recommended_rung": self.recommended_rung, "enforced": self.enforced,
                "pressure_factor": self.pressure_factor, "effective_limits": dict(self.effective_limits),
                "proposal_digest": self.proposal_digest, "receipt_id": self.receipt_id,
                "receipt_hash": self.receipt_hash, "suppressed": self.suppressed}


class GovernorReceiptLog:
    """Hash-chained JSONL receipts (append-only, flock-guarded). ``path=None`` keeps receipts in memory."""

    def __init__(self, path: str | Path | None, *, sinks: Iterable[Callable[[dict[str, Any]], Any]] = (),
                 max_memory: int = 2000):
        self.path = Path(path) if path is not None else None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.sinks = list(sinks)
        self.sink_errors: list[str] = []
        self._memory: list[dict[str, Any]] = []
        self._max_memory = max(1, int(max_memory))
        self._base_prev = "genesis"  # in-memory mode keeps a bounded window; the chain verifies from its base
        self._lock = threading.RLock()

    def _last(self) -> dict[str, Any] | None:
        if self.path is None:
            return self._memory[-1] if self._memory else None
        if not self.path.exists():
            return None
        with open(self.path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            chunk = b""
            while size > 0:
                step = min(4096, size)
                size -= step
                handle.seek(size)
                chunk = handle.read(step) + chunk
                lines = [line for line in chunk.splitlines() if line.strip()]
                if len(lines) > 1 or (lines and size == 0):
                    return json.loads(lines[-1])
        return None

    def records(self) -> list[dict[str, Any]]:
        if self.path is None:
            return [dict(r) for r in self._memory]
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _open(self) -> Any:
        if self.path is None:
            return contextlib.nullcontext()
        return open(self.path, "a+", encoding="utf-8")

    def _append(self, body: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock, self._open() as handle:
            try:
                if handle is not None:
                    fcntl.flock(handle, fcntl.LOCK_EX)
                last = self._last()
                prev = last["receipt_hash"] if last else self._base_prev
                seq = int(last["seq"]) + 1 if last else 0
                record = {**dict(body), "seq": seq, "prev_hash": prev, "created_at": time.time()}
                record["receipt_id"] = "gov_" + _sha({"prev": prev, "seq": record["seq"], "body": dict(body)})[7:31]
                record["receipt_hash"] = _sha(record)
                if handle is not None:
                    handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
                    handle.flush()
                else:
                    self._memory.append(record)
                    if len(self._memory) > self._max_memory:
                        self._base_prev = self._memory.pop(0)["receipt_hash"]
            finally:
                if handle is not None:
                    fcntl.flock(handle, fcntl.LOCK_UN)
        for sink in self.sinks:  # observers only: a failing sink never changes the decision
            try:
                sink(dict(record))
            except Exception as exc:  # noqa: BLE001
                self.sink_errors.append(f"{type(exc).__name__}: {exc}")
        return record

    def append_decision(self, body: Mapping[str, Any]) -> dict[str, Any]:
        return self._append({"type": "decision", **dict(body)})

    def verify(self) -> dict[str, Any]:
        errors, prev = [], self._base_prev if self.path is None else "genesis"
        records = self.records()
        for index, record in enumerate(records):
            body = {k: v for k, v in record.items() if k != "receipt_hash"}
            if record.get("prev_hash") != prev:
                errors.append(f"chain_break_at:{index}")
            if _sha(body) != record.get("receipt_hash"):
                errors.append(f"hash_mismatch_at:{index}")
            prev = record.get("receipt_hash")
        return {"valid": not errors, "count": len(records), "errors": errors}

    def settle(self, crystal_id: str) -> str:
        """D7: consume one unsettled ADMIT crystal receipt for ``crystal_id``; return its id or ''."""
        with self._lock:
            if not self.verify()["valid"]:
                return ""
            records = self.records()
            settled = {r.get("settles") for r in records if r.get("type") == "settlement"}
            for record in records:
                proposal = record.get("proposal") or {}
                if (record.get("type") == "decision" and record.get("outcome") == ADMIT
                        and proposal.get("kind") == "crystal" and proposal.get("crystal_id") == crystal_id
                        and record["receipt_id"] not in settled):
                    self._append({"type": "settlement", "settles": record["receipt_id"], "crystal_id": crystal_id,
                                  "run_id": record.get("run_id", "")})
                    return str(record["receipt_id"])
        return ""

    def summary(self) -> dict[str, Any]:
        decisions = [r for r in self.records() if r.get("type") == "decision"]
        by_outcome: dict[str, int] = {}
        for record in decisions:
            by_outcome[record["outcome"]] = by_outcome.get(record["outcome"], 0) + 1
        return {"decisions": len(decisions), "by_outcome": by_outcome,
                "false_suppression": sum(1 for r in decisions if r.get("suppressed")),
                "chain": self.verify()}


def _jsonl_sink(path_for: Callable[[Mapping[str, Any]], Path]) -> Callable[[dict[str, Any]], None]:
    def sink(record: dict[str, Any]) -> None:
        path = path_for(record)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
    return sink


def forensic_sink(directory: str | Path) -> Callable[[dict[str, Any]], None]:
    """L4 forensic archive: append-only governor receipts."""
    return _jsonl_sink(lambda record: Path(directory) / "governor_receipts.jsonl")


def chronicle_sink(chronicle_dir: str | Path) -> Callable[[dict[str, Any]], None]:
    """Chronicle: one receipts file per run beside TaskEnvelopeBuilder chronicles."""
    def path_for(record: Mapping[str, Any]) -> Path:
        run = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in str(record.get("run_id") or "unbound"))
        return Path(chronicle_dir) / f"governor-{run[:120]}.jsonl"
    return _jsonl_sink(path_for)


def _route_valid(route: Mapping[str, Any] | None) -> bool:
    if not route or route.get("execution_granted") or not route.get("proposal_only", False):
        return False
    body = {k: v for k, v in route.items() if k != "digest"}
    return route.get("digest") == _sha(body)


class ComputeGovernorSpine:
    def __init__(self, *, receipts: GovernorReceiptLog | None = None, enforce: bool | None = None,
                 l0_rules: Iterable[Callable[[Episode, Proposal], str | None]] = (), lattice: Any = None,
                 mcp_allowed: Iterable[str] | None = None, psi: Any = None,
                 circuits: Callable[[str], Mapping[str, Any]] | None = None,
                 negative_evidence: Callable[[dict[str, Any]], Any] | None = None, loop_threshold: int = 3):
        self.receipts = receipts if receipts is not None else GovernorReceiptLog(None)
        self.enforce = enforcement_enabled() if enforce is None else bool(enforce)
        self.l0_rules = list(l0_rules)
        self.lattice = lattice
        self.mcp_allowed = frozenset(mcp_allowed) if mcp_allowed is not None else None
        self.psi = psi
        self.circuits = circuits
        self.negative_evidence = negative_evidence or (lambda item: None)
        self.loop_threshold = max(2, int(loop_threshold))
        self._consumed: set[str] = set()
        self._lock = threading.Lock()

    # -- typed inputs ------------------------------------------------------------------------------
    def _l0(self, episode: Episode, proposal: Proposal) -> list[str]:
        hits = []
        if proposal.kind not in PROPOSAL_KINDS:
            hits.append("unknown_proposal_kind")
        if proposal.kind == "command":
            if not proposal.safety:
                hits.append("command_without_safety_classification")
            elif str(proposal.safety.get("decision") or "") == "block":
                hits.append("safety_block")
        if proposal.mcp_tool and (self.mcp_allowed is None or proposal.mcp_tool not in self.mcp_allowed):
            hits.append("mcp_tool_outside_vault_allowed_set")
        memory = proposal.memory or {}
        if any(item.get("grants") for item in memory.get("memory_nominations") or []) or any(
                item.get("tier") != "exact" for item in memory.get("memory_exact") or []):
            hits.append("memory_nomination_cannot_grant")  # vector/schema/graph hits never grant
        for rule in self.l0_rules:
            try:
                hit = rule(episode, proposal)
            except Exception as exc:  # noqa: BLE001 - a broken hard rule fails closed
                hit = f"rule_error:{type(exc).__name__}"
            if hit:
                hits.append(str(hit))
        return hits

    def _pressure_factor(self, episode: Episode, proposal: Proposal) -> float:
        return pressure_factor(proposal.lane, episode.psi_samples, self.psi)

    def _lattice(self, proposal: Proposal) -> tuple[str, str] | None:
        if proposal.kind != "crystal":
            return None
        if self.lattice is None:
            return (REVALIDATE, "lattice_unavailable_for_composite") if proposal.component_ids else None
        try:
            node = self.lattice.node(proposal.crystal_id)
        except LookupError:
            return (REVALIDATE, "composite_not_in_lattice") if proposal.component_ids else None
        except ValueError:
            return REVALIDATE, "lattice_node_tampered"
        if node.get("status") != "admitted":
            return REFUSE, f"lattice_node_not_admitted:{proposal.crystal_id}"
        for child in node.get("component_ids") or proposal.component_ids:
            try:
                status = self.lattice.node(child).get("status")
            except (LookupError, ValueError):
                status = "missing"
            if status != "admitted":
                return REFUSE, f"lattice_component_not_admitted:{child}"
        return None

    def _route(self, proposal: Proposal) -> tuple[str, str] | None:
        expected = ROUTE_FOR_RUNG.get(proposal.kind)
        if expected is None:
            return None
        route = proposal.route_decision
        if not _route_valid(route):
            return REVALIDATE, "route_decision_missing_or_invalid"
        if route.get("band") == "structural" and proposal.kind == "crystal":
            return ESCALATE, "ambiguous_structural_band"
        if route.get("route") != expected or (proposal.kind == "crystal" and (
                route.get("crystal_id") != proposal.crystal_id or not route.get("fingerprint_compatible"))):
            return REVALIDATE, f"route_does_not_nominate:{proposal.kind}"
        return None

    # -- the arbiter -----------------------------------------------------------------------------------
    def admit(self, episode: Episode, proposal: Proposal) -> GovernorDecision:
        factor = self._pressure_factor(episode, proposal)
        limits = {k: float(v) * factor for k, v in episode.limits.items()}
        outcome, reasons, recommended = ADMIT, [], ""
        hard = self._l0(episode, proposal)
        signature = proposal.signature()
        if hard:
            outcome, reasons = REFUSE, [f"l0:{h}" for h in hard]
        elif episode.signatures.count(signature) >= self.loop_threshold:
            outcome, reasons = REFUSE, ["loop_detected"]
            self.negative_evidence({"kind": "governor_loop_detected", "run_id": episode.run_id,
                                    "signature": signature, "repeats": episode.signatures.count(signature),
                                    "proposal_kind": proposal.kind})
        else:
            outcome, reasons, recommended = self._soft(episode, proposal, limits)
        if proposal.pathfinder:
            reasons.append("pathfinder_nomination_only")
        suppressed = outcome == REFUSE and not all(r.startswith(HARD_REASONS) for r in reasons
                                                   if r != "pathfinder_nomination_only")
        body = {"run_id": episode.run_id, "outcome": outcome, "reasons": reasons, "rung": proposal.kind,
                "recommended_rung": recommended, "enforced": self.enforce, "pressure_factor": factor,
                "effective_limits": limits, "proposal": proposal.to_dict(), "proposal_digest": proposal.digest(),
                "proposal_signature": signature, "suppressed": suppressed,
                "task_envelope_digest": _sha(dict(episode.task_envelope)) if episode.task_envelope else ""}
        record = self.receipts.append_decision(body)
        return GovernorDecision(outcome=outcome, reasons=tuple(reasons), rung=proposal.kind,
                                recommended_rung=recommended, enforced=self.enforce, pressure_factor=factor,
                                effective_limits=limits, proposal_digest=body["proposal_digest"],
                                receipt_id=record["receipt_id"], receipt_hash=record["receipt_hash"],
                                suppressed=suppressed)

    def _soft(self, episode: Episode, proposal: Proposal, limits: Mapping[str, float]) -> tuple[str, list[str], str]:
        if proposal.ambiguous:
            return ESCALATE, ["ambiguity_escalates_never_suppresses"], ""
        for check in (self._lattice, self._route):
            hit = check(proposal)
            if hit:
                return hit[0], [hit[1]], ""
        if proposal.kind == "command":
            decision = str(proposal.safety.get("decision") or "")
            if decision != "allow" and not proposal.approved:
                label = decision if decision in APPROVAL_DECISIONS else f"unknown:{decision}"
                return ESCALATE, [f"safety_requires_approval:{label}"], ""
        if proposal.kind in RUNGS:
            cheaper = RUNGS[:RUNGS.index(proposal.kind)]
            untried = [r for r in cheaper if r in episode.available_rungs and r not in episode.attempted_rungs]
            if untried:
                return REVALIDATE, [f"cheaper_rung_available:{untried[0]}"], untried[0]
        notes: list[str] = []
        if proposal.kind == "cloud":
            cascade = dict(proposal.quality_cascade or {})
            skipped = str(cascade.get("skipped") or "").strip()
            if cascade.get("passed") is True:
                notes.append("quality_cascade_passed")
            elif skipped:
                notes.append(f"quality_cascade_skipped:{skipped}")
            elif cascade.get("passed") is False:
                return ESCALATE, ["quality_cascade_failed"], ""
            elif cascade.get("unattested"):
                return REVALIDATE, ["quality_cascade_report_unattested"], ""
            else:
                return REVALIDATE, ["quality_cascade_required_before_cloud"], ""
        if self.circuits is not None and proposal.provider:
            try:
                state = str((self.circuits(proposal.provider) or {}).get("state") or "closed")
            except Exception:  # noqa: BLE001
                state = "unknown"
            if state in {"open", "unknown"}:
                return DEFER, [f"circuit_{state}:{proposal.provider}"], ""
        used = episode.used()
        for key, limit in limits.items():
            if used.get(key, 0.0) + float(proposal.estimate.get(key, 0.0) or 0.0) > limit:
                return DEFER, [f"budget_exhausted:{key}"], ""
        return ADMIT, notes, ""

    # -- execution only behind admit -----------------------------------------------------------------
    def run_admitted(self, decision: GovernorDecision, proposal: Proposal, fn: Callable[[], Any]) -> Any:
        if decision.proposal_digest != proposal.digest():
            raise PermissionError("governor decision does not cover this proposal")
        if not decision.permits():
            raise PermissionError(f"governor {decision.outcome}: {', '.join(decision.reasons)}")
        with self._lock:
            if decision.receipt_id in self._consumed:
                raise PermissionError("governor admit token already used")
            self._consumed.add(decision.receipt_id)
        return fn()

    def execute(self, episode: Episode, proposal: Proposal, fn: Callable[[], Any]) -> Any:
        return self.run_admitted(self.admit(episode, proposal), proposal, fn)


# -- PREC integrations -------------------------------------------------------------------------------

def seal_task_envelope(task_envelope: Mapping[str, Any], episode_envelope: Any) -> dict[str, Any]:
    """Perceive → Crystallize: bind the Task Envelope work shape to a verified D5 EpisodeEnvelope (both kept)."""
    episode_envelope.validate()
    if not (episode_envelope.verification or {}).get("passed"):
        raise ValueError("task envelope seals only into a verified episode envelope")
    task = dict(task_envelope)
    return {"schema": "beast.task_episode_binding.v1", "task_envelope": task,
            "episode_envelope": episode_envelope.to_dict(),
            "binding_digest": _sha({"task": _sha(task), "episode": episode_envelope.envelope_digest})}


def promote_skill_via_d6(skill_tree: Any, candidate_id: str, *, registry: Any, crystal_id: str,
                         approved_by: str) -> dict[str, Any]:
    """L3 promotion goes through D6: the backing coding crystal must be promoted and a human approver named."""
    if not str(approved_by or "").strip():
        raise PermissionError("approved_by_required")
    try:
        record = registry.get(crystal_id)
    except LookupError as exc:
        raise PermissionError("d6_crystal_unknown") from exc
    if record.get("status") != "promoted" or not (record.get("receipt") or {}).get("promoted"):
        raise PermissionError("d6_crystal_promotion_required")
    proof = {"crystal_id": crystal_id, "status": "promoted", "approved_by": approved_by}
    kwargs: dict[str, Any] = {"approved_by": approved_by}
    if "d6_promotion" in inspect.signature(skill_tree.promote_candidate).parameters:
        kwargs["d6_promotion"] = proof
    result = dict(skill_tree.promote_candidate(candidate_id, **kwargs))
    result["d6_crystal_id"] = crystal_id
    return result


def dry_run_eviction(governor: ComputeGovernorSpine, kind: str, targets: Iterable[str],
                     detail: Mapping[str, Any] | None = None) -> GovernorDecision:
    """Evictions (PSI, capsule, PRISM) are proposals: receipted through admit and never executed here."""
    return governor.admit(Episode(run_id=f"eviction:{kind}"),
                          Proposal(kind="eviction", lane="background", dry_run=True,
                                   targets=tuple(str(t) for t in targets),
                                   signature_material={"evictor": kind, **dict(detail or {})}))


class GovernedEvictor:
    """Wrap an evictor (e.g. PRISM ``evict_cold``) so evictions become dry-run governor proposals."""

    def __init__(self, target: Any, *, governor: ComputeGovernorSpine, kind: str):
        self._target, self._governor, self._kind = target, governor, kind
        self.last_decision: GovernorDecision | None = None

    def evict_cold(self, *, preserve_ids: set[str], maximum: int) -> int:
        self.last_decision = dry_run_eviction(self._governor, self._kind, (),
                                              {"maximum": int(maximum), "preserve": sorted(preserve_ids)})
        return 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._target, name)


__all__ = ["ADMIT", "CLAIM_BOUNDARY", "ComputeGovernorSpine", "DEFER", "ENFORCE_ENV", "ESCALATE", "Episode",
           "GovernedEvictor", "GovernorDecision", "GovernorReceiptLog", "OUTCOMES", "Proposal", "REFUSE",
           "REVALIDATE", "RUNGS", "chronicle_sink", "dry_run_eviction", "enforcement_enabled", "forensic_sink",
           "promote_skill_via_d6", "seal_task_envelope", "unified_limits", "pressure_factor",
           "attest_quality_cascade", "cascade_admission_input", "cascade_report_digest", "CASCADE_SKIP_ENV"]
