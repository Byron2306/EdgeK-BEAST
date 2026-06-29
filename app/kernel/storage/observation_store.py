import sqlite3
from pathlib import Path
from app.kernel.storage.forensic_memory import ForensicMemory
from app.kernel.storage.prec_lifecycle import PRECLifecycleStore

class ObservationStore:
    """Unified facade for all system storage repositories."""
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.forensic = ForensicMemory(str(data_dir / "forensic_l4.db"))
        self.prec = PRECLifecycleStore(str(data_dir / "prec_lifecycle.db"))
        
        # Connections for domains not yet fully refactored into Store classes
        self.swarm_db = str(data_dir / "swarm.db")
        self.skills_db = str(data_dir / "skills.db")
        self.traces_db = str(data_dir / "traces.db")

    def get_forensic(self) -> ForensicMemory:
        return self.forensic
    
    def get_prec(self) -> PRECLifecycleStore:
        return self.prec
        
    def get_swarm_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.swarm_db)
        
    def get_skills_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.skills_db)
        
    def get_traces_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.traces_db)
