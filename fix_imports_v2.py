import json
import re
import os
from pathlib import Path

# Load mapping
with open("new_mapping.json") as f:
    mapping = json.load(f)

# Regex to find imports: from app.kernel.something import ... or import app.kernel.something
# We want to capture the 'something' (the module) and if it has submodules, we need to handle that.
# This is tricky because the 'something' might already be app.kernel.compute.something

def fix_file(file_path):
    content = file_path.read_text()
    
    # Regex to find import statements
    # Example: from app.kernel.compute.inference_artifact_identity import ...
    # We want to extract 'inference_artifact_identity' and replace the whole import with the correct path
    
    # This is a heuristic: find all imports that start with 'app.kernel.'
    pattern = re.compile(r"(from|import)\s+(app\.kernel\.[a-zA-Z0-9._]+)")
    
    def replacement(match):
        prefix = match.group(1)
        full_module = match.group(2)
        
        # Extract the filename (last part)
        parts = full_module.split('.')
        filename = parts[-1]
        
        if filename in mapping:
            return f"{prefix} {mapping[filename]}"
        return match.group(0)
    
    new_content = pattern.sub(replacement, content)
    if new_content != content:
        file_path.write_text(new_content)
        return True
    return False

# Run on app and tests
for folder in ["app", "tests"]:
    for root, _, files in os.walk(folder):
        for file in files:
            if file.endswith(".py"):
                if fix_file(Path(root) / file):
                    print(f"Fixed imports in {Path(root) / file}")

