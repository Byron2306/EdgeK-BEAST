"""Contextual, privacy-safe commons for tool and skill capability evidence."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.kernel.capability_exchange import CapabilityExchange


class MetaToolCommons:
    """Aggregate shared priors while reserving adoption for local policy."""

    ALLOWED_KINDS = {"tool", "skill", "meta_tool", "meta_tool_recipe", "skill_recipe"}

    def __init__(
        self,
        *,
        db_path: Optional[str] = None,
        exchange: Optional[CapabilityExchange] = None,
        skill_registry: Any = None,
        contributor_sample_cap: int = 3,
    ) -> None:
        root = Path(__file__).resolve().parents[2]
        self.db_path = Path(db_path) if db_path else root / ".beast" / "meta_tool_commons.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.exchange = exchange or CapabilityExchange()
        self.skill_registry = skill_registry
        self.contributor_sample_cap = max(1, int(contributor_sample_cap))
        self._ensure_tables()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS commons_evidence (
                    evidence_hash TEXT PRIMARY KEY,
                    capability_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    capability_version TEXT NOT NULL,
                    schema_hash TEXT NOT NULL,
                    task_class TEXT NOT NULL,
                    role TEXT NOT NULL,
                    contributor TEXT NOT NULL,
                    envelope_json TEXT NOT NULL,
                    ingested_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_commons_evidence_context
                    ON commons_evidence(task_class, role, capability_id, schema_hash);
                CREATE TABLE IF NOT EXISTS commons_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    schema_hash TEXT NOT NULL,
                    task_class TEXT NOT NULL,
                    role TEXT NOT NULL,
                    risk_class TEXT NOT NULL,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    candidate_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS commons_adoptions (
                    candidate_id TEXT PRIMARY KEY,
                    decision TEXT NOT NULL,
                    approved_by TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    adopted_skill_id TEXT,
                    decided_at TEXT NOT NULL
                );
                """
            )

    def ingest(self, envelopes: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        accepted = 0
        duplicates = 0
        rejected: List[Dict[str, str]] = []
        with self._connect() as conn:
            for envelope in envelopes:
                validation = self.exchange.validate(envelope)
                if not validation["valid"]:
                    rejected.append({"evidence_hash": str(envelope.get("evidence_hash") or ""), "reason": validation["reason"]})
                    continue
                cap = envelope.get("capability") or {}
                context = envelope.get("context") or {}
                cursor = conn.execute(
                    """INSERT OR IGNORE INTO commons_evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        envelope["evidence_hash"], str(cap.get("capability_id")), str(cap.get("kind") or "tool"),
                        str(cap.get("version") or "unknown"), str(cap.get("schema_hash")),
                        str(context.get("task_class") or "general"), str(context.get("role") or "general"),
                        str(envelope.get("contributor") or "anonymous"), json.dumps(envelope, sort_keys=True), self._now(),
                    ),
                )
                if cursor.rowcount:
                    accepted += 1
                else:
                    duplicates += 1
        return {
            "beast_object_type": "meta_tool_commons_ingest",
            "accepted": accepted,
            "duplicates": duplicates,
            "rejected": rejected,
            "privacy_policy": "allowlisted_capability_evidence_only",
        }

    def ingest_swarm_runs(self, runs: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        """Convert local swarm traces into Commons priors without leaking task text.

        Swarm runs carry objectives and workspace context, so this adapter emits
        only role/profile/task-class/outcome economics. The envelope hash still
        gives Commons something stable to dedupe and rank.
        """
        envelopes: List[Dict[str, Any]] = []
        skipped = 0
        for run in runs:
            if not isinstance(run, dict):
                skipped += 1
                continue
            task_class = str(run.get("task_type") or "general")[:120]
            status = str(run.get("status") or run.get("state") or "unknown")[:40]
            risk_class = str(run.get("risk_level") or "unknown")[:20]
            state = str(run.get("state") or "")
            metadata = run.get("metadata") if isinstance(run.get("metadata"), dict) else {}
            profile = self._normalize_swarm_profile(metadata)
            value = run.get("value") if isinstance(run.get("value"), dict) else {}
            gates = run.get("gates") if isinstance(run.get("gates"), list) else []
            blocked = state == "blocked" or status in {"blocked", "approval_required"}
            safe = not any(str(gate.get("decision") or "") == "block" for gate in gates if isinstance(gate, dict))
            plan = run.get("plan") if isinstance(run.get("plan"), list) else []
            if not plan:
                plan = [{"role": "swarm", "action": status or "observed"}]
            for item in plan[:16]:
                if not isinstance(item, dict):
                    skipped += 1
                    continue
                role = str(item.get("role") or "swarm")[:120]
                action = str(item.get("action") or "observe")[:120]
                capability_id = f"swarm:{profile}:{role}:{action}"
                try:
                    envelope = self.exchange.prepare(
                        {
                            "capability_id": capability_id,
                            "kind": "skill",
                            "version": "swarm-role-v1",
                            "risk_class": risk_class,
                        },
                        {
                            "task_class": task_class,
                            "role": role,
                            "verified": status in {"ready", "succeeded", "completed"} or state == "completed",
                            "useful": not blocked,
                            "hidden_clean": profile in {"openclaw", "hermes", "zeroclaw"},
                            "rescued": status in {"ready", "succeeded"} and bool(value),
                            "safe": safe,
                            "status": status,
                            "tokens": int(float(value.get("tokens_saved") or value.get("tokens") or 0)),
                            "cost_usd": float(value.get("cost_saved_usd") or value.get("cost_usd") or 0.0),
                            "latency_ms": 0,
                            "evidence_scope": "local",
                        },
                    )
                    envelope["created_at"] = str(run.get("updated_at") or run.get("created_at") or "unknown")
                    envelope["swarm_trace"] = {
                        "run_hash": "sha256:" + hashlib.sha256(str(run.get("run_id") or "").encode()).hexdigest(),
                        "profile": profile[:80],
                        "role_action_hash": "sha256:" + hashlib.sha256(f"{role}:{action}".encode()).hexdigest(),
                    }
                    self._seal_envelope(envelope)
                    envelopes.append(envelope)
                except Exception:
                    skipped += 1
        result = self.ingest(envelopes)
        return {
            **result,
            "beast_object_type": "meta_tool_commons_swarm_ingest",
            "source": "local_swarm_runs",
            "prepared": len(envelopes),
            "skipped": skipped,
        }

    def ingest_cli_execution(self, execution: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a BEAST CLI execution result into local Commons evidence."""
        if not isinstance(execution, dict):
            return {
                "beast_object_type": "meta_tool_commons_cli_execution_ingest",
                "accepted": 0,
                "duplicates": 0,
                "rejected": [{"reason": "execution result must be a dictionary"}],
                "prepared": 0,
                "skipped": 1,
            }
        plan = execution.get("plan") if isinstance(execution.get("plan"), dict) else {}
        profile = plan.get("profile") if isinstance(plan.get("profile"), dict) else {}
        mode = str(plan.get("mode") or profile.get("mode") or "openclaw")
        status = str(execution.get("status") or "unknown")
        summary = execution.get("summary") if isinstance(execution.get("summary"), dict) else {}
        actions = plan.get("actions") if isinstance(plan.get("actions"), list) else []
        results = execution.get("results") if isinstance(execution.get("results"), list) else []
        if not actions and results:
            actions = results
        result_by_id = {
            str(item.get("action_id") or item.get("id") or index): item
            for index, item in enumerate(results)
            if isinstance(item, dict)
        }
        envelopes: List[Dict[str, Any]] = []
        skipped = 0
        task_class = str(((plan.get("canon") or {}).get("task_class") if isinstance(plan.get("canon"), dict) else "") or "agentic_cli")[:120]
        plan_hash = str(plan.get("plan_hash") or self._hash_plain(json.dumps(plan, sort_keys=True, default=str)))
        for index, action in enumerate(actions[:32]):
            if not isinstance(action, dict):
                skipped += 1
                continue
            action_id = str(action.get("action_id") or action.get("id") or index)
            matched = result_by_id.get(action_id, {})
            role = str(action.get("role") or action.get("kind") or "cli_action")[:120]
            risk = str(action.get("risk") or profile.get("risk") or "read_only")[:20]
            executed = bool(matched.get("executed"))
            blocked = str(matched.get("reason") or "").lower() in {"approval_required", "zeroclaw_planning_only"} or status == "blocked"
            safe = risk in {"read_only", "low", "none"} or not executed
            capability_id = self._safe_candidate_name(f"cli_{mode}_{role}_{action_id}")
            try:
                envelope = self.exchange.prepare(
                    {
                        "capability_id": capability_id,
                        "kind": "tool",
                        "version": "beast-cli-v1",
                        "risk_class": risk,
                    },
                    {
                        "task_class": task_class,
                        "role": role,
                        "verified": status in {"succeeded", "dry_run"} and not blocked,
                        "useful": not blocked,
                        "hidden_clean": mode in {"openclaw", "zeroclaw", "hermes"},
                        "rescued": executed and status == "succeeded",
                        "safe": safe,
                        "status": status,
                        "tokens": 0,
                        "cost_usd": 0.0,
                        "latency_ms": float(summary.get("latency_ms") or 0.0),
                        "evidence_scope": "local",
                    },
                )
                envelope["created_at"] = str(plan.get("created_at") or self._now())
                envelope["cli_trace"] = {
                    "plan_hash": plan_hash,
                    "mode": mode[:80],
                    "action_hash": "sha256:" + hashlib.sha256(action_id.encode()).hexdigest(),
                    "executed": executed,
                    "dry_run": status == "dry_run",
                }
                self._seal_envelope(envelope)
                envelopes.append(envelope)
            except Exception:
                skipped += 1
        result = self.ingest(envelopes)
        return {
            **result,
            "beast_object_type": "meta_tool_commons_cli_execution_ingest",
            "source": "beast_cli_execution",
            "mode": mode,
            "prepared": len(envelopes),
            "skipped": skipped,
        }

    def ingest_ollama_calibration(self, scout: Dict[str, Any], verifier: Dict[str, Any]) -> Dict[str, Any]:
        """Record whether a local Ollama scout decision matched verifier outcome."""
        if not isinstance(scout, dict) or not isinstance(verifier, dict):
            return {
                "beast_object_type": "meta_tool_commons_ollama_calibration",
                "accepted": 0,
                "duplicates": 0,
                "rejected": [{"reason": "scout and verifier must be dictionaries"}],
                "prepared": 0,
                "skipped": 1,
            }
        contract = scout.get("decision_contract") if isinstance(scout.get("decision_contract"), dict) else {}
        packet = scout.get("packet") if isinstance(scout.get("packet"), dict) else scout
        analysis = packet.get("local_analysis") if isinstance(packet.get("local_analysis"), dict) else {}
        task_envelope = packet.get("task_envelope") if isinstance(packet.get("task_envelope"), dict) else {}
        task_class = str(
            contract.get("task_type")
            or analysis.get("task_type")
            or task_envelope.get("task_class")
            or verifier.get("task_class")
            or "ollama_scout"
        )[:120]
        risk = str(contract.get("risk") or analysis.get("risk") or verifier.get("risk") or "unknown")[:20]
        source = str(contract.get("source") or analysis.get("source") or "ollama_scout")[:80]
        confidence = float(contract.get("confidence") or analysis.get("confidence") or 0.0)
        status = str(verifier.get("status") or "unknown")[:40]
        verified = bool(verifier.get("verified") or verifier.get("passed") or status in {"passed", "success", "succeeded", "verified"})
        safe = bool(verifier.get("safe", True))
        useful = verified and safe and confidence >= float(verifier.get("min_confidence") or 0.0)
        capability_id = self._safe_candidate_name(f"ollama_scout_{source}_{task_class}_{risk}")
        try:
            envelope = self.exchange.prepare(
                {
                    "capability_id": capability_id,
                    "kind": "tool",
                    "version": "ollama-scout-calibration-v1",
                    "risk_class": risk,
                },
                {
                    "task_class": task_class,
                    "role": "ollama_scout",
                    "verified": verified,
                    "useful": useful,
                    "hidden_clean": True,
                    "rescued": bool(verifier.get("rescued", False)),
                    "safe": safe,
                    "status": status,
                    "tokens": 0,
                    "cost_usd": 0.0,
                    "latency_ms": float(verifier.get("latency_ms") or 0.0),
                    "evidence_scope": "local",
                },
            )
            scout_fingerprint = {
                "source": source,
                "task_class": task_class,
                "risk": risk,
                "confidence_bucket": round(confidence, 1),
                "needs_cloud": bool(contract.get("needs_cloud") or analysis.get("needs_cloud")),
                "privacy_level": str(contract.get("privacy_level") or analysis.get("privacy_level") or "unknown")[:40],
            }
            verifier_fingerprint = {
                "status": status,
                "verified": verified,
                "safe": safe,
                "verifier": str(verifier.get("verifier") or "local_verifier")[:80],
            }
            envelope["created_at"] = str(verifier.get("created_at") or self._now())
            envelope["ollama_calibration"] = {
                "scout_hash": self._hash_plain(json.dumps(scout_fingerprint, sort_keys=True)),
                "verifier_hash": self._hash_plain(json.dumps(verifier_fingerprint, sort_keys=True)),
                "confidence_bucket": scout_fingerprint["confidence_bucket"],
                "matched_verifier": verified,
            }
            self._seal_envelope(envelope)
        except Exception as exc:
            return {
                "beast_object_type": "meta_tool_commons_ollama_calibration",
                "accepted": 0,
                "duplicates": 0,
                "rejected": [{"reason": str(exc)}],
                "prepared": 0,
                "skipped": 1,
            }
        result = self.ingest([envelope])
        return {
            **result,
            "beast_object_type": "meta_tool_commons_ollama_calibration",
            "source": "ollama_scout_verifier",
            "prepared": 1,
            "confidence_bucket": envelope["ollama_calibration"]["confidence_bucket"],
            "matched_verifier": verified,
        }

    def ingest_kv_cache_evidence(self, stats: Dict[str, Any], result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Record KV/cache transport reuse as local Commons evidence."""
        result = result if isinstance(result, dict) else {}
        stats = stats if isinstance(stats, dict) else {}
        total_blocks = int(stats.get("total_blocks") or 0)
        operations = int(stats.get("operations_logged") or result.get("operations_logged") or 0)
        if total_blocks <= 0 and operations <= 0 and not result:
            return {
                "beast_object_type": "meta_tool_commons_kv_cache_ingest",
                "source": "kv_cache_transport",
                "accepted": 0,
                "duplicates": 0,
                "rejected": [],
                "prepared": 0,
                "skipped": 1,
                "reason": "no kv/cache blocks or operations available",
            }

        engine_counts = stats.get("blocks_by_engine") if isinstance(stats.get("blocks_by_engine"), dict) else {}
        location_counts = stats.get("blocks_by_location") if isinstance(stats.get("blocks_by_location"), dict) else {}
        engine = str(result.get("engine") or next(iter(engine_counts.keys()), "unknown"))[:80]
        adapter = str(result.get("adapter") or "kv_cache_transport")[:80]
        looked_up = bool(result.get("looked_up") or operations > 0)
        round_tripped = bool(result.get("payload_round_tripped", looked_up))
        storage_ready = bool(result.get("storage_persisted") or location_counts.get("storage"))
        network_ready = bool(result.get("network_manifest_ready") or location_counts.get("network"))
        useful = looked_up or storage_ready or network_ready or total_blocks > 0
        verified = useful and (round_tripped or operations > 0)
        capability_id = self._safe_candidate_name(f"kv_cache_{engine}_{adapter}")
        try:
            envelope = self.exchange.prepare(
                {
                    "capability_id": capability_id,
                    "kind": "tool",
                    "version": "kv-cache-transport-v1",
                    "risk_class": "low",
                },
                {
                    "task_class": str(result.get("task_class") or "kv_cache_reuse")[:120],
                    "role": "kv_cache_transport",
                    "verified": verified,
                    "useful": useful,
                    "hidden_clean": True,
                    "rescued": bool(result.get("rescued", False)),
                    "safe": True,
                    "status": "ready" if verified else "observed",
                    "tokens": int(result.get("estimated_tokens_saved") or 0),
                    "cost_usd": float(result.get("estimated_cost_saved_usd") or 0.0),
                    "latency_ms": float(result.get("latency_ms") or 0.0),
                    "evidence_scope": "local",
                },
            )
            fingerprint = {
                "engine": engine,
                "adapter": adapter,
                "total_blocks": total_blocks,
                "operations_logged": operations,
                "total_size_bucket": self._bucket_int(int(stats.get("total_size_bytes") or 0)),
                "compressed_blocks": int(stats.get("compressed_blocks") or 0),
                "looked_up": looked_up,
                "storage_ready": storage_ready,
                "network_ready": network_ready,
            }
            envelope["created_at"] = str(result.get("created_at") or self._now())
            envelope["kv_cache_trace"] = {
                "fingerprint_hash": self._hash_plain(json.dumps(fingerprint, sort_keys=True)),
                "engine": engine,
                "adapter": adapter,
                "transport_kind": "cross_engine_kv_cache",
            }
            self._seal_envelope(envelope)
        except Exception as exc:
            return {
                "beast_object_type": "meta_tool_commons_kv_cache_ingest",
                "source": "kv_cache_transport",
                "accepted": 0,
                "duplicates": 0,
                "rejected": [{"reason": str(exc)}],
                "prepared": 0,
                "skipped": 1,
            }
        ingest = self.ingest([envelope])
        return {
            **ingest,
            "beast_object_type": "meta_tool_commons_kv_cache_ingest",
            "source": "kv_cache_transport",
            "prepared": 1,
            "capability_id": capability_id,
            "verified": verified,
            "useful": useful,
        }

    def ingest_discovery_sources(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Stage discovered tools/skills as guarded, schema-pinned hypotheses."""
        payload = payload if isinstance(payload, dict) else {}
        sources = payload.get("sources") if isinstance(payload.get("sources"), list) else []
        stage_candidates = bool(payload.get("stage_candidates", True))
        envelopes: List[Dict[str, Any]] = []
        staged: List[Dict[str, Any]] = []
        skipped: List[Dict[str, str]] = []

        for source_index, source in enumerate(sources[:50]):
            if not isinstance(source, dict):
                skipped.append({"source_index": str(source_index), "reason": "source must be an object"})
                continue
            source_type = self._safe_candidate_name(str(source.get("source_type") or source.get("type") or "unknown"))
            source_id = str(source.get("source_id") or source.get("id") or f"source_{source_index}")[:160]
            trust_level = str(source.get("trust_level") or "unknown")[:40]

            if source_type in {"mcp", "mcp_tool_catalog", "tool_catalog"}:
                items = source.get("items") if isinstance(source.get("items"), list) else source.get("tools")
                built_items = [
                    self._discovery_tool_envelope(source_type, source_id, trust_level, item, item_index)
                    for item_index, item in enumerate(items if isinstance(items, list) else [])
                ]
            elif source_type == "plugin_manifest":
                manifest = source.get("manifest") if isinstance(source.get("manifest"), dict) else source
                built_items = self._discovery_plugin_envelopes(source_id, trust_level, manifest)
            elif source_type in {"retrieval_document", "retrieval", "document"}:
                built_items = self._discovery_retrieval_envelopes(source_id, trust_level, source)
            elif source_type == "skill_manifest":
                items = source.get("items") if isinstance(source.get("items"), list) else source.get("skills")
                built_items = [
                    self._discovery_skill_envelope(source_id, trust_level, item, item_index)
                    for item_index, item in enumerate(items if isinstance(items, list) else [])
                ]
            else:
                skipped.append({"source_id": source_id, "source_type": source_type, "reason": "unsupported_source_type"})
                continue

            for built in built_items:
                if built.get("skip"):
                    skipped.append(built["skip"])
                    continue
                envelopes.append(built["envelope"])
                if stage_candidates:
                    staged.append(self.propose(built["candidate"], source=str(built.get("source") or f"discovery_{source_type}")))

        ingest = self.ingest(envelopes)
        return {
            **ingest,
            "beast_object_type": "meta_tool_commons_discovery_ingest",
            "sources_seen": len(sources[:50]),
            "prepared": len(envelopes),
            "candidates_staged": len(staged),
            "staged": staged[:25],
            "skipped": skipped[:50],
            "discovery_policy": {
                "stores_raw_documents": False,
                "executes_discovered_tools": False,
                "stages_hypotheses_only": True,
                "local_verification_required": True,
            },
            "authority": "discovered_metadata_is_advisory_until_local_verification",
        }

    def _discovery_tool_envelope(
        self,
        source_type: str,
        source_id: str,
        trust_level: str,
        item: Any,
        item_index: int,
    ) -> Dict[str, Any]:
        if not isinstance(item, dict):
            return {"skip": {"source_id": source_id, "item_index": str(item_index), "reason": "item must be an object"}}
        name = self._safe_candidate_name(str(item.get("tool_id") or item.get("name") or f"tool_{item_index}"))
        description = str(item.get("description") or "")[:500]
        risk_class = self._normalize_risk_class(item.get("risk_class") or item.get("risk") or "medium")
        if self._blocked_discovery_text(name, description, item.get("category")):
            return {"skip": {"source_id": source_id, "item_index": str(item_index), "capability": name, "reason": "blocked_dangerous_capability"}}
        if risk_class in {"critical", "prohibited"}:
            return {"skip": {"source_id": source_id, "item_index": str(item_index), "capability": name, "reason": "blocked_high_risk_discovery"}}

        schema_hash = str(item.get("tool_schema_hash") or item.get("schema_hash") or "")
        if not schema_hash.startswith("sha256:"):
            schema_hash = self._hash_json({
                "name": name,
                "description": description,
                "inputSchema": item.get("inputSchema") or item.get("input_schema") or {},
            })
        task_class = self._safe_task_class(item.get("task_class") or item.get("category") or "tool_discovery")
        role = self._safe_task_class(item.get("role") or "tool_selector")
        capability_id = f"{source_type}:{name}"
        envelope = self._prepare_discovery_envelope(
            capability_id=capability_id,
            kind="tool",
            version=str(item.get("version") or "discovered-v1"),
            schema_hash=schema_hash,
            risk_class=risk_class,
            task_class=task_class,
            role=role,
            source_type=source_type,
            source_id=source_id,
            trust_level=trust_level,
            source_payload={"name": name, "description": description, "schema_hash": schema_hash},
        )
        candidate = {
            "kind": "meta_tool_recipe",
            "name": f"{name}_binding",
            "version": "discovered-v1",
            "schema_hash": schema_hash,
            "task_class": task_class,
            "role": role,
            "risk_class": risk_class,
            "pattern": {"source_type": source_type, "capability_id": capability_id, "trust_level": trust_level},
            "action": {
                "type": "external_tool_binding",
                "capability_id": capability_id,
                "schema_hash": schema_hash,
                "execution_policy": "verify_before_use",
            },
            "evidence_hashes": [envelope["evidence_hash"]],
        }
        return {"envelope": envelope, "candidate": candidate}

    def _discovery_plugin_envelopes(self, source_id: str, trust_level: str, manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
        try:
            from app.kernel.plugin_marketplace import PluginMarketplace

            marketplace = PluginMarketplace()
            prepared = marketplace.prepare(manifest if isinstance(manifest, dict) else {})
            validation = marketplace.validate(prepared)
        except Exception as exc:
            return [{"skip": {"source_id": source_id, "reason": f"plugin_validation_unavailable:{exc}"}}]
        if not validation.get("valid"):
            return [{"skip": {"source_id": source_id, "reason": "plugin_manifest_invalid"}}]
        risk_class = self._normalize_risk_class(prepared.get("risk_class") or "medium")
        if risk_class in {"critical", "prohibited"}:
            return [{"skip": {"source_id": source_id, "reason": "blocked_high_risk_discovery"}}]

        plugin_id = self._safe_candidate_name(str(prepared.get("id") or source_id))
        built: List[Dict[str, Any]] = []
        for index, tool in enumerate(prepared.get("tools") or []):
            tool_dict = tool if isinstance(tool, dict) else {}
            item = {
                **tool_dict,
                "tool_id": f"{plugin_id}_{tool_dict.get('name') or index}",
                "task_class": "plugin_tool",
                "role": "plugin_selector",
                "risk_class": risk_class,
                "tool_schema_hash": tool_dict.get("tool_schema_hash") or "",
            }
            result = self._discovery_tool_envelope("plugin", source_id, trust_level, item, index)
            if "candidate" in result:
                result["candidate"]["action"].update({
                    "type": "plugin_tool_binding",
                    "plugin_id": plugin_id,
                    "tool_name": str(tool_dict.get("name") or index)[:120],
                    "execution_policy": "install_and_verify_before_use",
                })
                result["source"] = "discovery_plugin_manifest"
            built.append(result)
        return built

    def _discovery_retrieval_envelopes(self, source_id: str, trust_level: str, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        docs = source.get("documents") if isinstance(source.get("documents"), list) else [source]
        built: List[Dict[str, Any]] = []
        for doc_index, doc in enumerate(docs[:50]):
            if not isinstance(doc, dict):
                built.append({"skip": {"source_id": source_id, "reason": "document must be an object"}})
                continue
            capabilities = doc.get("capabilities") if isinstance(doc.get("capabilities"), list) else []
            doc_hash = self._hash_json({
                "title": str(doc.get("title") or "")[:240],
                "url": str(doc.get("url") or "")[:500],
                "summary": str(doc.get("summary") or "")[:1000],
            })
            for cap_index, cap in enumerate(capabilities[:25]):
                if not isinstance(cap, dict):
                    built.append({"skip": {"source_id": source_id, "reason": "capability must be an object"}})
                    continue
                cap_item = {
                    **cap,
                    "tool_id": cap.get("capability_id") or cap.get("name") or f"retrieved_capability_{doc_index}_{cap_index}",
                    "category": cap.get("task_class") or "retrieval_discovery",
                    "role": cap.get("role") or "knowledge_router",
                    "risk_class": cap.get("risk_class") or "medium",
                }
                result = self._discovery_tool_envelope("retrieval", source_id, trust_level, cap_item, cap_index)
                if "envelope" in result:
                    result["envelope"]["discovery_trace"]["document_hash"] = doc_hash
                    self._seal_envelope(result["envelope"])
                if "candidate" in result:
                    result["candidate"]["pattern"]["document_hash"] = doc_hash
                    result["candidate"]["action"]["type"] = "retrieved_capability_recipe"
                    result["source"] = "discovery_retrieval_document"
                built.append(result)
        return built

    def _discovery_skill_envelope(self, source_id: str, trust_level: str, item: Any, item_index: int) -> Dict[str, Any]:
        built = self._discovery_tool_envelope("skill_manifest", source_id, trust_level, item, item_index)
        if "candidate" in built:
            built["candidate"]["kind"] = "skill_recipe"
            built["candidate"]["action"] = {
                "type": "skill_recipe_binding",
                "capability_id": built["candidate"]["action"]["capability_id"],
                "schema_hash": built["candidate"]["schema_hash"],
                "execution_policy": "verify_before_use",
            }
            built["envelope"]["capability"]["kind"] = "skill"
            self._seal_envelope(built["envelope"])
            built["source"] = "discovery_skill_manifest"
        return built

    def _prepare_discovery_envelope(
        self,
        *,
        capability_id: str,
        kind: str,
        version: str,
        schema_hash: str,
        risk_class: str,
        task_class: str,
        role: str,
        source_type: str,
        source_id: str,
        trust_level: str,
        source_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        envelope = self.exchange.prepare(
            {
                "capability_id": capability_id[:180],
                "kind": kind,
                "version": version[:80],
                "schema_hash": schema_hash,
                "risk_class": risk_class,
            },
            {
                "task_class": task_class,
                "role": role,
                "verified": False,
                "useful": True,
                "hidden_clean": False,
                "safe": risk_class in {"low", "medium"},
                "status": "discovered_unverified",
                "tokens": 0,
                "cost_usd": 0.0,
                "latency_ms": 0,
                "evidence_scope": "local",
            },
        )
        envelope["discovery_trace"] = {
            "source_type": source_type[:80],
            "source_id_hash": self._hash_plain(source_id),
            "trust_level": trust_level[:40],
            "source_payload_hash": self._hash_json(source_payload),
            "raw_content_stored": False,
            "verified": False,
        }
        self._seal_envelope(envelope)
        return envelope

    def _seal_envelope(self, envelope: Dict[str, Any]) -> None:
        canonical_source = dict(envelope)
        canonical_source.pop("evidence_hash", None)
        canonical_source.pop("signature", None)
        canonical = json.dumps(canonical_source, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        envelope["evidence_hash"] = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
        signing_key = getattr(self.exchange, "signing_key", "")
        envelope["signature"] = (
            "hmac-sha256:" + hmac.new(signing_key.encode(), canonical.encode(), hashlib.sha256).hexdigest()
            if signing_key else "unsigned"
        )

    @staticmethod
    def _hash_plain(value: str) -> str:
        return "sha256:" + hashlib.sha256(str(value).encode()).hexdigest()

    @staticmethod
    def _hash_json(value: Any) -> str:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()

    @staticmethod
    def _normalize_risk_class(value: Any) -> str:
        risk = str(value or "medium").lower().strip()
        aliases = {"read_only": "low", "readonly": "low", "safe": "low", "dangerous": "critical"}
        risk = aliases.get(risk, risk)
        return risk if risk in {"low", "medium", "high", "critical", "prohibited"} else "medium"

    @classmethod
    def _safe_task_class(cls, value: Any) -> str:
        return cls._safe_candidate_name(str(value or "general"))[:120]

    @staticmethod
    def _blocked_discovery_text(*values: Any) -> bool:
        text = " ".join(str(value or "").lower() for value in values)
        blocked_terms = (
            "credential theft", "steal credentials", "password dump", "reverse shell",
            "persistence implant", "evasion", "exfiltrate", "exfiltration",
            "exploit chain", "malware", "ransomware",
        )
        return any(term in text for term in blocked_terms)

    def rank(self, *, task_class: Optional[str] = None, role: Optional[str] = None, kind: Optional[str] = None, limit: int = 25) -> Dict[str, Any]:
        clauses: List[str] = []
        values: List[Any] = []
        for column, value in (("task_class", task_class), ("role", role), ("kind", kind)):
            if value:
                clauses.append(f"{column} = ?")
                values.append(value)
        query = "SELECT envelope_json, contributor, capability_id, schema_hash, task_class, role FROM commons_evidence"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY ingested_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, values).fetchall()

        # A single contributor may inform a prior, but cannot flood it.
        counts: Dict[tuple[str, ...], int] = {}
        evidence: List[Dict[str, Any]] = []
        suppressed = 0
        for row in rows:
            key = (row["contributor"], row["capability_id"], row["schema_hash"], row["task_class"], row["role"])
            counts[key] = counts.get(key, 0) + 1
            if counts[key] > self.contributor_sample_cap:
                suppressed += 1
                continue
            evidence.append(json.loads(row["envelope_json"]))
        result = self.exchange.rank(evidence, task_class=task_class, role=role)
        result["beast_object_type"] = "meta_tool_commons_ranking"
        result["rankings"] = result["rankings"][: max(1, min(int(limit), 100))]
        result["count"] = len(result["rankings"])
        result["anti_gaming"] = {
            "contributor_sample_cap": self.contributor_sample_cap,
            "suppressed_samples": suppressed,
            "schema_pinning": True,
        }
        result["authority"] = "advisory_global_prior_local_policy_decides"
        return result

    def propose_swarm_candidates(
        self,
        *,
        task_class: Optional[str] = None,
        role: Optional[str] = None,
        min_samples: int = 2,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Stage local skill recipes from repeated safe Commons Swarm evidence."""
        clauses = ["capability_id LIKE 'swarm:%'"]
        values: List[Any] = []
        if task_class:
            clauses.append("task_class = ?")
            values.append(task_class)
        if role:
            clauses.append("role = ?")
            values.append(role)
        query = """
            SELECT envelope_json, capability_id, schema_hash, task_class, role
            FROM commons_evidence
            WHERE """ + " AND ".join(clauses) + """
            ORDER BY ingested_at DESC
        """
        with self._connect() as conn:
            rows = conn.execute(query, values).fetchall()

        groups: Dict[tuple[str, str, str, str], List[Dict[str, Any]]] = {}
        for row in rows:
            key = (row["capability_id"], row["schema_hash"], row["task_class"], row["role"])
            groups.setdefault(key, []).append(json.loads(row["envelope_json"]))

        proposed: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        for (capability_id, schema_hash, group_task_class, group_role), evidence in groups.items():
            if len(proposed) >= max(1, min(int(limit), 100)):
                break
            sample_size = len(evidence)
            if sample_size < max(1, int(min_samples)):
                skipped.append({"capability_id": capability_id, "reason": "below_min_samples", "sample_size": sample_size})
                continue
            verified_rate = self._outcome_rate(evidence, "verified")
            useful_rate = self._outcome_rate(evidence, "useful")
            safe_rate = self._outcome_rate(evidence, "safe")
            if safe_rate < 1.0 or useful_rate < 0.5:
                skipped.append({
                    "capability_id": capability_id,
                    "reason": "quality_gate",
                    "sample_size": sample_size,
                    "useful_rate": useful_rate,
                    "safe_rate": safe_rate,
                })
                continue
            profile, role_name, action_name = self._parse_swarm_capability(capability_id)
            candidate = {
                "kind": "skill_recipe",
                "name": self._safe_candidate_name(f"swarm_{profile}_{role_name}_{action_name}"),
                "version": "1.0",
                "schema_hash": schema_hash,
                "task_class": group_task_class,
                "role": group_role,
                "risk_class": "low" if safe_rate >= 1.0 and verified_rate >= 0.5 else "medium",
                "pattern": {
                    "source": "commons_swarm",
                    "capability_id": capability_id,
                    "task_class": group_task_class,
                    "role": group_role,
                    "sample_size": sample_size,
                    "verified_rate": verified_rate,
                    "useful_rate": useful_rate,
                    "safe_rate": safe_rate,
                },
                "action": {
                    "type": "swarm_role_recipe",
                    "profile": profile,
                    "role": role_name,
                    "action": action_name,
                    "execution_policy": "advisory_until_local_approval",
                    "approval_required": False,
                },
                "evidence_hashes": [str(item.get("evidence_hash")) for item in evidence if item.get("evidence_hash")],
            }
            proposed.append(self.propose(candidate, source="local_swarm_commons"))

        return {
            "beast_object_type": "meta_tool_commons_swarm_candidates",
            "source": "local_swarm_commons",
            "min_samples": max(1, int(min_samples)),
            "proposed_count": len(proposed),
            "skipped_count": len(skipped),
            "proposed": proposed,
            "skipped": skipped[:20],
            "authority": "staged_only_explicit_local_approval_required",
        }

    def propose(self, candidate: Dict[str, Any], *, source: str = "local") -> Dict[str, Any]:
        kind = str(candidate.get("kind") or candidate.get("candidate_type") or "")
        if kind not in self.ALLOWED_KINDS:
            raise ValueError(f"unsupported commons candidate kind: {kind}")
        name = str(candidate.get("name") or candidate.get("candidate_id") or "").strip()
        schema_hash = str(candidate.get("schema_hash") or "").strip()
        if not name or not schema_hash.startswith("sha256:"):
            raise ValueError("candidate name and sha256 schema_hash are required")
        normalized = {
            "kind": kind,
            "name": name,
            "version": str(candidate.get("version") or "1.0")[:80],
            "schema_hash": schema_hash,
            "task_class": str(candidate.get("task_class") or "general")[:120],
            "role": str(candidate.get("role") or "general")[:120],
            "risk_class": str(candidate.get("risk_class") or "medium")[:20],
            "pattern": candidate.get("pattern") or {"task_class": candidate.get("task_class") or "general"},
            "action": candidate.get("action") or candidate.get("promotion_action") or {},
            "evidence_hashes": sorted({str(item) for item in candidate.get("evidence_hashes", []) if item}),
            "source_candidate_id": candidate.get("candidate_id"),
        }
        canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        candidate_id = "commons_" + hashlib.sha256(canonical.encode()).hexdigest()[:20]
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO commons_candidates VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(candidate_id) DO UPDATE SET candidate_json=excluded.candidate_json, updated_at=excluded.updated_at""",
                (candidate_id, kind, name, normalized["version"], schema_hash, normalized["task_class"], normalized["role"],
                 normalized["risk_class"], str(source or "local"), "proposed", json.dumps(normalized, sort_keys=True), now, now),
            )
        return {"candidate_id": candidate_id, "status": "proposed", "candidate": normalized, "auto_adopted": False}

    def adopt(self, candidate_id: str, *, approved: bool = False, dry_run: bool = True, approved_by: str = "user", reason: str = "") -> Dict[str, Any]:
        candidate = self._candidate(candidate_id)
        base = {"candidate_id": candidate_id, "approved": bool(approved), "dry_run": bool(dry_run), "adopted": False}
        if dry_run:
            return {**base, "reason": "dry_run", "candidate": candidate}
        if not approved:
            return {**base, "reason": "explicit local approval required"}
        if not self.skill_registry:
            return {**base, "reason": "local skill registry unavailable"}
        if candidate["risk_class"] in {"critical", "prohibited"}:
            return {**base, "reason": "candidate risk class is not locally adoptable"}
        payload = candidate["candidate"]
        category = "swarm_recipe" if candidate["source"] == "local_swarm_commons" and payload.get("kind") == "skill_recipe" else "meta_tool_commons"
        skill = self.skill_registry.register_skill(
            name=payload["name"], category=category,
            pattern=payload.get("pattern") or {}, action=payload.get("action") or {},
            metadata={
                "commons_candidate_id": candidate_id, "schema_hash": payload["schema_hash"],
                "source": candidate["source"], "approved_by": approved_by,
                "executable_binding": payload.get("action", {}).get("type") if isinstance(payload.get("action"), dict) else "",
            },
        )
        skill_id = str(getattr(skill, "id", ""))
        now = self._now()
        with self._connect() as conn:
            conn.execute("UPDATE commons_candidates SET status='adopted', updated_at=? WHERE candidate_id=?", (now, candidate_id))
            conn.execute(
                """INSERT OR REPLACE INTO commons_adoptions VALUES (?, 'adopted', ?, ?, ?, ?)""",
                (candidate_id, approved_by, reason, skill_id, now),
            )
        return {**base, "adopted": True, "reason": "approved by local policy", "skill_id": skill_id}

    def candidates(self, *, status: Optional[str] = None, source: Optional[str] = None, limit: int = 25) -> Dict[str, Any]:
        clauses: List[str] = []
        values: List[Any] = []
        if status:
            clauses.append("status = ?")
            values.append(status)
        if source:
            clauses.append("source = ?")
            values.append(source)
        query = "SELECT * FROM commons_candidates"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY updated_at DESC LIMIT ?"
        values.append(max(1, min(int(limit), 100)))
        with self._connect() as conn:
            rows = conn.execute(query, values).fetchall()
        candidates = [
            {
                "candidate_id": row["candidate_id"],
                "kind": row["kind"],
                "name": row["name"],
                "version": row["version"],
                "schema_hash": row["schema_hash"],
                "task_class": row["task_class"],
                "role": row["role"],
                "risk_class": row["risk_class"],
                "source": row["source"],
                "status": row["status"],
                "candidate": json.loads(row["candidate_json"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]
        return {
            "beast_object_type": "meta_tool_commons_candidates",
            "candidates": candidates,
            "count": len(candidates),
            "status": status or "all",
            "source": source or "all",
        }

    def evidence_plane(self) -> Dict[str, Any]:
        """Return a privacy-safe rollup across all local reuse evidence bridges."""
        planes: Dict[str, Dict[str, Any]] = {}
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT envelope_json, capability_id, task_class, role, ingested_at FROM commons_evidence ORDER BY ingested_at DESC"
            ).fetchall()
            candidate_rows = conn.execute("SELECT source, status, COUNT(*) FROM commons_candidates GROUP BY source, status").fetchall()
            adoption_rows = conn.execute("SELECT decision, COUNT(*) FROM commons_adoptions GROUP BY decision").fetchall()

        latest_at = ""
        for row in rows:
            try:
                envelope = json.loads(row["envelope_json"])
            except Exception:
                continue
            plane = self._evidence_plane_for(envelope, str(row["capability_id"] or ""))
            bucket = planes.setdefault(plane, {
                "plane": plane,
                "evidence_count": 0,
                "verified_count": 0,
                "useful_count": 0,
                "safe_count": 0,
                "hidden_clean_count": 0,
                "rescued_count": 0,
                "local_scope_count": 0,
                "tokens": 0,
                "cost_usd": 0.0,
                "task_classes": {},
                "roles": {},
                "latest_at": "",
            })
            outcome = envelope.get("outcome") if isinstance(envelope.get("outcome"), dict) else {}
            economics = envelope.get("economics") if isinstance(envelope.get("economics"), dict) else {}
            bucket["evidence_count"] += 1
            bucket["verified_count"] += 1 if outcome.get("verified") else 0
            bucket["useful_count"] += 1 if outcome.get("useful") else 0
            bucket["safe_count"] += 1 if outcome.get("safe") else 0
            bucket["hidden_clean_count"] += 1 if outcome.get("hidden_clean") else 0
            bucket["rescued_count"] += 1 if outcome.get("rescued") else 0
            bucket["local_scope_count"] += 1 if envelope.get("evidence_scope") != "global" else 0
            bucket["tokens"] += int(economics.get("tokens") or 0)
            bucket["cost_usd"] += float(economics.get("cost_usd") or 0.0)
            task_class = str(row["task_class"] or "general")
            role = str(row["role"] or "general")
            bucket["task_classes"][task_class] = bucket["task_classes"].get(task_class, 0) + 1
            bucket["roles"][role] = bucket["roles"].get(role, 0) + 1
            bucket["latest_at"] = max(str(bucket["latest_at"] or ""), str(row["ingested_at"] or ""))
            latest_at = max(latest_at, str(row["ingested_at"] or ""))

        for bucket in planes.values():
            total = max(1, int(bucket["evidence_count"]))
            bucket["verified_rate"] = round(bucket["verified_count"] / total, 6)
            bucket["useful_rate"] = round(bucket["useful_count"] / total, 6)
            bucket["safe_rate"] = round(bucket["safe_count"] / total, 6)
            bucket["hidden_clean_rate"] = round(bucket["hidden_clean_count"] / total, 6)
            bucket["rescued_rate"] = round(bucket["rescued_count"] / total, 6)
            bucket["cost_usd"] = round(float(bucket["cost_usd"]), 8)
            bucket["top_task_classes"] = self._top_counts(bucket.pop("task_classes"))
            bucket["top_roles"] = self._top_counts(bucket.pop("roles"))

        candidate_summary: Dict[str, Dict[str, int]] = {}
        for row in candidate_rows:
            source = str(row[0] or "unknown")
            status = str(row[1] or "unknown")
            candidate_summary.setdefault(source, {})[status] = int(row[2] or 0)
        adoption_summary = {str(row[0] or "unknown"): int(row[1] or 0) for row in adoption_rows}
        ordered_planes = [
            planes[key] for key in ("swarm", "cli", "ollama", "kv_cache", "discovery", "other")
            if key in planes
        ]
        body = {
            "beast_object_type": "meta_tool_commons_evidence_plane",
            "version": "1.0",
            "plane_count": len(ordered_planes),
            "evidence_count": sum(int(item["evidence_count"]) for item in ordered_planes),
            "planes": ordered_planes,
            "candidate_summary": candidate_summary,
            "adoption_summary": adoption_summary,
            "latest_at": latest_at,
            "privacy_policy": "aggregate_counts_and_hashes_only_redacted_inputs",
            "authority": "advisory_local_policy_decides",
        }
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        body["plane_hash"] = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
        return body

    def state(self) -> Dict[str, Any]:
        with self._connect() as conn:
            evidence = conn.execute("SELECT COUNT(*) FROM commons_evidence").fetchone()[0]
            candidates = conn.execute("SELECT COUNT(*) FROM commons_candidates").fetchone()[0]
            adopted = conn.execute("SELECT COUNT(*) FROM commons_adoptions WHERE decision='adopted'").fetchone()[0]
        return {
            "beast_object_type": "meta_tool_commons_state", "version": "1.0",
            "evidence_count": evidence, "candidate_count": candidates, "adopted_count": adopted,
            "ranking_policy": "contextual_global_prior_local_posterior",
            "adoption_policy": "explicit_local_approval_only",
            "universal_leaderboard": False,
        }

    def snapshot(self, *, task_class: Optional[str] = None, role: Optional[str] = None) -> Dict[str, Any]:
        body = {
            "beast_object_type": "meta_tool_commons_snapshot", "version": "1.0",
            "created_at": self._now(), "ranking": self.rank(task_class=task_class, role=role),
            "policy": {"advisory_only": True, "schema_pinned": True, "local_approval_required": True},
        }
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        body["snapshot_hash"] = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
        return body

    def _candidate(self, candidate_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM commons_candidates WHERE candidate_id=?", (candidate_id,)).fetchone()
        if not row:
            raise ValueError(f"commons candidate not found: {candidate_id}")
        return {
            "candidate_id": row["candidate_id"], "kind": row["kind"], "risk_class": row["risk_class"],
            "source": row["source"], "status": row["status"], "candidate": json.loads(row["candidate_json"]),
        }

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _outcome_rate(evidence: List[Dict[str, Any]], key: str) -> float:
        if not evidence:
            return 0.0
        return round(sum(1 for item in evidence if bool((item.get("outcome") or {}).get(key))) / len(evidence), 6)

    @staticmethod
    def _parse_swarm_capability(capability_id: str) -> tuple[str, str, str]:
        parts = str(capability_id).split(":", 3)
        if len(parts) == 4 and parts[0] == "swarm":
            return parts[1] or "swarm", parts[2] or "role", parts[3] or "action"
        return "swarm", "role", str(capability_id or "action")

    @classmethod
    def _normalize_swarm_profile(cls, metadata: Dict[str, Any]) -> str:
        raw = metadata.get("profile") or metadata.get("execution_profile") or "swarm"
        if isinstance(raw, dict):
            raw = raw.get("profile") or raw.get("name") or raw.get("default_execution") or "swarm"
        return cls._safe_candidate_name(str(raw or "swarm")[:80])

    @staticmethod
    def _evidence_plane_for(envelope: Dict[str, Any], capability_id: str) -> str:
        if "swarm_trace" in envelope or capability_id.startswith("swarm:"):
            return "swarm"
        if "cli_trace" in envelope or capability_id.startswith("cli_"):
            return "cli"
        if "ollama_calibration" in envelope or capability_id.startswith("ollama_scout"):
            return "ollama"
        if "kv_cache_trace" in envelope or capability_id.startswith("kv_cache"):
            return "kv_cache"
        if "discovery_trace" in envelope or capability_id.startswith(("mcp_tool_catalog:", "tool_catalog:", "plugin:", "retrieval:", "skill_manifest:")):
            return "discovery"
        return "other"

    @staticmethod
    def _top_counts(counts: Dict[str, int], limit: int = 5) -> List[Dict[str, Any]]:
        return [
            {"name": key, "count": value}
            for key, value in sorted(counts.items(), key=lambda item: (-int(item[1]), str(item[0])))[:limit]
        ]

    @staticmethod
    def _bucket_int(value: int) -> int:
        value = max(0, int(value))
        if value <= 0:
            return 0
        bucket = 1
        while bucket < value:
            bucket *= 2
        return bucket

    @staticmethod
    def _safe_candidate_name(name: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_]+", "_", str(name).lower()).strip("_")
        safe = re.sub(r"_+", "_", safe)
        return (safe or "swarm_skill_recipe")[:96]
