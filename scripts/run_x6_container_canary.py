from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from app.kernel.transport.x4_contracts import build_manifest
from app.kernel.transport.x6_identity import NodeSigner
from app.kernel.transport.x6_runtime import run_x6_canary


ROOT = Path(__file__).resolve().parents[1]


@dataclass
class HttpContainerLane:
    name: str
    base_url: str
    physical_lane: bool = False
    setup_us: int = 0
    umem_bytes: int = 0
    _retries: int = 0

    def fetch(self, index: int, expected_digest: str) -> bytes:
        url = f"{self.base_url.rstrip('/')}/{index}-{expected_digest.removeprefix('sha256:')}.bin"
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=5) as response:
            if response.status != 200:
                raise RuntimeError(f"container peer returned HTTP {response.status} for chunk {index}")
            return response.read()

    @property
    def retries(self) -> int:
        return self._retries


def _docker(*args: str, capture_output: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sudo", "docker", *args],
        check=True,
        text=True,
        capture_output=capture_output,
    )


def _wait_http(url: str, deadline_seconds: float = 15.0) -> None:
    deadline = time.monotonic() + deadline_seconds
    last_error = "container peer did not become ready"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if 200 <= response.status < 500:
                    return
        except Exception as exc:  # pragma: no cover - best effort readiness
            last_error = str(exc)
        time.sleep(0.25)
    raise RuntimeError(last_error)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run X6 cross-node canary against a disposable Docker peer")
    parser.add_argument("object", help="path to object to transfer")
    parser.add_argument("--receipt", default=str(ROOT / "evidence" / "high_velocity_fabric" / f"x6_cross_node_container_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.json"))
    parser.add_argument("--cas-root", default=str(ROOT / ".beast" / "x6-container-cas"))
    parser.add_argument("--sender", default="beast-host-node")
    parser.add_argument("--receiver", default="beast-container-node")
    parser.add_argument("--port", type=int, default=18124)
    parser.add_argument("--image", default="python:3.13-slim")
    parser.add_argument("--container-name", default=f"beast-x6-peer-{int(time.time())}")
    args = parser.parse_args()

    source = Path(args.object).resolve()
    receipt_path = Path(args.receipt).resolve()
    cas_root = Path(args.cas_root).resolve()
    cas_root.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)

    data = source.read_bytes()
    manifest = build_manifest(data, 65536)
    signer = NodeSigner()

    with TemporaryDirectory(prefix="beast-x6-container-chunks-") as temporary:
        temp_root = Path(temporary)
        chunk_root = temp_root / "chunks"
        chunk_root.mkdir(parents=True, exist_ok=True)
        for chunk in manifest.chunks:
            part = data[chunk.offset:chunk.offset + chunk.size]
            name = f"{chunk.index}-{chunk.digest.removeprefix('sha256:')}.bin"
            (chunk_root / name).write_bytes(part)
        (chunk_root / "index.html").write_text("BEAST X6 container peer\n", encoding="utf-8")

        container_name = args.container_name
        try:
            _docker(
                "run",
                "--rm",
                "-d",
                "--name",
                container_name,
                "-p",
                f"{args.port}:8000",
                "-v",
                f"{chunk_root}:/srv/chunks:ro",
                args.image,
                "python",
                "-m",
                "http.server",
                "8000",
                "-d",
                "/srv/chunks",
            )
            _wait_http(f"http://127.0.0.1:{args.port}/")

            lane = HttpContainerLane(
                name="ordinary_socket",
                base_url=f"http://127.0.0.1:{args.port}",
                setup_us=1000,
            )
            receipt, reconstructed = run_x6_canary(
                data=data,
                sender_node=args.sender,
                receiver_node=args.receiver,
                signer=signer,
                trusted_public_keys={signer.public_key_b64},
                receiver_cas_root=cas_root,
                lanes=[lane],
            )
            if reconstructed != data:
                raise SystemExit("reconstruction mismatch")

            payload = dict(receipt.__dict__)
            payload["transport"] = {
                "peer_type": "docker_container_http_server",
                "container_name": container_name,
                "container_image": args.image,
                "container_port": args.port,
                "source_object": str(source),
            }
            receipt_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(receipt_path)
        finally:
            try:
                _docker("rm", "-f", container_name)
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
