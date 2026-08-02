from __future__ import annotations
import fcntl, os
from .sealed_capsule import REQUIRED_SEALS

def inspect_capsule_fd(fd: int) -> dict:
    st = os.fstat(fd); seals = fcntl.fcntl(fd, fcntl.F_GET_SEALS)
    return {"size_bytes": st.st_size, "seal_bitmap": seals, "required_seals_present": seals & REQUIRED_SEALS == REQUIRED_SEALS, "proc_link": os.readlink(f"/proc/self/fd/{fd}") if os.path.exists(f"/proc/self/fd/{fd}") else ""}
