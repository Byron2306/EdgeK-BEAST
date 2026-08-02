import os
from app.kernel.execution.secure_memory import create_anonymous_shared_memory

def test_memfd_creation():
    fd = create_anonymous_shared_memory(1024, "test_shm")
    assert fd >= 0
    # Verify it's a file
    assert os.path.exists(f"/proc/self/fd/{fd}")
    os.close(fd)
