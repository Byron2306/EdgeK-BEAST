import logging
from typing import Any, Optional

from app.kernel.compute.perceive import ProviderType, perceiver
from app.kernel.governance.reason import reasoner, GovernanceDecision
from app.kernel.execution.execute import executor
from app.kernel.execution.crystallize import crystallizer
from app.context.economizer import ContextEconomizer
from app.kernel.sensorium.contracts import content_hash
from app.kernel.sensorium.runtime import SensoriumRuntime, sensorium_runtime

logger = logging.getLogger(__name__)

class PRECOrchestrator:
    def __init__(self, economizer: ContextEconomizer, sensorium: Optional[SensoriumRuntime] = None):
        self.economizer = economizer
        self.sensorium = sensorium or sensorium_runtime

    async def execute_cycle(self, body, provider_type: ProviderType, session_id: str = "default"):
        original_request = body.copy()
        objective_hash = content_hash({"provider_type": provider_type.value, "request": original_request})
        mission_id = "mission_" + objective_hash.split(":", 1)[1][:24]
        workspace_identity = str(
            ((body.get("metadata") or {}) if isinstance(body.get("metadata"), dict) else {}).get("workspace_id")
            or "gateway"
        )
        initial_state_hash = content_hash({
            "provider_type": provider_type.value,
            "session_id": session_id,
            "model": body.get("model") or "",
            "workspace_identity": workspace_identity,
        })
        self._observe(
            mission_id,
            workspace_identity,
            event_type="mission.admitted",
            payload_schema="beast.sensor.mission.admitted.v1",
            payload={
                "provider_type": provider_type.value,
                "request_hash": objective_hash,
                "message_count": len(body.get("messages") or []),
                "stream": bool(body.get("stream")),
            },
        )

        try:
            # PERCEIVE
            ir = perceiver.perceive(body, provider_type)

            # ECONOMIZE
            economy_result = self.economizer.economize(ir)
            ir = economy_result.ir

            # REASON
            governance_result = reasoner.reason(ir, session_id)
            decision = getattr(governance_result.decision, "value", governance_result.decision)
            self._observe(
                mission_id,
                workspace_identity,
                event_type="mission.governance",
                payload_schema="beast.sensor.mission.governance.v1",
                payload={
                    "decision": str(decision),
                    "modified": governance_result.modified_ir is not None,
                    "reason_retained": False,
                },
            )

            # EXECUTE
            effective_ir = governance_result.modified_ir or ir
            provider_response = await executor.execute(effective_ir, governance_result)
            reasoner.record_usage(effective_ir, session_id, governance_result.budget_impact)
            response_hash = content_hash(provider_response)
            self._observe(
                mission_id,
                workspace_identity,
                event_type="mission.executed",
                payload_schema="beast.sensor.mission.executed.v1",
                payload={
                    "provider_type": provider_type.value,
                    "response_hash": response_hash,
                    "error_present": "error" in provider_response,
                    "provider_execution_requested": bool(
                        (provider_response.get("edgek_compute") or {}).get("provider_execution_requested", True)
                    ),
                },
            )

            # CRYSTALLIZE
            await crystallizer.crystallize(
                original_request=original_request,
                ir=ir,
                governance_result=governance_result,
                provider_response=provider_response,
                session_id=session_id,
                provider_type=provider_type.value
            )
            self._observe(
                mission_id,
                workspace_identity,
                event_type="mission.crystallized",
                payload_schema="beast.sensor.mission.crystallized.v1",
                payload={"response_hash": response_hash, "crystallizer_completed": True},
            )
            outcome_status = "governed_denial" if str(decision).lower() == "deny" else "completed"
            self._close_episode(
                mission_id,
                objective_hash=objective_hash,
                workspace_identity=workspace_identity,
                initial_state_hash=initial_state_hash,
                outcome={"status": outcome_status, "effect_hash": response_hash},
            )
            return governance_result, provider_response, ir
        except Exception as exc:
            error_hash = content_hash({"error_type": type(exc).__name__})
            self._observe(
                mission_id,
                workspace_identity,
                event_type="mission.failed",
                payload_schema="beast.sensor.mission.failed.v1",
                payload={"error_type": type(exc).__name__, "error_message_retained": False},
            )
            self._close_episode(
                mission_id,
                objective_hash=objective_hash,
                workspace_identity=workspace_identity,
                initial_state_hash=initial_state_hash,
                outcome={"status": "failed", "effect_hash": error_hash},
            )
            raise

    def _observe(
        self,
        mission_id: str,
        workspace_identity: str,
        *,
        event_type: str,
        payload_schema: str,
        payload: dict[str, Any],
    ) -> None:
        try:
            self.sensorium.observe_owned(
                event_type=event_type,
                source="prec_orchestrator",
                payload_schema=payload_schema,
                payload=payload,
                mission_id=mission_id,
                workspace_id=workspace_identity,
            )
        except Exception as exc:
            logger.warning("Sensorium observation failed without affecting PREC: %s", type(exc).__name__)

    def _close_episode(self, mission_id: str, **episode: Any) -> None:
        try:
            self.sensorium.close_episode(mission_id, **episode)
        except Exception as exc:
            logger.warning("Sensorium episode close failed without affecting PREC: %s", type(exc).__name__)
