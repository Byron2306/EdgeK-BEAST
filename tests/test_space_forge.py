from app.kernel.commons.space_forge import SpaceForge


class FakeSocket:
    def __init__(self,*a): pass
    def setsockopt(self,*a): pass
    def bind(self,a): self.addr=a
    def getsockname(self): return ('127.0.0.1', 41000)
    def close(self): pass


def test_space_manifest_is_bounded_and_signed():
    space=SpaceForge().validate({"space_id":"beast/lab","image_digest":"sha256:"+"a"*64,"cpu":2,"memory_mb":512,"mounts":["commons://datasets/x"],"outbound_policy":"deny","port":0,"signature":"sig"})
    assert space.port == 0 and space.outbound_policy == "deny"

def test_space_receives_port_lease():
    forge=SpaceForge()
    forge.broker._socket_factory=FakeSocket
    space=forge.validate({"space_id":"beast/lab","image_digest":"sha256:"+"a"*64,"cpu":1,"memory_mb":128,"outbound_policy":"deny","port":0,"signature":"sig"})
    lease=forge.lease_port(space, workspace_id="w1",capability_ref="cap:1",policy_generation="policy:1")
    assert lease.service_id == "beast/lab"
    assert lease.authority_ref==space.authority_ref and lease.capability_ref=="cap:1"
    assert lease.policy_generation=="policy:1"
    forge.broker.release(lease.lease_id)
