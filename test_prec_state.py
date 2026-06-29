
import sqlite3
from pathlib import Path
from app.kernel.storage.prec_lifecycle import PRECLifecycleStore

db_path = Path(".beast/prec_lifecycle.db")
print(f"DB exists: {db_path.exists()}")

store = PRECLifecycleStore(db_path=str(db_path))
try:
    state = store.state()
    print(state)
except Exception as e:
    print(f"Error: {e}")
