
import json
from pathlib import Path
from app.cli.api import load_local_commons_snapshot

def test_commons_snapshot():
    snapshot = load_local_commons_snapshot()
    print(json.dumps(snapshot, indent=2, default=str))

if __name__ == "__main__":
    test_commons_snapshot()
