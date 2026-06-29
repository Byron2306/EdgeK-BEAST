import sqlite3
from pathlib import Path
from typing import Optional

class BaseStore:
    def __init__(self, db_path: Optional[str] = None, default_db_name: str = "default.db"):
        if db_path is None:
            db_path = Path(__file__).resolve().parents[2] / "data" / default_db_name
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        # We must avoid circular imports. This base class is used by stores
        # which are initialized by the container.
        return sqlite3.connect(str(self.db_path))

    def _init_db(self):
        raise NotImplementedError("Subclasses must implement _init_db")
