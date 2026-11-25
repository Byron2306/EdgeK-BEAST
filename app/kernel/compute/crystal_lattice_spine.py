"""Lattice Spine: a governed, fail-closed composition graph over promoted coding crystals.

Claim boundary: PGEC Appendix B lists general multi-crystal composition as *emerging, not established*. This module
governs composition (PGEC §8.1(4): every stage may refuse independently); it does not prove composites safe or useful.

* Nodes are promoted coding crystals and composites (``component_ids`` >= 2 distinct children); edges use
  ``crystal_hypergraph.EDGE_TYPES`` and every write is re-validated through a ``CrystalHypergraph``.
* Composite authority is the intersection A_L = ⋂ A_Ci (PGEC eq. 3, §8.2 no hidden authority).
* Admission = every child verified + composite verifier (>= 3/3 held-out) + operator approval (PGEC §2.4); otherwise
  REFUSE, REVALIDATE or ESCALATE.  Demotion propagates upward (IEI v0.9 §7.13.1).
* Every mutation is witnessed on the existing ``CrystalLatticeLedger`` and ``CrystalChainLedger`` (no second ledger).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.kernel.compute.coding_crystals import CRYSTAL_PARAMETERS, CodingCrystalCandidate, coding_catalog_digest
from app.kernel.compute.crystal_hypergraph import CrystalHypergraph

ADMIT, REFUSE, REVALIDATE, ESCALATE = "ADMIT", "REFUSE", "REVALIDATE", "ESCALATE"
NODE_TYPE = {"crystal": "Crystal", "composite": "Crystal", "verifier": "Verifier"}
COMPOSITE_VERIFICATION = {"requires_children_verified": True, "heldout_min": 3, "verifier": "composite_heldout_replay",
                          "verify_command_parameter": "verify_command"}
CLAIM_BOUNDARY = ("governed_fail_closed_composition_graph; PGEC Appendix B: general multi-crystal composition is "
                  "emerging, not established")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def authority_of(candidate: CodingCrystalCandidate) -> frozenset[str]:
    """A_C: the reviewed tools a crystal may drive (a composite's own intersected envelope when present)."""
    if candidate.authority:
        return frozenset(candidate.authority)
    return frozenset(str(step["tool_id"]) for step in candidate.steps if step["tool_id"])


def compose_candidates(children: Sequence[CodingCrystalCandidate], *, task_family: str, source_run_id: str,
                       source_envelope_digest: str, learned_budget: Mapping[str, float]) -> CodingCrystalCandidate:
    """Build (not admit) a composite: children's recipes in order, one completion step, A_L = ⋂ A_Ci."""
    ids = [child.crystal_id for child in children]
    if len(set(ids)) < 2 or len(set(ids)) != len(ids):
        raise ValueError("a composite needs at least two distinct children")
    for child in children:
        child.validate()
    authority = frozenset.intersection(*(authority_of(child) for child in children))
    steps: list[dict[str, str]] = []
    for child in children:
        steps.extend(dict(step) for step in child.steps[:-1])
    steps.append(dict(children[-1].steps[-1]))
    used = {step["tool_id"] for step in steps if step["tool_id"]}
    if not used <= authority:
        raise ValueError(f"composite steps exceed the intersected authority A_L: {sorted(used - authority)}")
    composite = CodingCrystalCandidate(
        crystal_id="", task_family=task_family, steps=tuple(steps), parameters=CRYSTAL_PARAMETERS,
        opcode_catalog_digest=coding_catalog_digest(), source_run_id=source_run_id,
        source_envelope_digest=source_envelope_digest, learned_budget={k: float(v) for k, v in learned_budget.items()},
        component_ids=tuple(ids), authority=tuple(sorted(authority)),
        composite_verification=dict(COMPOSITE_VERIFICATION)).sealed()
    composite.validate()
    return composite


class CrystalLattice:
    """Persistent lattice under .beast; every mutation is witnessed on the existing lattice ledger and crystal chain."""

    def __init__(self, path: str | Path, *, registry: Any, lattice_ledger: Any, chain: Any):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.registry = registry
        self.lattice_ledger = lattice_ledger
        self.chain = chain
        self._lock = threading.RLock()
        with self._connect() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS nodes(node_id TEXT PRIMARY KEY, kind TEXT NOT NULL, task_family TEXT NOT NULL,
              status TEXT NOT NULL, publisher_id TEXT NOT NULL, component_ids TEXT NOT NULL, authority TEXT NOT NULL,
              registry_digest TEXT NOT NULL, admission TEXT NOT NULL, record_digest TEXT NOT NULL, updated_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS edges(seq INTEGER PRIMARY KEY AUTOINCREMENT, edge_type TEXT NOT NULL,
              source_ids TEXT NOT NULL, target_id TEXT NOT NULL, UNIQUE(edge_type, source_ids, target_id));
            """)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        return connection

    # -- records ---------------------------------------------------------------------------------------------
    @staticmethod
    def _digest_row(row: Mapping[str, Any]) -> str:
        return _sha({k: row[k] for k in ("node_id", "kind", "task_family", "status", "publisher_id", "component_ids",
                                         "authority", "registry_digest", "admission")})

    def _put_node(self, c: sqlite3.Connection, **row: Any) -> dict[str, Any]:
        row["component_ids"] = json.dumps(list(row.get("component_ids") or []))
        row["authority"] = json.dumps(sorted(row.get("authority") or []))
        row["admission"] = json.dumps(row.get("admission") or {}, sort_keys=True, default=str)
        row["record_digest"] = self._digest_row(row)
        c.execute("INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(node_id) DO UPDATE SET status=excluded.status,"
                  "admission=excluded.admission,record_digest=excluded.record_digest,updated_at=excluded.updated_at",
                  tuple(row[k] for k in ("node_id", "kind", "task_family", "status", "publisher_id", "component_ids",
                                         "authority", "registry_digest", "admission", "record_digest")) + (time.time(),))
        return row

    def node(self, node_id: str) -> dict[str, Any]:
        with self._connect() as c:
            row = c.execute("SELECT * FROM nodes WHERE node_id=?", (node_id,)).fetchone()
        if row is None:
            raise LookupError(f"unknown lattice node: {node_id}")
        data = dict(row)
        if self._digest_row(data) != data["record_digest"]:
            raise ValueError(f"lattice node record tampered: {node_id}")
        return {**data, "component_ids": json.loads(data["component_ids"]), "authority": json.loads(data["authority"]),
                "admission": json.loads(data["admission"])}

    def nodes(self) -> list[dict[str, Any]]:
        with self._connect() as c:
            ids = [r["node_id"] for r in c.execute("SELECT node_id FROM nodes ORDER BY updated_at").fetchall()]
        out = []
        for node_id in ids:
            try:
                out.append(self.node(node_id))
            except ValueError:
                out.append({"node_id": node_id, "status": "tampered"})
        return out

    def edges(self) -> list[dict[str, Any]]:
        with self._connect() as c:
            rows = c.execute("SELECT * FROM edges ORDER BY seq").fetchall()
        return [{"edge_type": r["edge_type"], "source_ids": json.loads(r["source_ids"]), "target_id": r["target_id"]}
                for r in rows]

    def _hypergraph(self, c: sqlite3.Connection) -> CrystalHypergraph:
        graph = CrystalHypergraph()
        for row in c.execute("SELECT node_id, kind FROM nodes").fetchall():
            graph.add_node(row["node_id"], NODE_TYPE[row["kind"]])
        for row in c.execute("SELECT * FROM edges ORDER BY seq").fetchall():
            graph.add_edge(row["edge_type"], json.loads(row["source_ids"]), row["target_id"])
        return graph

    def _add_edge(self, c: sqlite3.Connection, edge_type: str, sources: Iterable[str], target: str) -> None:
        c.execute("INSERT OR IGNORE INTO edges(edge_type, source_ids, target_id) VALUES(?,?,?)",
                  (edge_type, json.dumps(list(sources)), target))

    def _witness(self, op: str, node_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        body = {"beast_object_type": "crystal_lattice_spine_mutation", "version": "1.0", "op": op, "node_id": node_id,
                **dict(payload), "claim_boundary": CLAIM_BOUNDARY, "private_payload_exported": False}
        checkpoint = self.lattice_ledger.append(body)
        block = self.chain.append(f"crystal_lattice_spine_{op}", node_id, {
            **body, "checkpoint_hash": checkpoint["checkpoint_hash"]})
        return {"checkpoint_hash": checkpoint["checkpoint_hash"], "block_hash": block["block_hash"]}

    def _mutate(self, op: str, node_id: str, payload: Mapping[str, Any], write) -> dict[str, Any]:
        """Write + hypergraph validation + witness inside one transaction; any failure rolls the write back."""
        with self._lock:
            c = self._connect()
            try:
                c.execute("BEGIN IMMEDIATE")
                write(c)
                self._hypergraph(c)  # raises ValueError on an invalid node/edge type or dangling edge
                witness = self._witness(op, node_id, payload)
                c.commit()
                return witness
            except Exception:
                c.rollback()
                raise
            finally:
                c.close()

    # -- mutations -------------------------------------------------------------------------------------------
    def add_crystal(self, crystal_id: str, *, publisher_id: str) -> dict[str, Any]:
        """Admit a single D6-promoted crystal as a lattice leaf (its promotion was already a verifier act)."""
        record = self.registry.get(crystal_id)
        if record["status"] != "promoted":
            raise PermissionError("only promoted coding crystals may join the lattice")
        candidate = record["candidate_object"]
        candidate.validate()
        if candidate.component_ids:
            raise PermissionError("composites enter through admit_composite")

        def write(c):
            self._put_node(c, node_id=crystal_id, kind="crystal", task_family=candidate.task_family, status="admitted",
                           publisher_id=publisher_id, component_ids=[], authority=sorted(authority_of(candidate)),
                           registry_digest=candidate.digest, admission={"replay_receipt": record.get("receipt")})

        witness = self._mutate("add", crystal_id, {"kind": "crystal", "publisher_id": publisher_id,
                                                   "registry_digest": candidate.digest}, write)
        return {"node": self.node(crystal_id), "witness": witness}

    def _outcome(self, outcome: str, composite: CodingCrystalCandidate, reason: str, **extra: Any) -> dict[str, Any]:
        if outcome != ADMIT:
            self.registry.record_negative(composite.task_family, kind=f"lattice_{outcome.lower()}:{reason.split(':')[0]}",
                                          evidence_digest=composite.digest, crystal_id=composite.crystal_id)
            with self._lock:
                witness = self._witness(outcome.lower(), composite.crystal_id or "composite:invalid",
                                        {"reason": reason, "component_ids": list(composite.component_ids)})
            extra["witness"] = witness
        return {"outcome": outcome, "reason": reason, "crystal_id": composite.crystal_id, **extra}

    def witness_scoped_refusal(self, receipt: Mapping[str, Any]) -> dict[str, Any]:
        """Witness a pre-actuation refusal without demoting an admitted node."""
        node_id = str(receipt["crystal_id"])
        if self.node(node_id)["status"] != "admitted":
            raise PermissionError("scoped refusal needs an admitted lattice node")
        with self._lock:
            return self._witness("scoped_refusal", node_id, {
                key: receipt[key] for key in ("scope_digest", "run_id", "receipt_digest", "reason")
            })

    def admit_composite(self, composite: CodingCrystalCandidate, *, verifier: Any, publisher_id: str,
                        approved_by: str) -> dict[str, Any]:
        children = list(composite.component_ids)
        if len(set(children)) < 2 or len(set(children)) != len(children):
            return self._outcome(REFUSE, composite, "fewer_than_two_distinct_children")
        try:
            composite.validate()
        except ValueError as exc:
            return self._outcome(REFUSE, composite, f"composite_invalid:{exc}")
        child_candidates = []
        for child_id in children:
            try:
                node = self.node(child_id)
            except LookupError:
                return self._outcome(REFUSE, composite, f"child_unknown:{child_id}")
            except ValueError:
                return self._outcome(REVALIDATE, composite, f"child_record_tampered:{child_id}")
            if node["status"] != "admitted":
                return self._outcome(REFUSE, composite, f"child_not_verified:{child_id}")
            try:
                record = self.registry.get(child_id)
            except (LookupError, ValueError):
                return self._outcome(REVALIDATE, composite, f"child_registry_unreadable:{child_id}")
            if record["status"] == "demoted":
                return self._outcome(REFUSE, composite, f"child_not_verified:{child_id}")
            if record["status"] != "promoted" or record["candidate_object"].digest != node["registry_digest"]:
                return self._outcome(REVALIDATE, composite, f"child_drifted:{child_id}")
            child_candidates.append(record["candidate_object"])
        if composite.crystal_id in self._descendants(children):
            return self._outcome(REFUSE, composite, "cycle")
        intersection = sorted(frozenset.intersection(*(authority_of(child) for child in child_candidates)))
        if list(composite.authority) != intersection:
            return self._outcome(REFUSE, composite, "authority_not_intersection")
        if self._conflicting(children):
            return self._outcome(ESCALATE, composite, "children_conflict")
        if verifier is None:
            return self._outcome(ESCALATE, composite, "composite_verifier_missing")
        if (getattr(verifier, "candidate_id", "") != composite.crystal_id or not getattr(verifier, "promoted", False)
                or int(getattr(verifier, "successes", 0)) < 3 or int(getattr(verifier, "successes", 0))
                != int(getattr(verifier, "attempts", -1))):
            return self._outcome(REFUSE, composite, "composite_verifier_failed")
        if not str(approved_by or "").strip():
            return self._outcome(ESCALATE, composite, "operator_promotion_required")
        receipt = asdict(verifier)
        verifier_id = "verifier:" + _sha(receipt).split(":", 1)[1][:24]
        self.registry.add_candidate(composite)

        def write(c):
            self._put_node(c, node_id=composite.crystal_id, kind="composite", task_family=composite.task_family,
                           status="admitted", publisher_id=publisher_id, component_ids=children,
                           authority=intersection, registry_digest=composite.digest,
                           admission={"verifier": receipt, "approved_by": approved_by,
                                      "children_digests": {cid: self.node(cid)["record_digest"] for cid in children}})
            self._put_node(c, node_id=verifier_id, kind="verifier", task_family=composite.task_family,
                           status="admitted", publisher_id=publisher_id, component_ids=[], authority=[],
                           registry_digest=_sha(receipt), admission={})
            self._add_edge(c, "COMPOSES_WITH", children, composite.crystal_id)
            self._add_edge(c, "VERIFIED_BY", [composite.crystal_id], verifier_id)

        witness = self._mutate("admit", composite.crystal_id, {
            "kind": "composite", "component_ids": children, "authority": intersection, "publisher_id": publisher_id,
            "verifier": {"successes": receipt["successes"], "attempts": receipt["attempts"]}, "approved_by": approved_by,
        }, write)
        self.registry.promote(composite.crystal_id, verifier)
        return {"outcome": ADMIT, "reason": "children_verified_and_composite_verifier_passed",
                "crystal_id": composite.crystal_id, "node": self.node(composite.crystal_id), "witness": witness}

    def _parents(self, node_id: str) -> list[str]:
        return [e["target_id"] for e in self.edges() if e["edge_type"] == "COMPOSES_WITH" and node_id in e["source_ids"]]

    def _descendants(self, roots: Iterable[str]) -> set[str]:
        children = {e["target_id"]: e["source_ids"] for e in self.edges() if e["edge_type"] == "COMPOSES_WITH"}
        seen: set[str] = set()
        stack = list(roots)
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(children.get(current, []))
        return seen

    def _conflicting(self, children: Sequence[str]) -> bool:
        group = set(children)
        return any(e["edge_type"] == "CONFLICTS_WITH" and e["target_id"] in group and group & set(e["source_ids"])
                   for e in self.edges())

    def ancestors(self, node_id: str) -> list[str]:
        order: list[str] = []
        frontier = [node_id]
        while frontier:
            nxt: list[str] = []
            for current in frontier:
                for parent in self._parents(current):
                    if parent not in order:
                        order.append(parent)
                        nxt.append(parent)
            frontier = nxt
        return order

    def demote(self, node_id: str, *, reason: str, evidence_digest: str = "") -> dict[str, Any]:
        """Demote a node and, transitively, every composite that contains it (IEI v0.9 §7.13.1)."""
        chain = [node_id, *self.ancestors(node_id)]
        demoted: list[str] = []
        for index, current in enumerate(chain):
            try:
                node = self.node(current)
            except LookupError:
                continue
            except ValueError:
                node = None  # a tampered record is demoted regardless
            if node is not None and node["status"] == "demoted":
                continue
            cause = reason if index == 0 else f"component_demoted:{node_id}"
            row = node or {"node_id": current, "kind": "crystal", "task_family": "", "publisher_id": "",
                           "component_ids": [], "authority": [], "registry_digest": "", "admission": {}}

            def write(c, row=row, cause=cause):
                self._put_node(c, node_id=row["node_id"], kind=row["kind"], task_family=row["task_family"],
                               status="demoted", publisher_id=row["publisher_id"], component_ids=row["component_ids"],
                               authority=row["authority"], registry_digest=row["registry_digest"],
                               admission={**dict(row["admission"] or {}),
                                          "demotion": {"reason": cause, "evidence_digest": evidence_digest}})

            self._mutate("demote", current, {"reason": cause, "evidence_digest": evidence_digest,
                                             "origin": node_id}, write)
            try:
                if self.registry.get(current)["status"] != "demoted":
                    self.registry.demote(current, reason=cause, evidence_digest=evidence_digest)
            except (LookupError, ValueError):
                pass
            demoted.append(current)
        return {"demoted": demoted, "origin": node_id, "reason": reason}

    def _set_status(self, node: Mapping[str, Any], status: str, admission: Mapping[str, Any], op: str,
                    payload: Mapping[str, Any]) -> dict[str, Any]:
        def write(c):
            self._put_node(c, node_id=node["node_id"], kind=node["kind"], task_family=node["task_family"], status=status,
                           publisher_id=node["publisher_id"], component_ids=node["component_ids"],
                           authority=node["authority"], registry_digest=node["registry_digest"], admission=admission)

        return self._mutate(op, node["node_id"], payload, write)

    def supersede(self, node_id: str, *, by: str, reason: str, evidence_digest: str = "") -> dict[str, Any]:
        """Reversible retirement (defrag): an admitted node yields to an admitted same-family node.

        Not a failure: no registry demotion, no clawback. Refused while an admitted composite still contains the
        node, so the lattice never serves a composite whose component is no longer served."""
        if node_id == by:
            raise PermissionError("a node cannot supersede itself")
        node, winner = self.node(node_id), self.node(by)
        if node["status"] != "admitted" or winner["status"] != "admitted":
            raise PermissionError("supersede needs two admitted lattice nodes")
        if node["task_family"] != winner["task_family"]:
            raise PermissionError("supersede is same-family only")
        live_parents = [p for p in self._parents(node_id) if self.node(p)["status"] == "admitted"]
        if live_parents:
            raise PermissionError(f"node is a component of admitted composites {live_parents}; supersede them first")
        record = {"by": by, "reason": reason, "evidence_digest": evidence_digest, "prior_status": node["status"],
                  "at": time.time()}
        admission = {**dict(node["admission"] or {}), "superseded": record}
        return self._set_status(node, "superseded", admission, "supersede",
                                {"by": by, "reason": reason, "evidence_digest": evidence_digest})

    def restore(self, node_id: str, *, reason: str) -> dict[str, Any]:
        """Undo a supersede: the node returns to admitted; the history stays in the witnessed admission record."""
        node = self.node(node_id)
        if node["status"] != "superseded":
            raise PermissionError("only superseded lattice nodes can be restored")
        admission = dict(node["admission"] or {})
        prior = admission.pop("superseded", {})
        admission["supersede_history"] = list(admission.get("supersede_history") or []) + [
            {**dict(prior), "restored": True, "restore_reason": reason}]
        return self._set_status(node, prior.get("prior_status", "admitted"), admission, "restore",
                                {"reason": reason, "superseded_by": prior.get("by", "")})

    # -- queries ---------------------------------------------------------------------------------------------
    def best_for_family(self, task_family: str) -> str | None:
        """Highest admitted node for a family: composites before leaves, newest first.  Nomination only."""
        candidates = [n for n in self.nodes() if n.get("status") == "admitted" and n.get("task_family") == task_family
                      and n.get("kind") in {"crystal", "composite"}]
        if not candidates:
            return None
        candidates.sort(key=lambda n: (n["kind"] == "composite", n.get("updated_at", 0)), reverse=True)
        return candidates[0]["node_id"]

    def verify(self) -> dict[str, Any]:
        tampered = [n["node_id"] for n in self.nodes() if n.get("status") == "tampered"]
        ledger, chain = self.lattice_ledger.verify(), self.chain.verify()
        with self._connect() as c:
            try:
                self._hypergraph(c)
                graph_ok = True
            except ValueError:
                graph_ok = False
        return {"valid": not tampered and ledger.valid and chain.valid and graph_ok, "tampered_nodes": tampered,
                "lattice_ledger_head": ledger.head_hash, "crystal_chain_head": chain.head_hash, "hypergraph_valid": graph_ok}

    def state(self) -> dict[str, Any]:
        return {"beast_object_type": "crystal_lattice_spine_state", "version": "1.0", "claim_boundary": CLAIM_BOUNDARY,
                "nodes": self.nodes(), "edges": self.edges(), "verification": self.verify()}


def default_lattice(
    workspace: str | Path,
    registry: Any,
    *,
    env: Mapping[str, str] | None = None,
    isolated: bool = False,
) -> CrystalLattice:
    """Production wiring: .beast lattice, witnessed on the gateway's existing lattice ledger and Commons crystal chain."""
    import os

    from app.kernel.security.crystal_chain import CrystalChainLedger
    from app.kernel.security.crystal_lattice_ledger import CrystalLatticeLedger

    project = Path(__file__).resolve().parents[3]
    environ = os.environ if env is None else env
    trial_root = Path(workspace) / ".beast" / "crystals" / "trial-witness"
    commons_root = (
        trial_root if isolated else
        Path(environ.get("BEAST_COMMONS_ROOT") or project / "data" / "commons_spaces")
    )
    lattice_ledger_root = (
        trial_root if isolated else
        Path(environ.get("BEAST_CRYSTAL_LATTICE_LEDGER_ROOT")
             or project / "benchmarks" / "results" / "crystal_lattice_ledger")
    )
    return CrystalLattice(Path(workspace) / ".beast" / "crystals" / "crystal_lattice.sqlite3", registry=registry,
                          lattice_ledger=CrystalLatticeLedger(lattice_ledger_root),
                          chain=CrystalChainLedger(commons_root / ".crystal_chain" / "blocks.jsonl",
                                                   node_id=environ.get("BEAST_COMMONS_NODE_ID", "local-commons")))


__all__ = ["ADMIT", "CLAIM_BOUNDARY", "ESCALATE", "REFUSE", "REVALIDATE", "CrystalLattice", "authority_of", "demote_with_clawback",
           "compose_candidates", "default_lattice"]


def demote_with_clawback(lattice: CrystalLattice, ledger: Any, crystal_id: str, *, reason: str,
                         evidence_digest: str = "") -> dict[str, Any]:
    """Demote upward through the lattice; claw back the origin's credits and every demoted ancestor's premium.

    A composite's ledger entries keyed to its own id are only its premium (children are keyed to themselves), so
    demoting L reverses L's premium and leaves children whole; demoting a child reverses the child and its parents.
    """
    result = lattice.demote(crystal_id, reason=reason, evidence_digest=evidence_digest)
    clawed = {node: ledger.clawback(node, reason=reason if node == crystal_id else f"component_demoted:{crystal_id}",
                                    evidence_digest=evidence_digest)
              for node in result["demoted"]}
    return {**result, "clawbacks": clawed}


def spine_state(workspace: str | Path) -> dict[str, Any]:
    """Read-only view for ``GET /edgek/crystal-lattice/spine``; never creates the lattice."""
    path = Path(workspace) / ".beast" / "crystals" / "crystal_lattice.sqlite3"
    if not path.is_file():
        return {"beast_object_type": "crystal_lattice_spine_state", "version": "1.0", "available": False,
                "claim_boundary": CLAIM_BOUNDARY, "path": str(path)}
    from app.kernel.compute.coding_crystals import CodingCrystalRegistry

    registry = CodingCrystalRegistry(Path(workspace) / ".beast" / "crystals" / "coding_crystals.sqlite3")
    return {**default_lattice(workspace, registry).state(), "available": True, "path": str(path)}
