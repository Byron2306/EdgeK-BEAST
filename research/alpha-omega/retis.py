"""RETIS v1: bounded loopback transport observation; no external egress."""
import socket, threading, hashlib, time, json, sys, subprocess, shutil
from resurrectio import Ed25519PrivateKey
from evidence import sign,digest,verify_chain
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat

def transfer(kind,size):
    if kind not in ("tcp","udp") or type(size) is not int or not 1<=size<=1048576:
        raise ValueError("invalid transfer")
    data=hashlib.shake_256(str(size).encode()).digest(size)
    typ=socket.SOCK_STREAM if kind=="tcp" else socket.SOCK_DGRAM
    received=bytearray(); errors=[]
    with socket.socket(socket.AF_INET,typ) as server:
        server.bind(("127.0.0.1",0)); server.settimeout(5)
        endpoint=server.getsockname()
        if kind=="tcp": server.listen(1)
        def reader():
            try:
                if kind=="tcp":
                    with server.accept()[0] as conn:
                        conn.settimeout(5)
                        while len(received)<size:
                            b=conn.recv(65536)
                            if not b: break
                            received.extend(b)
                else:
                    while len(received)<size:
                        b,peer=server.recvfrom(1200)
                        received.extend(b)
                        server.sendto(hashlib.sha256(b).digest(),peer)
            except Exception as e: errors.append(repr(e))
        t=threading.Thread(target=reader); t.start()
        sent=0; ack_bytes=0; start=time.monotonic_ns()
        with socket.socket(socket.AF_INET,typ) as client:
            client.settimeout(5); client.connect(endpoint)
            source=client.getsockname()
            if kind=="tcp": client.sendall(data); sent=size; client.shutdown(socket.SHUT_WR)
            else:
                for i in range(0,size,1200):
                    b=data[i:i+1200]; sent+=client.send(b)
                    ack=client.recv(32); ack_bytes+=len(ack)
                    if ack!=hashlib.sha256(b).digest(): raise ValueError("ack mismatch")
        t.join(6); elapsed=time.monotonic_ns()-start
        if t.is_alive() or errors or bytes(received)!=data: raise RuntimeError("transfer mismatch "+str(errors))
    return dict(transport=kind,source=list(source),destination=list(endpoint),payload_sent=sent,payload_received=len(received),application_ack_bytes=ack_bytes,wall_ns=elapsed,payload_sha256=hashlib.sha256(data).hexdigest(),wire_bytes=None,wire_status="UNMEASURED",external_egress_observed=False)

def run():
    rows=[transfer(k,n) for k in ("tcp","udp") for n in (1544,262144,1048576) for _ in range(3)]
    key=Ed25519PrivateKey.generate(); campaign=digest(rows); chain=[]; prev=""
    for row in rows:
        e=sign(key,campaign,"retis-local","network",len(chain),prev,row);chain.append(e);prev=digest(e)
    verify_chain(chain,{"retis-local":("network",key.public_key())},campaign,len(rows),prev)
    return dict(rows=rows,receipts=chain,head=prev,campaign=campaign,public_key=key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw).hex(),capabilities={k:bool(shutil.which(k)) for k in ("ip","bpftool","tcpdump")},xdp_exercised=False,af_xdp_exercised=False,namespace_isolation=False,independent_custody=False,paid_execution_authorized=False,scientific_authorization=False)
if __name__=="__main__": print(json.dumps(run(),indent=2))
