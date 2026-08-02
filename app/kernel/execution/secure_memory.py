"""Anonymous shared memory handling using memfd."""
from __future__ import annotations
import os

def create_anonymous_shared_memory(size: int, name: str = "beast_shm") -> int:
    """Create an anonymous shared memory file descriptor."""
    # MFD_CLOEXEC: close on exec, MFD_ALLOW_SEALING: allow memfd sealing
    fd = os.memfd_create(name, os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    os.ftruncate(fd, size)
    return fd
