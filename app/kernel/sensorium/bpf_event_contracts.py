from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import IntEnum
import hashlib
import json
import time
from typing import Any, Mapping

SCHEMA_VERSION = "beast.bpf.sensorium.v1"
MAX_COMM = 16
MAX_FILENAME = 96
MAX_PATH = 192


class BPFEventKind(IntEnum):
    EXEC = 1
    EXIT = 2
    TCP_CONNECT = 3
    SOCKET_BIND = 4
    FILE_MUTATION = 5
    SCHED_LATENCY = 6
    NET_BYTES = 7
    LOSS = 255


@dataclass(frozen=True, slots=True)
class KernelObservation:
    kind: BPFEventKind
    timestamp_ns: int
    cpu: int
    pid: int
    tgid: int
    uid: int
    gid: int
    cgroup_id: int
    sequence: int
    comm: str = ""
    fields: Mapping[str, int | str | bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.timestamp_ns < 0 or self.sequence < 0:
            raise ValueError("negative timestamp or sequence")
        for name, value in (("cpu", self.cpu), ("pid", self.pid), ("tgid", self.tgid), ("uid", self.uid), ("gid", self.gid)):
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        object.__setattr__(self, "comm", self.comm[:MAX_COMM])
        safe: dict[str, int | str | bool] = {}
        forbidden = {"payload", "secret", "token", "private_key", "capability", "fd"}
        for key, value in self.fields.items():
            k = str(key)
            if k.lower() in forbidden:
                raise ValueError(f"forbidden raw field: {k}")
            if isinstance(value, str):
                value = value[:MAX_PATH]
            elif not isinstance(value, (int, bool)):
                raise TypeError(f"unsupported field type for {k}")
            safe[k] = value
        object.__setattr__(self, "fields", safe)

    @property
    def digest(self) -> str:
        body = json.dumps(self.to_dict(include_digest=False), sort_keys=True, separators=(",", ":")).encode()
        return "sha256:" + hashlib.sha256(body).hexdigest()

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        result = asdict(self)
        result["kind"] = self.kind.name.lower()
        result["schema"] = SCHEMA_VERSION
        if include_digest:
            result["observation_digest"] = self.digest
        return result


@dataclass(frozen=True, slots=True)
class BPFHealthReceipt:
    started_ns: int
    observed: int
    emitted: int
    kernel_reserve_failures: int
    userspace_decode_failures: int
    sequence_gaps: int
    ring_poll_errors: int
    authority: str = "observation_only"
    raw_payload_retained: bool = False

    @property
    def loss_total(self) -> int:
        return self.kernel_reserve_failures + self.userspace_decode_failures + self.sequence_gaps + self.ring_poll_errors

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["loss_total"] = self.loss_total
        d["healthy"] = self.loss_total == 0
        d["ended_ns"] = time.monotonic_ns()
        return d
