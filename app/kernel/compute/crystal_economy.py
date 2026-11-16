"""D7 shadow economy for coding crystals: measured reduction receipts, ledger-only credits, ratings, clawback.

Source of truth (cited by section):
* PGEC v1.0 eq. (6): V_K = C_avoided - (C_lookup + C_verify + C_risk + C_maintenance); credit = max(0, V_K).
* Inference Economy v0.9 Table 3 / section 9: counterfactual or estimated tokens are never realised savings.
* v0.9 section 7.12.4 runtime contract + 7.13.5: no saving counts unless verification quality is preserved.
* v0.9 section 7.13.1: false hits -> demotion, rollback and credit reversal (clawback here).
* v0.9 section 7.13.2: append-only, chain-witnessed ledger; tampering is detected, never rewritten.
* v0.9 section 7.13.3: internal BEAST credits only, not cryptocurrency or redeemable finance.
* PGEC section 2.4 (Proof Preservation / Promotion Sovereignty): remote content is a hypothesis; only local
  held-out reproduction plus operator promotion makes a crystal usable, so only local reuse can earn credit.

Credits are attributed to the publishing identity (signing key id) and its Commons space; a ledger only ever
credits reuse it witnessed locally.  Ratings are a bounded multiplier (0.5x-1.5x) on one verified reuse's credit;
they never gate promotion, trust or reuse.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from app.kernel.networking.commons_spaces import build_reduction_receipt, validate_reduction_receipt

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "docs" / "schemas" / "compute_reduction_receipt.schema.json"
CREDIT_UNIT = "non_financial_commons_credit"
# Cost weights in credit units (ruling, see phase-7 plan): one model turn is the unit of avoided inference.
COST_WEIGHTS = {"model_turn": 1.0, "tool_call": 0.1, "observed_ktokens": 0.5, "wall_second": 0.01}
C_MAINTENANCE = 0.05
RATING_MIN, RATING_MAX = 0.5, 1.5
LEDGER_POLICY = {"unit": CREDIT_UNIT, "transferable": False, "redeemable": False, "financial_value": None,
                 "settlement": "none", "mode": "shadow_ledger_only"}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")


def _sha(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def budget_view(budget: Mapping[str, Any]) -> dict[str, Any]:
    """Measured Episode Envelope budget; tokens are flagged estimated when any turn lacked provider usage."""
    return {
        "model_turns": int(budget.get("model_turns") or 0),
        "tool_calls": int(budget.get("tool_calls") or 0),
        "tokens_total": int(budget.get("tokens_total") or 0),
        "tokens_estimated": int(budget.get("tokens_estimated_turns") or 0) > 0,
        "wall_ms": float(budget.get("wall_ms") or 0.0),
    }


def _cost(view: Mapping[str, Any], *, include_tokens: bool) -> float:
    cost = (COST_WEIGHTS["model_turn"] * view["model_turns"] + COST_WEIGHTS["tool_call"] * view["tool_calls"]
            + COST_WEIGHTS["wall_second"] * view["wall_ms"] / 1000.0)
    if include_tokens:
        cost += COST_WEIGHTS["observed_ktokens"] * view["tokens_total"] / 1000.0
    return cost


def recurrence_value(baseline: Mapping[str, Any], reuse: Mapping[str, Any], *, false_reuse_rate: float = 0.0) -> dict[str, Any]:
    """PGEC eq. (6) from measured budgets.  Estimated tokens are excluded from both sides and flagged."""
    tokens_observed = not baseline["tokens_estimated"] and not reuse["tokens_estimated"]
    c_avoided = _cost(baseline, include_tokens=tokens_observed)
    c_lookup_verify = _cost(reuse, include_tokens=tokens_observed)
    c_risk = max(0.0, min(1.0, float(false_reuse_rate))) * c_avoided
    v_k = c_avoided - (c_lookup_verify + c_risk + C_MAINTENANCE)
    return {"c_avoided": round(c_avoided, 6), "c_lookup_plus_verify": round(c_lookup_verify, 6),
            "c_risk": round(c_risk, 6), "c_maintenance": C_MAINTENANCE, "v_k": round(v_k, 6),
            "credit": round(max(0.0, v_k), 6), "tokens_counted": tokens_observed, "weights": dict(COST_WEIGHTS),
            "formula": "PGEC v1.0 eq.(6): V_K = C_avoided - (C_lookup + C_verify + C_risk + C_maintenance)"}


def reuse_reduction_receipt(*, baseline_budget: Mapping[str, Any], baseline_digest: str, baseline_source: str,
                            baseline_verified: bool, reuse_envelope: Any, crystal_id: str, space_id: str,
                            space_manifest_hash: str, publisher_id: str, consumer: Mapping[str, str], kind: str,
                            local_reproduction_verified: bool, promotion_verified: bool,
                            false_reuse_rate: float = 0.0, route_id: str = "coding_crystal",
                            extra_provenance: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Schema-valid compute_reduction_receipt built only from measured Episode Envelope budgets."""
    base, reuse = budget_view(baseline_budget), budget_view(reuse_envelope.budget)
    value = recurrence_value(base, reuse, false_reuse_rate=false_reuse_rate)
    tokens_delta = base["tokens_total"] - reuse["tokens_total"]
    observed_tokens = max(0, tokens_delta) if value["tokens_counted"] else 0
    reuse_passed = bool((reuse_envelope.verification or {}).get("passed"))
    return build_reduction_receipt(
        space_manifest={"space_id": space_id, "manifest_hash": space_manifest_hash},
        baseline_route={"route_id": "model_planner", "budget": base, "envelope_digest": baseline_digest,
                        "baseline_source": baseline_source, "verified": bool(baseline_verified)},
        optimized_route={"route_id": route_id, "budget": reuse, "run_id": reuse_envelope.run_id,
                         "envelope_digest": reuse_envelope.envelope_digest, "verified": reuse_passed,
                         "local_reproduction_verified": bool(local_reproduction_verified),
                         "promotion_verified": bool(promotion_verified)},
        displacement={"provider_calls_avoided": max(0, base["model_turns"] - reuse["model_turns"]),
                      "provider_tokens_avoided": observed_tokens, "tokens_avoided": observed_tokens,
                      "tokens_avoided_estimated": max(0, tokens_delta) if not value["tokens_counted"] else 0,
                      "tokens_estimated": not value["tokens_counted"], "tool_calls_avoided": base["tool_calls"] - reuse["tool_calls"],
                      "counterfactual": False,
                      "evidence_class": "measured_episode_envelope_budget" if baseline_source == "local_envelope"
                      else "measured_reuse_vs_publisher_signed_baseline"},
        verifier={"name": "episode_envelope_verification", "passed": reuse_passed and bool(baseline_verified),
                  "reuse_passed": reuse_passed, "baseline_passed": bool(baseline_verified)},
        resource_deltas={"model_turns": reuse["model_turns"] - base["model_turns"],
                         "tool_calls": reuse["tool_calls"] - base["tool_calls"],
                         "wall_ms": round(reuse["wall_ms"] - base["wall_ms"], 3), "gpu_avoided": False,
                         "recurrence_value": value},
        provenance={"source": "beast.coding_crystal." + kind, "kind": kind, "crystal_id": crystal_id,
                    "publisher_id": publisher_id, "publisher_space_id": space_id, "consumer": dict(consumer),
                    "measurement": "episode_envelope_budget", "local_reproduction_verified": bool(local_reproduction_verified),
                    "promotion_verified": bool(promotion_verified), **dict(extra_provenance or {}), **LEDGER_POLICY},
        rollback_available=True, approval_required=True,
    )


def _scaled(view: Mapping[str, Any], share: float) -> dict[str, Any]:
    return {**view, "model_turns": view["model_turns"] * share, "tool_calls": view["tool_calls"] * share,
            "tokens_total": view["tokens_total"] * share, "wall_ms": view["wall_ms"] * share}


def composite_reuse_receipt(*, composite_baseline: Mapping[str, Any], composite_baseline_digest: str, reuse_envelope: Any,
                            composite_id: str, space_id: str, space_manifest_hash: str, lattice_publisher_id: str,
                            consumer: Mapping[str, str], components: Iterable[Mapping[str, Any]],
                            local_reproduction_verified: bool, promotion_verified: bool,
                            false_reuse_rate: float = 0.0,
                            child_false_reuse_rates: Mapping[str, float] | None = None) -> dict[str, Any]:
    """Composite reuse receipt: V_L from measured budgets, and per-child V_Ci (PGEC eq. 6) sealed into provenance.

    V_Ci = child's measured baseline cost minus a step-proportional share of the composite's measured reuse cost; the
    attribution rule is recorded on every component.  Ledger caps guarantee credits never exceed max(0, V_L).
    """
    reuse = budget_view(reuse_envelope.budget)
    items = [dict(c) for c in components]
    total_steps = sum(max(1, int(c.get("steps") or 1)) for c in items) or 1
    rates = dict(child_false_reuse_rates or {})
    sealed_components = []
    for item in items:
        share = max(1, int(item.get("steps") or 1)) / total_steps
        value = recurrence_value(budget_view(item.get("baseline_budget") or {}), _scaled(reuse, share),
                                 false_reuse_rate=float(rates.get(str(item.get("crystal_id")), 0.0)))
        sealed_components.append({"crystal_id": str(item["crystal_id"]), "publisher_id": str(item.get("publisher_id") or ""),
                                  "space_id": str(item.get("space_id") or ""), "share": round(share, 6),
                                  "recurrence_value": value,
                                  "attribution": "child_measured_baseline_minus_step_proportional_reuse_cost"})
    return reuse_reduction_receipt(
        baseline_budget=composite_baseline, baseline_digest=composite_baseline_digest,
        baseline_source="composite_measured_baseline", baseline_verified=True, reuse_envelope=reuse_envelope,
        crystal_id=composite_id, space_id=space_id, space_manifest_hash=space_manifest_hash,
        publisher_id=lattice_publisher_id, consumer=consumer, kind="composite_reuse",
        local_reproduction_verified=local_reproduction_verified, promotion_verified=promotion_verified,
        false_reuse_rate=false_reuse_rate, route_id="coding_crystal_composite",
        extra_provenance={"components": sealed_components, "lattice_publisher_id": lattice_publisher_id})


def validate_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """JSON-schema (docs/schemas/compute_reduction_receipt.schema.json) + seal/fingerprint validation."""
    errors: list[str] = []
    try:
        import jsonschema

        jsonschema.validate(dict(receipt), json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    except Exception as exc:  # schema failure or schema unavailable both fail closed
        errors.append(f"schema: {type(exc).__name__}: {str(exc)[:160]}")
    seal = validate_reduction_receipt(dict(receipt))
    if not seal.get("valid"):
        errors.append("seal_or_fingerprint_invalid")
    return {"valid": not errors, "errors": errors}


class CrystalShadowLedger:
    """Append-only, hash-chained, ledger-only credits (no money, no settlement)."""

    def __init__(self, path: str | Path, *, local_node_id: str, local_publisher_id: str = "",
                 controller_of: Callable[[str], str] | None = None,
                 governor_settlement: Callable[[str], str] | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.local_node_id = str(local_node_id)
        self.local_publisher_id = str(local_publisher_id)
        self.controller_of = controller_of or (lambda identity: identity)
        # Compute Governor spine: when set, credit settles only against a governor ADMIT receipt (one per receipt).
        self.governor_settlement = governor_settlement
        self._lock = threading.RLock()
        with self._connect() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS entries(seq INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL,
              crystal_id TEXT NOT NULL, publisher_id TEXT NOT NULL, space_id TEXT NOT NULL, consumer_node TEXT,
              consumer_user TEXT, receipt_id TEXT, reuse_fingerprint TEXT, units REAL NOT NULL, reason TEXT,
              detail TEXT NOT NULL, prev_hash TEXT NOT NULL, entry_hash TEXT NOT NULL UNIQUE, created_at REAL NOT NULL);
            CREATE UNIQUE INDEX IF NOT EXISTS entries_reuse_once ON entries(reuse_fingerprint) WHERE reuse_fingerprint IS NOT NULL;
            CREATE UNIQUE INDEX IF NOT EXISTS entries_rating_once ON entries(receipt_id) WHERE kind='rating';
            CREATE TABLE IF NOT EXISTS receipts(receipt_id TEXT PRIMARY KEY, crystal_id TEXT NOT NULL, kind TEXT NOT NULL,
              payload TEXT NOT NULL, created_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS clawed(crystal_id TEXT PRIMARY KEY, reason TEXT, evidence_digest TEXT, at REAL);
            CREATE TABLE IF NOT EXISTS space_bindings(crystal_id TEXT PRIMARY KEY, space_id TEXT NOT NULL,
              space_manifest_hash TEXT NOT NULL, publisher_id TEXT NOT NULL, bound_at REAL NOT NULL);
            """)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        return connection

    # -- chain ---------------------------------------------------------------------------------
    def _append(self, c: sqlite3.Connection, **row: Any) -> dict[str, Any]:
        last = c.execute("SELECT entry_hash FROM entries ORDER BY seq DESC LIMIT 1").fetchone()
        body = {k: row.get(k) for k in ("kind", "crystal_id", "publisher_id", "space_id", "consumer_node", "consumer_user",
                                       "receipt_id", "reuse_fingerprint", "units", "reason", "detail")}
        body["units"] = round(float(body["units"] or 0.0), 6)
        body["detail"] = json.dumps(body.get("detail") or {}, sort_keys=True, default=str)
        body["prev_hash"] = last["entry_hash"] if last else "genesis"
        body["entry_hash"] = _sha({k: body[k] for k in sorted(body) if k != "entry_hash"})
        body["created_at"] = time.time()
        c.execute("INSERT INTO entries(kind,crystal_id,publisher_id,space_id,consumer_node,consumer_user,receipt_id,"
                  "reuse_fingerprint,units,reason,detail,prev_hash,entry_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  tuple(body[k] for k in ("kind", "crystal_id", "publisher_id", "space_id", "consumer_node", "consumer_user",
                                          "receipt_id", "reuse_fingerprint", "units", "reason", "detail", "prev_hash",
                                          "entry_hash", "created_at")))
        return {**body, "detail": json.loads(body["detail"])}

    def entries(self, *, crystal_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as c:
            rows = c.execute("SELECT * FROM entries ORDER BY seq").fetchall()
        out = [dict(r) | {"detail": json.loads(r["detail"])} for r in rows]
        return [e for e in out if crystal_id is None or e["crystal_id"] == crystal_id]

    def verify_chain(self) -> dict[str, Any]:
        prev = "genesis"
        for entry in self.entries():
            body = {k: entry[k] for k in ("kind", "crystal_id", "publisher_id", "space_id", "consumer_node", "consumer_user",
                                         "receipt_id", "reuse_fingerprint", "units", "reason")}
            body["units"] = round(float(body["units"]), 6)
            body["detail"] = json.dumps(entry["detail"], sort_keys=True, default=str)
            body["prev_hash"] = prev
            if entry["prev_hash"] != prev or _sha({k: body[k] for k in sorted(body)}) != entry["entry_hash"]:
                return {"valid": False, "broken_at": entry["seq"]}
            prev = entry["entry_hash"]
        return {"valid": True, "head": prev}

    # -- space binding -------------------------------------------------------------------------
    def bind_space(self, crystal_id: str, *, space_id: str, space_manifest_hash: str, publisher_id: str) -> None:
        with self._lock, self._connect() as c:
            c.execute("INSERT OR REPLACE INTO space_bindings VALUES(?,?,?,?,?)",
                      (crystal_id, space_id, space_manifest_hash, publisher_id, time.time()))

    def space_binding(self, crystal_id: str) -> dict[str, Any] | None:
        with self._connect() as c:
            row = c.execute("SELECT * FROM space_bindings WHERE crystal_id=?", (crystal_id,)).fetchone()
        return dict(row) if row else None

    def false_reuse_rate(self, crystal_id: str) -> float:
        with self._connect() as c:
            row = c.execute("SELECT SUM(kind='reuse') AS ok, SUM(kind='false_reuse') AS bad FROM entries WHERE crystal_id=?",
                            (crystal_id,)).fetchone()
        ok, bad = int(row["ok"] or 0), int(row["bad"] or 0)
        return bad / (ok + bad) if ok + bad else 0.0

    def is_clawed(self, crystal_id: str) -> bool:
        with self._connect() as c:
            return c.execute("SELECT 1 FROM clawed WHERE crystal_id=?", (crystal_id,)).fetchone() is not None

    # -- accounting ----------------------------------------------------------------------------
    def _self_dealing(self, publisher_id: str, consumer_node: str, consumer_user: str) -> bool:
        publisher = self.controller_of(publisher_id)
        return publisher in {self.controller_of(consumer_node), self.controller_of(consumer_user),
                             self.controller_of(self.local_publisher_id) if self.local_publisher_id else None}

    def account_reuse(self, receipt: Mapping[str, Any], *, crystal_status: str) -> dict[str, Any]:
        """Credit max(0, V_K) for one locally witnessed, verified reuse; every refusal is recorded with 0 units."""
        prov = dict(receipt.get("provenance") or {})
        consumer = dict(prov.get("consumer") or {})
        crystal_id, publisher_id = str(prov.get("crystal_id") or ""), str(prov.get("publisher_id") or "")
        optimized = dict(receipt.get("optimized_route") or {})
        fingerprint = _sha({"crystal_id": crystal_id, "reuse_envelope": optimized.get("envelope_digest"),
                            "consumer": consumer})
        value = dict((receipt.get("resource_deltas") or {}).get("recurrence_value") or {})
        reason = ""
        validation = validate_receipt(receipt)
        if not validation["valid"]:
            reason = "receipt_invalid"
        elif prov.get("kind") != "reuse":
            reason = "not_a_reuse_receipt"
        elif str(consumer.get("node_id") or "") != self.local_node_id:
            reason = "remote_claim_not_locally_witnessed"
        elif not (receipt.get("verifier") or {}).get("passed"):
            reason = "verification_quality_not_preserved"
        elif not (prov.get("local_reproduction_verified") and prov.get("promotion_verified")) or crystal_status != "promoted":
            reason = "not_locally_reproduced_and_promoted"
        elif self.is_clawed(crystal_id):
            reason = "crystal_clawed_back"
        elif self._self_dealing(publisher_id, str(consumer.get("node_id") or ""), str(consumer.get("user_id") or "")):
            reason = "self_dealing"
        units = float(value.get("credit") or 0.0) if not reason else 0.0
        if not reason and units <= 0:
            reason = "non_positive_recurrence_value"
        with self._lock, self._connect() as c:
            if c.execute("SELECT 1 FROM entries WHERE reuse_fingerprint=?", (fingerprint,)).fetchone():
                return {"credited": False, "units": 0.0, "reason": "duplicate_reuse", "receipt_id": receipt.get("receipt_id")}
            governor_receipt = self._governor_receipt(crystal_id) if not reason else ""
            if not reason and self.governor_settlement is not None and not governor_receipt:
                reason, units = "governor_receipt_missing", 0.0
            c.execute("INSERT OR IGNORE INTO receipts VALUES(?,?,?,?,?)", (receipt.get("receipt_id"), crystal_id,
                      "reuse", json.dumps(dict(receipt), sort_keys=True, default=str), time.time()))
            entry = self._append(c, kind="reuse" if not reason else "reuse_refused", crystal_id=crystal_id,
                                 publisher_id=publisher_id, space_id=str(receipt.get("space_id") or ""),
                                 consumer_node=consumer.get("node_id"), consumer_user=consumer.get("user_id"),
                                 receipt_id=receipt.get("receipt_id"), reuse_fingerprint=fingerprint, units=units,
                                 reason=reason or "credited", detail={"recurrence_value": value,
                                                                      "validation_errors": validation["errors"],
                                                                      "governor_receipt": governor_receipt})
        return {"credited": not reason, "units": entry["units"], "reason": reason or "credited",
                "receipt_id": receipt.get("receipt_id"), "entry_hash": entry["entry_hash"]}

    def _governor_receipt(self, crystal_id: str) -> str:
        if self.governor_settlement is None:
            return ""
        try:
            return str(self.governor_settlement(crystal_id) or "")
        except Exception:  # noqa: BLE001 - settlement source failure fails closed
            return ""

    def record_reproduction(self, receipt: Mapping[str, Any]) -> dict[str, Any]:
        """Held-out reproduction receipts are evidence for promotion, never credit."""
        prov = dict(receipt.get("provenance") or {})
        with self._lock, self._connect() as c:
            c.execute("INSERT OR IGNORE INTO receipts VALUES(?,?,?,?,?)", (receipt.get("receipt_id"), prov.get("crystal_id"),
                      "reproduction", json.dumps(dict(receipt), sort_keys=True, default=str), time.time()))
            entry = self._append(c, kind="reproduction", crystal_id=str(prov.get("crystal_id") or ""),
                                 publisher_id=str(prov.get("publisher_id") or ""), space_id=str(receipt.get("space_id") or ""),
                                 consumer_node=(prov.get("consumer") or {}).get("node_id"),
                                 consumer_user=(prov.get("consumer") or {}).get("user_id"), receipt_id=receipt.get("receipt_id"),
                                 reuse_fingerprint=None, units=0.0, reason="reproduction_evidence_only",
                                 detail={"verified": bool((receipt.get("verifier") or {}).get("passed"))})
        return {"credited": False, "units": 0.0, "reason": "reproduction_evidence_only", "entry_hash": entry["entry_hash"]}

    def rate(self, receipt_id: str, *, rater_node: str, rater_user: str, stars: int) -> dict[str, Any]:
        """A bounded multiplier (0.5x..1.5x) on one credited reuse; only that reuse's own consumer may rate, once."""
        if not 1 <= int(stars) <= 5:
            raise ValueError("rating must be 1..5 stars")
        with self._lock, self._connect() as c:
            reuse = c.execute("SELECT * FROM entries WHERE receipt_id=? AND kind='reuse'", (receipt_id,)).fetchone()
            if reuse is None:
                raise PermissionError("ratings must reference a credited, verified reuse receipt")
            if (rater_node, rater_user) != (reuse["consumer_node"], reuse["consumer_user"]):
                raise PermissionError("only the verified reuser of this receipt may rate it")
            if self._self_dealing(reuse["publisher_id"], rater_node, rater_user):
                raise PermissionError("a publisher cannot rate its own crystal")
            if self.is_clawed(reuse["crystal_id"]):
                raise PermissionError("crystal was clawed back")
            if c.execute("SELECT 1 FROM entries WHERE receipt_id=? AND kind='rating'", (receipt_id,)).fetchone():
                raise PermissionError("this reuse has already been rated")
            multiplier = RATING_MIN + (int(stars) - 1) * (RATING_MAX - RATING_MIN) / 4.0
            delta = float(reuse["units"]) * (multiplier - 1.0)
            entry = self._append(c, kind="rating", crystal_id=reuse["crystal_id"], publisher_id=reuse["publisher_id"],
                                 space_id=reuse["space_id"], consumer_node=rater_node, consumer_user=rater_user,
                                 receipt_id=receipt_id, reuse_fingerprint=None, units=delta, reason=f"stars:{int(stars)}",
                                 detail={"multiplier": multiplier, "base_units": float(reuse["units"])})
        return {"multiplier": multiplier, "units": entry["units"], "entry_hash": entry["entry_hash"]}

    # -- lattice spine: composite reuse -----------------------------------------------------------
    def account_composite_reuse(self, receipt: Mapping[str, Any], *, lattice_status: str,
                                child_status: Mapping[str, str]) -> dict[str, Any]:
        """Children keep max(0, V_Ci); the lattice publisher earns S = max(0, V_L - Σ max(0, V_Ci)); Σ credits <= V_L."""
        prov = dict(receipt.get("provenance") or {})
        consumer = dict(prov.get("consumer") or {})
        node, user = str(consumer.get("node_id") or ""), str(consumer.get("user_id") or "")
        composite_id, lattice_publisher = str(prov.get("crystal_id") or ""), str(prov.get("publisher_id") or "")
        receipt_id = str(receipt.get("receipt_id") or "")
        optimized = dict(receipt.get("optimized_route") or {})
        fingerprint = _sha({"crystal_id": composite_id, "reuse_envelope": optimized.get("envelope_digest"),
                            "consumer": consumer, "kind": "composite_reuse"})
        value = dict((receipt.get("resource_deltas") or {}).get("recurrence_value") or {})
        v_l = max(0.0, float(value.get("v_k") or 0.0))
        components = [dict(c) for c in prov.get("components") or []]
        reason = ""
        validation = validate_receipt(receipt)
        if not validation["valid"]:
            reason = "receipt_invalid"
        elif prov.get("kind") != "composite_reuse":
            reason = "not_a_composite_reuse_receipt"
        elif node != self.local_node_id:
            reason = "remote_claim_not_locally_witnessed"
        elif not (receipt.get("verifier") or {}).get("passed"):
            reason = "verification_quality_not_preserved"
        elif not (prov.get("local_reproduction_verified") and prov.get("promotion_verified")) or lattice_status != "admitted":
            reason = "composite_not_admitted_to_lattice"
        elif self.is_clawed(composite_id):
            reason = "crystal_clawed_back"
        elif len({c.get("crystal_id") for c in components}) < 2:
            reason = "fewer_than_two_distinct_children"
        elif v_l <= 0:
            reason = "non_positive_recurrence_value"
        with self._lock, self._connect() as c:
            if c.execute("SELECT 1 FROM entries WHERE reuse_fingerprint=?", (fingerprint,)).fetchone():
                return {"credited": False, "reason": "duplicate_reuse", "premium": 0.0, "total": 0.0,
                        "receipt_id": receipt_id}
            if not reason and self.governor_settlement is not None and not self._governor_receipt(composite_id):
                reason = "governor_receipt_missing"
            c.execute("INSERT OR IGNORE INTO receipts VALUES(?,?,?,?,?)", (receipt_id, composite_id, "composite_reuse",
                      json.dumps(dict(receipt), sort_keys=True, default=str), time.time()))
            if reason:
                self._append(c, kind="composite_reuse_refused", crystal_id=composite_id, publisher_id=lattice_publisher,
                             space_id=str(receipt.get("space_id") or ""), consumer_node=node, consumer_user=user,
                             receipt_id=receipt_id, reuse_fingerprint=fingerprint, units=0.0, reason=reason,
                             detail={"v_l": v_l, "validation_errors": validation["errors"]})
                return {"credited": False, "reason": reason, "premium": 0.0, "total": 0.0, "receipt_id": receipt_id}
            gross = [max(0.0, float((comp.get("recurrence_value") or {}).get("v_k") or 0.0)) for comp in components]
            credits, refusals = [], []
            for comp, amount in zip(components, gross, strict=True):
                child, publisher = str(comp.get("crystal_id")), str(comp.get("publisher_id") or "")
                why = ""
                if child_status.get(child) not in {"promoted", "admitted"}:
                    why = "child_not_verified"
                elif self.is_clawed(child):
                    why = "crystal_clawed_back"
                elif self._self_dealing(publisher, node, user):
                    why = "self_dealing"
                credits.append(0.0 if why else amount)
                refusals.append(why)
            paid = sum(credits)
            scaled = paid > v_l
            if scaled:
                credits = [amount * v_l / paid for amount in credits]
            premium, premium_reason = 0.0, "scaled_children_exhaust_v_l" if scaled else ""
            if not scaled:
                surplus = max(0.0, v_l - sum(gross))
                lattice_controller = self.controller_of(lattice_publisher)
                if all(self.controller_of(str(comp.get("publisher_id") or "")) == lattice_controller for comp in components):
                    premium_reason = "lattice_publisher_controls_every_child"
                elif self._self_dealing(lattice_publisher, node, user):
                    premium_reason = "consumer_shares_lattice_publisher_controller"
                elif surplus <= 0:
                    premium_reason = "no_surplus_over_children"
                else:
                    premium = min(surplus, max(0.0, v_l - sum(credits)))
                    premium_reason = "surplus_premium"
            self._append(c, kind="composite_reuse", crystal_id=composite_id, publisher_id=lattice_publisher,
                         space_id=str(receipt.get("space_id") or ""), consumer_node=node, consumer_user=user,
                         receipt_id=receipt_id, reuse_fingerprint=fingerprint, units=0.0, reason="accounted",
                         detail={"v_l": v_l, "gross_children": gross, "scaled": scaled, "premium": premium,
                                 "premium_reason": premium_reason, "recurrence_value": value})
            for comp, amount, why in zip(components, credits, refusals, strict=True):
                child = str(comp.get("crystal_id"))
                self._append(c, kind="composite_component" if not why else "composite_component_refused",
                             crystal_id=child, publisher_id=str(comp.get("publisher_id") or ""),
                             space_id=str(comp.get("space_id") or ""), consumer_node=node, consumer_user=user,
                             receipt_id=f"{receipt_id}#{child}", reuse_fingerprint=_sha([fingerprint, child]),
                             units=amount, reason=why or "credited",
                             detail={"composite_id": composite_id, "recurrence_value": comp.get("recurrence_value"),
                                     "attribution": comp.get("attribution"), "scaled": scaled})
            if premium > 0:
                self._append(c, kind="lattice_premium", crystal_id=composite_id, publisher_id=lattice_publisher,
                             space_id=str(receipt.get("space_id") or ""), consumer_node=node, consumer_user=user,
                             receipt_id=f"{receipt_id}#premium", reuse_fingerprint=_sha([fingerprint, "premium"]),
                             units=premium, reason="surplus_premium", detail={"v_l": v_l, "children": sum(gross)})
        total = sum(credits) + premium
        return {"credited": True, "reason": "credited", "receipt_id": receipt_id, "v_l": v_l, "scaled": scaled,
                "children": dict(zip([str(comp.get("crystal_id")) for comp in components], credits, strict=True)),
                "premium": round(premium, 6), "premium_reason": premium_reason, "total": round(total, 6)}

    def rate_composite(self, receipt_id: str, *, rater_node: str, rater_user: str, stars: int) -> dict[str, Any]:
        """One rating per composite reuse, by its own consumer; children x(0.5..1.5); total stays <= V_L."""
        if not 1 <= int(stars) <= 5:
            raise ValueError("rating must be 1..5 stars")
        multiplier = RATING_MIN + (int(stars) - 1) * (RATING_MAX - RATING_MIN) / 4.0
        with self._lock, self._connect() as c:
            head = c.execute("SELECT * FROM entries WHERE receipt_id=? AND kind='composite_reuse'", (receipt_id,)).fetchone()
            if head is None:
                raise PermissionError("ratings must reference a credited, verified composite reuse receipt")
            if (rater_node, rater_user) != (head["consumer_node"], head["consumer_user"]):
                raise PermissionError("only the verified reuser of this receipt may rate it")
            if self._self_dealing(head["publisher_id"], rater_node, rater_user):
                raise PermissionError("a lattice publisher cannot rate its own composite")
            if c.execute("SELECT 1 FROM entries WHERE receipt_id LIKE ? AND kind='rating'", (receipt_id + "#%",)).fetchone():
                raise PermissionError("this reuse has already been rated")
            detail = json.loads(head["detail"])
            v_l = float(detail.get("v_l") or 0.0)
            rows = c.execute("SELECT * FROM entries WHERE receipt_id LIKE ?", (receipt_id + "#%",)).fetchall()
            children = [r for r in rows if r["kind"] == "composite_component" and not self.is_clawed(r["crystal_id"])]
            total = sum(float(r["units"]) for r in rows)
            premium_left = sum(float(r["units"]) for r in rows if r["crystal_id"] == head["crystal_id"])
            wanted = {r["crystal_id"]: float(r["units"]) * (multiplier - 1.0) for r in children}
            increase = sum(v for v in wanted.values() if v > 0)
            overflow = max(0.0, total + increase - v_l)
            cut_premium = min(overflow, premium_left)
            leftover = overflow - cut_premium
            scale = 1.0 if increase <= 0 else max(0.0, (increase - leftover) / increase)
            granted = 0.0
            if cut_premium > 0:
                self._append(c, kind="premium_adjustment", crystal_id=head["crystal_id"], publisher_id=head["publisher_id"],
                             space_id=head["space_id"], consumer_node=rater_node, consumer_user=rater_user,
                             receipt_id=f"{receipt_id}#premium-adjustment", reuse_fingerprint=None, units=-cut_premium,
                             reason="rating_overflow_reduces_premium", detail={"v_l": v_l})
            for row in children:
                delta = wanted[row["crystal_id"]]
                delta = delta * scale if delta > 0 else delta
                granted += delta
                self._append(c, kind="rating", crystal_id=row["crystal_id"], publisher_id=row["publisher_id"],
                             space_id=row["space_id"], consumer_node=rater_node, consumer_user=rater_user,
                             receipt_id=f"{receipt_id}#{row['crystal_id']}", reuse_fingerprint=None, units=delta,
                             reason=f"stars:{int(stars)}", detail={"multiplier": multiplier, "capped_at_v_l": scale < 1.0})
        return {"multiplier": multiplier, "units": round(granted, 6), "premium_reduced": round(cut_premium, 6)}

    def record_false_reuse(self, crystal_id: str, *, publisher_id: str, space_id: str, evidence_digest: str) -> None:
        with self._lock, self._connect() as c:
            self._append(c, kind="false_reuse", crystal_id=crystal_id, publisher_id=publisher_id, space_id=space_id,
                         consumer_node=self.local_node_id, consumer_user=None, receipt_id=None, reuse_fingerprint=None,
                         units=0.0, reason="postcondition_failed", detail={"evidence_digest": evidence_digest})

    def clawback(self, crystal_id: str, *, reason: str, evidence_digest: str = "") -> dict[str, Any]:
        """Demotion reverses every outstanding credit for the crystal (v0.9 7.13.1 credit reversal); idempotent."""
        with self._lock, self._connect() as c:
            if c.execute("SELECT 1 FROM clawed WHERE crystal_id=?", (crystal_id,)).fetchone():
                return {"clawed_back": 0.0, "already": True}
            rows = c.execute("SELECT publisher_id, space_id, SUM(units) AS units FROM entries WHERE crystal_id=? "
                             "GROUP BY publisher_id, space_id", (crystal_id,)).fetchall()
            total = 0.0
            for row in rows:
                if float(row["units"] or 0) > 0:
                    self._append(c, kind="clawback", crystal_id=crystal_id, publisher_id=row["publisher_id"],
                                 space_id=row["space_id"], consumer_node=self.local_node_id, consumer_user=None,
                                 receipt_id=None, reuse_fingerprint=None, units=-float(row["units"]), reason=reason,
                                 detail={"evidence_digest": evidence_digest})
                    total += float(row["units"])
            c.execute("INSERT INTO clawed VALUES(?,?,?,?)", (crystal_id, reason, evidence_digest, time.time()))
        return {"clawed_back": round(total, 6), "already": False}

    def balances(self) -> dict[str, Any]:
        rows: dict[tuple[str, str], dict[str, Any]] = {}
        for e in self.entries():
            key = (e["publisher_id"], e["space_id"])
            row = rows.setdefault(key, {"publisher_id": key[0], "space_id": key[1], "units": 0.0, "verified_reuses": 0,
                                        "consumers": set(), "ratings": 0, "clawbacks": 0})
            row["units"] += float(e["units"])
            if e["kind"] == "reuse":
                row["verified_reuses"] += 1
                row["consumers"].add((e["consumer_node"], e["consumer_user"]))
            row["ratings"] += e["kind"] == "rating"
            row["clawbacks"] += e["kind"] == "clawback"
        out = [{**{k: v for k, v in r.items() if k != "consumers"}, "units": round(r["units"], 6),
                "distinct_consumers": len(r["consumers"])} for r in rows.values()]
        return {**LEDGER_POLICY, "accounts": out, "chain": self.verify_chain()}

    def export(self, *, space_id: str | None = None) -> dict[str, Any]:
        entries = [e for e in self.entries() if space_id is None or e["space_id"] == space_id]
        with self._connect() as c:
            receipts = [json.loads(r["payload"]) for r in c.execute("SELECT payload FROM receipts ORDER BY created_at")]
        receipts = [r for r in receipts if space_id is None or r.get("space_id") == space_id]
        return {"beast_object_type": "coding_crystal_shadow_ledger_export", "node_id": self.local_node_id,
                **LEDGER_POLICY, "entries": entries, "receipts": receipts, "chain": self.verify_chain()}


def aggregate_federated(exports: Iterable[Mapping[str, Any]], *, attested_nodes: Iterable[str],
                        controller_of: Callable[[str], str] | None = None) -> dict[str, Any]:
    """Cross-node view: only attested nodes' own locally witnessed entries count; one node = one voice per crystal
    reuse fingerprint; entries whose consumer shares a controller with the publisher are excluded (self-dealing)."""
    controller_of = controller_of or (lambda identity: identity)
    attested = set(attested_nodes)
    totals: dict[str, float] = {}
    rejected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for export in exports:
        node = str(export.get("node_id") or "")
        if node not in attested:
            rejected.append({"node_id": node, "reason": "node_not_attested"})
            continue
        entries = list(export.get("entries") or [])
        prev = "genesis"
        broken = False
        for e in entries:
            body = {k: e[k] for k in ("kind", "crystal_id", "publisher_id", "space_id", "consumer_node", "consumer_user",
                                     "receipt_id", "reuse_fingerprint", "units", "reason")}
            body["units"] = round(float(body["units"]), 6)
            body["detail"] = json.dumps(e["detail"], sort_keys=True, default=str)
            body["prev_hash"] = prev
            if e["prev_hash"] != prev or _sha({k: body[k] for k in sorted(body)}) != e["entry_hash"]:
                broken = True
                break
            prev = e["entry_hash"]
        if broken:
            rejected.append({"node_id": node, "reason": "ledger_chain_broken"})
            continue
        for e in entries:
            if e["entry_hash"] in seen:  # the same ledger exported twice counts once
                rejected.append({"node_id": node, "reason": "duplicate_entry", "seq": e["seq"]})
                continue
            seen.add(e["entry_hash"])
            if e["kind"] in {"reuse", "rating"} and e["consumer_node"] != node:
                rejected.append({"node_id": node, "reason": "foreign_witness", "seq": e["seq"]})
                continue
            if controller_of(e["publisher_id"]) in {controller_of(node), controller_of(str(e.get("consumer_user") or ""))}:
                rejected.append({"node_id": node, "reason": "self_dealing", "seq": e["seq"]})
                continue
            if e.get("reuse_fingerprint"):
                if e["reuse_fingerprint"] in seen:
                    rejected.append({"node_id": node, "reason": "duplicate_reuse", "seq": e["seq"]})
                    continue
                seen.add(e["reuse_fingerprint"])
            totals[e["publisher_id"]] = round(totals.get(e["publisher_id"], 0.0) + float(e["units"]), 6)
    return {**LEDGER_POLICY, "publishers": totals, "rejected": rejected}


class CrystalReuseEconomy:
    """Glue between the planner runtime and the shadow ledger: one receipt per sealed crystal run."""

    def __init__(self, ledger: CrystalShadowLedger, *, envelope_store: Any = None, local_user_id: str = "operator"):
        self.ledger = ledger
        self.envelope_store = envelope_store
        self.local_user_id = local_user_id

    def _baseline(self, candidate: Any) -> tuple[Mapping[str, Any], str, str, bool]:
        if self.envelope_store is not None and getattr(candidate, "source_run_id", ""):
            try:
                local = self.envelope_store.get(candidate.source_run_id)
            except LookupError:  # this node never ran the baseline itself
                local = None
            if local is not None and local.envelope_digest == candidate.source_envelope_digest:
                return dict(local.budget), local.envelope_digest, "local_envelope", bool((local.verification or {}).get("passed"))
        # Publisher-measured envelope budget, bound into the signed candidate digest (still a measurement, flagged).
        return dict(candidate.learned_budget), candidate.source_envelope_digest, "publisher_signed_envelope", True

    def on_reuse_sealed(self, *, record: Mapping[str, Any], candidate: Any, envelope: Any, replay: bool) -> dict[str, Any]:
        binding = self.ledger.space_binding(candidate.crystal_id)
        provenance = dict(record.get("provenance") or {})
        commons = dict(provenance.get("commons") or {})
        if binding is None and commons.get("space_manifest_hash"):
            binding = {"space_id": commons.get("space_id"), "space_manifest_hash": commons["space_manifest_hash"],
                       "publisher_id": provenance.get("signer_key_id") or ""}
        if binding is None:  # unpublished local crystal: bound to its own candidate digest, publisher = local key
            from app.kernel.compute.crystal_commons import space_id_for

            binding = {"space_id": space_id_for(candidate.crystal_id), "space_manifest_hash": candidate.digest,
                       "publisher_id": self.ledger.local_publisher_id}
        baseline, digest, source, baseline_ok = self._baseline(candidate)
        status = str(record.get("status") or "")
        receipt = reuse_reduction_receipt(
            baseline_budget=baseline, baseline_digest=digest, baseline_source=source, baseline_verified=baseline_ok,
            reuse_envelope=envelope, crystal_id=candidate.crystal_id, space_id=str(binding["space_id"]),
            space_manifest_hash=str(binding["space_manifest_hash"]), publisher_id=str(binding["publisher_id"]),
            consumer={"node_id": self.ledger.local_node_id, "user_id": self.local_user_id},
            kind="reproduction" if replay else "reuse",
            local_reproduction_verified=status == "promoted" and bool((record.get("receipt") or {}).get("promoted")),
            promotion_verified=status == "promoted",
            false_reuse_rate=self.ledger.false_reuse_rate(candidate.crystal_id))
        entry = self.ledger.record_reproduction(receipt) if replay else self.ledger.account_reuse(receipt, crystal_status=status)
        return {"receipt": receipt, "entry": entry}


__all__ = ["composite_reuse_receipt", "CREDIT_UNIT", "CrystalReuseEconomy", "CrystalShadowLedger", "LEDGER_POLICY", "aggregate_federated",
           "budget_view", "recurrence_value", "reuse_reduction_receipt", "validate_receipt"]
