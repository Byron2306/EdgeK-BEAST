"""Governed built-in BEAST plugins with real local invocation paths."""
from __future__ import annotations
from typing import Any, Dict, List

PLUGIN_SPECS = [
    ("beast.commons.guardian","Commons Guardian",["commons_integrity_audit","anti_gaming_audit"]),
    ("beast.crystal.matchmaker","Crystal Matchmaker",["match_compute_spaces"]),
    ("beast.inference.inverter","Inference Inverter",["build_inversion_plan"]),
    ("beast.forge.qualifier","Forge Qualifier",["qualify_forge_candidates"]),
    ("beast.market.sentinel","Marketplace Sentinel",["marketplace_gate_audit"]),
    ("beast.context.surgeon","Context Surgeon",["context_budget_plan"]),
]

def manifests(marketplace) -> List[Dict[str, Any]]:
    rows=[]
    for plugin_id,name,tools in PLUGIN_SPECS:
        manifest={
            "beast_plugin_manifest_version":"1.0","id":plugin_id,"name":name,"version":"1.0.0","publisher":"BEAST Core",
            "risk_class":"medium","entrypoint":{"kind":"python","module":"app.kernel.beast_builtin_plugins"},
            "tools":[{"name":tool,"description":f"Governed local {tool.replace('_',' ')}","inputSchema":{"type":"object","additionalProperties":True}} for tool in tools],
            "permissions":{"filesystem_read":[],"filesystem_write":[],"network_domains":[],"environment":[],"subprocess":False},
            "budget":{"max_tokens_per_call":0,"max_cost_usd_per_call":0,"max_latency_ms":5000,"calls_per_hour":1000},
            "approval_policy":{"install":True,"first_run":True,"network":False,"external_write":False,"filesystem_write":False},
        }
        rows.append(marketplace.prepare(manifest))
    return rows

def invoke(plugin_id:str,tool_name:str,payload:Dict[str,Any],services:Dict[str,Any])->Dict[str,Any]:
    allowed={plugin:set(tools) for plugin,_,tools in PLUGIN_SPECS}
    if plugin_id not in allowed or tool_name not in allowed[plugin_id]: raise ValueError("tool is not declared by this built-in plugin")
    registry=services["registry"]; economy=services["economy"]; scale=services["scale"]; testnet=services["testnet"]
    if plugin_id=="beast.commons.guardian":
        return testnet.audit() if tool_name=="anti_gaming_audit" else {"registry":registry.list_spaces()["scoreboard"],"duplicates":economy.duplicate_report(),"scale":registry.scale_readiness()}
    if plugin_id=="beast.crystal.matchmaker":
        wanted=str(payload.get("task_class") or payload.get("objective") or "").lower(); rows=[]
        for item in registry.list_spaces().get("spaces") or []:
            hay=(str(item.get("task_class"))+" "+str(item.get("name"))).lower(); score=sum(1 for token in wanted.split() if token in hay)
            if score: rows.append({"space_id":item.get("space_id"),"score":score,"verified":item.get("verifier_passed"),"adoption_state":item.get("adoption_state")})
        return {"matches":sorted(rows,key=lambda x:(-x["score"],str(x["space_id"])))[:20],"authority":"advisory_match_local_verification_required"}
    if plugin_id=="beast.inference.inverter":
        deterministic=bool(payload.get("deterministic") or payload.get("verifier_available")); return {"route":"reuse_crystallized_compute" if deterministic else "local_ollama_then_governed_escalation","cloud_call_allowed":False if deterministic else bool(payload.get("cloud_approved",False)),"required_gates":["fingerprint","privacy","verifier","approval"]}
    if plugin_id=="beast.forge.qualifier":
        candidates=registry.registration_candidates(limit=int(payload.get("limit") or 100)); kinds={}
        for item in candidates.get("candidates") or []: kinds[str(item.get("candidate_kind"))]=kinds.get(str(item.get("candidate_kind")),0)+1
        return {"candidate_count":candidates.get("count"),"kinds":kinds,"promotion_rule":"candidate-specific live verifier and mutation oracles required"}
    if plugin_id=="beast.market.sentinel":
        catalog=scale.marketplace_catalog(); return {"listing_count":catalog["listing_count"],"public_launch_ready":catalog["public_launch_ready"],"readiness":catalog["readiness"],"anti_inflation_rules":catalog["anti_inflation_rules"]}
    if plugin_id=="beast.context.surgeon":
        budget=max(256,min(int(payload.get("token_budget") or 4000),200000)); files=max(1,int(payload.get("candidate_files") or 1)); return {"token_budget":budget,"per_file_budget":max(64,budget//files),"strategy":"symbols_then_relevant_spans_then_fingerprints","raw_repository_export":False}
    raise ValueError("unknown built-in plugin or tool")
