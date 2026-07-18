"""Identical sealed uplift protocol across Ollama and independent llama.cpp."""
from __future__ import annotations

import hashlib
import inspect
import json
import random
import subprocess
import time
import urllib.request
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.kernel.compute.milestone11_uplift import (
    LANES, LaneAttempt, Milestone11Experiment, OllamaNativeAdapter, _sha,
)
from app.kernel.sensorium.contracts_hash import content_hash


class LlamaCppServerAdapter:
    adapter_id = "llama-cpp-openai-chat-v1"
    runtime_family = "llama.cpp"

    def __init__(self, endpoint: str, model: str = "qwen2.5-0.5b-q4_k_m"):
        self.endpoint, self.model = endpoint.rstrip("/"), model

    def generate(self, prompt: str, seed: int) -> tuple[str, int, int]:
        body = json.dumps({"model": self.model, "messages":[{"role":"user","content":prompt}],
            "stream":False,"temperature":0,"seed":seed,"max_tokens":96}).encode()
        request = urllib.request.Request(self.endpoint+"/v1/chat/completions",data=body,headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(request,timeout=120) as response: result=json.loads(response.read())
        usage=result.get("usage") or {}; text=result["choices"][0]["message"]["content"]
        return str(text),int(usage.get("prompt_tokens") or 0),int(usage.get("completion_tokens") or 0)


class Milestone11CrossRuntimeExperiment:
    def __init__(self, *, ollama_endpoint: str = "http://127.0.0.1:11434",
                 llama_endpoint: str = "http://127.0.0.1:11435", seed: int = 731947,
                 model_blob: Path = Path("/home/byron/.ollama/models/blobs/sha256-c5396e06af294bd101b30dce59131a76d2b773e76950acc870eda801d3ab0515"),
                 llama_binary: Path = Path("/home/byron/.local/lib/beast/llama.cpp-a582222/bin/llama-server")):
        self.seed,self.model_blob,self.llama_binary=int(seed),Path(model_blob),Path(llama_binary)
        self.adapters=(OllamaNativeAdapter(ollama_endpoint,"qwen2.5:0.5b"),LlamaCppServerAdapter(llama_endpoint))

    @staticmethod
    def _file_digest(path: Path) -> str: return _sha(path.read_bytes())

    def run(self, *, tasks: int = 12, minimum_uplift: float = .25) -> dict[str,Any]:
        if tasks < 8: raise ValueError("cross-runtime preregistration requires at least eight tasks")
        crystal={"contract_id":"beast.crystal.sha256-utf8.v2","operation":"sha256_utf8","parameters":["bounded_utf8"],
            "max_bytes":4096,"applicability":{"nonempty":True,"domain":"bytes/utf8","freshness_epoch":1},
            "authority":"pure-transform/no-ambient-authority","provider_state":None,
            "verifier":"python.hashlib.sha256/exact-lowercase-hex"}
        crystal_digest=content_hash(crystal); rng=random.Random(self.seed)
        values=["".join(rng.choice("abcdefghijkmnpqrstuvwxyz23456789") for _ in range(rng.randint(29,83))) for _ in range(tasks)]
        task_commitment=content_hash([_sha(v) for v in values])
        identities=self._identities(crystal_digest)
        prereg={"protocol":"beast.milestone11.cross-runtime-paired-uplift.v1","seed":self.seed,"sample_size_per_runtime":tasks,
            "minimum_useful_uplift":minimum_uplift,"lanes":LANES,"runtime_families":["ollama","llama.cpp"],
            "task_commitment":task_commitment,"crystal_digest":crystal_digest,"alpha":.05,
            "required_gates":["distinct_runtime_families>=2","independent_runtime_adapter_verified","provider_absent_replay","negative_controls_safe"]}
        schedule=[(adapter.adapter_id,index,lane) for adapter in self.adapters for index in range(tasks) for lane in LANES]
        rng.shuffle(schedule); adapter_map={item.adapter_id:item for item in self.adapters}; attempts=[]
        for adapter_id,index,lane in schedule:
            adapter=adapter_map[adapter_id]; value=values[index]; expected=hashlib.sha256(value.encode()).hexdigest()
            task_id=_sha(f"{task_commitment}:{index}"); prompt=Milestone11Experiment._prompt(lane,value)
            initial=content_hash({"task":task_id,"value_digest":_sha(value),"effect_state":"empty","runtime":adapter.runtime_family})
            started=time.perf_counter(); refused=False; calls=pt=ct=0
            if lane in {"raw_model","ordinary_context","reuse_disabled"}:
                output,pt,ct=adapter.generate(prompt,self.seed+index);calls=1
            elif lane=="promoted_crystal": output=Milestone11Experiment._execute_crystal(value,crystal,crystal_digest)
            else: output="";refused=True
            latency=(time.perf_counter()-started)*1000
            normalized=output.strip().lower().strip("`").removeprefix("sha256:").strip()
            passed=refused if lane in {"sham_crystal","stale_crystal","wrong_domain_crystal"} else normalized==expected
            authority=content_hash({"task":task_id,"adapter":adapter_id,"lane":lane,"crystal":crystal_digest,
                "decision":"execute" if lane=="promoted_crystal" else ("refuse" if refused else "provider")})
            attempts.append(LaneAttempt(task_id,adapter_id,lane,expected,_sha(prompt),_sha(output),passed,refused,calls,pt,ct,
                round(latency,3),0,initial,authority))
        statistics={}; runtime_gates={}
        for adapter in self.adapters:
            rows=[item for item in attempts if item.adapter_id==adapter.adapter_id]
            raw={item.task_id:item for item in rows if item.lane=="raw_model"}; full={item.task_id:item for item in rows if item.lane=="promoted_crystal"}
            pairs=[(raw[key].passed,full[key].passed) for key in sorted(raw)]
            effect=sum(int(b)-int(a) for a,b in pairs)/tasks;bo=sum(a and not b for a,b in pairs);ao=sum(b and not a for a,b in pairs)
            ci=Milestone11Experiment._bootstrap_ci(pairs,self.seed);p=Milestone11Experiment._mcnemar(bo,ao)
            controls=[item for item in rows if item.lane in LANES[4:]]
            provider_absent=all(item.provider_calls==0 and item.passed for item in full.values())
            safe=all(item.refused and item.passed and item.unsafe_effects==0 for item in controls)
            uplift=all(item.passed for item in full.values()) and effect>=minimum_uplift and ci[0]>=minimum_uplift and p<.05
            statistics[adapter.runtime_family]={"adapter_id":adapter.adapter_id,"raw_successes":sum(item.passed for item in raw.values()),
                "full_successes":sum(item.passed for item in full.values()),"paired_effect":effect,"bootstrap_95ci":ci,"exact_mcnemar_p":p}
            runtime_gates[adapter.runtime_family]={"uplift_verified":uplift,"provider_absent_replay":provider_absent,"negative_controls_safe":safe}
        families={item["runtime_family"] for item in identities}; independent=len(families)>=2 and len({item["binary_digest"] for item in identities})>=2
        gates={"distinct_runtime_families":len(families),"independent_runtime_adapter_verified":independent,
            "provider_absent_replay":all(item["provider_absent_replay"] for item in runtime_gates.values()),
            "negative_controls_safe":all(item["negative_controls_safe"] for item in runtime_gates.values()),
            "uplift_verified_both":all(item["uplift_verified"] for item in runtime_gates.values())}
        gates["milestone_11_runtime_independence_complete"]=bool(gates["distinct_runtime_families"]>=2 and gates["independent_runtime_adapter_verified"] and gates["provider_absent_replay"] and gates["negative_controls_safe"] and gates["uplift_verified_both"])
        packet={"schema":"beast.milestone11.cross-runtime-evidence.v1",
            "claim":"BEAST produced a statistically verified fixed-model system uplift by replacing an unsuitable inference operation with an authorized, promoted, provider-absent deterministic Crystal.",
            "weight_update_claim":False,"preregistration":prereg,"preregistration_digest":content_hash(prereg),
            "sealed_tasks":{"count":tasks,"commitment":task_commitment,"revealed_value_digests":[_sha(v) for v in values]},
            "runtime_identities":identities,"crystal_ir":crystal,"crystal_digest":crystal_digest,
            "verifier_digest":content_hash({"normalization":"strip/lower/remove-sha256-prefix","objective":"hashlib.sha256 exact"}),
            "attempts":[asdict(item) for item in attempts],"statistics":statistics,"runtime_gates":runtime_gates,"gates":gates,
            "accounting":{"all_attempts_retained":len(attempts)==len(self.adapters)*tasks*len(LANES),
                "provider_calls":sum(item.provider_calls for item in attempts),"prompt_tokens":sum(item.prompt_tokens for item in attempts),
                "completion_tokens":sum(item.completion_tokens for item in attempts)}}
        packet["evidence_digest"]=content_hash(packet);return packet

    def _identities(self, crystal_digest: str) -> list[dict[str,Any]]:
        ollama_binary=Path(subprocess.check_output(["bash","-lc","command -v ollama"],text=True).strip())
        values=[]
        for adapter,binary,version in ((self.adapters[0],ollama_binary,subprocess.check_output([str(ollama_binary),"--version"],text=True,stderr=subprocess.STDOUT).strip()),
                                       (self.adapters[1],self.llama_binary,subprocess.check_output([str(self.llama_binary),"--version"],text=True,stderr=subprocess.STDOUT,env={"LD_LIBRARY_PATH":str(self.llama_binary.parent.parent/"lib")}).strip())):
            values.append({"adapter_id":adapter.adapter_id,"runtime_family":adapter.runtime_family,"endpoint":adapter.endpoint,
                "endpoint_identity":content_hash({"url":adapter.endpoint,"runtime_family":adapter.runtime_family}),
                "binary_path":str(binary),"binary_digest":self._file_digest(binary),"runtime_version":version,
                "model_file":str(self.model_blob),"model_file_digest":self._file_digest(self.model_blob),"quantization":"Q4_K_M",
                "decoding":{"temperature":0,"seed":self.seed,"max_tokens":96},
                "adapter_implementation_digest":_sha(inspect.getsource(type(adapter))),"crystal_digest":crystal_digest})
        return values


def verify_cross_runtime_packet(packet: dict[str,Any]) -> None:
    body=dict(packet); supplied=body.pop("evidence_digest",None)
    if supplied!=content_hash(body): raise ValueError("cross-runtime evidence digest mismatch")
    identities=packet.get("runtime_identities") or []
    if len(identities)<2 or len({item.get("runtime_family") for item in identities})<2:
        raise ValueError("two runtime identities are required")
    required=("binary_digest","runtime_version","model_file_digest","quantization","decoding",
              "adapter_implementation_digest","endpoint_identity","crystal_digest")
    if any(not all(item.get(field) for field in required) for item in identities):
        raise ValueError("runtime identity binding is incomplete")
    if len({item["binary_digest"] for item in identities})<2:
        raise ValueError("runtime binaries are not independent")
    if len({item["model_file_digest"] for item in identities})!=1 or len({item["crystal_digest"] for item in identities})!=1:
        raise ValueError("runtime lanes did not share exact model and crystal identities")
    tasks=int(packet["sealed_tasks"]["count"]); attempts=packet.get("attempts") or []
    if len(attempts)!=len(identities)*tasks*len(LANES):
        raise ValueError("cross-runtime attempt ledger is incomplete")
    for identity in identities:
        rows=[row for row in attempts if row["adapter_id"]==identity["adapter_id"]]
        task_ids={row["task_id"] for row in rows}
        if len(task_ids)!=tasks or any({row["lane"] for row in rows if row["task_id"]==task}!=set(LANES) for task in task_ids):
            raise ValueError("runtime paired lane matrix is incomplete")
        full=[row for row in rows if row["lane"]=="promoted_crystal"]
        controls=[row for row in rows if row["lane"] in LANES[4:]]
        if not all(row["passed"] and row["provider_calls"]==0 for row in full):
            raise ValueError("provider-absent recurrence failed")
        if not all(row["passed"] and row["refused"] and row["unsafe_effects"]==0 for row in controls):
            raise ValueError("negative controls failed")
    gates=packet["gates"]
    if not (gates["distinct_runtime_families"]>=2 and gates["independent_runtime_adapter_verified"]
            and gates["provider_absent_replay"] and gates["negative_controls_safe"]
            and gates["milestone_11_runtime_independence_complete"]):
        raise ValueError("cross-runtime decisive gate failed")
