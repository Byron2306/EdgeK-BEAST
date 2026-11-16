#!/usr/bin/env python3
"""Generate, but never silently install or enable, Socket Guardian user units."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.kernel.networking.fabric_topology import FabricTopology, TopologyDriftError  # noqa: E402
from app.kernel.networking.service_registry import ServiceRegistry


def _contract(registry_file: Path, lab_manifest: Path | None, compose_base: Path | None,
              compose_override: Path | None) -> dict:
    topology = FabricTopology.load(
        services_path=registry_file,
        lab_manifest_path=lab_manifest or REPOSITORY_ROOT / ".beast" / "remote-commons-lab" / "manifest.json",
        compose_base_path=compose_base or REPOSITORY_ROOT / "docker-compose.commons-lab.yml",
        compose_override_path=compose_override,
    )
    try:
        return topology.guardian_bindings()
    except TopologyDriftError as exc:
        raise RuntimeError(f"refusing to generate Guardian units on topology drift: {exc.findings}") from exc


def _install_instructions(output_dir: Path, socket_names: list[str], consumers: list[str], config_file: Path,
                          contract: dict, registry_file: Path) -> str:
    ports = ", ".join(f"{name}={item['port']}" for name, item in sorted(contract["services"].items()))
    port_list = [str(item["port"]) for _, item in sorted(contract["services"].items())]
    beast_port = str(contract["services"].get("beast", {}).get("port") or port_list[0])
    units = " ".join(socket_names)
    return (
        "# Socket Guardian user units — operator install steps (generated, NOT installed)\n\n"
        f"Topology digest: `{contract['topology_digest']}`  Contract ports: {ports}\n\n"
        f"Enabling a `.socket` unit makes systemd own its port ({', '.join(port_list)}). If a port is the operator's\n"
        "running 8101 gateway, stop that process first; otherwise use the lab registry (spare port 8131).\n\n"
        "1. Provision host roots (D3.1; writes ~/.config/beast and ~/.local/state/beast, keys mode 0600):\n"
        f"   `.venv/bin/python scripts/provision_guardian_validation.py --plan --registry {registry_file}` then\n"
        f"   `.venv/bin/python scripts/provision_guardian_validation.py --registry {registry_file} "
        "--sovereign-proof /home/byron/Metatron/live_horror_class_proof_qwen15m/00_manifest.json`\n"
        "   (ARDA authorizer = Metatron `backend.services.arda_authorization_service` from /usr/lib/arda/src/arda_os,\n"
        "   run in `seraph-backend:latest`; `--arda-build-context /home/byron/Metatron` rebuilds the July image)\n"
        "2. Start the ARDA authorizer (127.0.0.1:18401):\n"
        "   `docker compose -f ~/.config/beast/arda-guardian-compose.yaml up -d` then fail-closed smoke (expect 403):\n"
        "   `curl -sS -X POST -H 'content-type: application/json' -d '{}' "
        "http://127.0.0.1:18401/authorize/socket-guardian`\n"
        "3. Install the units:\n"
        f"   `mkdir -p ~/.config/systemd/user && cp {output_dir}/*.socket {output_dir}/*.service "
        "~/.config/systemd/user/`\n"
        "   `systemctl --user daemon-reload`\n"
        f"   `systemd-analyze --user verify ~/.config/systemd/user/beast-socket-guardian.service`\n"
        "4. Enable and start (sockets first, then the Guardian, then consumers):\n"
        f"   `systemctl --user enable --now {units}`\n"
        "   `systemctl --user enable --now beast-socket-guardian.service`\n"
        + "".join(f"   `systemctl --user enable --now {name}`\n" for name in consumers)
        + "5. Verify:\n"
        "   `systemctl --user status beast-socket-guardian.service`\n"
        "   `journalctl --user -u beast-socket-guardian.service -n 50`\n"
        f"   `ss -ltnp | grep -E ':({'|'.join(port_list)})\\b'`\n"
        f"   `curl -fsS http://127.0.0.1:{beast_port}/health`\n"
        f"   `.venv/bin/python scripts/check_fabric_topology.py --services {registry_file}`\n"
        "   `cat ~/.local/state/beast/beast-handoff.json | python3 -m json.tool | head`\n"
        f"\nGuardian config: `{config_file}`\n"
        "Rollback: `systemctl --user disable --now beast-*-guardian-consumer.service beast-socket-guardian.service "
        f"{units}` and remove the copied unit files.\n"
    )


def generate(registry_file: Path, config_file: Path, output_dir: Path, repository: Path, *,
             lab_manifest: Path | None = None, compose_base: Path | None = None,
             compose_override: Path | None = None) -> list[Path]:
    registry = ServiceRegistry.from_file(registry_file)
    contract = _contract(registry_file, lab_manifest, compose_base, compose_override)
    guardian_services = set(contract["services"])
    if not guardian_services:
        raise ValueError("at least one service must explicitly opt into socket_guardian ownership")
    output_dir.mkdir(parents=True, exist_ok=True)
    # Guardian authorization binds the consumer's executable identity.  The
    # deployment appraisal is produced with the project interpreter, so the
    # generated user units must use that exact venv rather than an arbitrary
    # system Python (which would correctly be rejected by ARDA).
    interpreter = repository / ".venv" / "bin" / "python"
    if not interpreter.is_file():
        interpreter = repository / "venv" / "bin" / "python"
    if not interpreter.is_file():
        interpreter = Path(sys.executable).resolve()
    socket_names = [
        f"beast-socket-guardian-{name}.socket"
        for name, service in registry.services.items()
        if service.enabled and name in guardian_services
    ]
    service = output_dir / "beast-socket-guardian.service"
    service.write_text(
        "[Unit]\n"
        "Description=BEAST proof-carrying socket guardian\n"
        f"Requires={' '.join(socket_names)}\n"
        f"After=network.target {' '.join(socket_names)}\n\n"
        "[Service]\n"
        "Type=simple\n"
        f"WorkingDirectory={repository}\n"
        f"ExecStart={interpreter} -m app.kernel.execution.socket_guardian_daemon --config {config_file}\n"
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
        if not item.enabled or name not in guardian_services:
            continue
        path = output_dir / f"beast-socket-guardian-{name}.socket"
        path.write_text(
            "[Unit]\n"
            f"Description=BEAST externally retained listener for {name}\n"
            f"X-Beast-Topology-Digest={contract['topology_digest']}\n\n"
            "[Socket]\n"
            f"ListenStream={contract['services'][name]['upstream']}\n"
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
        if service_id not in guardian_services or not registry.services[service_id].enabled:
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
            f"Environment=BEAST_GUARDIAN_SERVICE_REGISTRY={registry_file}\n"
            "Environment=BEAST_GUARDIAN_RECEIPT_PUBLIC_KEY=%h/.config/beast/guardian-receipt-ed25519.pub.pem\n"
            "Environment=BEAST_GUARDIAN_AUTHORITY_PUBLIC_KEY=%h/.config/beast/arda-operation-ed25519.pub.pem\n"
            "LoadCredential=guardian_authorization_token:%h/.config/beast/guardian-authorization.token\n"
            "Environment=BEAST_GUARDIAN_AUTHORIZATION_TOKEN_FILE=%d/guardian_authorization_token\n"
            f"Environment=BEAST_GUARDIAN_HANDOFF_RECEIPT=%S/beast/{service_id}-handoff.json\n"
            f"ExecStart={interpreter} {repository / 'bin' / 'beast'} {command}\n"
            "Restart=on-failure\n"
            "RestartSec=2s\n"
            "StateDirectory=beast\n"
            "UMask=0077\n"
            "NoNewPrivileges=yes\n"
            "PrivateTmp=yes\n"
            "ProtectSystem=strict\n"
            "ProtectHome=read-only\n"
            # The gateway's local workspace graph/Chroma index is persisted
            # under the selected BEAST workspace.  Keep the system sandbox
            # strict, but permit that single configured workspace alongside
            # the dedicated runtime state directory.
            f"ReadWritePaths=%S/beast {repository}\n"
            "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6\n"
            "LockPersonality=yes\n\n"
            "[Install]\n"
            "WantedBy=default.target\n",
            encoding="utf-8",
        )
        outputs.append(consumer)
    install = output_dir / "INSTALL.md"
    install.write_text(_install_instructions(
        output_dir, socket_names, [p.name for p in outputs if p.name.endswith("-guardian-consumer.service")],
        config_file, contract, registry_file), encoding="utf-8")
    outputs.append(install)
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
    parser.add_argument("--lab-manifest", default="")
    parser.add_argument("--compose-base", default="")
    parser.add_argument("--compose-override", default="")
    args = parser.parse_args()
    root = REPOSITORY_ROOT
    for path in generate(
        (root / args.registry).resolve(),
        (root / args.config).resolve(),
        (root / args.output).resolve(),
        root,
        lab_manifest=Path(args.lab_manifest).expanduser() if args.lab_manifest else None,
        compose_base=Path(args.compose_base).expanduser() if args.compose_base else None,
        compose_override=Path(args.compose_override).expanduser() if args.compose_override else None,
    ):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
