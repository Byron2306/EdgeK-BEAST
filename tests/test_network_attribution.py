import pytest
from app.kernel.sensorium.network_attribution import attribute_socket

def test_socket_to_mission_attribution_is_content_bound():
    item=attribute_socket(socket={"identity":"socket:abc","cgroup_id":"cg:1","workspace_id":"ws:1","network_namespace":"ns:1","vrf":"vrf-commons"},process_identity="process:def",mission_id="mission:1")
    assert item.vrf == "vrf-commons" and item.digest().startswith("sha256:")
    with pytest.raises(ValueError): attribute_socket(socket={},process_identity="process:def",mission_id="m")
