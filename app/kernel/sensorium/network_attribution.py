"""Deterministic packet-to-mission attribution records."""
from __future__ import annotations
from dataclasses import dataclass, asdict
import hashlib, json

@dataclass(frozen=True)
class NetworkAttribution:
    socket_identity: str
    process_identity: str
    cgroup_id: str
    workspace_id: str
    mission_id: str
    network_namespace: str
    vrf: str
    def validate(self) -> None:
        if not self.socket_identity.startswith("socket:") or not self.process_identity.startswith("process:"): raise ValueError("typed socket/process identities are required")
        if not all((self.cgroup_id,self.workspace_id,self.mission_id,self.network_namespace,self.vrf)): raise ValueError("network attribution is incomplete")
    def digest(self) -> str:
        self.validate()
        body=json.dumps(asdict(self),sort_keys=True,separators=(",",":"))
        return "sha256:"+hashlib.sha256(body.encode()).hexdigest()

def attribute_socket(*, socket: dict, process_identity: str, mission_id: str) -> NetworkAttribution:
    required=("identity","cgroup_id","workspace_id","network_namespace","vrf")
    missing=[key for key in required if not socket.get(key)]
    if missing: raise ValueError("missing attribution fields: "+",".join(missing))
    if not process_identity.startswith("process:"): raise ValueError("process_identity must be typed")
    item=NetworkAttribution(socket["identity"],process_identity,socket["cgroup_id"],socket["workspace_id"],mission_id,socket["network_namespace"],socket["vrf"])
    item.validate(); return item
