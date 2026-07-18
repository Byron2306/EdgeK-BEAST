"""Read-only host capability projection for the process/cgroup plane."""

from __future__ import annotations

import os
import select
import signal
from pathlib import Path
from typing import Any, Dict

from app.kernel.execution.cgroup_capsule import CgroupV2Discovery


def process_plane_capabilities(cgroup_root: Path = Path("/sys/fs/cgroup")) -> Dict[str, Any]:
    return {
        "beast_object_type": "beast_process_plane_capabilities",
        "version": "1.0",
        "authority": "read_only",
        "actuator_available": False,
        "platform": {
            "pidfd_open": hasattr(os, "pidfd_open"),
            "pidfd_send_signal": hasattr(signal, "pidfd_send_signal"),
            "epoll": hasattr(select, "epoll"),
            "procfs": Path("/proc").is_dir(),
        },
        "cgroup_v2": CgroupV2Discovery(cgroup_root).state(),
        "claim_boundary": {
            "pidfd": "live_internal_handle_not_serialized_identity",
            "signals": "authorization_required_pidfd_only",
            "cgroup_mutation": "action_specific_authorization_required",
            "cgroup_kill": "destructive_approval_receipt_required",
        },
    }
