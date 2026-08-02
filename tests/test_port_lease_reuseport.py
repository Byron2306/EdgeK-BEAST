import socket
from app.kernel.execution.port_lease_broker import PortLeaseBroker

def test_so_reuseport_enabled():
    broker = PortLeaseBroker()
    # Reserve a port. The setsockopt is called internally.
    lease = broker.reserve("test_svc", "test_ws", port=0)
    
    # Retrieve the socket associated with the lease
    _, sock, _ = broker._leases[lease.lease_id]
    
    # Check SO_REUSEPORT value
    reuseport = sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT)
    assert reuseport == 1
    
    broker.release(lease.lease_id)
