from app.kernel.execution.port_lease_broker import PortLeaseBroker


class FakeSocket:
    _next_port = 41000
    def __init__(self, *_args):
        self.port = FakeSocket._next_port
        FakeSocket._next_port += 1
    def setsockopt(self, *_args): pass
    def bind(self, address):
        if address[1]: self.port = address[1]
    def getsockname(self): return ("127.0.0.1", self.port)
    def listen(self, _backlog=0): self.listening = True
    def close(self): self.closed = True


def broker():
    return PortLeaseBroker(socket_factory=FakeSocket)


def test_port_lease_is_owned_until_release():
    leases = broker()
    lease = leases.reserve("beast-gateway", "workspace-1")
    assert lease.port > 0
    assert lease.receipt_digest.startswith("sha256:")
    assert leases.snapshot() == (lease,)
    _socket, handoff = leases.take_socket_with_receipt(lease.lease_id)
    assert handoff.lease_id == lease.lease_id
    assert handoff.receipt_digest.startswith("sha256:")
    assert leases.snapshot()[0].lifecycle_state == "handed_off"
    leases.release(lease.lease_id)
    assert leases.snapshot() == ()


def test_requested_port_cannot_be_double_leased():
    leases = broker()
    first = leases.reserve("service-a", "workspace-1")
    second = leases.reserve("service-b", "workspace-1")
    assert first.port != second.port
    leases.release(first.lease_id)
    leases.release(second.lease_id)


def test_listener_generation_increments_when_identity_is_rebound():
    leases = broker()
    first = leases.reserve("service-a", "workspace-1", port=42000)
    leases.release(first.lease_id)
    second = leases.reserve("service-a", "workspace-1", port=42000)
    try:
        assert second.listener_generation == first.listener_generation + 1
    finally:
        leases.release(second.lease_id)


def test_port_lease_supports_udp_ipv6_metadata_and_authority():
    leases = broker()
    lease = leases.reserve(
        "dns-observer", "workspace-1", host="::1", family="AF_INET6", protocol="UDP",
        authority_ref="cap:1", appraisal_ref="app:1",
    )
    try:
        assert lease.family == "AF_INET6"
        assert lease.protocol == "UDP"
        assert lease.authority_ref == "cap:1"
        assert lease.appraisal_ref == "app:1"
    finally:
        leases.release(lease.lease_id)
