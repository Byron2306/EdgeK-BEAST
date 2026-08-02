from __future__ import annotations
from dataclasses import dataclass
import os, socket, struct
@dataclass(frozen=True)
class PeerAdmissionReceipt:
    admitted: bool; pid:int; uid:int; gid:int; process_lease_id:str=""; reason:str=""
class PeerAdmissionPolicy:
    def __init__(self, *, expected_uid=None, process_lease_resolver=None, workspace_checker=None, arda_checker=None):
        self.expected_uid=expected_uid; self.process_lease_resolver=process_lease_resolver; self.workspace_checker=workspace_checker; self.arda_checker=arda_checker
    @staticmethod
    def credentials(sock):
        raw=sock.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,struct.calcsize("3i")); return struct.unpack("3i",raw)
    def admit(self,sock,*,workspace_id,arda_ref):
        pid,uid,gid=self.credentials(sock)
        if self.expected_uid is not None and uid!=self.expected_uid: return PeerAdmissionReceipt(False,pid,uid,gid,reason="uid_mismatch")
        lease=self.process_lease_resolver(pid) if self.process_lease_resolver else {"lease_id":f"pid:{pid}","active":True}
        if not lease or not lease.get("active"): return PeerAdmissionReceipt(False,pid,uid,gid,reason="stale_process_lease")
        if self.workspace_checker and not self.workspace_checker(lease,workspace_id): return PeerAdmissionReceipt(False,pid,uid,gid,lease.get("lease_id",""),"workspace_mismatch")
        if self.arda_checker and not self.arda_checker(lease,arda_ref): return PeerAdmissionReceipt(False,pid,uid,gid,lease.get("lease_id",""),"arda_refused")
        return PeerAdmissionReceipt(True,pid,uid,gid,lease.get("lease_id",""))
