import json, resource, subprocess
from pathlib import Path
from .x3_contracts import *
from .x3_policy import choose_mode

class X3Lab:
    def __init__(self,config,runner=subprocess.run): config.validate(); self.c=config; self.run=runner
    def preflight(self):
        if not Path("/sys/kernel/btf/vmlinux").exists(): raise RuntimeError("kernel BTF unavailable")
    def cmd(self,*args,check=True): return self.run(args,text=True,capture_output=True,check=check)
    def setup(self):
        if self.c.production_interface: raise RuntimeError("production NIC disabled in X3")
        self.cmd("ip","netns","add",self.c.namespace_tx); self.cmd("ip","netns","add",self.c.namespace_rx)
        self.cmd("ip","link","add",self.c.veth_tx,"type","veth","peer","name",self.c.veth_rx)
        self.cmd("ip","link","set",self.c.veth_tx,"netns",self.c.namespace_tx); self.cmd("ip","link","set",self.c.veth_rx,"netns",self.c.namespace_rx)
        self.cmd("ip","-n",self.c.namespace_tx,"link","set","lo","up")
        self.cmd("ip","-n",self.c.namespace_rx,"link","set","lo","up")
        self.cmd("ip","-n",self.c.namespace_tx,"addr","add","10.203.0.1/30","dev",self.c.veth_tx)
        self.cmd("ip","-n",self.c.namespace_rx,"addr","add","10.203.0.2/30","dev",self.c.veth_rx)
        self.cmd("ip","-n",self.c.namespace_tx,"link","set",self.c.veth_tx,"up")
        self.cmd("ip","-n",self.c.namespace_rx,"link","set",self.c.veth_rx,"up")
    def cleanup(self):
        for ns in (self.c.namespace_tx,self.c.namespace_rx): self.cmd("ip","netns","del",ns,check=False)
    def benchmark(self,binary,mode):
        before=resource.getrusage(resource.RUSAGE_CHILDREN)
        cp=self.cmd(binary,"--mode",mode.value,"--duration",str(self.c.duration_seconds),"--packet-size",str(self.c.packet_size))
        after=resource.getrusage(resource.RUSAGE_CHILDREN); d=json.loads(cp.stdout)
        return X3Metrics(mode,int(d["packets_tx"]),int(d["packets_rx"]),int(d["bytes_tx"]),int(d["bytes_rx"]),int(d.get("drops",0)),int(d.get("ring_saturation_events",0)),float(d["p50_latency_us"]),float(d["p95_latency_us"]),float(d["p99_latency_us"]),after.ru_utime-before.ru_utime,after.ru_stime-before.ru_stime)
    def ceremony(self,binary):
        self.preflight(); ms=[]
        try:
            self.setup()
            for mode in (TransportMode.AF_XDP_ZERO_COPY,TransportMode.AF_XDP_COPY,TransportMode.UDP_FALLBACK):
                try: ms.append(self.benchmark(binary,mode))
                except Exception:
                    if mode is TransportMode.UDP_FALLBACK: raise
            return X3Receipt(self.c,tuple(ms),choose_mode(ms),True,False)
        finally: self.cleanup()
