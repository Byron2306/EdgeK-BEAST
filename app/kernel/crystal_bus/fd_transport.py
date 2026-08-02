from __future__ import annotations
from dataclasses import dataclass
import array, os, socket
from .capsule_messages import CapsuleOffer
from .sequence_ledger import SequenceLedger
@dataclass
class ReceivedCapsule:
    offer: CapsuleOffer; fd:int; peer_receipt:object
    def close(self):
        if self.fd>=0: os.close(self.fd); self.fd=-1
class CrystalBusEndpoint:
    def __init__(self,sock,*,peer_policy,workspace_id,arda_ref="",max_frame=65536):
        if sock.family!=socket.AF_UNIX or (sock.type & socket.SOCK_SEQPACKET)!=socket.SOCK_SEQPACKET: raise ValueError("AF_UNIX SOCK_SEQPACKET required")
        self.sock=sock; self.peer_policy=peer_policy; self.workspace_id=workspace_id; self.arda_ref=arda_ref; self.max_frame=max_frame; self.seq=SequenceLedger()
    @classmethod
    def pair(cls,**kwargs):
        a,b=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET); return cls(a,**kwargs),cls(b,**kwargs)
    def send_capsule(self,offer,fd):
        offer=offer.with_sequence(self.seq.next_send()); data=offer.encode()
        if len(data)>self.max_frame: raise ValueError("frame too large")
        self.sock.sendmsg([data],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array("i",[fd]))])
        return offer
    def receive_capsule(self):
        peer=self.peer_policy.admit(self.sock,workspace_id=self.workspace_id,arda_ref=self.arda_ref)
        if not peer.admitted: raise PermissionError(peer.reason)
        data,anc,flags,_=self.sock.recvmsg(self.max_frame,socket.CMSG_SPACE(8*array.array("i").itemsize))
        fds=[]
        for level,kind,payload in anc:
            if level==socket.SOL_SOCKET and kind==socket.SCM_RIGHTS:
                vals=array.array("i"); vals.frombytes(payload[:len(payload)-len(payload)%vals.itemsize]); fds.extend(vals)
        try:
            if flags & getattr(socket,"MSG_TRUNC",0): raise ValueError("truncated frame")
            offer=CapsuleOffer.decode(data); self.seq.accept(offer.sequence)
            if len(fds)!=1 or offer.fd_count!=1: raise ValueError("exactly one descriptor required")
            st=os.fstat(fds[0])
            if st.st_size!=offer.capsule_size: raise ValueError("capsule size mismatch")
            return ReceivedCapsule(offer,fds[0],peer)
        except Exception:
            for fd in fds: os.close(fd)
            raise
