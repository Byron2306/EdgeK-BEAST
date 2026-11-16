"""Experimental Task 3: Defragmentation Daemon for coding crystals (IEI v0.9 §7.12 Table 14).

Default-off (BEAST_DEFRAG_DAEMON) and dry-run first; mutations additionally need BEAST_DEFRAG_APPLY=1 plus a
Compute Governor admit. Rules:

- exact duplicates (identical program modulo source run) → the less-used copy is ``superseded``;
- near duplicates (opcode-bigram Jaccard ≥ threshold) are *nominated* only; a merge needs an injected proof
  verifier returning ``passed=True`` + an evidence digest (similarity nominates, never grants);
- stale crystals (no promotion/reuse activity in the window) → ``retired_stale``;
- compaction is SQLite VACUUM only: no row is ever deleted, proof receipts stay inside each record.

Every mutation is a status overlay written through the registry (digest-checked) and a hash-chained ledger entry
carrying the prior state; ``undo(receipt_id)`` restores it. Lattice nodes are not mutated here (lattice demotion is
one-way by design); the plan reports them read-only.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

DAEMON_ENV = "BEAST_DEFRAG_DAEMON"
APPLY_ENV = "BEAST_DEFRAG_APPLY"
SERVED = {"promoted"}
RETIRABLE = {"candidate", "quarantined", "promoted"}
# Memory Hull residue identity ignores write-time fields: same task/decision/evidence/correlation = same residue.
HULL_VOLATILE = {"created_at", "residue_id", "markdown_sha256"}
HULL_QUARANTINE = ".defrag"


def _on(env: Mapping[str, str], key: str) -> bool:
    return str(env.get(key, "")).strip().lower() in {"1", "true", "yes", "on"}


def _sha(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def program_key(candidate: Mapping[str, Any]) -> str:
    return _sha({k: candidate.get(k) for k in ("task_family", "steps", "parameters", "opcode_catalog_digest",
                                                "component_ids", "authority", "composite_verification")})


def _bigrams(candidate: Mapping[str, Any]) -> set[tuple[str, str]]:
    ops = [f"{s.get('opcode')}|{s.get('tool_id')}|{s.get('expect')}" for s in candidate.get("steps") or ()]
    return set(zip(ops, ops[1:], strict=False)) or set(ops and [(ops[0], "")])


def jaccard(a: Mapping[str, Any], b: Mapping[str, Any]) -> float:
    x, y = _bigrams(a), _bigrams(b)
    return len(x & y) / len(x | y) if x | y else 0.0


class DefragDaemon:
    def __init__(self, *, registry: Any, ledger_path: str | Path, governor: Any = None,
                 env: Mapping[str, str] | None = None, merge_verifier: Callable[[str, str], Any] | None = None,
                 near_threshold: float = 0.8, stale_after_s: float = 14 * 86400,
                 promoted_stale_after_s: float = 90 * 86400, clock: Callable[[], float] = time.time,
                 hull: Any = None):
        from app.kernel.governance.governor_spine import ComputeGovernorSpine

        self.registry = registry
        self.ledger_path = Path(ledger_path)
        self.governor = governor if governor is not None else ComputeGovernorSpine()
        self.env = dict(os.environ if env is None else env)
        self.merge_verifier = merge_verifier
        self.near_threshold = float(near_threshold)
        self.stale_after_s = float(stale_after_s)
        self.promoted_stale_after_s = float(promoted_stale_after_s)
        self.clock = clock
        self.hull = hull  # optional MemoryHull (Addendum A §7.14.1); hull ops use the same flags + ledger

    # -- read side ----------------------------------------------------------------------------------
    def _require(self, apply: bool = False) -> None:
        if not _on(self.env, DAEMON_ENV):
            raise PermissionError(f"defrag daemon is disabled (set {DAEMON_ENV}=1)")
        if apply and not _on(self.env, APPLY_ENV):
            raise PermissionError(f"defrag apply is disabled; dry-run only (set {APPLY_ENV}=1 to apply)")

    def _records(self) -> list[dict[str, Any]]:
        with sqlite3.connect(self.registry.path) as connection:
            rows = connection.execute("SELECT crystal_id, updated_at FROM coding_crystals ORDER BY crystal_id").fetchall()
        out = []
        for crystal_id, updated_at in rows:
            try:
                record = self.registry.get(crystal_id)
            except (LookupError, ValueError):
                continue  # tampered records are never touched
            record.pop("candidate_object", None)
            record["_updated_at"] = float(updated_at)
            out.append(record)
        return out

    def plan(self) -> dict[str, Any]:
        self._require()
        records = self._records()
        now = self.clock()
        by_key: dict[str, list[dict[str, Any]]] = {}
        for record in records:
            if record["status"] in SERVED:
                by_key.setdefault(program_key(record["candidate"]), []).append(record)
        rank = lambda r: (-int(r.get("reuse_count") or 0), r["_updated_at"], r["crystal_id"])  # noqa: E731
        dupes, superseded = [], set()
        for group in by_key.values():
            group.sort(key=rank)
            for loser in group[1:]:
                dupes.append({"keep": group[0]["crystal_id"], "supersede": loser["crystal_id"],
                              "reason": "identical_program"})
                superseded.add(loser["crystal_id"])
        live = sorted((r for r in records if r["status"] in SERVED and r["crystal_id"] not in superseded), key=rank)
        nominations, taken = [], set()
        for i, keep in enumerate(live):
            if keep["crystal_id"] in taken:
                continue
            for other in live[i + 1:]:
                if other["crystal_id"] in taken or other["task_family"] != keep["task_family"]:
                    continue
                score = jaccard(keep["candidate"], other["candidate"])
                if score >= self.near_threshold:
                    nominations.append({"keep": keep["crystal_id"], "candidate": other["crystal_id"],
                                        "similarity": round(score, 4), "granted": False,
                                        "requires": "merge_verifier proof (passed + evidence_digest)"})
                    taken.add(other["crystal_id"])
        stale = []
        for record in records:
            if record["status"] not in RETIRABLE or record["crystal_id"] in superseded:
                continue
            last = max([record["_updated_at"]] + [float(u.get("at") or 0) for u in record.get("reuses") or ()])
            window = self.promoted_stale_after_s if record["status"] == "promoted" else self.stale_after_s
            if now - last > window:
                stale.append({"crystal_id": record["crystal_id"], "status": record["status"],
                              "idle_s": round(now - last, 1)})
        return {"dry_run": True, "records": len(records), "exact_duplicates": dupes,
                "near_duplicate_nominations": nominations, "stale": stale,
                "claim_boundary": "similarity nominates only; merges need proof; nothing is deleted"}

    # -- ledger --------------------------------------------------------------------------------------
    def ledger_entries(self) -> list[dict[str, Any]]:
        if not self.ledger_path.exists():
            return []
        return [json.loads(line) for line in self.ledger_path.read_text(encoding="utf-8").splitlines() if line]

    def _append(self, entry: dict[str, Any]) -> dict[str, Any]:
        entries = self.ledger_entries()
        entry = {"seq": len(entries), "prev_hash": entries[-1]["hash"] if entries else "", "at": self.clock(), **entry}
        entry["hash"] = _sha(entry)
        entry["receipt_id"] = "defrag:" + entry["hash"][7:31]
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with self.ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    def verify_ledger(self) -> dict[str, Any]:
        prev = ""
        for index, entry in enumerate(self.ledger_entries()):
            body = {k: v for k, v in entry.items() if k not in {"hash", "receipt_id"}}
            if entry.get("seq") != index or entry.get("prev_hash") != prev or _sha(body) != entry.get("hash"):
                return {"valid": False, "broken_at": index}
            prev = entry["hash"]
        return {"valid": True, "entries": len(self.ledger_entries())}

    # -- write side -----------------------------------------------------------------------------------
    def _admit(self, action: str, targets: list[str]) -> Any:
        from app.kernel.governance.governor_spine import Episode, Proposal

        proposal = Proposal(kind="eviction", lane="background", tool_id=f"defrag:{action}",
                            targets=tuple(targets), signature_material={"defrag": action, "targets": sorted(targets)})
        decision = self.governor.admit(Episode(run_id=f"defrag:{action}"), proposal)
        return decision, proposal

    def _overlay(self, crystal_id: str, new_status: str, op: str, detail: Mapping[str, Any],
                 governor_receipt: str) -> dict[str, Any]:
        record = self.registry.get(crystal_id)
        prior = record["status"]
        entry = self._append({"op": op, "crystal_id": crystal_id, "prior_status": prior, "new_status": new_status,
                              "prior_record_digest": record["record_digest"], "governor_receipt_id": governor_receipt,
                              **dict(detail)})
        history = list(record.get("defrag_history") or []) + [entry["receipt_id"]]
        with self.registry._lock:
            self.registry._mutate(crystal_id, status=new_status, defrag_history=history,
                                  defrag={"op": op, "receipt_id": entry["receipt_id"], "prior_status": prior})
        return entry

    def apply(self) -> dict[str, Any]:
        self._require(apply=True)
        plan = self.plan()
        targets = ([d["supersede"] for d in plan["exact_duplicates"]] + [n["candidate"] for n in
                   plan["near_duplicate_nominations"]] + [s["crystal_id"] for s in plan["stale"]])
        decision, proposal = self._admit("apply", targets)

        def run() -> list[dict[str, Any]]:
            receipts = []
            for dupe in plan["exact_duplicates"]:
                receipts.append(self._overlay(dupe["supersede"], "superseded", "supersede_exact",
                                              {"superseded_by": dupe["keep"], "proof": {"kind": "identical_program"}},
                                              decision.receipt_id))
            for nom in plan["near_duplicate_nominations"]:
                proof = self.merge_verifier(nom["keep"], nom["candidate"]) if self.merge_verifier else None
                proof = dict(proof or {})
                if proof.get("passed") is True and str(proof.get("evidence_digest") or "").startswith("sha256:"):
                    receipts.append(self._overlay(nom["candidate"], "superseded", "merge_near_duplicate",
                                                  {"superseded_by": nom["keep"], "similarity": nom["similarity"],
                                                   "proof": proof}, decision.receipt_id))
            for item in plan["stale"]:
                receipts.append(self._overlay(item["crystal_id"], "retired_stale", "retire_stale",
                                              {"idle_s": item["idle_s"]}, decision.receipt_id))
            return receipts

        receipts = self.governor.run_admitted(decision, proposal, run)
        return {"dry_run": False, "plan": plan, "receipts": receipts,
                "governor": {"outcome": decision.outcome, "receipt_id": decision.receipt_id}}

    def undo(self, receipt_id: str) -> dict[str, Any]:
        self._require(apply=True)
        entries = self.ledger_entries()
        target = next((e for e in entries if e.get("receipt_id") == receipt_id and e["op"] != "undo"), None)
        if target is None or any(e["op"] == "undo" and e.get("undoes") == receipt_id for e in entries):
            raise LookupError(f"no undoable defrag receipt {receipt_id}")
        if target["op"] == "hull_quarantine":
            return self._undo_hull(target)
        if target["op"].startswith("hull_"):
            raise LookupError(f"defrag receipt {receipt_id} ({target['op']}) is not undoable")
        record = self.registry.get(target["crystal_id"])
        if record["status"] != target["new_status"]:
            raise PermissionError("crystal changed since the defrag receipt; refusing blind undo")
        entry = self._append({"op": "undo", "undoes": receipt_id, "crystal_id": target["crystal_id"],
                              "prior_status": record["status"], "new_status": target["prior_status"]})
        with self.registry._lock:
            self.registry._mutate(target["crystal_id"], status=target["prior_status"], defrag=None,
                                  defrag_history=list(record.get("defrag_history") or []) + [entry["receipt_id"]])
        return entry

    # -- memory hull (Addendum A §7.14.1) -----------------------------------------------------------
    def _hull(self) -> Any:
        if self.hull is None:
            raise LookupError("no memory hull attached to this defrag daemon")
        return self.hull

    def plan_hull(self) -> dict[str, Any]:
        """Dry run: verify every sidecar, find exact-duplicate residue and index drift. Mutates nothing."""
        self._require()
        hull = self._hull()
        from app.kernel.storage.memory_hull import VAULT_SECTIONS

        verified, failed, groups, on_disk = [], [], {}, set()
        for section in VAULT_SECTIONS:
            for sidecar in sorted((hull.root / section).glob("*.residue.json")):
                check = hull.verify_sidecar(sidecar)
                try:
                    payload = json.loads(sidecar.read_text(encoding="utf-8")).get("payload") or {}
                except (OSError, json.JSONDecodeError):
                    payload = {}
                rid = str(payload.get("residue_id") or sidecar.name[: -len(".residue.json")])
                on_disk.add(rid)
                if not check.get("verified"):
                    # The vault is operator-editable: a failed seal may be an intended edit. Report, never move.
                    failed.append({"residue_id": rid, "section": section, "seal_verified":
                                   bool((check.get("seal") or {}).get("verified")),
                                   "markdown_hash_valid": bool(check.get("markdown_hash_valid")),
                                   "action": "operator_review_or_reseal"})
                    continue
                verified.append(rid)
                key = _sha({k: v for k, v in payload.items() if k not in HULL_VOLATILE})
                groups.setdefault(key, []).append((str(payload.get("created_at") or ""), rid, section))
        dupes = []
        for members in groups.values():
            members.sort()
            for _created, rid, section in members[1:]:
                dupes.append({"keep": members[0][1], "quarantine": rid, "section": section,
                              "reason": "identical_residue_content"})
        indexed = {str(r.get("residue_id")) for r in hull._read_index().get("records", [])}
        drift = {"unindexed": sorted(on_disk - indexed), "missing_files": sorted(indexed - on_disk)}
        orphans = sorted(str(p.relative_to(hull.root)) for section in VAULT_SECTIONS
                         for p in (hull.root / section).glob("*.md")
                         if not p.with_name(p.name[:-3] + ".residue.json").exists())
        return {"dry_run": True, "root": str(hull.root), "verified": len(verified), "exact_duplicates": dupes,
                "review_failed": failed, "index_drift": drift, "orphan_markdown": orphans,
                "claim_boundary": "duplicates are quarantined reversibly under .defrag/; failed seals and orphan "
                                  "markdown are reported for the operator; nothing is deleted"}

    def apply_hull(self) -> dict[str, Any]:
        self._require(apply=True)
        hull = self._hull()
        plan = self.plan_hull()
        targets = [d["quarantine"] for d in plan["exact_duplicates"]]
        decision, proposal = self._admit("hull_apply", targets or [str(hull.root)])

        def run() -> list[dict[str, Any]]:
            receipts = []
            for dupe in plan["exact_duplicates"]:
                receipts.append(self._quarantine_residue(hull, dupe, decision.receipt_id))
            if receipts or plan["index_drift"]["unindexed"] or plan["index_drift"]["missing_files"]:
                receipts.append(self._reindex(hull, "hull_reindex", decision.receipt_id))
            return receipts

        receipts = self.governor.run_admitted(decision, proposal, run)
        return {"dry_run": False, "plan": plan, "receipts": receipts,
                "governor": {"outcome": decision.outcome, "receipt_id": decision.receipt_id}}

    @staticmethod
    def _file_sha(path: Path) -> str:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

    def _quarantine_residue(self, hull: Any, dupe: Mapping[str, Any], governor_receipt: str) -> dict[str, Any]:
        rid, section = dupe["quarantine"], dupe["section"]
        bucket = Path(HULL_QUARANTINE) / f"{int(self.clock() * 1e6)}-{rid}"
        files = []
        for suffix in (".md", ".residue.json"):
            source = hull._contained_path(hull.root / section / f"{rid}{suffix}")
            if not source.exists():
                continue
            rel = source.relative_to(hull.root)
            dest = hull.root / bucket / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            files.append({"original": str(rel), "quarantined": str(bucket / rel), "sha256": self._file_sha(source)})
            shutil.move(str(source), str(dest))
        return self._append({"op": "hull_quarantine", "crystal_id": "", "residue_id": rid, "section": section,
                             "kept": dupe["keep"], "reason": dupe["reason"], "files": files,
                             "governor_receipt_id": governor_receipt})

    def _reindex(self, hull: Any, op: str, governor_receipt: str, **detail: Any) -> dict[str, Any]:
        before = hull._read_index()
        after = hull.rebuild_index()
        return self._append({"op": op, "crystal_id": "", "index_sha256_before": before.get("index_sha256", ""),
                             "index_sha256_after": after["index_sha256"], "records_before":
                             len(before.get("records", [])), "records_after": after["record_count"],
                             "governor_receipt_id": governor_receipt, **detail})

    def _undo_hull(self, target: Mapping[str, Any]) -> dict[str, Any]:
        hull = self._hull()
        for f in target["files"]:
            held = hull._contained_path(hull.root / f["quarantined"])
            if not held.exists() or self._file_sha(held) != f["sha256"]:
                raise PermissionError("quarantined residue changed since the defrag receipt; refusing blind undo")
            if (hull.root / f["original"]).exists():
                raise PermissionError(f"{f['original']} exists again; refusing to overwrite")
        decision, proposal = self._admit("hull_undo", [target["residue_id"]])

        def run() -> dict[str, Any]:
            for f in target["files"]:
                original = hull._contained_path(hull.root / f["original"])
                original.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(hull.root / f["quarantined"]), str(original))
            return self._reindex(hull, "undo", decision.receipt_id, undoes=target["receipt_id"],
                                 residue_id=target["residue_id"], files=target["files"])

        return self.governor.run_admitted(decision, proposal, run)


    def compact(self) -> dict[str, Any]:
        self._require(apply=True)
        path = Path(self.registry.path)
        decision, proposal = self._admit("compact", [str(path)])

        def run() -> dict[str, Any]:
            def rows() -> int:
                with sqlite3.connect(path) as connection:
                    return sum(connection.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: S608
                               for t in ("coding_crystals", "coding_crystal_negatives"))
            before_rows, before_bytes = rows(), path.stat().st_size
            connection = sqlite3.connect(path)
            try:
                connection.execute("VACUUM")
            finally:
                connection.close()
            out = {"path": str(path), "rows_before": before_rows, "rows_after": rows(),
                   "bytes_before": before_bytes, "bytes_after": path.stat().st_size, "deleted_rows": 0}
            self._append({"op": "compact", "crystal_id": "", **out, "governor_receipt_id": decision.receipt_id})
            return out

        return self.governor.run_admitted(decision, proposal, run)


__all__ = ["APPLY_ENV", "DAEMON_ENV", "HULL_QUARANTINE", "DefragDaemon", "jaccard", "program_key"]
