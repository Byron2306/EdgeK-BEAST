import os
from pathlib import Path
from app.kernel.registry.commons_space_registry import CommonsSpaceRegistry
from app.kernel.networking.commons_spaces import MANIFEST_NAME

def debug_registry():
    # Force the registry to look at the correct directory
    data_dir = Path("/home/byron/Hivenance/edgek_beast_gateway/edgek-beast/data/commons_spaces")
    
    print(f"DEBUG: Checking directory: {data_dir}")
    print(f"DEBUG: Directory exists: {data_dir.exists()}")
    
    registry = CommonsSpaceRegistry(root=data_dir)
    print(f"Registry Root: {registry.root}")
    
    # Check if files exist at all using the registry's root
    manifests = list(registry.root.glob(f"*/{MANIFEST_NAME}"))
    print(f"Found {len(manifests)} manifests using glob from registry.root.")

    # Try registry list
    spaces = registry.list_spaces()
    print(f"Registry count from list_spaces: {spaces['count']}")

if __name__ == "__main__":
    debug_registry()
