import os
from pathlib import Path
from app.kernel.registry.commons_space_registry import CommonsSpaceRegistry

def check():
    print(f"Default BEAST_COMMONS_ROOT: {os.environ.get('BEAST_COMMONS_ROOT')}")
    
    # Instantiate as the UI does
    registry = CommonsSpaceRegistry()
    print(f"Registry root used: {registry.root}")
    
    spaces = registry.list_spaces()
    print(f"Count: {spaces['count']}")

if __name__ == "__main__":
    check()
