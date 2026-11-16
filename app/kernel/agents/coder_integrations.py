"""Bounded integration coordinator for the Desktop IDE Agent Coder path.

This module does not grant authority.  It invokes existing read-only or
proposal-only integrations before provider handoff and existing sealed
learning integrations after verified completion.  Every attempt becomes one
small, redacted event suitable for SSE, run history, and the Systems Atlas.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
_TRUE = frozenset({"1", "true", "yes", "on", "enabled"})
_METRIC_KEYS = frozenset(
    {
        "hits",
        "records",
        "original_tokens",
        "compressed_tokens",
        "counted_savings_tokens",
        "savings_tokens",
        "savings_ratio",
        "fidelity_passed",
        "verified",
        "eligible",
    }
)


def _is_enabled(environ: Mapping[str, str], flag: str) -> bool:
    return str(environ.get(flag, "")).strip().lower() in _TRUE


def _safe_metrics(values: Mapping[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    combined = {**dict(values or {}), **extra}
    return {
        str(key): value
        for key, value in combined.items()
        if key in _METRIC_KEYS and isinstance(value, (bool, int, float))
    }


class CoderIntegrationCoordinator:
    """Coordinate optional Agent Coder integrations without expanding scope."""

    def __init__(
        self,
        workspace: str | Path,
        *,
        environ: Mapping[str, str] | None = None,
        compression_router: Any = None,
        vector_memory: Any = None,
        memory_hull: Any = None,
        crystal_preflight: Callable[..., Mapping[str, Any]] | None = None,
        family_lookup: Callable[..., Mapping[str, Any] | None] | None = None,
        crystal_status: Callable[..., Mapping[str, Any]] | None = None,
        bus_probe: Callable[..., Mapping[str, Any]] | None = None,
        swarm_selector: Callable[..., Mapping[str, Any]] | None = None,
        crystal_producer: Callable[..., Mapping[str, Any]] | None = None,
    ) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.environ = dict(os.environ if environ is None else environ)
        self.compression_router = compression_router
        self.vector_memory = vector_memory
        self.memory_hull = memory_hull
        self.crystal_preflight = crystal_preflight
        self.family_lookup = family_lookup
        self.crystal_status = crystal_status
        self.bus_probe = bus_probe
        self.swarm_selector = swarm_selector
        self.crystal_producer = crystal_producer
        # Raw advisory snippets are intentionally kept out of returned events
        # and durable evidence.  The caller may attach this bounded in-memory
        # context to the current provider handoff only.
        self.advisory_context: list[dict[str, Any]] = []

    @staticmethod
    def _event(
        capability: str,
        status: str,
        *,
        mode: str,
        reason: str,
        metrics: Mapping[str, Any] | None = None,
        artifacts: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "capability": str(capability),
            "status": status if status in {"fired", "skipped", "failed"} else "failed",
            "mode": str(mode)[:80],
            "reason": str(reason)[:120],
            "metrics": _safe_metrics(metrics),
            "artifacts": {
                str(key): str(value)[:160]
                for key, value in dict(artifacts or {}).items()
                if key in {"receipt_id", "residue_id", "crystal_id", "task_family"}
                and isinstance(value, (str, int))
            },
            "authority": "advisory_or_existing_gate_only",
        }
        event = {"event_type": f"agent.integration.{payload['status']}", "payload": payload}
        logger.info("agent integration %s", json.dumps(event, sort_keys=True, separators=(",", ":")))
        return event

    def _compression(self, objective: str, source: str, diagnostics: str) -> tuple[list[dict[str, Any]], str, str]:
        if not _is_enabled(self.environ, "BEAST_COMPRESSION_TIERS"):
            return [self._event("compression.tiers", "skipped", mode="opt_in", reason="feature_flag_disabled")], source, diagnostics
        router = self.compression_router
        if router is None:
            from app.context.compression_tiers import default_router

            router = default_router()
        events: list[dict[str, Any]] = []

        def invoke(capability: str, tier: str, payload: str, *, query: str = "", kind: str = "test") -> str:
            if not payload:
                events.append(self._event(capability, "skipped", mode="governed_compression", reason="no_eligible_context"))
                return payload
            try:
                output = router.compress(tier, payload, query=query, kind=kind)
                fidelity = output.get("fidelity") if isinstance(output.get("fidelity"), Mapping) else {}
                metrics = output.get("metrics") if isinstance(output.get("metrics"), Mapping) else {}
                governor = output.get("governor") if isinstance(output.get("governor"), Mapping) else {}
                passed = bool(fidelity.get("passed"))
                events.append(
                    self._event(
                        capability,
                        "fired" if passed else "skipped",
                        mode="governed_compression",
                        reason="fidelity_passed" if passed else "fidelity_refused",
                        metrics={**dict(metrics), "fidelity_passed": passed},
                        artifacts={"receipt_id": governor.get("receipt_id", "")},
                    )
                )
                return str(output.get("content") if passed else payload)
            except Exception as exc:  # optional integration containment
                events.append(self._event(capability, "failed", mode="governed_compression", reason=type(exc).__name__))
                return payload

        # RepoRelay is represented by the tested native repo-map tier.  The
        # payload is the workspace path, never source text in the event.
        invoke("compression.reporelay", "repo_map", str(self.workspace), query=objective)
        source = invoke("compression.longcodezip", "longcodezip", source, query=objective)
        diagnostics = invoke("compression.rtk", "rtk", diagnostics, query=objective, kind="test")
        diagnostics = invoke("compression.sqz", "sqz", diagnostics, query=objective, kind="test")
        return events, source, diagnostics

    def _vector_events(self, objective: str) -> list[dict[str, Any]]:
        try:
            fabric = self.vector_memory
            if fabric is None:
                from app.kernel.adapters.vector_memory import VectorMemoryFabric

                fabric = VectorMemoryFabric(self.workspace)
            result = fabric.search(objective, limit=8, purposes=("workspace_source", "verified_skill"))
            hits = int(result.get("result_count") or len(result.get("hits") or []))
            for hit in (result.get("hits") or [])[:4]:
                if not isinstance(hit, Mapping):
                    continue
                content = str(hit.get("content") or "").strip()
                if content:
                    self.advisory_context.append(
                        {
                            "source": "vector_rag",
                            "id": str(hit.get("id") or "")[:120],
                            "score": float(hit.get("score") or 0.0),
                            "backend": str(hit.get("backend") or "")[:40],
                            "content": content[:1200],
                            "authority": "advisory_only_requires_operator_acceptance",
                        }
                    )
            return [self._event("vector_rag", "fired", mode="advisory_retrieval", reason="retrieval_completed", metrics={"hits": hits})]
        except Exception as exc:
            return [self._event("vector_rag", "failed", mode="advisory_retrieval", reason=type(exc).__name__)]

    def _memory_recall_events(self, objective: str) -> list[dict[str, Any]]:
        try:
            hull = self._hull()
            records = hull.search(objective, limit=8)
            for record in records[:4]:
                if not isinstance(record, Mapping):
                    continue
                summary = str(record.get("decision") or record.get("task") or "").strip()
                if summary:
                    self.advisory_context.append(
                        {
                            "source": "memory_hull",
                            "id": str(record.get("residue_id") or "")[:120],
                            "content": summary[:800],
                            "authority": "sealed_local_advisory_recall",
                        }
                    )
            return [self._event("memory_hull.recall", "fired", mode="sealed_local_recall", reason="recall_completed", metrics={"records": len(records)})]
        except Exception as exc:
            return [self._event("memory_hull.recall", "failed", mode="sealed_local_recall", reason=type(exc).__name__)]

    def _hull(self) -> Any:
        if self.memory_hull is None:
            from app.kernel.storage.memory_hull import MemoryHull

            self.memory_hull = MemoryHull(self.workspace / ".beast" / "memory_hull")
        return self.memory_hull

    def _crystal_events(self, objective: str, metadata: Mapping[str, Any]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        if self.crystal_preflight is None:
            events.append(self._event("crystal_reuse", "skipped", mode="runtime_owned", reason="delegated_to_existing_runtime_preflight"))
        else:
            try:
                decision = self.crystal_preflight(objective=objective, metadata=metadata)
                hit = str(decision.get("action") or "").startswith("reuse_")
                events.append(self._event("crystal_reuse", "fired", mode="reuse_preflight", reason=str(decision.get("reason") or ("hit" if hit else "miss"))))
            except Exception as exc:
                events.append(self._event("crystal_reuse", "failed", mode="reuse_preflight", reason=type(exc).__name__))

        try:
            if self.family_lookup is None:
                from app.kernel.compute.family_crystals import infer_task_family, lookup_promoted_family_crystal

                family = infer_task_family(objective, metadata)
                hit = lookup_promoted_family_crystal(family, env=self.environ)
            else:
                family = str(metadata.get("task_family") or "")
                hit = self.family_lookup(objective=objective, metadata=metadata)
            events.append(
                self._event(
                    "family_crystal",
                    "fired" if hit else "skipped",
                    mode="read_only_promoted_lookup",
                    reason="promoted_family_crystal_hit" if hit else "no_promoted_family_crystal",
                    artifacts={
                        "crystal_id": (hit or {}).get("crystal_id", ""),
                        "task_family": (hit or {}).get("task_family", family),
                    },
                )
            )
        except Exception as exc:
            events.append(self._event("family_crystal", "failed", mode="read_only_promoted_lookup", reason=type(exc).__name__))

        try:
            if self.crystal_status is None:
                from app.kernel.compute.coding_crystal_runtime import crystal_runtime_status

                status = crystal_runtime_status(self.workspace, env=self.environ)
            else:
                status = self.crystal_status(workspace=self.workspace, env=self.environ)
            ready = bool(status.get("enabled"))
            events.append(self._event("coding_crystal.production", "fired" if ready else "skipped", mode="armed_awaiting_verified_completion" if ready else "opt_in", reason=str(status.get("reason") or ("ready" if ready else "disabled"))))
        except Exception as exc:
            events.append(self._event("coding_crystal.production", "failed", mode="status_probe", reason=type(exc).__name__))
        return events

    def _bus_event(self, metadata: Mapping[str, Any]) -> dict[str, Any]:
        if not _is_enabled(self.environ, "BEAST_CONSOLIDATED_CRYSTAL_BUS"):
            return self._event("crystal_bus", "skipped", mode="opt_in", reason="feature_flag_disabled")
        if self.bus_probe is None:
            return self._event("crystal_bus", "skipped", mode="awaiting_admitted_capsule", reason="no_transfer_eligible_capsule")
        try:
            result = self.bus_probe(workspace=self.workspace, metadata=metadata)
            eligible = bool(result.get("eligible"))
            return self._event("crystal_bus", "fired" if eligible else "skipped", mode="transfer_eligible" if eligible else "awaiting_admitted_capsule", reason=str(result.get("reason") or "probe_completed"), metrics={"eligible": eligible})
        except Exception as exc:
            return self._event("crystal_bus", "failed", mode="transfer_preflight", reason=type(exc).__name__)

    def _swarm_event(self, objective: str, metadata: Mapping[str, Any]) -> dict[str, Any]:
        if not _is_enabled(self.environ, "BEAST_SWARM_SPECIALIST"):
            return self._event("swarm_specialist", "skipped", mode="advisory", reason="feature_flag_disabled")
        try:
            if self.swarm_selector is None:
                route = metadata.get("adaptive_route") if isinstance(metadata.get("adaptive_route"), Mapping) else {}
                result = {"selected": route.get("route") == "local_specialist_adapter", "reason": "local_specialist_proposed" if route.get("route") == "local_specialist_adapter" else "no_specialist_proposal"}
            else:
                result = self.swarm_selector(objective=objective, metadata=metadata)
            selected = bool(result.get("selected"))
            return self._event("swarm_specialist", "fired" if selected else "skipped", mode="advisory_selection", reason=str(result.get("reason") or "selection_completed"))
        except Exception as exc:
            return self._event("swarm_specialist", "failed", mode="advisory_selection", reason=type(exc).__name__)

    def prepare(
        self,
        *,
        objective: str,
        source_context: str = "",
        diagnostic_context: str = "",
        task_metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run bounded pre-provider integrations and return redacted evidence."""
        metadata = dict(task_metadata or {})
        self.advisory_context = []
        compression, source, diagnostics = self._compression(objective, source_context, diagnostic_context)
        events = [
            *compression,
            *self._vector_events(objective),
            *self._memory_recall_events(objective),
            *self._crystal_events(objective, metadata),
            self._bus_event(metadata),
            self._swarm_event(objective, metadata),
        ]
        return {"events": events, "source_context": source, "diagnostic_context": diagnostics}

    def complete(self, *, run_id: str, objective: str, verified: bool) -> dict[str, Any]:
        """Seal verified completion and extract a non-promoted crystal candidate."""
        if not verified:
            return {
                "events": [
                    self._event("memory_hull.seal", "skipped", mode="postflight", reason="run_not_verified"),
                    self._event("coding_crystal.production", "skipped", mode="postflight", reason="run_not_verified"),
                ]
            }
        events: list[dict[str, Any]] = []
        try:
            receipt = self._hull().write_residue(
                task=objective,
                decision="Agent Coder run reached verified completion.",
                evidence={"run_id": run_id, "verified": True},
                section="tasks",
                policy_tags=("agent_coder", "verified_completion"),
                correlation_id=run_id,
            )
            events.append(self._event("memory_hull.seal", "fired" if receipt.get("verified") else "failed", mode="sealed_local_residue", reason="seal_verified" if receipt.get("verified") else "seal_verification_failed", metrics={"verified": bool(receipt.get("verified"))}, artifacts={"residue_id": receipt.get("residue_id", "")}))
        except Exception as exc:
            events.append(self._event("memory_hull.seal", "failed", mode="sealed_local_residue", reason=type(exc).__name__))

        if not _is_enabled(self.environ, "BEAST_CODING_CRYSTALS"):
            events.append(self._event("coding_crystal.production", "skipped", mode="opt_in", reason="feature_flag_disabled"))
            return {"events": events}
        try:
            if self.crystal_producer is None:
                from app.kernel.compute.coding_crystal_runtime import learn_from_run

                result = learn_from_run(self.workspace, run_id, env=self.environ, approved_by="")
            else:
                result = self.crystal_producer(workspace=self.workspace, run_id=run_id, env=self.environ, approved_by="")
            status = str(result.get("status") or "unknown")
            fired = status == "verified_awaiting_operator_promotion"
            events.append(self._event("coding_crystal.production", "fired" if fired else "skipped", mode=status, reason=status, artifacts={"crystal_id": result.get("crystal_id", "")}))
        except Exception as exc:
            events.append(self._event("coding_crystal.production", "failed", mode="candidate_extraction", reason=type(exc).__name__))
        return {"events": events}


__all__ = ["CoderIntegrationCoordinator"]
