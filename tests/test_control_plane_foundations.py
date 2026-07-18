import pytest
from app.kernel.networking.service_registry import ServiceRegistry
from app.kernel.capability.tool_buckets import bucket_tools, exposure_receipt
from app.kernel.compute.resource_executor import ResourceExecutor, WorkloadProfile
from app.kernel.workspaces.byron_manifest import load
from app.kernel.workspaces.workspace_identity import discover, stable_workspace_uuid

def test_service_registry_generates_unique_hosts_and_proxy():
    registry=ServiceRegistry({"beast":{"hostname":"beast.test","upstream":"127.0.0.1:8101","port":8101}})
    assert "beast.test" in registry.hosts_entries() and "proxy_pass" in registry.nginx_config()
    assert registry.resolve("beast.test").port == 8101
    with pytest.raises(ValueError): ServiceRegistry({"bad":{"hostname":"public.example","upstream":"127.0.0.1:1","port":1}})

def test_tool_buckets_are_phase_and_risk_aware():
    tools=[{"name":"read","bucket":"Observe"},{"name":"deploy","bucket":"Execute"}]
    assert [x["name"] for x in bucket_tools(tools,phase="Observe")] == ["read"]
    assert bucket_tools(tools,phase="Execute",risk="high")==[{"name":"read","bucket":"Observe"}]
    assert exposure_receipt(tools,phase="Execute",risk="high")["hidden_count"] == 1

def test_resource_executor_requires_hazardous_approval():
    executor=ResourceExecutor(max_workers=1)
    with pytest.raises(PermissionError): executor.submit(WorkloadProfile("hazardous"),lambda:1)
    assert executor.submit(WorkloadProfile("interactive"),lambda:2).result()==2
    assert executor.snapshot()["interactive"]["completed"] == 1
    executor.shutdown()

def test_resource_executor_has_bounded_admission_and_exclusive_keys():
    executor=ResourceExecutor(max_workers=1,queue_depth=0)
    blocker=__import__("threading").Event()
    first=executor.submit(WorkloadProfile("exclusive",exclusive_keys=("workspace:1",)),blocker.wait,.5)
    with pytest.raises(RuntimeError): executor.submit(WorkloadProfile("exclusive",exclusive_keys=("workspace:1",)),lambda:2)
    blocker.set(); first.result(); assert executor.snapshot()["exclusive"]["rejected"]==1
    executor.shutdown()

def test_workspace_identity_and_inherited_manifests(tmp_path):
    (tmp_path/".byron").mkdir(); (tmp_path/".byron"/"project.yaml").write_text("family: beast\nexclusions: [artifacts]\n",encoding="utf-8")
    identity=discover(tmp_path,workspace_uuid=stable_workspace_uuid(tmp_path))
    assert identity.matches(identity) and identity.digest().startswith("sha256:")
    manifest=load(tmp_path)
    assert manifest["family"]=="beast" and "artifacts" in manifest["exclusions"]
