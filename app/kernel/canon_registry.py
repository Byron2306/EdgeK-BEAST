"""Compatibility import for the refactored Canon registry module.

DEPRECATED_COMPAT_IMPORT: new code should import
`app.kernel.registry.canon_registry` directly.
"""

from app.kernel.registry.canon_registry import *  # noqa: F401,F403
