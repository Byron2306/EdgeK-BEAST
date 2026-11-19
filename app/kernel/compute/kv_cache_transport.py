"""Compatibility alias for the plan path ``app/kernel/compute/kv_transport.py``.

The Phase 7 Cross-Engine KV Cache Transport module is defined at
``kv_transport.py``. This alias keeps existing imports and tests working
without drifting a second copy of the 41 KB implementation.
"""

from app.kernel.compute.kv_transport import *  # noqa: F401,F403
from app.kernel.compute.kv_transport import (  # noqa: F401
    CacheEngine,
    CacheLocation,
    CrossEngineKVCacheTransport,
    KVCacheBlock,
    KVCacheTransportOperation,
    bind_default_transport,
    default_transport,
)
