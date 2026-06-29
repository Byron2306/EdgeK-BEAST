import pytest
from app.kernel.compute.container import container
from app.kernel.compute.factory import ServiceFactory
from app.kernel.storage.observation_store import ObservationStore
from pathlib import Path

# Integration test to check if core services are containerized and accessible
def test_prec_pipeline_service_availability():
    # Setup - Manually initialize the container to satisfy pytest collection
    data_dir = Path(__file__).resolve().parents[1] / "data"
    observation_store = ObservationStore(data_dir)
    container.register("observation_store", observation_store)
    
    ServiceFactory.initialize()
    
    assert container.get("observation_store") is not None
    assert container.get("prec_orchestrator") is not None
