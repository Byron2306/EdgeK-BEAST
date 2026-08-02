"""Composition root for the read-only Phase S1 Sensorium."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from app.kernel.sensorium.adapters import BeastOwnedEventFactory
from app.kernel.sensorium.contracts import RuntimeEpisode, SensorEvent
from app.kernel.sensorium.episode_builder import RuntimeEpisodeBuilder
from app.kernel.sensorium.event_sequencer import PublishReceipt, SensoriumEventSequencer
from app.kernel.sensorium.exporter import SensoriumOutboxExporter
from app.kernel.sensorium.privacy import SensorPrivacyGate
from app.kernel.sensorium.read_model import SensoriumReadModel
from app.kernel.sensorium.socket_reconciler import SocketIdentityReconciler
from app.kernel.compute.runtime_crystallizer import RuntimeCrystallizer, CrystalIR
from app.kernel.compute.heldout_replay import HeldOutReplayGate, ReplayReceipt
from app.kernel.compute.crystal_generalizer import CrystalGeneralizer, GeneralizationReceipt
from app.kernel.compute.typed_crystal_ir import TypedCrystalCompiler, ExecutableCrystalIR


class SensoriumRuntime:
    def __init__(
        self,
        *,
        capacity: int = 512,
        export_root: Optional[Path] = None,
        boot_id: Optional[str] = None,
        journal_path: Optional[Path] = None,
    ):
        self.privacy_gate = SensorPrivacyGate()
        if journal_path is None and os.environ.get("BEAST_SENSORIUM_JOURNAL"):
            journal_path = Path(os.environ["BEAST_SENSORIUM_JOURNAL"]).expanduser()
        if journal_path is not None:
            from app.kernel.sensorium.journal import SensoriumJournal
            self.journal = SensoriumJournal(journal_path)
        else:
            self.journal = None
        self.sequencer = SensoriumEventSequencer(capacity=capacity, privacy_gate=self.privacy_gate, journal=self.journal)
        self.episodes = RuntimeEpisodeBuilder()
        self.factory = BeastOwnedEventFactory(boot_id=boot_id)
        selected_root = export_root or Path(
            os.environ.get("BEAST_SENSORIUM_OUTBOX", "~/.beast/outbox/sensorium")
        ).expanduser()
        self.exporter = SensoriumOutboxExporter(selected_root)
        self.read_model = SensoriumReadModel(self.sequencer, self.episodes)
        self.socket_reconciler = SocketIdentityReconciler()
        self.crystallizer = RuntimeCrystallizer()
        self.replay_gate = HeldOutReplayGate()
        self.generalizer = CrystalGeneralizer()
        self.typed_ir_compiler = TypedCrystalCompiler()
        self._guardian_event_ids: set[int] = set()

    def crystallize_episode(self, mission_id: str, *, identity: str, task_family: list[str], parameters: list[str], preconditions: list[str], postconditions: list[str]) -> CrystalIR:
        """Extract Crystal IR only from a closed, observed runtime episode."""
        episodes = [episode for episode in self.episodes.latest_closed(100) if episode.mission_id == mission_id]
        if not episodes:
            raise ValueError("mission has no closed runtime episode")
        episode = episodes[-1]
        payload = {
            "episode_hash": episode.episode_hash,
            "events": [{"type": event_id} for event_id in episode.event_ids],
            "evidence": list(episode.event_ids),
        }
        return self.crystallizer.extract(payload, identity=identity, task_family=task_family, parameters=parameters, preconditions=preconditions, postconditions=postconditions)

    def replay_crystal(self, crystal: CrystalIR, variants: list[Any], replay: Callable[[CrystalIR, Any], bool]) -> ReplayReceipt:
        """Run held-out variants; promotion requires every replay to succeed."""
        return self.replay_gate.evaluate(crystal.identity, variants, lambda variant: replay(crystal, variant))

    def generalize_episodes(
        self,
        mission_ids: list[str],
        *,
        identity: str,
        task_family: list[str],
    ) -> tuple[CrystalIR, GeneralizationReceipt]:
        """Infer a bounded candidate from closed natural episode evidence."""
        selected = [episode for episode in self.episodes.latest_closed(100) if episode.mission_id in set(mission_ids)]
        missing = sorted(set(mission_ids) - {episode.mission_id for episode in selected})
        if missing:
            raise ValueError(f"missions have no closed runtime episode: {', '.join(missing)}")
        return self.generalizer.generalize(selected, identity=identity, task_family=task_family)

    def compile_candidate(self, candidate: CrystalIR, *, capability_lease: str = "") -> ExecutableCrystalIR:
        """Compile a learned candidate only through reviewed opcode contracts."""
        return self.typed_ir_compiler.compile(candidate, capability_lease=capability_lease)

    def replay_typed_crystal(self, crystal: ExecutableCrystalIR, variants: list[Any], *, root: Optional[Path] = None, **policy: Any) -> Any:
        """Run structured held-out replay without accepting caller callbacks."""
        from app.kernel.compute.crystal_replay_lab import CrystalReplayLaboratory
        laboratory = CrystalReplayLaboratory(
            self.typed_ir_compiler.registry,
            root=root,
            **policy,
        )
        return laboratory.run(crystal, variants)

    def promote_typed_crystal(self, crystal: ExecutableCrystalIR, replay: Any, registry: Any, **promotion: Any) -> Any:
        """Promote only through the authoritative physical-crystal registry."""
        crystal.validate(self.typed_ir_compiler.registry)
        return registry.promote(crystal, replay, **promotion)

    def evaluate_crystal_recurrence(self, crystal: ExecutableCrystalIR, context: Any, gate: Any, **clock: Any) -> Any:
        """Produce a fresh applicability decision; this does not grant authority."""
        crystal.validate(self.typed_ir_compiler.registry)
        return gate.evaluate(crystal, context, **clock)

    def execute_crystal_recurrence(self, crystal: ExecutableCrystalIR, proof: Any, authorization: Any, recurrence: Any, interpreter: Any, **execution: Any) -> Any:
        """Execute a promoted recurrence through the authorization-bound interpreter."""
        crystal.validate(self.typed_ir_compiler.registry)
        return interpreter.execute(crystal, proof, authorization, recurrence, **execution)

    def observe_socket(self, observation: Dict[str, Any], *, lease_index: Optional[Dict[object, str]] = None) -> Any:
        """Reconcile and publish a socket observation without acquiring authority."""
        reconciled = self.socket_reconciler.reconcile(observation, lease_index=lease_index)
        self.read_model.register_socket(reconciled)
        self.observe_physical(
            event_type="socket.reconciled",
            source="beast_socket_reconciler",
            payload_schema="beast.sensor.socket.reconciled.v1",
            operation="socket.reconcile",
            phase="observation",
            subject=reconciled.identity.identity,
            result="observed",
            payload={
                "socket_identity": reconciled.identity.identity,
                "local_port": reconciled.identity.local_port,
                "service_id": reconciled.identity.service_id,
                "lease_match": reconciled.lease_match,
                "compatibility_hint": reconciled.compatibility_hint,
                "listener_generation": reconciled.identity.listener_generation,
                "network_namespace": reconciled.identity.network_namespace,
                "vrf": reconciled.identity.vrf,
                "reads": [f"socket_inventory:{reconciled.identity.network_namespace}"],
                "produces": [f"socket_state:{reconciled.identity.identity}"],
                "descriptor_refs": [reconciled.identity.identity, reconciled.identity.owning_process],
            },
            workspace_id=reconciled.identity.workspace_id,
        )
        return reconciled

    def collect_linux_sockets(self, *, workspace_id: str, lease_index: Optional[Dict[object, str]] = None,
                              proc_root: Path | str = "/proc") -> Dict[str, Any]:
        """Ingest a read-only procfs TCP/UDP inventory with explicit limits."""
        from app.kernel.sensorium.linux_collectors import collect_socket_observations
        observations, receipt = collect_socket_observations(
            workspace_id=workspace_id, proc_root=proc_root,
        )
        admitted = 0
        for observation in observations:
            self.observe_socket(observation, lease_index=lease_index)
            admitted += 1
        self.read_model.set_collector_receipt(receipt)
        self.observe_owned(event_type="sensorium.collector_snapshot", source="sensorium_linux_procfs",
            payload_schema="beast.sensorium.collector_snapshot.v1",
            payload={"collector": "procfs", "socket_count": admitted, "read_only": True,
                     "limitations": receipt["limitations"]}, workspace_id=workspace_id)
        return {**receipt, "admitted": admitted}

    def retire_socket(self, socket_identity: str, *, reason: str, workspace_id: str = "") -> bool:
        """Remove stale topology and make the disappearance observable."""
        removed = self.read_model.remove_socket(socket_identity)
        self.observe_owned(
            event_type="socket.retired", source="beast_socket_reconciler",
            payload_schema="beast.sensor.socket.retired.v1",
            payload={"socket_identity": socket_identity, "reason": reason, "removed": removed},
            workspace_id=workspace_id,
        )
        return removed

    def ingest_guardian_events(self, events, *, workspace_by_lease: Optional[Dict[str,str]] = None) -> int:
        """Project durable Socket Guardian transitions into the read-only Sensorium."""
        admitted=0; workspace_by_lease=workspace_by_lease or {}
        for event in sorted(events,key=lambda item:int(item.get("event_id") or 0)):
            event_id=int(event.get("event_id") or 0)
            if event_id<=0 or event_id in self._guardian_event_ids:
                continue
            lease_id=str(event.get("lease_id") or "")
            previous_state = str(event.get("previous_state") or "")
            next_state = str(event.get("next_state") or "")
            effect_payload = {
                "guardian_event_id":event_id,"lease_id":lease_id,
                "previous_state":previous_state,
                "next_state":next_state,
                "reason":str(event.get("reason") or ""),
                "peer_pid":int(event.get("peer_pid") or 0),
                "peer_uid":int(event.get("peer_uid") or 0),
                "payload_digest":str(event.get("payload_digest") or ""),
                "descriptor_refs": [lease_id] if lease_id else [],
                "produces": [f"port_lease_state:{lease_id}"] if lease_id else [],
            }
            if lease_id and previous_state and next_state and previous_state != next_state:
                effect_payload["state_transition"] = {
                    "resource": f"port_lease:{lease_id}",
                    "from": previous_state,
                    "to": next_state,
                }
            self.observe_physical(
                event_type="port_lease.transition",source="beast_socket_guardian",
                payload_schema="beast.sensor.port_lease.transition.v1",
                operation="port_lease.transition", phase="observation",
                subject=f"port_lease:{lease_id or 'unknown'}", result="observed",
                payload=effect_payload,
                workspace_id=workspace_by_lease.get(lease_id,""),
                confidence_method="guardian_durable_lifecycle_ledger",
            )
            self._guardian_event_ids.add(event_id); admitted+=1
        if len(self._guardian_event_ids)>4096:
            self._guardian_event_ids=set(sorted(self._guardian_event_ids)[-2048:])
        return admitted

    def observe(self, event: SensorEvent, *, export_internal: bool = False) -> PublishReceipt:
        receipt = self.sequencer.publish(event)
        for generated in receipt.generated:
            self.episodes.ingest(generated)
            if export_internal:
                self.exporter.export_entry(generated)
        self.episodes.ingest(receipt.admitted)
        if export_internal:
            self.exporter.export_entry(receipt.admitted)
        return receipt

    def observe_owned(
        self,
        *,
        event_type: str,
        source: str,
        payload_schema: str,
        payload: Dict[str, Any],
        mission_id: str = "",
        workspace_id: str = "",
        export_internal: bool = False,
        **event_options: Any,
    ) -> PublishReceipt:
        event = self.factory.build(
            event_type=event_type,
            source=source,
            payload_schema=payload_schema,
            payload=payload,
            mission_id=mission_id,
            workspace_id=workspace_id,
            **event_options,
        )
        return self.observe(event, export_internal=export_internal)

    def observe_physical(
        self,
        *,
        event_type: str,
        source: str,
        payload_schema: str,
        operation: str,
        phase: str,
        subject: str,
        result: str,
        payload: Optional[Dict[str, Any]] = None,
        export_internal: bool = False,
        **event_options: Any,
    ) -> PublishReceipt:
        event = self.factory.physical_event(
            event_type=event_type,
            source=source,
            payload_schema=payload_schema,
            operation=operation,
            phase=phase,
            subject=subject,
            result=result,
            payload=payload,
            **event_options,
        )
        return self.observe(event, export_internal=export_internal)

    def capture_adapter(
        self,
        *,
        event_type: str,
        source: str,
        payload_schema: str,
        adapter: Callable[[], Dict[str, Any]],
        mission_id: str = "",
        workspace_id: str = "",
    ) -> PublishReceipt:
        try:
            payload = adapter()
            if not isinstance(payload, dict):
                raise TypeError("adapter result must be an object")
            return self.observe_owned(
                event_type=event_type,
                source=source,
                payload_schema=payload_schema,
                payload=payload,
                mission_id=mission_id,
                workspace_id=workspace_id,
            )
        except Exception as exc:
            return self.observe_owned(
                event_type="sensorium.adapter_failure",
                source="sensorium_adapter_boundary",
                payload_schema="beast.sensorium.adapter_failure.v1",
                payload={
                    "adapter_source": source,
                    "requested_event_type": event_type,
                    "error_type": type(exc).__name__,
                    "error_message_retained": False,
                },
                mission_id=mission_id,
                workspace_id=workspace_id,
                confidence_method="adapter_boundary_exception",
            )

    def close_episode(
        self,
        mission_id: str,
        *,
        objective_hash: str,
        workspace_identity: str,
        initial_state_hash: str,
        outcome: Dict[str, Any],
        resources: Optional[Dict[str, float]] = None,
        export: bool = False,
    ) -> RuntimeEpisode:
        episode = self.episodes.close(
            mission_id,
            objective_hash=objective_hash,
            workspace_identity=workspace_identity,
            initial_state_hash=initial_state_hash,
            outcome=outcome,
            resources=resources,
        )
        if export:
            self.exporter.export_episode(episode)
        return episode

    def state(self, *, event_limit: int = 25, episode_limit: int = 10) -> Dict[str, Any]:
        return self.read_model.state(event_limit=event_limit, episode_limit=episode_limit)


sensorium_runtime = SensoriumRuntime()
