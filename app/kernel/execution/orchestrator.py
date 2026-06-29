import logging
from app.kernel.compute.perceive import ProviderType, perceiver
from app.kernel.governance.reason import reasoner, GovernanceDecision
from app.kernel.execution.execute import executor
from app.kernel.execution.crystallize import crystallizer
from app.context.economizer import ContextEconomizer

logger = logging.getLogger(__name__)

class PRECOrchestrator:
    def __init__(self, economizer: ContextEconomizer):
        self.economizer = economizer

    async def execute_cycle(self, body, provider_type: ProviderType, session_id: str = "default"):
        original_request = body.copy()
        
        # PERCEIVE
        ir = perceiver.perceive(body, provider_type)
        
        # ECONOMIZE
        economy_result = self.economizer.economize(ir)
        ir = economy_result.ir
        
        # REASON
        governance_result = reasoner.reason(ir, session_id)
        
        # EXECUTE
        effective_ir = governance_result.modified_ir or ir
        provider_response = await executor.execute(effective_ir, governance_result)
        reasoner.record_usage(effective_ir, session_id, governance_result.budget_impact)
        
        # CRYSTALLIZE
        crystallize_result = await crystallizer.crystallize(
            original_request=original_request,
            ir=ir,
            governance_result=governance_result,
            provider_response=provider_response,
            session_id=session_id,
            provider_type=provider_type.value
        )
        
        return governance_result, provider_response, ir
