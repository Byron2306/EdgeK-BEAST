import json
from pathlib import Path
from app.kernel.registry.commons_space_registry import CommonsSpaceRegistry
from app.kernel.networking.commons_spaces import MANIFEST_NAME

def debug_registry():
    registry = CommonsSpaceRegistry()
    print(f"Registry Root: {registry.root}")
    
    # Manually check for manifest files
    manifests = list(registry.root.glob(f"*/{MANIFEST_NAME}"))
    print(f"Found {len(manifests)} manifests directly using glob.")
    
    # Check if files exist at all
    for p in registry.root.glob("*"):
        if p.is_dir():
            manifest_path = p / MANIFEST_NAME
            exists = manifest_path.exists()
            print(f"Directory: {p.name}, Manifest exists: {exists}")
            if exists:
                print(f"  Path: {manifest_path}")

    # Try registry list
    spaces = registry.list_spaces()
    print(f"Registry count from list_spaces: {spaces['count']}")

if __name__ == "__main__":
    debug_registry()
