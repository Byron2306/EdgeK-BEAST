#!/usr/bin/env python3
"""Generate, but never silently install or enable, Socket Guardian user units."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.kernel.networking.service_registry import ServiceRegistry


def generate(registry_file: Path, config_file: Path, output_dir: Path, repository: Path) -> list[Path]:
    registry = ServiceRegistry.from_file(registry_file)
    output_dir.mkdir(parents=True, exist_ok=True)
    socket_names = [f"beast-socket-guardian-{name}.socket" for name, service in registry.services.items() if service.enabled]
    service = output_dir / "beast-socket-guardian.service"
    service.write_text(
        "[Unit]\n"
        "Description=BEAST proof-carrying socket guardian\n"
        f"Requires={' '.join(socket_names)}\n"
        f"After=network.target {' '.join(socket_names)}\n\n"
        "[Service]\n"
        "Type=simple\n"
        f"WorkingDirectory={repository}\n"
        f"ExecStart=/usr/bin/python3 -m app.kernel.execution.socket_guardian_daemon --config {config_file}\n"
        "Restart=on-failure\n"
        "RestartSec=2s\n"
        "RuntimeDirectory=beast\n"
        "StateDirectory=beast\n"
        "Environment=XDG_STATE_HOME=%S\n"
        "ReadWritePaths=%t/beast %S/beast\n"
        "UMask=0077\n"
        "NoNewPrivileges=yes\n"
        "PrivateTmp=yes\n"
        "ProtectSystem=strict\n"
        "ProtectHome=read-only\n"
        "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6\n"
        "LockPersonality=yes\n"
        "MemoryDenyWriteExecute=yes\n\n"
        "[Install]\n"
        "WantedBy=default.target\n",
        encoding="utf-8",
    )
    outputs = [service]
    for name, item in registry.services.items():
        if not item.enabled:
            continue
        path = output_dir / f"beast-socket-guardian-{name}.socket"
        path.write_text(
            "[Unit]\n"
            f"Description=BEAST externally retained listener for {name}\n\n"
            "[Socket]\n"
            f"ListenStream={item.upstream}\n"
            f"FileDescriptorName={name}\n"
            "Service=beast-socket-guardian.service\n"
            "NoDelay=true\n"
            "Backlog=128\n\n"
            "[Install]\n"
            "WantedBy=sockets.target\n",
            encoding="utf-8",
        )
        outputs.append(path)
    for service_id, command in (
        ("beast", "gateway --socket-mode guardian --guardian-service beast"),
        ("commons", "commons-gateway --socket-mode guardian"),
    ):
        if service_id not in registry.services or not registry.services[service_id].enabled:
            continue
        consumer = output_dir / f"beast-{service_id}-guardian-consumer.service"
        consumer.write_text(
            "[Unit]\n"
            f"Description=BEAST {service_id} Guardian socket consumer\n"
            "Requires=beast-socket-guardian.service\n"
            "After=beast-socket-guardian.service network.target\n\n"
            "[Service]\n"
            "Type=simple\n"
            f"WorkingDirectory={repository}\n"
            "Environment=BEAST_SOCKET_MODE=guardian\n"
            "Environment=BEAST_STATE_ROOT=%S/beast\n"
            "Environment=BEAST_COMMONS_ROOT=%S/beast/commons-spaces\n"
            "EnvironmentFile=-%h/.config/beast/socket-consumer.env\n"
            "Environment=BEAST_GUARDIAN_CONTROL_SOCKET=%t/beast/socket-guardian.sock\n"
            "Environment=BEAST_GUARDIAN_RECEIPT_PUBLIC_KEY=%h/.config/beast/guardian-receipt-ed25519.pub.pem\n"
            "Environment=BEAST_GUARDIAN_AUTHORITY_PUBLIC_KEY=%h/.config/beast/arda-operation-ed25519.pub.pem\n"
            "LoadCredential=guardian_authorization_token:%h/.config/beast/guardian-authorization.token\n"
            "Environment=BEAST_GUARDIAN_AUTHORIZATION_TOKEN_FILE=%d/guardian_authorization_token\n"
            f"Environment=BEAST_GUARDIAN_HANDOFF_RECEIPT=%S/beast/{service_id}-handoff.json\n"
            f"ExecStart=/usr/bin/python3 {repository / 'bin' / 'beast'} {command}\n"
            "Restart=on-failure\n"
            "RestartSec=2s\n"
            "StateDirectory=beast\n"
            "UMask=0077\n"
            "NoNewPrivileges=yes\n"
            "PrivateTmp=yes\n"
            "ProtectSystem=strict\n"
            "ProtectHome=read-only\n"
            "ReadWritePaths=%S/beast\n"
            "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6\n"
            "LockPersonality=yes\n\n"
            "[Install]\n"
            "WantedBy=default.target\n",
            encoding="utf-8",
        )
        outputs.append(consumer)
    manifest = output_dir / "MANIFEST.txt"
    manifest.write_text(
        "Generated Socket Guardian user units.\n"
        "These files are intentionally not installed or enabled automatically.\n"
        "Enabling a socket reserves its port; the target service must first consume the Guardian handoff FD.\n"
        + "\n".join(path.name for path in outputs + [manifest])
        + "\n",
        encoding="utf-8",
    )
    outputs.append(manifest)
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", default=".byron/services.yaml")
    parser.add_argument("--config", default=".byron/socket-guardian.yaml")
    parser.add_argument("--output", default=".beast/generated/systemd-user")
    args = parser.parse_args()
    root = REPOSITORY_ROOT
    for path in generate(
        (root / args.registry).resolve(),
        (root / args.config).resolve(),
        (root / args.output).resolve(),
        root,
    ):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
