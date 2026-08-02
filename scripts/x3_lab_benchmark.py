#!/usr/bin/env python3
"""X3 namespace benchmark with explicit UDP fallback and native AF_XDP lanes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "bpf" / "build" / "beast_x3_af_xdp_worker"
REDIRECT_OBJECT = ROOT / "bpf" / "build" / "beast_x3_redirect.bpf.o"

RX = r'''import socket,sys,time,json
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.bind(("10.203.0.2",45678)); s.settimeout(.2)
end=time.monotonic()+float(sys.argv[1]); n=0; b=0
while time.monotonic()<end:
 try:
  d,a=s.recvfrom(65535); n+=1; b+=len(d); s.sendto(d,a)
 except TimeoutError: pass
print(json.dumps({"packets_rx":n,"bytes_rx":b}))'''
TX = r'''import socket,sys,time,json,statistics
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.settimeout(.2); payload=b"B"*int(sys.argv[2]); end=time.monotonic()+float(sys.argv[1]); n=0; b=0; lat=[]
while time.monotonic()<end:
 t=time.perf_counter_ns(); s.sendto(payload,("10.203.0.2",45678))
 try:
  d,_=s.recvfrom(65535); n+=1; b+=len(d); lat.append((time.perf_counter_ns()-t)/1000)
 except TimeoutError: pass
lat.sort()
def q(p): return lat[min(len(lat)-1,int((len(lat)-1)*p))] if lat else 0
print(json.dumps({"packets_tx":n,"bytes_tx":b,"p50_latency_us":q(.50),"p95_latency_us":q(.95),"p99_latency_us":q(.99)}))'''
XDP_TX = r'''import socket,sys,time,json
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); payload=b"B"*int(sys.argv[2])
end=time.monotonic()+float(sys.argv[1]); interval=1.0/float(sys.argv[3]); next_send=time.monotonic(); n=0; b=0
while time.monotonic()<end:
 s.sendto(payload,("10.203.0.2",45678)); n+=1; b+=len(payload)
 next_send+=interval; delay=next_send-time.monotonic()
 if delay>0: time.sleep(delay)
print(json.dumps({"packets_tx":n,"bytes_tx":b}))'''
ECHO_TX = r'''import socket,sys,time,json
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.settimeout(.5); payload=b"B"*int(sys.argv[2])
end=time.monotonic()+float(sys.argv[1]); interval=1.0/float(sys.argv[3]); next_send=time.monotonic(); sent=0; received=0; lat=[]
while time.monotonic()<end:
 t=time.perf_counter_ns(); s.sendto(payload,("10.203.0.2",45678)); sent+=1
 try:
  d,_=s.recvfrom(65535); received+=1; lat.append((time.perf_counter_ns()-t)/1000)
 except TimeoutError: pass
 next_send+=interval; delay=next_send-time.monotonic()
 if delay>0: time.sleep(delay)
lat.sort()
def q(p): return lat[min(len(lat)-1,int((len(lat)-1)*p))] if lat else 0
print(json.dumps({"packets_sent":sent,"bytes_sent":sent*len(payload),"packets_echoed":received,"p50_latency_us":q(.50),"p95_latency_us":q(.95),"p99_latency_us":q(.99)}))'''

def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--mode", required=True, choices=("udp_fallback", "af_xdp_copy", "af_xdp_zero_copy", "af_xdp_echo"))
    p.add_argument("--duration",type=int,required=True)
    p.add_argument("--packet-size",type=int,required=True)
    p.add_argument("--rx-interface", default="eth0", help="Interface in beast-x3-rx")
    p.add_argument("--queue-id", type=int, default=0)
    p.add_argument("--packets-per-second", type=int, default=1000, help="Paced AF_XDP proof traffic rate")
    p.add_argument("--generic-xdp", action="store_true", help="Use SKB/generic XDP; required for the veth lab")
    a=p.parse_args()
    if a.mode in {"af_xdp_copy", "af_xdp_zero_copy", "af_xdp_echo"}:
        build = subprocess.run(["make", "-C", str(ROOT / "bpf"), "beast-x3-worker"], capture_output=True, text=True)
        if build.returncode:
            print(build.stderr, file=sys.stderr, end="")
            return build.returncode
        worker_cmd = [
            "ip", "netns", "exec", "beast-x3-rx", str(WORKER),
            "--interface", a.rx_interface, "--object", str(REDIRECT_OBJECT),
            "--queue", str(a.queue_id), "--duration", str(a.duration + 1),
        ]
        if a.mode == "af_xdp_zero_copy":
            worker_cmd.append("--zero-copy")
        if a.mode == "af_xdp_echo":
            worker_cmd.append("--echo")
        if a.generic_xdp:
            worker_cmd.append("--generic-xdp")
        worker = subprocess.Popen(worker_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            # The worker owns setup; wait briefly before producing measured traffic.
            time.sleep(0.25)
            try:
                traffic_script = ECHO_TX if a.mode == "af_xdp_echo" else XDP_TX
                sent = subprocess.run(
                    ["ip", "netns", "exec", "beast-x3-tx", "/usr/bin/python3", "-c", traffic_script,
                     str(a.duration), str(a.packet_size), str(a.packets_per_second)],
                    check=True, capture_output=True, text=True,
                )
            except subprocess.CalledProcessError as exc:
                print(f"X3 sender command failed (exit {exc.returncode}): {exc.stderr.strip()}", file=sys.stderr)
                return exc.returncode
            output, errors = worker.communicate(timeout=a.duration + 5)
        finally:
            if worker.poll() is None:
                worker.kill()
        if worker.returncode:
            print(errors, file=sys.stderr, end="")
            return worker.returncode
        received = json.loads(output)
        transmitted = json.loads(sent.stdout)
        if a.mode == "af_xdp_echo":
            print(json.dumps({
                **transmitted, **received,
                "echo_drops": max(0, transmitted["packets_sent"] - transmitted["packets_echoed"]),
                "latency_measurement": "af_xdp_native_echo",
            }))
            return 0
        print(json.dumps({
            **transmitted, **received,
            "drops": max(0, transmitted["packets_tx"] - received["packets_rx"]),
            "ring_saturation_events": received["fill_starvation"],
            "latency_measurement": "not_applicable_one_way_receive_worker",
        }))
        return 0
    rx=subprocess.Popen(["ip","netns","exec","beast-x3-rx","/usr/bin/python3","-c",RX,str(a.duration+1)],stdout=subprocess.PIPE,text=True)
    try:
        tx=subprocess.run(["ip","netns","exec","beast-x3-tx","/usr/bin/python3","-c",TX,str(a.duration),str(a.packet_size)],check=True,capture_output=True,text=True)
        received=json.loads(rx.communicate(timeout=3)[0]); sent=json.loads(tx.stdout)
    finally:
        if rx.poll() is None: rx.kill()
    print(json.dumps({**sent,**received,"drops":max(0,sent["packets_tx"]-received["packets_rx"]),"ring_saturation_events":0}))
    return 0
if __name__ == "__main__": raise SystemExit(main())
