"""Restart-safe user-mode socket ownership for the BEAST Port Lease Broker.

The guardian is deliberately a separate process boundary.  It owns listening
sockets while IDE/gateway/broker processes come and go, persists generation
and lifecycle evidence in SQLite, and duplicates descriptors to authenticated
clients with SCM_RIGHTS.
"""
from __future__ import annotations

import array
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import threading
import time
import uuid
from typing import Any, Callable, Mapping

from app.kernel.compute.crystal_bus import peer_credentials
from app.kernel.execution.port_lease_broker import PortLease, SocketHandoffReceipt
from app.kernel.execution.guardian_authorization import capability_mapping
from app.kernel.sensorium.contracts import ProcessLease


MAX_FRAME = 256 * 1024
ACTIVE_STATES = {"reserved", "handed_off", "healthy", "unhealthy"}


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: Mapping[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


class GuardianProtocolError(RuntimeError):
    pass


class SocketGuardianServer:
    """SOCK_SEQPACKET service which remains alive across broker restarts."""

    def __init__(
        self, socket_path: str | Path, ledger_path: str | Path, *,
        expected_uid: int | None = None, signer=None, guardian_id: str = "beast.socket-guardian.v1",
        require_authority: bool = True, require_process_lease: bool = True,
        authorize: Callable[[Mapping[str, Any]], bool] | None = None,
        service_registry=None, health_probe: Callable[[PortLease], bool] | None = None,
        max_active_leases: int = 128,
    ):
        self.socket_path = Path(socket_path)
        self.ledger_path = Path(ledger_path)
        self.expected_uid = os.getuid() if expected_uid is None else expected_uid
        self.signer = signer
        self.guardian_id = guardian_id
        self.require_authority = require_authority
        self.require_process_lease = require_process_lease
        self.authorize = authorize
        self.service_registry = service_registry
        self.health_probe = health_probe
        self.max_active_leases = max(1, int(max_active_leases))
        if self.require_authority and (self.authorize is None or self.signer is None):
            raise RuntimeError("protected guardian requires an authorizer and receipt signer")
        self._server: socket.socket | None = None
        self._sockets: dict[str, socket.socket] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._initialize_ledger()

    def _connect_db(self) -> sqlite3.Connection:
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.ledger_path), timeout=10, isolation_level=None)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _initialize_ledger(self) -> None:
        connection = self._connect_db()
        try:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS generations (identity_key TEXT PRIMARY KEY, generation INTEGER NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS leases (lease_id TEXT PRIMARY KEY, payload TEXT NOT NULL, "
                "lifecycle_state TEXT NOT NULL, health_state TEXT NOT NULL, updated_at REAL NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS lifecycle_events (event_id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "lease_id TEXT NOT NULL, previous_state TEXT NOT NULL, next_state TEXT NOT NULL, "
                "reason TEXT NOT NULL, peer_pid INTEGER NOT NULL, peer_uid INTEGER NOT NULL, "
                "created_at REAL NOT NULL, payload_digest TEXT NOT NULL)"
            )
            # A guardian restart loses its own descriptors. Never claim that
            # receipts left by an earlier guardian instance are still live.
            rows = connection.execute(
                "SELECT lease_id, payload, lifecycle_state FROM leases WHERE lifecycle_state IN "
                "('reserved','handed_off','healthy','unhealthy')"
            ).fetchall()
            for lease_id, payload_text, previous in rows:
                payload = json.loads(payload_text)
                payload["lifecycle_state"] = "orphaned_guardian_restart"
                connection.execute(
                    "UPDATE leases SET payload=?, lifecycle_state=?, updated_at=? WHERE lease_id=?",
                    (json.dumps(payload, sort_keys=True), "orphaned_guardian_restart", time.time(), lease_id),
                )
                self._record_event(connection, lease_id, previous, "orphaned_guardian_restart", "guardian_restart", 0, self.expected_uid, payload)
        finally:
            connection.close()

    @staticmethod
    def _record_event(connection, lease_id: str, previous: str, next_state: str,
                      reason: str, peer_pid: int, peer_uid: int, payload: Mapping[str, Any]) -> None:
        connection.execute(
            "INSERT INTO lifecycle_events "
            "(lease_id, previous_state, next_state, reason, peer_pid, peer_uid, created_at, payload_digest) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (lease_id, previous, next_state, reason, peer_pid, peer_uid, time.time(), _digest(payload)),
        )

    def start(self) -> None:
        if self._server is not None:
            raise RuntimeError("socket guardian is already running")
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        if self.socket_path.exists():
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            try:
                probe.connect(str(self.socket_path))
            except OSError:
                self.socket_path.unlink()
            else:
                raise RuntimeError("another socket guardian owns the control path")
            finally:
                probe.close()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        server.bind(str(self.socket_path))
        os.chmod(self.socket_path, 0o600)
        server.listen(32)
        server.settimeout(0.2)
        self._server = server
        self._stop.clear()

    def adopt_inherited_socket(
        self,
        service_id: str,
        inherited: socket.socket,
        *,
        workspace_id: str,
        authority_ref: str,
        capability_ref: str,
        appraisal_ref: str,
        policy_generation: str,
        registry_digest: str = "",
        network_namespace: str = "host",
        vrf: str = "production",
        ttl_seconds: float = 0,
    ) -> PortLease:
        """Adopt a duplicate of a listener retained by an external supervisor.

        The caller keeps its descriptor. This property is what allows a new
        guardian process to recover after guardian failure without rebinding
        the port. systemd is the intended external supervisor.
        """

        if not service_id or not workspace_id:
            raise ValueError("service_id and workspace_id are required")
        if self.require_authority and not all((authority_ref, capability_ref, appraisal_ref, policy_generation)):
            raise PermissionError("inherited socket adoption requires complete authority binding")
        held = inherited.dup()
        try:
            family = "AF_INET6" if held.family == socket.AF_INET6 else "AF_INET" if held.family == socket.AF_INET else ""
            base_type = held.type & 0xF
            protocol = "TCP" if base_type == socket.SOCK_STREAM else "UDP" if base_type == socket.SOCK_DGRAM else ""
            if not family or not protocol:
                raise ValueError("only inherited IPv4/IPv6 TCP/UDP sockets are supported")
            address = held.getsockname()
            host, port = str(address[0]), int(address[1])
            if protocol == "TCP" and not held.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN):
                raise ValueError("inherited TCP descriptor is not a listening socket")
            request = {
                "service_id": service_id,
                "registry_digest": registry_digest,
            }
            # The authoritative service registry describes the backend
            # upstream. A systemd-retained socket is the frontend listener and
            # may intentionally use a different port.
            current_registry_digest = self._validate_registry(
                request,
                host=host,
                port=port,
                enforce_endpoint=False,
            )
            generation_key = json.dumps(
                [family, protocol, host, port, network_namespace, vrf], separators=(",", ":")
            )
            issued_mono = time.monotonic_ns()
            issued_unix = time.time()
            material = {
                "service_id": service_id,
                "workspace_id": workspace_id,
                "host": host,
                "port": port,
                "protocol": protocol,
                "family": family,
                "network_namespace": network_namespace,
                "vrf": vrf,
                "issued_at_monotonic_ns": issued_mono,
                "issued_at_unix": issued_unix,
                "authority_ref": authority_ref,
                "capability_ref": capability_ref,
                "appraisal_ref": appraisal_ref,
                "policy_generation": policy_generation,
                "registry_digest": current_registry_digest,
                "adoption_source": "external-supervisor",
            }
            connection = self._connect_db()
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT generation FROM generations WHERE identity_key=?", (generation_key,)
                ).fetchone()
                generation = int(row[0]) + 1 if row else 1
                connection.execute(
                    "INSERT INTO generations(identity_key,generation) VALUES(?,?) "
                    "ON CONFLICT(identity_key) DO UPDATE SET generation=excluded.generation",
                    (generation_key, generation),
                )
                material["listener_generation"] = generation
                lease_id = "portlease:" + hashlib.sha256(_canonical(material)).hexdigest()
                lease = PortLease(
                    lease_id=lease_id,
                    service_id=service_id,
                    workspace_id=workspace_id,
                    host=host,
                    port=port,
                    protocol=protocol,
                    issued_at_monotonic_ns=issued_mono,
                    receipt_digest=_digest(material),
                    network_namespace=network_namespace,
                    listener_generation=generation,
                    expires_at_monotonic_ns=issued_mono + int(ttl_seconds * 1e9) if ttl_seconds else 0,
                    family=family,
                    vrf=vrf,
                    lifecycle_state="reserved",
                    health_state="unknown",
                    authority_ref=authority_ref,
                    appraisal_ref=appraisal_ref,
                    capability_ref=capability_ref,
                    policy_generation=policy_generation,
                    registry_digest=current_registry_digest,
                    issued_at_unix=issued_unix,
                    expires_at_unix=issued_unix + ttl_seconds if ttl_seconds else 0,
                )
                connection.execute(
                    "INSERT INTO leases(lease_id,payload,lifecycle_state,health_state,updated_at) VALUES(?,?,?,?,?)",
                    (lease_id, json.dumps(lease.__dict__, sort_keys=True), "reserved", "unknown", time.time()),
                )
                self._record_event(
                    connection, lease_id, "", "reserved", "external_supervisor_adoption",
                    0, self.expected_uid, lease.__dict__,
                )
                connection.execute("COMMIT")
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
            finally:
                connection.close()
            with self._lock:
                self._sockets[lease_id] = held
            return lease
        except Exception:
            held.close()
            raise

    def adopt_pidfd_socket(
        self,
        service_id: str,
        target_pid: int,
        target_fd: int,
        **kwargs,
    ) -> PortLease:
        """Adopt a socket from another process by stealing its file descriptor using pidfd."""
        from app.kernel.system_monitor import ExecutionPrimitives
        import socket
        import os
        
        pidfd = ExecutionPrimitives.pidfd_open(target_pid, 0)
        if pidfd < 0:
            raise OSError(f"Failed to open pidfd for process {target_pid}")
            
        try:
            stolen_fd = ExecutionPrimitives.pidfd_getfd(pidfd, target_fd, 0)
            if stolen_fd < 0:
                raise OSError(f"Failed to steal fd {target_fd} from process {target_pid}")
                
            held = socket.socket(fileno=stolen_fd)
            try:
                return self.adopt_inherited_socket(service_id, held, **kwargs)
            finally:
                held.detach()
                os.close(stolen_fd)
        finally:
            os.close(pidfd)

    def adopt_systemd_environment(
        self,
        bindings: Mapping[str, Mapping[str, Any]],
        *,
        environment: Mapping[str, str] | None = None,
        unset_environment: bool = True,
    ) -> tuple[PortLease, ...]:
        """Adopt LISTEN_FDS using LISTEN_FDNAMES as service identifiers.

        Unknown descriptor names are rejected; there is no positional fallback
        which could silently attach a production port to the wrong service.
        """

        env = os.environ if environment is None else environment
        try:
            listen_pid = int(env.get("LISTEN_PID", "0"))
            listen_fds = int(env.get("LISTEN_FDS", "0"))
        except ValueError as exc:
            raise RuntimeError("invalid systemd socket activation environment") from exc
        if not listen_fds:
            return ()
        if listen_pid != os.getpid():
            raise PermissionError("LISTEN_FDS are not addressed to this guardian process")
        names = str(env.get("LISTEN_FDNAMES") or "").split(":")
        if len(names) != listen_fds or any(not name for name in names):
            raise RuntimeError("every inherited descriptor requires a unique LISTEN_FDNAME")
        if len(names) != len(set(names)):
            raise RuntimeError("duplicate systemd socket descriptor names are forbidden")
        adopted: list[PortLease] = []
        try:
            for offset, service_id in enumerate(names):
                if service_id not in bindings:
                    raise PermissionError(f"no authority binding exists for inherited socket {service_id}")
                inherited = socket.socket(fileno=3 + offset)
                try:
                    adopted.append(
                        self.adopt_inherited_socket(service_id, inherited, **dict(bindings[service_id]))
                    )
                finally:
                    inherited.detach()
        except Exception:
            for lease in adopted:
                with self._lock:
                    held = self._sockets.pop(lease.lease_id, None)
                    if held is not None:
                        held.close()
                released = lease.__class__(**{
                    **lease.__dict__,
                    "lifecycle_state": "released",
                    "release_reason": "systemd_adoption_transaction_rollback",
                })
                self._transition(
                    released, lease.lifecycle_state, "released",
                    "systemd_adoption_transaction_rollback", 0, self.expected_uid,
                )
            raise
        finally:
            if unset_environment and environment is None:
                for key in ("LISTEN_PID", "LISTEN_FDS", "LISTEN_FDNAMES"):
                    os.environ.pop(key, None)
        return tuple(adopted)

    def serve_forever(self) -> None:
        if self._server is None:
            self.start()
        assert self._server is not None
        next_reap = time.monotonic()
        while not self._stop.is_set():
            if time.monotonic() >= next_reap:
                self._expire_due()
                next_reap = time.monotonic() + 5.0
            try:
                connection, _ = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                if self._stop.is_set():
                    break
                raise
            try:
                self._handle_connection(connection)
            finally:
                connection.close()

    def stop(self, *, release_sockets: bool = True) -> None:
        self._stop.set()
        if release_sockets:
            with self._lock:
                for held in self._sockets.values():
                    held.close()
                self._sockets.clear()
        if self._server is not None:
            self._server.close()
            self._server = None
        try:
            self.socket_path.unlink()
        except FileNotFoundError:
            pass

    def _handle_connection(self, connection: socket.socket) -> None:
        pid, uid, gid = peer_credentials(connection)
        if uid != self.expected_uid:
            self._send(connection, {"ok": False, "error": "peer_uid_not_authorized"})
            return
        data, _ancillary, flags, _address = connection.recvmsg(MAX_FRAME)
        if flags & getattr(socket, "MSG_TRUNC", 0):
            self._send(connection, {"ok": False, "error": "frame_truncated"})
            return
        try:
            request = json.loads(data)
            if not isinstance(request, dict):
                raise ValueError("request must be an object")
            self._validate_request_identity(request, pid=pid)
            result, fd = self._dispatch(request, peer_pid=pid, peer_uid=uid)
            self._send(connection, {"ok": True, "request_id": request.get("request_id"), "result": result}, fd=fd)
        except Exception as exc:
            self._send(connection, {
                "ok": False, "request_id": request.get("request_id") if isinstance(locals().get("request"), dict) else "",
                "error": type(exc).__name__, "message": str(exc),
            })

    def _validate_request_identity(self, request: Mapping[str, Any], *, pid: int) -> None:
        if not request.get("request_id") or not request.get("op"):
            raise GuardianProtocolError("request_id and op are required")
        if self.require_process_lease:
            value = request.get("process_lease")
            if not isinstance(value, Mapping):
                raise PermissionError("validated ProcessLease is required")
            lease = ProcessLease(**{k: v for k, v in value.items() if k in ProcessLease.__dataclass_fields__})
            lease.validate()
            if lease.pid_at_observation != pid:
                raise PermissionError("ProcessLease does not identify the connected peer")
        if self.require_authority and request.get("op") not in {"snapshot", "events"}:
            for field in ("workspace_id", "capability_ref", "appraisal_ref", "policy_generation"):
                if not request.get(field):
                    raise PermissionError(f"{field} is required by protected guardian policy")
        if self.authorize is not None and request.get("op") not in {"snapshot", "events"} and not self.authorize(request):
            raise PermissionError("guardian authorization callback vetoed request")

    def _validate_registry(
        self,
        request: Mapping[str, Any],
        *,
        host: str,
        port: int,
        enforce_endpoint: bool = True,
    ) -> str:
        if self.service_registry is None:
            return str(request.get("registry_digest") or "")
        supplied = str(request.get("registry_digest") or "")
        current = self.service_registry.digest()
        if supplied != current:
            raise PermissionError("service registry digest mismatch")
        service_id = str(request.get("service_id") or "")
        service = self.service_registry.services.get(service_id)
        if service is None:
            raise PermissionError("service is absent from authoritative registry")
        if enforce_endpoint and (
            service.port != port
            or service.upstream.rsplit(":", 1)[0] != host
        ):
            raise PermissionError(
                "requested listener disagrees with authoritative registry"
            )
        return current

    def _dispatch(self, request: Mapping[str, Any], *, peer_pid: int, peer_uid: int) -> tuple[Mapping[str, Any], int | None]:
        op = str(request["op"])
        if op == "reserve":
            return self._reserve(request, peer_pid, peer_uid), None
        if op == "recover":
            lease, receipt, fd = self._recover(request, peer_pid, peer_uid)
            return {"lease": lease.__dict__, "handoff_receipt": receipt.__dict__}, fd
        if op == "release":
            return self._release(request, peer_pid, peer_uid).__dict__, None
        if op == "mark_health":
            return self._mark_health(request, peer_pid, peer_uid).__dict__, None
        if op == "snapshot":
            return {"leases": [item.__dict__ for item in self._snapshot()]}, None
        if op == "events":
            return {"events": self._events(int(request.get("limit") or 100))}, None
        if op == "reconcile_registry":
            return self._reconcile_registry(request, peer_pid, peer_uid), None
        if op == "probe_health":
            return self._probe_health(request, peer_pid, peer_uid), None
        raise GuardianProtocolError(f"unsupported guardian operation: {op}")

    def _reserve(self, request: Mapping[str, Any], peer_pid: int, peer_uid: int) -> Mapping[str, Any]:
        family = str(request.get("family") or "AF_INET")
        protocol = str(request.get("protocol") or "TCP").upper()
        if family not in {"AF_INET", "AF_INET6"} or protocol not in {"TCP", "UDP"}:
            raise ValueError("unsupported listener family or protocol")
        host = str(request.get("host") or ("::1" if family == "AF_INET6" else "127.0.0.1"))
        port = int(request.get("port") or 0)
        if not 0 <= port <= 65535:
            raise ValueError("port is outside the valid range")
        socket_family = socket.AF_INET6 if family == "AF_INET6" else socket.AF_INET
        socket_type = socket.SOCK_DGRAM if protocol == "UDP" else socket.SOCK_STREAM
        held = socket.socket(socket_family, socket_type)
        try:
            with self._lock:
                if len(self._sockets) >= self.max_active_leases:
                    raise RuntimeError("guardian lease capacity exhausted")
            held.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            held.bind((host, port))
            actual_port = int(held.getsockname()[1])
            if protocol == "TCP":
                held.listen(int(request.get("backlog") or 32))
            registry_digest = self._validate_registry(request, host=host, port=actual_port)
            namespace = str(request.get("network_namespace") or "host")
            vrf = str(request.get("vrf") or "production")
            generation_key = json.dumps([family, protocol, host, actual_port, namespace, vrf], separators=(",", ":"))
            connection = self._connect_db()
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute("SELECT generation FROM generations WHERE identity_key=?", (generation_key,)).fetchone()
                predecessor_generation = int(request.get("predecessor_generation") or 0)
                if predecessor_generation < 0:
                    raise ValueError("predecessor listener generation cannot be negative")
                generation = max(int(row[0]) + 1 if row else 1, predecessor_generation + 1)
                connection.execute(
                    "INSERT INTO generations(identity_key,generation) VALUES(?,?) "
                    "ON CONFLICT(identity_key) DO UPDATE SET generation=excluded.generation",
                    (generation_key, generation),
                )
                issued_mono = time.monotonic_ns()
                issued_unix = time.time()
                ttl = float(request.get("ttl_seconds") or 0)
                material = {
                    "service_id": str(request.get("service_id") or ""),
                    "workspace_id": str(request.get("workspace_id") or ""),
                    "host": host, "port": actual_port, "protocol": protocol,
                    "family": family, "network_namespace": namespace, "vrf": vrf,
                    "listener_generation": generation, "issued_at_monotonic_ns": issued_mono,
                    "predecessor_generation": predecessor_generation,
                    "issued_at_unix": issued_unix,
                    "authority_ref": str(request.get("authority_ref") or self.guardian_id),
                    "capability_ref": str(request.get("capability_ref") or ""),
                    "appraisal_ref": str(request.get("appraisal_ref") or ""),
                    "policy_generation": str(request.get("policy_generation") or ""),
                    "registry_digest": registry_digest,
                }
                lease_id = "portlease:" + hashlib.sha256(_canonical(material)).hexdigest()
                lease = PortLease(
                    lease_id=lease_id, service_id=material["service_id"], workspace_id=material["workspace_id"],
                    host=host, port=actual_port, protocol=protocol,
                    issued_at_monotonic_ns=issued_mono, receipt_digest=_digest(material),
                    network_namespace=namespace, listener_generation=generation,
                    expires_at_monotonic_ns=issued_mono + int(ttl * 1e9) if ttl else 0,
                    family=family, vrf=vrf, lifecycle_state="reserved", health_state="unknown",
                    authority_ref=material["authority_ref"], appraisal_ref=material["appraisal_ref"],
                    capability_ref=material["capability_ref"], policy_generation=material["policy_generation"],
                    registry_digest=registry_digest, issued_at_unix=issued_unix,
                    expires_at_unix=issued_unix + ttl if ttl else 0,
                )
                payload_text = json.dumps(lease.__dict__, sort_keys=True)
                connection.execute(
                    "INSERT INTO leases(lease_id,payload,lifecycle_state,health_state,updated_at) VALUES(?,?,?,?,?)",
                    (lease_id, payload_text, "reserved", "unknown", time.time()),
                )
                self._record_event(connection, lease_id, "", "reserved", "reserve", peer_pid, peer_uid, lease.__dict__)
                connection.execute("COMMIT")
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
            finally:
                connection.close()
            with self._lock:
                self._sockets[lease_id] = held
            return lease.__dict__
        except Exception:
            held.close()
            raise

    def _load_active(self, lease_id: str) -> PortLease:
        with self._lock:
            if lease_id not in self._sockets:
                raise KeyError("guardian does not own the requested socket")
        connection = self._connect_db()
        try:
            row = connection.execute("SELECT payload,lifecycle_state FROM leases WHERE lease_id=?", (lease_id,)).fetchone()
        finally:
            connection.close()
        if row is None or row[1] not in ACTIVE_STATES:
            raise KeyError("lease is not active")
        lease = PortLease(**json.loads(row[0]))
        if lease.expires_at_unix and time.time() >= lease.expires_at_unix:
            raise PermissionError("lease has expired")
        return lease

    @staticmethod
    def _binds(request: Mapping[str, Any], lease: PortLease) -> bool:
        return all((
            request.get("workspace_id") == lease.workspace_id,
            request.get("capability_ref") == lease.capability_ref,
            request.get("appraisal_ref") == lease.appraisal_ref,
            request.get("policy_generation") == lease.policy_generation,
            (not lease.registry_digest or request.get("registry_digest") == lease.registry_digest),
        ))

    def _recover(self, request: Mapping[str, Any], peer_pid: int, peer_uid: int):
        lease_id = str(request.get("lease_id") or "")
        lease = self._load_active(lease_id)
        if not self._binds(request, lease):
            raise PermissionError("recovery binding does not match the original lease authority")
        transferred = time.monotonic_ns()
        previous = lease.lifecycle_state
        lease = lease.__class__(**{**lease.__dict__, "lifecycle_state": "handed_off", "transferred_at_monotonic_ns": transferred})
        receipt_body = {
            "lease_id": lease.lease_id, "service_id": lease.service_id,
            "workspace_id": lease.workspace_id, "listener_generation": lease.listener_generation,
            "network_namespace": lease.network_namespace, "vrf": lease.vrf,
            "authority_ref": lease.authority_ref, "capability_ref": lease.capability_ref,
            "appraisal_ref": lease.appraisal_ref, "policy_generation": lease.policy_generation,
            "registry_digest": lease.registry_digest, "guardian_id": self.guardian_id,
            "transferred_at_monotonic_ns": transferred,
        }
        signature = base64.b64encode(self.signer.sign(_canonical(receipt_body))).decode("ascii") if self.signer else ""
        receipt = SocketHandoffReceipt(**receipt_body, receipt_digest=_digest(receipt_body), signature=signature)
        self._transition(lease, previous, "handed_off", "descriptor_recovery", peer_pid, peer_uid)
        with self._lock:
            fd = self._sockets[lease_id].fileno()
        return lease, receipt, fd

    def _transition(self, lease: PortLease, previous: str, next_state: str, reason: str,
                    peer_pid: int, peer_uid: int) -> None:
        connection = self._connect_db()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "UPDATE leases SET payload=?, lifecycle_state=?, health_state=?, updated_at=? WHERE lease_id=?",
                (json.dumps(lease.__dict__, sort_keys=True), next_state, lease.health_state, time.time(), lease.lease_id),
            )
            self._record_event(connection, lease.lease_id, previous, next_state, reason, peer_pid, peer_uid, lease.__dict__)
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def _release(self, request, peer_pid, peer_uid) -> PortLease:
        lease = self._load_active(str(request.get("lease_id") or ""))
        if not self._binds(request, lease):
            raise PermissionError("release binding does not match lease authority")
        previous = lease.lifecycle_state
        lease = lease.__class__(**{**lease.__dict__, "lifecycle_state": "released", "release_reason": str(request.get("reason") or "explicit_release")})
        with self._lock:
            self._sockets.pop(lease.lease_id).close()
        self._transition(lease, previous, "released", lease.release_reason, peer_pid, peer_uid)
        return lease

    def _mark_health(self, request, peer_pid, peer_uid) -> PortLease:
        lease = self._load_active(str(request.get("lease_id") or ""))
        if not self._binds(request, lease):
            raise PermissionError("health binding does not match lease authority")
        healthy = bool(request.get("healthy"))
        previous = lease.lifecycle_state
        next_state = "healthy" if healthy else "unhealthy"
        lease = lease.__class__(**{**lease.__dict__, "lifecycle_state": next_state, "health_state": next_state})
        self._transition(lease, previous, next_state, "health_probe", peer_pid, peer_uid)
        return lease

    def _snapshot(self) -> tuple[PortLease, ...]:
        self._expire_due()
        connection = self._connect_db()
        try:
            rows = connection.execute(
                "SELECT payload FROM leases WHERE lifecycle_state IN ('reserved','handed_off','healthy','unhealthy') ORDER BY updated_at"
            ).fetchall()
            return tuple(PortLease(**json.loads(row[0])) for row in rows)
        finally:
            connection.close()

    def _expire_due(self) -> None:
        now = time.time()
        connection = self._connect_db()
        try:
            rows = connection.execute(
                "SELECT payload FROM leases WHERE lifecycle_state IN ('reserved','handed_off','healthy','unhealthy')"
            ).fetchall()
        finally:
            connection.close()
        for row in rows:
            lease = PortLease(**json.loads(row[0]))
            if not lease.expires_at_unix or now < lease.expires_at_unix:
                continue
            with self._lock:
                held = self._sockets.pop(lease.lease_id, None)
                if held is not None:
                    held.close()
            expired = lease.__class__(**{**lease.__dict__, "lifecycle_state": "expired", "release_reason": "ttl_expired"})
            self._transition(expired, lease.lifecycle_state, "expired", "ttl_expired", 0, self.expected_uid)

    def _events(self, limit: int) -> list[dict[str, Any]]:
        connection = self._connect_db()
        try:
            rows = connection.execute(
                "SELECT event_id,lease_id,previous_state,next_state,reason,peer_pid,peer_uid,created_at,payload_digest "
                "FROM lifecycle_events ORDER BY event_id DESC LIMIT ?", (max(1, min(limit, 1000)),)
            ).fetchall()
        finally:
            connection.close()
        keys = ("event_id", "lease_id", "previous_state", "next_state", "reason", "peer_pid", "peer_uid", "created_at", "payload_digest")
        return [dict(zip(keys, row)) for row in rows]

    def _reconcile_registry(self, request, peer_pid, peer_uid) -> Mapping[str, Any]:
        if self.service_registry is None:
            raise RuntimeError("guardian has no authoritative service registry")
        expected_digest = self.service_registry.digest()
        if request.get("registry_digest") != expected_digest:
            raise PermissionError("registry reconciliation requires the current digest")
        reconciled, revoked = [], []
        for lease in self._snapshot():
            service = self.service_registry.services.get(lease.service_id)
            matches = bool(
                service and service.port == lease.port
                and service.upstream.rsplit(":", 1)[0] == lease.host
                and lease.registry_digest == expected_digest
            )
            if matches:
                reconciled.append(lease.lease_id)
                continue
            with self._lock:
                held = self._sockets.pop(lease.lease_id, None)
                if held is not None:
                    held.close()
            released = lease.__class__(**{**lease.__dict__, "lifecycle_state": "released", "release_reason": "service_registry_drift"})
            self._transition(released, lease.lifecycle_state, "released", "service_registry_drift", peer_pid, peer_uid)
            revoked.append(lease.lease_id)
        return {"registry_digest": expected_digest, "reconciled": reconciled, "revoked": revoked}

    def _probe_health(self, request, peer_pid, peer_uid) -> Mapping[str, Any]:
        if self.health_probe is None:
            raise RuntimeError("guardian health probe is not configured")
        results = []
        for lease in self._snapshot():
            if request.get("workspace_id") and lease.workspace_id != request.get("workspace_id"):
                continue
            healthy = bool(self.health_probe(lease))
            previous = lease.lifecycle_state
            next_state = "healthy" if healthy else "unhealthy"
            updated = lease.__class__(**{**lease.__dict__, "lifecycle_state": next_state, "health_state": next_state})
            self._transition(updated, previous, next_state, "active_health_probe", peer_pid, peer_uid)
            results.append({"lease_id": lease.lease_id, "healthy": healthy})
        return {"results": results}

    @staticmethod
    def _send(connection: socket.socket, payload: Mapping[str, Any], *, fd: int | None = None) -> None:
        ancillary = []
        if fd is not None:
            ancillary.append((socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [fd])))
        connection.sendmsg([_canonical(payload)], ancillary)


class SocketGuardianClient:
    """Authenticated client used by each replaceable broker process."""

    def __init__(self, socket_path: str | Path, *, expected_uid: int | None = None,
                 process_lease_provider: Callable[[], ProcessLease] | None = None,
                 operation_capability_provider: Callable[[Mapping[str, Any]], Any] | None = None,
                 receipt_verifier=None, expected_guardian_id: str = "beast.socket-guardian.v1",
                 require_signed_receipts: bool = True):
        self.socket_path = Path(socket_path)
        self.expected_uid = os.getuid() if expected_uid is None else expected_uid
        self.process_lease_provider = process_lease_provider
        self.operation_capability_provider = operation_capability_provider
        self.receipt_verifier = receipt_verifier
        self.expected_guardian_id = expected_guardian_id
        self.require_signed_receipts = require_signed_receipts
        if self.require_signed_receipts and self.receipt_verifier is None:
            raise RuntimeError("protected guardian client requires a receipt verifier")

    def _request(self, op: str, payload: Mapping[str, Any], *, expect_fd: bool = False):
        request = {"request_id": str(uuid.uuid4()), "op": op, **dict(payload)}
        if self.process_lease_provider is not None:
            request["process_lease"] = self.process_lease_provider().to_dict()
        if op not in {"snapshot", "events"} and self.operation_capability_provider is not None:
            request["authorization_capability"] = capability_mapping(
                self.operation_capability_provider(request)
            )
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        connection.connect(str(self.socket_path))
        try:
            if peer_credentials(connection)[1] != self.expected_uid:
                raise PermissionError("socket guardian uid is not trusted")
            connection.send(_canonical(request))
            data, ancillary, flags, _address = connection.recvmsg(MAX_FRAME, socket.CMSG_SPACE(array.array("i").itemsize))
            if flags & getattr(socket, "MSG_TRUNC", 0):
                raise GuardianProtocolError("guardian response was truncated")
            response = json.loads(data)
            if not response.get("ok"):
                raise GuardianProtocolError(str(response.get("message") or response.get("error") or "guardian rejected request"))
            if response.get("request_id") != request["request_id"]:
                raise GuardianProtocolError("guardian response request binding mismatch")
            fds: list[int] = []
            for level, kind, raw in ancillary:
                if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                    values = array.array("i")
                    values.frombytes(raw[: len(raw) - (len(raw) % values.itemsize)])
                    fds.extend(values.tolist())
            if expect_fd and len(fds) != 1:
                for received in fds:
                    os.close(received)
                raise GuardianProtocolError("guardian did not return exactly one socket descriptor")
            if not expect_fd and fds:
                for received in fds:
                    os.close(received)
                raise GuardianProtocolError("guardian returned an unexpected descriptor")
            return response["result"], (fds[0] if fds else None)
        finally:
            connection.close()

    def reserve(self, service_id: str, workspace_id: str, **kwargs) -> PortLease:
        result, _ = self._request("reserve", {"service_id": service_id, "workspace_id": workspace_id, **kwargs})
        return PortLease(**result)

    def recover(self, lease_id: str, *, workspace_id: str, capability_ref: str,
                appraisal_ref: str, policy_generation: str, registry_digest: str = ""):
        result, fd = self._request("recover", {
            "lease_id": lease_id, "workspace_id": workspace_id, "capability_ref": capability_ref,
            "appraisal_ref": appraisal_ref, "policy_generation": policy_generation,
            "registry_digest": registry_digest,
        }, expect_fd=True)
        assert fd is not None
        lease = PortLease(**result["lease"])
        receipt = SocketHandoffReceipt(**result["handoff_receipt"])
        self._verify_receipt(receipt)
        return lease, socket.socket(fileno=fd), receipt

    def _verify_receipt(self, receipt: SocketHandoffReceipt) -> None:
        body = {key: value for key, value in receipt.__dict__.items() if key not in {"receipt_digest", "signature"}}
        if receipt.guardian_id != self.expected_guardian_id or receipt.receipt_digest != _digest(body):
            raise PermissionError("socket handoff receipt binding is invalid")
        if self.require_signed_receipts and not receipt.signature:
            raise PermissionError("socket handoff receipt is unsigned")
        if self.receipt_verifier is not None:
            try:
                self.receipt_verifier.verify(base64.b64decode(receipt.signature, validate=True), _canonical(body))
            except Exception as exc:
                raise PermissionError("socket handoff signature is invalid") from exc

    def release(self, lease_id: str, **binding) -> PortLease:
        result, _ = self._request("release", {"lease_id": lease_id, **binding})
        return PortLease(**result)

    def mark_health(self, lease_id: str, *, healthy: bool, **binding) -> PortLease:
        result, _ = self._request("mark_health", {"lease_id": lease_id, "healthy": healthy, **binding})
        return PortLease(**result)

    def snapshot(self) -> tuple[PortLease, ...]:
        result, _ = self._request("snapshot", {})
        return tuple(PortLease(**item) for item in result["leases"])

    def events(self, *, limit: int = 100) -> tuple[Mapping[str, Any], ...]:
        result, _ = self._request("events", {"limit": limit})
        return tuple(result["events"])

    def reconcile_registry(self, *, registry_digest: str, **binding) -> Mapping[str, Any]:
        result, _ = self._request("reconcile_registry", {"registry_digest": registry_digest, **binding})
        return result

    def probe_health(self, **binding) -> Mapping[str, Any]:
        result, _ = self._request("probe_health", binding)
        return result
