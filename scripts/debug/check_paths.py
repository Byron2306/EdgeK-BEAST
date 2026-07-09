from pathlib import Path
import os
p = Path("app/kernel/registry/commons_space_registry.py").resolve()
print(f"Path: {p}")
print(f"Parents[2]: {p.parents[2]}")
