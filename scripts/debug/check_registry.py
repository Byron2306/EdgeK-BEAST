
import json
from app.kernel.registry.commons_space_registry import CommonsSpaceRegistry

def check_registry():
    registry = CommonsSpaceRegistry()
    spaces = registry.list_spaces()
    print(json.dumps(spaces, indent=2, default=str))

if __name__ == "__main__":
    check_registry()
