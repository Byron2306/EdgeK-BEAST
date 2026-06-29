import os
import json
from pathlib import Path

mapping = {}
kernel_dir = Path("app/kernel")
for root, _, files in os.walk(kernel_dir):
    for file in files:
        if file.endswith(".py"):
            path = Path(root) / file
            module_path = ".".join(path.with_suffix("").parts)
            mapping[file.replace(".py", "")] = module_path.replace(os.path.sep, ".")

print(json.dumps(mapping, indent=4))
