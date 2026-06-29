class ServiceContainer:
    def __init__(self):
        self._services = {}
    
    def register(self, name: str, service: object):
        self._services[name] = service
        
    def get(self, name: str) -> object:
        if name == "observation_store" and name not in self._services:
            from pathlib import Path
            from app.kernel.storage.observation_store import ObservationStore

            data_dir = Path(__file__).resolve().parents[2] / "data"
            self.register(name, ObservationStore(data_dir))
        if name not in self._services:
            raise ValueError(f"Service '{name}' not registered in container.")
        return self._services[name]

# Global container instance
container = ServiceContainer()
