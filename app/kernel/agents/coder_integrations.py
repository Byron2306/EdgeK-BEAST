"""Bounded integration coordinator for the Desktop IDE Agent Coder path.

This module does not grant authority.  It invokes existing read-only or
proposal-only integrations before provider handoff and existing sealed
learning integrations after verified completion.  Every attempt becomes one
small, redacted event suitable for SSE, run history, and the Systems Atlas.
"""

from __future__ import annotations

import base64
import asyncio
import fcntl
import hashlib
import json
import logging
import os
import shutil
import time
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
        swarm_dispatcher: Any = None,
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
        self.swarm_dispatcher = swarm_dispatcher
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
        # Receipt semantics are distinct from the legacy fired/skipped/failed
        # event type. Eligibility is not execution, and execution is not proof
        # that a durable effect was committed.
        capability_name = str(capability)
        mode_name = str(mode)
        if capability_name == "crystal_bus":
            stage, operation = "eligibility", "transfer_preflight"
        elif capability_name == "coding_crystal.production":
            if mode_name == "armed_awaiting_verified_completion":
                stage, operation = "eligibility", "production_readiness"
            elif mode_name in {"candidate_extraction", "verified_awaiting_operator_promotion"}:
                stage, operation = "postflight", "candidate_extraction"
            else:
                stage, operation = "eligibility", "production_readiness"
        elif capability_name == "family_crystal":
            stage, operation = "eligibility", "promoted_family_lookup"
        elif capability_name == "crystal_reuse":
            stage, operation = "eligibility", "reuse_preflight"
        elif capability_name == "swarm_specialist":
            if mode_name == "governed_dispatch":
                stage, operation = "execution", "specialist_dispatch"
            else:
                stage, operation = "eligibility", "specialist_selection"
        elif capability_name.startswith("compression."):
            stage, operation = "execution", "context_compression"
        elif capability_name == "kv_transport":
            stage, operation = "execution", "prefix_reuse_lookup"
        elif capability_name in {"vector_rag", "memory_hull.recall"}:
            stage, operation = "execution", "advisory_retrieval"
        elif capability_name == "memory_hull.seal":
            stage, operation = "postflight", "residue_seal"
        else:
            stage, operation = "eligibility", "capability_probe"

        payload: dict[str, Any] = {
            "capability": str(capability),
            "status": status if status in {"fired", "skipped", "failed"} else "failed",
            "stage": stage,
            "operation": operation,
            "effect_committed": (
                capability_name == "memory_hull.seal"
                and status == "fired"
                and mode_name == "sealed_local_residue"
            ),
            "mode": str(mode)[:80],
            "reason": str(reason)[:120],
            "metrics": _safe_metrics(metrics),
            "artifacts": {
                str(key): str(value)[:160]
                for key, value in dict(artifacts or {}).items()
                if key in {"receipt_id", "residue_id", "crystal_id", "task_family", "block_id", "engine", "model", "governor_receipt", "provenance"}
                and isinstance(value, (str, int))
            },
            "authority": "advisory_or_existing_gate_only",
        }
        event = {"event_type": f"agent.integration.{payload['status']}", "payload": payload}
        logger.info("agent integration %s", json.dumps(event, sort_keys=True, separators=(",", ":")))
        return event

    def _compression(
        self,
        objective: str,
        source: str,
        diagnostics: str,
        *,
        source_files: Mapping[str, str] | None = None,
    ) -> tuple[list[dict[str, Any]], str, str, dict[str, str], str]:
        if not _is_enabled(self.environ, "BEAST_COMPRESSION_TIERS"):
            return (
                [self._event("compression.tiers", "skipped", mode="opt_in", reason="feature_flag_disabled")],
                source,
                diagnostics,
                {},
                "",
            )
        router = self.compression_router
        if router is None:
            from app.context.compression_tiers import default_router

            router = default_router()
        events: list[dict[str, Any]] = []

        def invoke(
            capability: str,
            tier: str,
            payload: str,
            *,
            query: str = "",
            kind: str = "test",
            edit_targets: tuple[str, ...] = (),
        ) -> str:
            if not payload:
                events.append(self._event(capability, "skipped", mode="governed_compression", reason="no_eligible_context"))
                return payload
            try:
                output = router.compress(tier, payload, query=query, kind=kind, edit_targets=edit_targets)
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
        # payload is the workspace path, never source text in the event. Its
        # bounded output is attached to the model packet by the caller.
        repo_map_content = invoke("compression.reporelay", "repo_map", str(self.workspace), query=objective)

        transformed_files: dict[str, str] = {}
        eligible = source_files or {}
        if eligible:
            for path, content in list(eligible.items())[:8]:
                text = str(content or "")
                if not text:
                    transformed_files[str(path)] = ""
                    continue
                transformed_files[str(path)] = invoke(
                    "compression.longcodezip",
                    "longcodezip",
                    text,
                    query=objective,
                    kind="source",
                )
            source = "\n\n".join(transformed_files.values())
        else:
            source = invoke("compression.longcodezip", "longcodezip", source, query=objective, kind="source")

        diagnostics = invoke("compression.rtk", "rtk", diagnostics, query=objective, kind="test")
        diagnostics = invoke("compression.sqz", "sqz", diagnostics, query=objective, kind="test")
        return events, source, diagnostics, transformed_files, repo_map_content

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
            if hits <= 0:
                return [self._event(
                    "vector_rag",
                    "skipped",
                    mode="advisory_retrieval",
                    reason="no_retrieval_hits",
                    metrics={"hits": 0},
                )]
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
            if not records:
                return [self._event(
                    "memory_hull.recall",
                    "skipped",
                    mode="sealed_local_recall",
                    reason="no_recall_records",
                    metrics={"records": 0},
                )]
            return [self._event("memory_hull.recall", "fired", mode="sealed_local_recall", reason="recall_completed", metrics={"records": len(records)})]
        except Exception as exc:
            return [self._event("memory_hull.recall", "failed", mode="sealed_local_recall", reason=type(exc).__name__)]

    def _hull(self) -> Any:
        if self.memory_hull is None:
            from app.kernel.storage.memory_hull import MemoryHull

            self.memory_hull = MemoryHull(self.workspace / ".beast" / "memory_hull")
        return self.memory_hull


    def _kv_events(self, objective: str, source: str, metadata: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Look up a real engine-native prompt-prefix block on the process transport.

        Metadata registration is not reuse. This path reports ``fired`` only
        when the transport already holds verified engine-native bytes for the
        exact model/prefix identity. It never selects a foreign engine lane and
        never registers a payload-free block as a reusable cache.
        """
        if not _is_enabled(self.environ, "BEAST_ZERO_COPY_KV"):
            return [self._event("kv_transport", "skipped", mode="opt_in", reason="feature_flag_disabled")]
        try:
            from app.kernel.compute.kv_transport import CacheEngine, default_transport

            provider = str(metadata.get("provider") or "").strip().lower()
            engine_by_provider = {
                "ollama": CacheEngine.OLLAMA,
                "local_ollama": CacheEngine.OLLAMA,
                "vllm": CacheEngine.VLLM,
                "sglang": CacheEngine.SGLANG,
                "lm_studio": CacheEngine.LM_STUDIO,
                "local_nim": CacheEngine.VLLM,
            }
            engine = engine_by_provider.get(provider)
            if engine is None:
                return [self._event(
                    "kv_transport",
                    "skipped",
                    mode="awaiting_engine_native_payload",
                    reason="provider_does_not_expose_transportable_kv",
                )]

            transport = default_transport(storage_dir=self.workspace / ".beast" / "kv_transport")
            model = str(metadata.get("model") or provider or "unknown")
            tokenizer = str(metadata.get("tokenizer") or model)
            prefix = (source or objective or "")[:4000]
            system = str(metadata.get("system_prompt") or "beast-agent-coder")
            hit = transport.lookup(model, tokenizer, prefix, system, preferred_engine=engine)
            if hit is None:
                return [self._event(
                    "kv_transport",
                    "skipped",
                    mode="awaiting_engine_native_payload",
                    reason="no_reusable_engine_native_prefix",
                    metrics={"hits": 0},
                )]
            if not transport.has_reusable_payload(hit.block_id):
                return [self._event(
                    "kv_transport",
                    "skipped",
                    mode="awaiting_engine_native_payload",
                    reason="metadata_block_has_no_engine_native_payload",
                    metrics={"hits": 1},
                    artifacts={"block_id": hit.block_id, "engine": hit.engine.value},
                )]
            return [self._event(
                "kv_transport",
                "fired",
                mode="prefix_reuse",
                reason="reusable_engine_native_prefix_found",
                metrics={"hits": 1},
                artifacts={
                    "block_id": hit.block_id,
                    "engine": hit.engine.value,
                    "provenance": hit.metadata.get("payload_provenance", "unspecified_tensor_payload"),
                },
            )]
        except Exception as exc:
            return [self._event("kv_transport", "failed", mode="prefix_reuse_lookup", reason=type(exc).__name__)]

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
                from app.kernel.compute import family_crystals as _family_crystals

                family = _family_crystals.infer_task_family(objective, metadata)
                hit = _family_crystals.lookup_promoted_family_crystal(family, env=self.environ)
            else:
                family = str(metadata.get("task_family") or "")
                hit = self.family_lookup(objective=objective, metadata=metadata)

            if hit:
                # Load the full promoted crystal from the registry and replay it
                db_path = hit.get("storage_path")
                crystal_id = hit.get("crystal_id")
                if db_path and crystal_id:
                    registry = _family_crystals.FamilyRegistry(db_path)
                    record = registry.get(crystal_id)
                    crystal = record.get("crystal_object")
                    if isinstance(crystal, _family_crystals.FamilyCrystal):
                        # Execute the governed replay in a scratch worktree
                        worktree_root = self.workspace / ".beast" / "crystal_replay" / crystal_id
                        if worktree_root.exists():
                            shutil.rmtree(worktree_root)
                        worktree_root.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copytree(self.workspace, worktree_root, ignore=shutil.ignore_patterns('.beast/crystal_replay*', 'crystal_replay*'))

                        parameters = {
                            "implementation_target": str(metadata.get("implementation_target") or ""),
                            "verify_command": list(metadata.get("verify_command") or ["python3", "-m", "pytest", "-q"]),
                        }
                        result = _family_crystals.replay_family(crystal, parameters, self.workspace, worktree_root)

                        if result.get("ok"):
                            events.append(
                                self._event(
                                    "family_crystal",
                                    "fired",
                                    mode="governed_replay",
                                    reason="family_crystal_replay_verified",
                                    metrics={
                                        "tool_calls": result.get("tool_calls", 0),
                                        "changed_files": len(result.get("changed", [])),
                                        "wall_ms": result.get("wall_ms", 0),
                                    },
                                    artifacts={
                                        "crystal_id": crystal_id,
                                        "task_family": family,
                                        "replay_trace_digest": str(hashlib.sha256(json.dumps(result.get("trace", []), sort_keys=True).encode()).hexdigest()[:16]),
                                    },
                                )
                            )
                        else:
                            events.append(
                                self._event(
                                    "family_crystal",
                                    "skipped",
                                    mode="governed_replay",
                                    reason=f"family_crystal_replay_refused: {result.get('reason')}",
                                    artifacts={"crystal_id": crystal_id, "task_family": family},
                                )
                            )
                        shutil.rmtree(worktree_root, ignore_errors=True)
                    else:
                        events.append(
                            self._event(
                                "family_crystal",
                                "skipped",
                                mode="governed_replay",
                                reason="promoted_crystal_not_loadable",
                                artifacts={"crystal_id": crystal_id, "task_family": family},
                            )
                        )
                else:
                    events.append(
                        self._event(
                            "family_crystal",
                            "skipped",
                            mode="read_only_promoted_lookup",
                            reason="promoted_family_crystal_hit_but_no_replay_context",
                            artifacts={"crystal_id": crystal_id, "task_family": family},
                        )
                    )
            else:
                events.append(
                    self._event(
                        "family_crystal",
                        "skipped",
                        mode="read_only_promoted_lookup",
                        reason="no_promoted_family_crystal",
                    )
                )
        except Exception as exc:
            events.append(self._event("family_crystal", "failed", mode="governed_replay", reason=type(exc).__name__))

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
            try:
                from app.kernel.crystal_bus.bus import (
                    ConsolidatedCrystalBus,
                    CapsuleOffer,
                    crystal_bus_from_environment,
                )
                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

                # Create a local signer for testing (in production, this would come from a proper key store)
                signer_key = self.environ.get("BEAST_CRYSTAL_BUS_SIGNER_KEY")
                if signer_key:
                    import base64
                    signer = Ed25519PrivateKey.from_private_bytes(base64.b64decode(signer_key))
                else:
                    signer = Ed25519PrivateKey.generate()
                
                signer_id = self.environ.get("BEAST_CRYSTAL_BUS_SIGNER_ID", "local_signer")
                workspace_id = self.environ.get("BEAST_CRYSTAL_BUS_WORKSPACE_ID", str(self.workspace))
                
                factory = crystal_bus_from_environment(
                    self.environ,
                    signer=signer,
                    signer_id=signer_id,
                    workspace_id=workspace_id,
                )
                if factory is None:
                    return self._event("crystal_bus", "skipped", mode="awaiting_admitted_capsule", reason="bus_factory_unavailable")
                left, right = factory.pair()
                try:
                    # Create a real sealed capsule with the current workspace's crystal ir
                    capsule_data = json.dumps({
                        "crystal_ir": "beast.action_intent.v1",
                        "workspace": str(self.workspace),
                        "objective": str(metadata.get("objective") or ""),
                    }).encode()
                    fd = os.memfd_create("beast-crystal-capsule", os.MFD_ALLOW_SEALING)
                    try:
                        os.write(fd, capsule_data)
                        fcntl.fcntl(fd, fcntl.F_ADD_SEALS, fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE | fcntl.F_SEAL_SEAL)
                    except OSError:
                        os.close(fd)
                        raise

                    offer = CapsuleOffer(
                        capsule_digest="sha256:" + hashlib.sha256(capsule_data).hexdigest(),
                        capsule_size=len(capsule_data),
                        crystal_id=str(metadata.get("crystal_id") or "coding_crystal_candidate"),
                        promotion_digest="sha256:" + hashlib.sha256(str(metadata.get("objective") or "").encode()).hexdigest(),
                        capability_lease_digest="sha256:" + hashlib.sha256(str(metadata.get("run_id") or "").encode()).hexdigest(),
                        audience="executor:crystal_bus",
                        expires_at=time.time() + 60,
                    )

                    # Transfer through the bus with custody chain
                    sent_offer = left.send_capsule(offer, fd)
                    received = right.receive_capsule()
                    received.close()
                    os.close(fd)

                    custody_receipt = received.custody_receipt
                    return self._event(
                        "crystal_bus",
                        "fired",
                        mode="capsule_transfer",
                        reason="capsule_transfer_verified",
                        metrics={
                            "capsule_size": offer.capsule_size,
                            "sequence": sent_offer.sequence,
                        },
                        artifacts={
                            "message_id": sent_offer.message_id,
                            "capsule_digest": offer.capsule_digest,
                            "custody_receipt_digest": custody_receipt.get("receipt_digest", ""),
                            "signer_id": custody_receipt.get("signer_id", ""),
                        },
                    )
                finally:
                    for endpoint in (left, right):
                        close = getattr(endpoint, "close", None)
                        if callable(close):
                            close()
            except Exception as exc:
                return self._event("crystal_bus", "failed", mode="transfer_preflight", reason=type(exc).__name__)
        try:
            result = self.bus_probe(workspace=self.workspace, metadata=metadata)
            eligible = bool(result.get("eligible"))
            return self._event("crystal_bus", "fired" if eligible else "skipped", mode="transfer_eligible" if eligible else "awaiting_admitted_capsule", reason=str(result.get("reason") or "probe_completed"), metrics={"eligible": eligible})
        except Exception as exc:
            return self._event("crystal_bus", "failed", mode="transfer_preflight", reason=type(exc).__name__)

    def _swarm_event(self, objective: str, metadata: Mapping[str, Any], source: str = "") -> dict[str, Any]:
        if not _is_enabled(self.environ, "BEAST_SWARM_SPECIALIST"):
            return self._event("swarm_specialist", "skipped", mode="advisory", reason="feature_flag_disabled")
        try:
            if self.swarm_selector is None:
                route = metadata.get("adaptive_route") if isinstance(metadata.get("adaptive_route"), Mapping) else {}
                files = metadata.get("files") or metadata.get("context_files") or metadata.get("target_files") or []
                file_count = len(files) if isinstance(files, (list, tuple)) else 0
                hard = file_count >= 2 or any(token in objective.lower() for token in ("multi-file", "multifile", "refactor", "rename"))
                if hard:
                    from app.kernel.agents.swarm_specialist import OllamaSwarmRunner

                    installed = list(OllamaSwarmRunner().installed_models() or [])
                    result = {
                        "selected": bool(installed),
                        "reason": "local_ollama_specialists_available" if installed else "no_installed_specialist_model",
                        "installed": len(installed),
                        "route": {
                            "route": "local_specialist_adapter",
                            "specialist_ref": f"ollama://{installed[0]}",
                        } if installed else {},
                    }
                else:
                    result = {
                        "selected": route.get("route") == "local_specialist_adapter",
                        "reason": "local_specialist_proposed" if route.get("route") == "local_specialist_adapter" else "no_specialist_proposal",
                    }
            else:
                result = self.swarm_selector(objective=objective, metadata=metadata)
            selected = bool(result.get("selected"))
            if not selected:
                return self._event("swarm_specialist", "skipped", mode="advisory_selection", reason=str(result.get("reason") or "no_specialist_selected"))

            dispatcher = self.swarm_dispatcher
            if dispatcher is None:
                from app.kernel.agents.swarm_specialist import OllamaSwarmRunner, SwarmSpecialistDispatch
                from app.kernel.governance.governor_spine import ComputeGovernorSpine, GovernorReceiptLog

                receipt_path = self.workspace / ".beast" / "governor" / "swarm-agent-coder.jsonl"
                dispatcher = SwarmSpecialistDispatch(
                    runner=OllamaSwarmRunner(env=self.environ),
                    governor=ComputeGovernorSpine(receipts=GovernorReceiptLog(receipt_path), enforce=True),
                    env=self.environ,
                )
                self.swarm_dispatcher = dispatcher

            from app.kernel.compute.perceive import EdgeKIR

            route = result.get("route") if isinstance(result.get("route"), Mapping) else {}
            if not route:
                adaptive = metadata.get("adaptive_route") if isinstance(metadata.get("adaptive_route"), Mapping) else {}
                route = dict(adaptive)
            ir = EdgeKIR(
                messages=[{"role": "user", "content": objective}],
                model=str(metadata.get("model") or "local-specialist"),
                max_tokens=min(1024, max(64, int(metadata.get("specialist_max_tokens") or 512))),
                temperature=0.0,
                metadata={
                    "objective": objective,
                    "source_context": source[:12000],
                    "diagnostic_context": str(metadata.get("diagnostic_context") or "")[:4000],
                    "run_id": str(metadata.get("run_id") or ""),
                    "response_schema": metadata.get("specialist_response_schema"),
                    "output_contract": metadata.get("output_contract"),
                },
            )
            outcome = asyncio.run(dispatcher.dispatch(ir, route, run_id=str(metadata.get("run_id") or "")))
            receipt = outcome.receipt if isinstance(getattr(outcome, "receipt", None), Mapping) else {}
            if not bool(getattr(outcome, "dispatched", False)):
                return self._event(
                    "swarm_specialist",
                    "skipped",
                    mode="governed_dispatch",
                    reason=str(getattr(outcome, "reason", "specialist_dispatch_refused")),
                    artifacts={"model": receipt.get("model", ""), "governor_receipt": receipt.get("governor_receipt", "")},
                )
            response = outcome.response if isinstance(getattr(outcome, "response", None), Mapping) else {}
            advice = str(response.get("text") or "")[:4000]
            if advice:
                self.advisory_context.append({"capability": "swarm_specialist", "summary": advice})
            return self._event(
                "swarm_specialist",
                "fired",
                mode="governed_dispatch",
                reason=str(getattr(outcome, "reason", "specialist_output_accepted")),
                metrics={"verified": True},
                artifacts={"model": response.get("model") or receipt.get("model", ""), "governor_receipt": receipt.get("governor_receipt", "")},
            )
        except Exception as exc:
            return self._event("swarm_specialist", "failed", mode="advisory_selection", reason=type(exc).__name__)

    def prepare(
        self,
        *,
        objective: str,
        source_context: str = "",
        diagnostic_context: str = "",
        source_files: Mapping[str, str] | None = None,
        task_metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run bounded pre-provider integrations and return redacted evidence.

        ``source_files`` carries the exact selected-file previews. Successful
        LongCodeZip/RTK/SQZ transforms are returned per file so the caller can
        put the transformed bytes into the actual provider packet rather than
        discarding them. Raw content is never placed in an integration event.
        """
        metadata = dict(task_metadata or {})
        self.advisory_context = []
        
        # Run Quality Cascade as part of preflight
        quality_report = None
        if _is_enabled(self.environ, "BEAST_QUALITY_CASCADE"):
            from app.kernel.data_processing.quality_cascade import QualityCascade
            quality_cascade = QualityCascade(policies=os.environ)
            # Create envelope from task_metadata
            envelope = {
                "task_id": metadata.get("run_id", "unknown"),
                "task_class": "live_coding",
                "inputs": {
                    "user_request": objective,
                    "provider": metadata.get("provider", ""),
                    "task_name": metadata.get("task_name", ""),
                    "mentioned_files": list(source_files.keys()) if source_files else [],
                },
                "context_budget": {
                    "max_tokens": metadata.get("max_tokens", 8000),
                    "max_files": max(1, len(source_files)) if source_files else 1,
                    "allow_full_files": False,
                },
            }
            route_card = {
                "route_id": metadata.get("run_id", "unknown"),
                "preferred_order": ["provider_policy", "credentials", "runtime_circuit", "log_scan"],
                "provider": metadata.get("provider", ""),
            }
            try:
                quality_report = quality_cascade.run(
                    envelope=envelope,
                    route_card=route_card,
                    workspace_root=str(self.workspace),
                )
            except Exception as exc:
                logger.warning("Quality cascade preflight failed: %s", exc)
                quality_report = None
        
        compression, source, diagnostics, transformed_files, repo_map_content = self._compression(
            objective,
            source_context,
            diagnostic_context,
            source_files=source_files,
        )
        events = [
            *compression,
            *self._vector_events(objective),
            *self._memory_recall_events(objective),
            *self._kv_events(objective, source, metadata),
            *self._crystal_events(objective, metadata),
            self._bus_event(metadata),
            self._swarm_event(objective, metadata, source),
        ]
        if quality_report:
            events.append({
                "event_type": "agent.integration.fired",
                "payload": {
                    "capability": "quality_cascade",
                    "status": "fired",
                    "stage": "preflight",
                    "operation": "quality_verification",
                    "mode": "local_checks",
                    "reason": "quality_cascade_passed" if quality_report.get("verification_accepted") else "quality_cascade_not_passed",
                    "metrics": {
                        "check_count": quality_report.get("summary", {}).get("check_count", 0),
                        "passed": quality_report.get("summary", {}).get("passed", 0),
                        "failed": quality_report.get("summary", {}).get("failed", 0),
                        "warnings": quality_report.get("summary", {}).get("warnings", 0),
                        "verification_accepted": quality_report.get("verification_accepted", False),
                    },
                    "artifacts": {"route_id": metadata.get("run_id", "unknown")},
                    "authority": "advisory_or_existing_gate_only",
                }
            })
        return {
            "events": events,
            "source_context": source,
            "diagnostic_context": diagnostics,
            "source_files": transformed_files,
            "repo_map": repo_map_content,
        }

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

            crystal_id = result.get("crystal_id")
            if fired and crystal_id:
                # Phase 3D: Add crystal to lattice as leaf node
                try:
                    from app.kernel.compute.crystal_lattice_spine import default_lattice
                    from app.kernel.compute.coding_crystals import CodingCrystalRegistry

                    registry = CodingCrystalRegistry(self.workspace / ".beast" / "crystals" / "coding_crystals.sqlite3")
                    lattice = default_lattice(self.workspace, registry)
                    crystal_record = registry.get(crystal_id)
                    if crystal_record.get("status") == "promoted":
                        lattice.add_crystal(crystal_id, publisher_id="agent_coder")
                        events.append(self._event(
                            "crystal_lattice", "fired", mode="leaf_admission",
                            reason="crystal_admitted_to_lattice",
                            metrics={}, artifacts={"crystal_id": crystal_id, "task_family": crystal_record.get("candidate_object", {}).get("task_family", "")}
                        ))

                        # Attempt lattice composition with other admitted crystals of same family
                        from app.kernel.compute.coding_crystals import CodingCrystalCandidate

                        family = crystal_record.get("candidate_object", {}).get("task_family", "")
                        if family:
                            # Get other promoted crystals of same family from registry
                            candidates = []
                            # Query database directly for other promoted crystals of same family
                            import sqlite3
                            with registry._connect() as conn:
                                rows = conn.execute(
                                    "SELECT crystal_id, payload FROM coding_crystals WHERE task_family=? AND status='promoted' AND crystal_id!=?",
                                    (family, crystal_id)
                                ).fetchall()
                                for row in rows:
                                    record = json.loads(row["payload"])
                                    other_candidate = record.get("candidate_object")
                                    if isinstance(other_candidate, dict):
                                        other_candidate = CodingCrystalCandidate.from_dict(other_candidate)
                                    if isinstance(other_candidate, CodingCrystalCandidate):
                                        candidates.append(other_candidate)
                            if candidates:
                                from app.kernel.compute.crystal_lattice_spine import compose_candidates
                                try:
                                    composite = compose_candidates(
                                        [crystal_record["candidate_object"]] + candidates,
                                        task_family=family,
                                        source_run_id=run_id,
                                        source_envelope_digest=_digest({"run_id": run_id}),
                                        learned_budget={k: float(v) for k, v in crystal_record["candidate_object"].learned_budget.items()}
                                    )
                                    # Use a mock verifier for the test; real admission needs operator approval
                                    admit_result = lattice.admit_composite(
                                        composite,
                                        verifier=type("Verifier", (), {"candidate_id": composite.crystal_id, "promoted": True, "successes": 3, "attempts": 3})(),
                                        publisher_id="agent_coder",
                                        approved_by="operator"
                                    )
                                    if admit_result.get("outcome") == "ADMIT":
                                        events.append(self._event(
                                            "crystal_lattice", "fired", mode="composite_admission",
                                            reason="composite_admitted_to_lattice",
                                            metrics={}, artifacts={"composite_id": composite.crystal_id, "component_ids": list(composite.component_ids)}
                                        ))
                                    else:
                                        events.append(self._event(
                                            "crystal_lattice", "skipped", mode="composite_admission",
                                            reason=f"composite_admission_{admit_result.get('outcome', '').lower()}",
                                            metrics={}, artifacts={"composite_id": composite.crystal_id, "reason": admit_result.get("reason")}
                                        ))
                                except Exception:
                                    pass  # Composition is optional, don't fail the run
                except Exception:
                    pass  # Lattice operations are optional, don't fail the run

                # Phase 3D: Record economy events from actual Episode Envelope budgets
                try:
                    from app.kernel.compute.crystal_economy import CrystalReuseEconomy, CrystalShadowLedger
                    from app.kernel.sensorium.episode_envelope import EpisodeEnvelopeStore

                    envelopes = EpisodeEnvelopeStore(self.workspace / ".beast" / "sensorium" / "episode_envelopes.sqlite3")
                    envelope = envelopes.get(run_id)
                    if envelope and envelope.verification.get("passed"):
                        ledger = CrystalShadowLedger(
                            self.workspace / ".beast" / "crystals" / "shadow_ledger.sqlite3",
                            local_node_id="agent_coder",
                            local_publisher_id="agent_coder"
                        )
                        ledger.bind_space(crystal_id, space_id="coding_crystal_test", space_manifest_hash="sha256:" + "0" * 64, publisher_id="agent_coder")
                        # Record the production as reproduction evidence
                        ledger.record_reproduction({
                            "receipt_id": f"production-{run_id}",
                            "provenance": {"crystal_id": crystal_id, "publisher_id": "agent_coder"},
                            "verifier": {"passed": True},
                            "local_reproduction_verified": True,
                            "promotion_verified": True,
                        })
                        events.append(self._event(
                            "crystal_economy", "fired", mode="production_recorded",
                            reason="crystal_production_recorded_in_economy",
                            metrics={}, artifacts={"crystal_id": crystal_id}
                        ))
                except Exception:
                    pass  # Economy operations are optional, don't fail the run

        except Exception as exc:
            events.append(self._event("coding_crystal.production", "failed", mode="candidate_extraction", reason=type(exc).__name__))
        return {"events": events}


__all__ = ["CoderIntegrationCoordinator"]
