"""Canonical risk/phase buckets for lazy, least-authority tool exposure."""
BUCKETS=("Observe","Reason","Verify","Modify","Connect","Execute","Administer")
RISK_LEVELS=("low","medium","high","critical")

def bucket_tools(tools, *, phase="Observe", network=False, mutating=False, risk="low", approved=False, failed_tools=()):
    if phase not in BUCKETS: raise ValueError("unknown tool bucket")
    if risk not in RISK_LEVELS: raise ValueError("unknown risk level")
    allowed={"Observe"}
    if phase in BUCKETS[1:]: allowed.update(BUCKETS[:BUCKETS.index(phase)+1])
    if network: allowed.add("Connect")
    if mutating: allowed.update({"Modify","Execute"})
    if risk in {"high","critical"} and not approved: allowed.discard("Execute")
    if risk == "critical" and not approved: allowed.discard("Modify")
    failures=set(failed_tools)
    return [tool for tool in tools if str(tool.get("bucket","Observe")) in allowed and tool.get("name") not in failures]

def exposure_receipt(tools, **context):
    visible=bucket_tools(tools,**context)
    return {"buckets":list(BUCKETS),"context":context,"visible":[item.get("name") for item in visible],"hidden_count":len(tools)-len(visible)}
