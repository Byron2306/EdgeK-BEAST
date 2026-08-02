from dataclasses import dataclass, asdict
from enum import Enum
from hashlib import sha256
import json

class TransportMode(str, Enum):
    AF_XDP_ZERO_COPY="af_xdp_zero_copy"
    AF_XDP_COPY="af_xdp_copy"
    UDP_FALLBACK="udp_fallback"

@dataclass(frozen=True)
class X3LabConfig:
    namespace_tx:str="beast-x3-tx"; namespace_rx:str="beast-x3-rx"
    veth_tx:str="beastx3tx"; veth_rx:str="beastx3rx"
    frame_size:int=2048; frame_count:int=4096; packet_size:int=512; duration_seconds:int=10
    production_interface:str|None=None; allow_production_nic:bool=False
    def validate(self):
        if self.production_interface and not self.allow_production_nic: raise ValueError("production interface requires explicit override")
        if len(self.veth_tx)>15 or len(self.veth_rx)>15: raise ValueError("interface name too long")
        if self.frame_size not in (2048,4096): raise ValueError("unsupported frame size")
        if not 256<=self.frame_count<=65536: raise ValueError("frame count out of bounds")
        if not 64<=self.packet_size<=self.frame_size: raise ValueError("packet size out of bounds")
        if not 1<=self.duration_seconds<=300: raise ValueError("duration out of bounds")

@dataclass(frozen=True)
class X3Metrics:
    mode:TransportMode; packets_tx:int; packets_rx:int; bytes_tx:int; bytes_rx:int
    drops:int; ring_saturation_events:int; p50_latency_us:float; p95_latency_us:float; p99_latency_us:float
    cpu_user_seconds:float; cpu_system_seconds:float
    @property
    def delivery_ratio(self): return self.packets_rx/self.packets_tx if self.packets_tx else 0.0
    def validate(self):
        if min(self.packets_tx,self.packets_rx,self.bytes_tx,self.bytes_rx,self.drops,self.ring_saturation_events)<0: raise ValueError("negative counter")
        if self.packets_rx>self.packets_tx: raise ValueError("rx exceeds tx")

@dataclass(frozen=True)
class X3Receipt:
    config:X3LabConfig; measurements:tuple[X3Metrics,...]; selected_mode:TransportMode
    fallback_available:bool; production_nic_touched:bool; authority:str="transport_laboratory_only"
    @property
    def digest(self):
        body=asdict(self); body["selected_mode"]=self.selected_mode.value
        for m in body["measurements"]: m["mode"]=m["mode"].value if hasattr(m["mode"],"value") else m["mode"]
        return "sha256:"+sha256(json.dumps(body,sort_keys=True,separators=(",",":")).encode()).hexdigest()
