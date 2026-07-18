"""Read-mostly runtime contracts for BEAST's Sensorium and crystal plane."""

from app.kernel.sensorium.artifact_taxonomy import (
    ArtifactAuthority,
    CrystalArtifactClass,
    CrystalArtifactDescriptor,
    authority_allows,
    describe_existing_artifact,
)
from app.kernel.sensorium.architecture_decisions import sensorium_architecture_decision_register
from app.kernel.sensorium.contracts import (
    ComputeCrystal,
    ContractValidationError,
    ProcessLease,
    RuntimeEpisode,
    SensorEvent,
    SocketIdentity,
)
from app.kernel.sensorium.physical_effects import PhysicalEffect, physical_effect_payload
from app.kernel.sensorium.adapters import BeastOwnedEventFactory
from app.kernel.sensorium.episode_builder import RuntimeEpisodeBuilder
from app.kernel.sensorium.event_sequencer import PublishReceipt, SensoriumEventSequencer, SequencedEvent
from app.kernel.sensorium.exporter import SensoriumOutboxExporter
from app.kernel.sensorium.privacy import SensorPrivacyError, SensorPrivacyGate
from app.kernel.sensorium.read_model import SensoriumReadModel
from app.kernel.sensorium.socket_reconciler import ReconciledSocket, SocketIdentityReconciler, SocketReconciliationError
from app.kernel.sensorium.journal import SensoriumJournal

__all__ = [
    "ArtifactAuthority",
    "BeastOwnedEventFactory",
    "ComputeCrystal",
    "ContractValidationError",
    "CrystalArtifactClass",
    "CrystalArtifactDescriptor",
    "ProcessLease",
    "PhysicalEffect",
    "PublishReceipt",
    "RuntimeEpisodeBuilder",
    "RuntimeEpisode",
    "SensorEvent",
    "SensorPrivacyError",
    "SensorPrivacyGate",
    "SensoriumEventSequencer",
    "SensoriumOutboxExporter",
    "SensoriumReadModel",
    "SequencedEvent",
    "SocketIdentity",
    "ReconciledSocket",
    "SocketIdentityReconciler",
    "SocketReconciliationError",
    "SensoriumJournal",
    "authority_allows",
    "describe_existing_artifact",
    "sensorium_architecture_decision_register",
    "physical_effect_payload",
]
