print("DEBUG: factory.py imported")
from app.kernel.compute.container import container
from pathlib import Path

class ServiceFactory:
    _initialized = False

    @staticmethod
    def initialize():
        if ServiceFactory._initialized:
            print("ServiceFactory: Already initialized.")
            return

        print("ServiceFactory: Initializing...")
        from app.kernel.governance.reason import reasoner
        from app.kernel.execution.crystallize import crystallizer
        from app.kernel.governance.runtime import runtime_governor
        from app.kernel.networking.swarm import swarm_kernel
        from app.kernel.compute.enterprise import enterprise_manager
        from app.context.economizer import ContextEconomizer
        from app.kernel.execution.orchestrator import PRECOrchestrator
        from app.kernel.storage.observation_store import ObservationStore

        # Storage
        data_dir = Path(__file__).resolve().parents[2] / "data"
        observation_store = ObservationStore(data_dir)
        container.register("observation_store", observation_store)
        print("ServiceFactory: Registered observation_store.")

        # Core services
        container.register("reasoner", reasoner)
        container.register("crystallizer", crystallizer)
        container.register("runtime_governor", runtime_governor)
        container.register("swarm_kernel", swarm_kernel)
        container.register("enterprise_manager", enterprise_manager)
        
        # Orchestration
        context_economizer = ContextEconomizer(reasoner.policies)
        container.register("context_economizer", context_economizer)
        prec_orchestrator = PRECOrchestrator(context_economizer)
        container.register("prec_orchestrator", prec_orchestrator)
        
        ServiceFactory._initialized = True
        print("ServiceFactory: Initialization complete.")
