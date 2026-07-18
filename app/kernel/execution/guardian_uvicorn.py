"""Run ASGI services on authority-bound sockets recovered from the Guardian."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import threading
import time
from typing import Any, Mapping

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.kernel.execution.guardian_authorization import (
    GUARDIAN_CAPABILITY_AUDIENCE,
    guardian_operation_body,
    guardian_operation_digest,
)
from app.kernel.execution.process_identity import LinuxProcessIdentityCollector
from app.kernel.execution.socket_guardian import SocketGuardianClient
from app.kernel.integration.arda_metatron_bridge import SignedJsonHttpAuthorizer


class GuardianStartupError(RuntimeError):
    pass


class GuardianListenerUnavailable(GuardianStartupError):
    """A transient startup condition: the expected listener is not adopted yet."""


class GuardianOperationCapabilityProvider:
    """Request a capability whose digest exactly covers a Guardian operation."""

    def __init__(self, authorizer: SignedJsonHttpAuthorizer):
        self.authorizer = authorizer

    def __call__(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        digest = guardian_operation_digest(request)
        authority_request = {
            **guardian_operation_body(request),
            "request_digest": digest,
        }
        decision = self.authorizer(authority_request)
        if not isinstance(decision, Mapping) or decision.get("allowed") is not True:
            raise PermissionError("ARDA/Metatron denied Guardian socket operation")
        capability = decision.get("capability")
        if not isinstance(capability, Mapping) or capability.get("request_digest") != digest:
            raise PermissionError("authority returned no exact Guardian operation capability")
        return capability


def _required_environment(environment: Mapping[str, str], names: tuple[str, ...]) -> dict[str, str]:
    values = {name: str(environment.get(name) or "").strip() for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise GuardianStartupError(
            "Guardian socket mode requires protected configuration: " + ", ".join(missing)
        )
    return values


def _read_trust_file(path: Path, *, description: str) -> bytes:
    if path.is_symlink():
        raise GuardianStartupError(f"{description} must not be a symbolic link")
    try:
        metadata = path.stat()
        if not stat.S_ISREG(metadata.st_mode):
            raise GuardianStartupError(f"{description} must be a regular file")
        if stat.S_IMODE(metadata.st_mode) & 0o022:
            raise GuardianStartupError(f"{description} must not be group/world writable")
        if metadata.st_uid not in {0, os.getuid()}:
            raise GuardianStartupError(f"{description} has an unexpected owner")
        return path.read_bytes()
    except GuardianStartupError:
        raise
    except OSError as exc:
        raise GuardianStartupError(f"cannot read {description}: {path}") from exc


def _authorization_headers(environment: Mapping[str, str]) -> dict[str, str]:
    inline = str(environment.get("BEAST_GUARDIAN_AUTHORIZATION_TOKEN") or "").strip()
    token_path_value = str(
        environment.get("BEAST_GUARDIAN_AUTHORIZATION_TOKEN_FILE") or ""
    ).strip()
    if inline and token_path_value:
        raise GuardianStartupError("configure one Guardian authorization token source, not two")
    if inline.startswith("REPLACE_"):
        raise GuardianStartupError("Guardian socket mode refuses a placeholder authorization token")
    token = inline
    if token_path_value:
        token_path = Path(os.path.expandvars(token_path_value)).expanduser()
        if token_path.is_symlink():
            raise GuardianStartupError("Guardian authorization credential must not be a symbolic link")
        try:
            metadata = token_path.stat()
            if not stat.S_ISREG(metadata.st_mode):
                raise GuardianStartupError("Guardian authorization credential must be a regular file")
            if metadata.st_uid != os.getuid():
                raise GuardianStartupError("Guardian authorization credential has an unexpected owner")
            mode = stat.S_IMODE(metadata.st_mode)
            if mode & 0o077:
                raise GuardianStartupError(
                    "Guardian authorization credential must not be group/world accessible"
                )
            token = token_path.read_text(encoding="utf-8").strip()
        except GuardianStartupError:
            raise
        except OSError as exc:
            raise GuardianStartupError(
                f"cannot read Guardian authorization credential: {token_path}"
            ) from exc
    if token.startswith("REPLACE_"):
        raise GuardianStartupError("Guardian socket mode refuses a placeholder authorization token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def build_guardian_client_from_environment(
    *, environment: Mapping[str, str] | None = None,
) -> tuple[SocketGuardianClient, dict[str, str]]:
    env = os.environ if environment is None else environment
    names = (
        "BEAST_GUARDIAN_CONTROL_SOCKET",
        "BEAST_GUARDIAN_RECEIPT_PUBLIC_KEY",
        "BEAST_GUARDIAN_AUTHORIZATION_URL",
        "BEAST_GUARDIAN_AUTHORITY_PUBLIC_KEY",
        "BEAST_GUARDIAN_WORKSPACE_ID",
        "BEAST_GUARDIAN_POLICY_GENERATION",
        "BEAST_GUARDIAN_APPRAISAL_REF",
    )
    values = _required_environment(env, names)
    for name in (
        "BEAST_GUARDIAN_WORKSPACE_ID",
        "BEAST_GUARDIAN_POLICY_GENERATION",
        "BEAST_GUARDIAN_APPRAISAL_REF",
    ):
        if values[name].startswith("REPLACE_"):
            raise GuardianStartupError(f"Guardian socket mode refuses placeholder {name}")
    authority = str(env.get("BEAST_GUARDIAN_AUTHORITY") or "arda").strip()
    if authority not in {"arda", "metatron"}:
        raise GuardianStartupError("Guardian operation authority must be arda or metatron")
    control_socket = Path(os.path.expandvars(values["BEAST_GUARDIAN_CONTROL_SOCKET"])).expanduser()
    receipt_path = Path(os.path.expandvars(values["BEAST_GUARDIAN_RECEIPT_PUBLIC_KEY"])).expanduser()
    authority_key_path = Path(os.path.expandvars(values["BEAST_GUARDIAN_AUTHORITY_PUBLIC_KEY"])).expanduser()
    receipt_key = serialization.load_pem_public_key(
        _read_trust_file(receipt_path, description="Guardian receipt public key")
    )
    if not isinstance(receipt_key, Ed25519PublicKey):
        raise GuardianStartupError("Guardian receipt verifier must be an Ed25519 public key")
    authority_key = serialization.load_pem_public_key(
        _read_trust_file(authority_key_path, description="ARDA/Metatron authority public key")
    )
    if not isinstance(authority_key, Ed25519PublicKey):
        raise GuardianStartupError("Guardian operation authority must use an Ed25519 public key")
    headers = _authorization_headers(env)
    signed_authorizer = SignedJsonHttpAuthorizer(
        values["BEAST_GUARDIAN_AUTHORIZATION_URL"],
        str(authority_key_path),
        authority=authority,
        expected_audience=GUARDIAN_CAPABILITY_AUDIENCE,
        expected_policy_generation=values["BEAST_GUARDIAN_POLICY_GENERATION"],
        expected_appraisal_ref=values["BEAST_GUARDIAN_APPRAISAL_REF"],
        timeout=float(env.get("BEAST_GUARDIAN_AUTHORIZATION_TIMEOUT") or 3.0),
        headers=headers,
    )
    client = SocketGuardianClient(
        control_socket,
        expected_uid=int(env.get("BEAST_GUARDIAN_EXPECTED_UID") or os.getuid()),
        process_lease_provider=lambda: LinuxProcessIdentityCollector().collect(
            os.getpid(), owner_scope="beast-guardian-socket-consumer"
        ),
        operation_capability_provider=GuardianOperationCapabilityProvider(signed_authorizer),
        receipt_verifier=receipt_key,
        expected_guardian_id=str(env.get("BEAST_GUARDIAN_ID") or "beast.socket-guardian.v1"),
        require_signed_receipts=True,
    )
    return client, {
        "workspace_id": values["BEAST_GUARDIAN_WORKSPACE_ID"],
        "policy_generation": values["BEAST_GUARDIAN_POLICY_GENERATION"],
        "appraisal_ref": values["BEAST_GUARDIAN_APPRAISAL_REF"],
        "authority": authority,
    }


def recover_named_listener(
    client: SocketGuardianClient,
    *,
    service_id: str,
    workspace_id: str,
    policy_generation: str,
    appraisal_ref: str,
):
    candidates = [
        lease for lease in client.snapshot()
        if lease.service_id == service_id
        and lease.workspace_id == workspace_id
        and lease.policy_generation == policy_generation
        and lease.appraisal_ref == appraisal_ref
    ]
    if not candidates:
        raise GuardianListenerUnavailable(
            f"Guardian has no active listener for service={service_id} workspace={workspace_id}"
        )
    if len(candidates) != 1:
        generations = sorted(lease.listener_generation for lease in candidates)
        raise GuardianStartupError(
            f"Guardian listener selection is ambiguous for {service_id}: generations={generations}"
        )
    lease = candidates[0]
    if lease.protocol != "TCP":
        raise GuardianStartupError("ASGI HTTP startup requires a Guardian-owned TCP listener")
    recovered, held, receipt = client.recover(
        lease.lease_id,
        workspace_id=workspace_id,
        capability_ref=lease.capability_ref,
        appraisal_ref=appraisal_ref,
        policy_generation=policy_generation,
        registry_digest=lease.registry_digest,
    )
    if held.getsockname()[1] != recovered.port:
        held.close()
        raise GuardianStartupError("recovered descriptor address does not match its signed lease")
    return recovered, held, receipt


def _write_handoff_receipt(path: str, lease, receipt) -> None:
    if not path:
        return
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    payload = (
        json.dumps(
            {"lease": lease.__dict__, "handoff_receipt": receipt.__dict__},
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    descriptor = os.open(
        temporary,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_TRUNC
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise GuardianStartupError("failed to persist Guardian handoff receipt")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, target)
    directory = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def run_uvicorn_with_guardian(
    app: Any,
    *,
    service_id: str,
    client: SocketGuardianClient,
    binding: Mapping[str, str],
    log_level: str = "warning",
    handoff_receipt_path: str = "",
) -> None:
    """Recover a named listener and run Uvicorn without another bind call."""

    import uvicorn

    lease, held, receipt = recover_named_listener(
        client,
        service_id=service_id,
        workspace_id=str(binding["workspace_id"]),
        policy_generation=str(binding["policy_generation"]),
        appraisal_ref=str(binding["appraisal_ref"]),
    )
    os.environ["BEAST_ACTIVE_SERVICE_ID"] = service_id
    os.environ["BEAST_ACTIVE_PORT_LEASE_ID"] = lease.lease_id
    os.environ["BEAST_ACTIVE_LISTENER_GENERATION"] = str(lease.listener_generation)
    os.environ["BEAST_ACTIVE_GUARDIAN_RECEIPT"] = receipt.receipt_digest
    _write_handoff_receipt(handoff_receipt_path, lease, receipt)

    config = uvicorn.Config(app, log_level=log_level, lifespan="on")
    server = uvicorn.Server(config)
    monitor_stop = threading.Event()
    health_errors: list[Exception] = []

    def mark_ready() -> None:
        deadline = time.monotonic() + 30.0
        while not monitor_stop.wait(0.025):
            if server.started:
                try:
                    client.mark_health(
                        lease.lease_id,
                        healthy=True,
                        workspace_id=lease.workspace_id,
                        capability_ref=lease.capability_ref,
                        appraisal_ref=lease.appraisal_ref,
                        policy_generation=lease.policy_generation,
                        registry_digest=lease.registry_digest,
                    )
                except Exception as exc:
                    health_errors.append(exc)
                    server.should_exit = True
                return
            if time.monotonic() >= deadline:
                return

    monitor = threading.Thread(target=mark_ready, name="guardian-uvicorn-health", daemon=True)
    monitor.start()
    try:
        server.run(sockets=[held])
    finally:
        monitor_stop.set()
        monitor.join(timeout=1)
        try:
            client.mark_health(
                lease.lease_id,
                healthy=False,
                workspace_id=lease.workspace_id,
                capability_ref=lease.capability_ref,
                appraisal_ref=lease.appraisal_ref,
                policy_generation=lease.policy_generation,
                registry_digest=lease.registry_digest,
            )
        except Exception:
            pass
        held.close()
    if health_errors:
        raise GuardianStartupError("Guardian refused the service healthy transition") from health_errors[0]


def run_uvicorn_from_environment(
    app: Any,
    *,
    service_id: str,
    log_level: str = "warning",
) -> None:
    client, binding = build_guardian_client_from_environment()
    timeout = float(os.environ.get("BEAST_GUARDIAN_STARTUP_TIMEOUT") or 20.0)
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        try:
            run_uvicorn_with_guardian(
                app,
                service_id=service_id,
                client=client,
                binding=binding,
                log_level=log_level,
                handoff_receipt_path=str(os.environ.get("BEAST_GUARDIAN_HANDOFF_RECEIPT") or ""),
            )
            return
        except (ConnectionError, FileNotFoundError, GuardianListenerUnavailable) as exc:
            if time.monotonic() >= deadline:
                raise GuardianStartupError(
                    f"Guardian listener for {service_id} was not recoverable before startup deadline"
                ) from exc
            time.sleep(0.1)
