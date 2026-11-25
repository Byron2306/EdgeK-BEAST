"""Promoted coding crystal -> sealed memfd capsule -> zero-model replay in a separate process (default-off).

``BEAST_CRYSTAL_CAPSULE=1`` enables it. The flow:

* The parent writes the crystal's executable payload into a memfd and seals it with
  F_SEAL_SHRINK|GROW|WRITE|SEAL, the same seal set as ``kv_memfd_handoff``. The payload holds the
  reviewed steps, the parameters, the expected postcondition and the worktree binding.
* The parent hands only the fd to a child over AF_UNIX SCM_RIGHTS. No payload bytes cross the socket.
* The child checks the seals (F_GET_SEALS), mmaps the capsule read-only and checks the digests.
* The child replays the reviewed opcodes with no model client and no network. When ``unshare`` allows it,
  the child runs in an empty network namespace; it also counts AF_INET/AF_INET6 sockets, connects and
  DNS lookups, and HTTP client sends.
* The child checks the postcondition. The parent re-verifies it independently.

Claim boundary: this is a host-local capsule. The crystal (steps, digest, D6 promotion) comes from the registry. The
capsule only carries it; it never widens authority. Replay can only run opcodes from the reviewed coding catalog
(``coding_opcode_registry``). Every edit comes from ``resolve_constant`` over the observed failure, never from
the capsule's own text.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import mmap
import os
import shutil
import socket
import struct
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.kernel.compute.kv_memfd_handoff import HEADER, SEALS

CAPSULE_ENV = "BEAST_CRYSTAL_CAPSULE"
SCHEMA = "beast.crystal_memfd_capsule.v1"
REPO_ROOT = Path(__file__).resolve().parents[3]
SEAL_NAMES = {fcntl.F_SEAL_SEAL: "F_SEAL_SEAL", fcntl.F_SEAL_SHRINK: "F_SEAL_SHRINK",
              fcntl.F_SEAL_GROW: "F_SEAL_GROW", fcntl.F_SEAL_WRITE: "F_SEAL_WRITE"}
MAX_CAPSULE = 4 * 1024 * 1024


def capsule_enabled(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return str(env.get(CAPSULE_ENV, "")).strip().lower() in {"1", "true", "yes", "on"}


def _canon(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def sha256_bytes(raw: bytes | memoryview) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def seal_names(flags: int) -> list[str]:
    return [name for bit, name in sorted(SEAL_NAMES.items()) if flags & bit]


# -- payload / manifest -----------------------------------------------------------------------------------
def build_payload(candidate: Any, *, registry_record_digest: str, promotion: Mapping[str, Any],
                  parameters: Mapping[str, Any], postcondition: Mapping[str, Any],
                  binding: Mapping[str, Any]) -> bytes:
    candidate.validate()
    return _canon({"schema": SCHEMA, "crystal": candidate.to_dict(), "registry_record_digest": registry_record_digest,
                   "promotion": dict(promotion), "parameters": dict(parameters),
                   "postcondition": dict(postcondition), "binding": dict(binding)})


def build_manifest(payload: bytes, *, crystal_id: str, crystal_digest: str) -> dict[str, Any]:
    body = {"schema": SCHEMA, "crystal_id": crystal_id, "crystal_digest": crystal_digest,
            "payload_sha256": sha256_bytes(payload), "payload_bytes": len(payload), "privacy": "host_local",
            "publishable": False}
    body["manifest_digest"] = sha256_bytes(_canon(body))
    return body


def _check_manifest(manifest: Mapping[str, Any]) -> None:
    body = {k: v for k, v in manifest.items() if k != "manifest_digest"}
    if manifest.get("schema") != SCHEMA or manifest.get("privacy") != "host_local" or manifest.get("publishable"):
        raise PermissionError("capsule manifest must be host_local and unpublishable")
    if sha256_bytes(_canon(body)) != manifest.get("manifest_digest"):
        raise PermissionError("capsule manifest digest mismatch")


def _require(env: Mapping[str, str] | None = None) -> None:
    if not capsule_enabled(env):
        raise PermissionError(f"crystal memfd capsule is disabled (set {CAPSULE_ENV}=1)")


def seal_capsule(manifest: Mapping[str, Any], payload: bytes, *, seal: bool = True,
                 env: Mapping[str, str] | None = None) -> tuple[int, dict[str, Any]]:
    """Write header+manifest+payload into a memfd once and seal it. Returns (fd, measured write stats)."""
    _require(env)
    header = _canon(dict(manifest))
    fd = os.memfd_create("beast-crystal-capsule", os.MFD_ALLOW_SEALING | os.MFD_CLOEXEC)
    stats = {"write_calls": 0, "bytes_written": 0}
    try:
        for chunk in (memoryview(HEADER.pack(len(header)) + header), memoryview(payload)):
            done = 0
            while done < len(chunk):
                n = os.write(fd, chunk[done:])
                done += n
                stats["write_calls"] += 1
                stats["bytes_written"] += n
        if seal:
            fcntl.fcntl(fd, fcntl.F_ADD_SEALS, SEALS)
        stats["seals_readback"] = fcntl.fcntl(fd, fcntl.F_GET_SEALS)
        stats["seal_names"] = seal_names(stats["seals_readback"])
        stats["capsule_bytes"] = os.fstat(fd).st_size
        stats["header_bytes"] = HEADER.size + len(header)
        return fd, stats
    except Exception:
        os.close(fd)
        raise


def write_attempt_refused(fd: int) -> dict[str, Any]:
    """Prove the seal: a write to a sealed capsule must fail with EPERM."""
    try:
        os.pwrite(fd, b"X", 0)
    except PermissionError as exc:
        return {"refused": True, "errno": exc.errno, "error": "EPERM"}
    except OSError as exc:
        return {"refused": True, "errno": exc.errno, "error": type(exc).__name__}
    return {"refused": False}


def _decode_frame(base: memoryview, expected_manifest_digest: str) -> tuple[dict[str, Any], memoryview, int]:
    """Validate the exact same framing and hashes regardless of transport."""
    size = base.nbytes
    if size <= HEADER.size or size > MAX_CAPSULE:
        raise PermissionError("capsule size out of bounds")
    with base[:HEADER.size] as head:
        (length,) = HEADER.unpack(head)
    if not 0 < length < size - HEADER.size:
        raise PermissionError("capsule manifest length out of bounds")
    with base[HEADER.size:HEADER.size + length] as raw:
        manifest = json.loads(bytes(raw))
    _check_manifest(manifest)
    if manifest["manifest_digest"] != expected_manifest_digest:
        raise PermissionError("capsule manifest is not the one offered")
    payload = base[HEADER.size + length:]
    try:
        if payload.nbytes != manifest["payload_bytes"] or sha256_bytes(payload) != manifest["payload_sha256"]:
            raise PermissionError("capsule payload digest mismatch: tampered capsule refused")
    except BaseException:
        payload.release()
        raise
    return manifest, payload, length


def open_capsule(fd: int, *, expected_manifest_digest: str) -> tuple[dict[str, Any], memoryview, Any, dict[str, Any]]:
    """Require seals and a read-only mapping, then validate the shared frame."""
    seals = fcntl.fcntl(fd, fcntl.F_GET_SEALS)
    if seals & SEALS != SEALS:
        raise PermissionError(f"capsule is not sealed (seals={seal_names(seals)})")
    size = os.fstat(fd).st_size
    if size <= HEADER.size or size > MAX_CAPSULE:
        raise PermissionError("capsule size out of bounds")
    mapped = mmap.mmap(fd, size, access=mmap.ACCESS_READ)
    base = memoryview(mapped)
    try:
        manifest, payload, length = _decode_frame(base, expected_manifest_digest)
    except BaseException:
        base.release()
        mapped.close()
        raise
    return manifest, payload, (base, mapped), {"seals_readback": seals, "seal_names": seal_names(seals),
                                                "capsule_bytes": size, "mmaps": 1, "mmap_access": "ACCESS_READ",
                                                "manifest_header_bytes_copied": length}


# -- reviewed replay interpreter ------------------------------------------------------------------------------
def _run_verify(command: Sequence[str], cwd: Path) -> dict[str, Any]:
    started = time.perf_counter()
    done = subprocess.run(list(command), cwd=cwd, capture_output=True, text=True, timeout=120, check=False,
                          env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1", "LANG": "C.UTF-8"})
    out = (done.stdout + "\n" + done.stderr).strip()
    ran = 0
    for line in out.splitlines():
        if line.startswith("Ran ") and " test" in line:
            ran = int(line.split()[1])
    return {"returncode": done.returncode, "output": out, "tests_run": ran,
            "ms": round((time.perf_counter() - started) * 1000, 3)}


def replay_crystal(candidate: Any, parameters: Mapping[str, Any], root: Path, worktree: Path) -> dict[str, Any]:
    """Run only reviewed opcodes. The edit is derived by resolve_constant from the observed failure."""
    from app.kernel.compute.coding_crystals import coding_opcode_registry, resolve_constant

    candidate.validate()
    registry = coding_opcode_registry()
    target = str(parameters["implementation_target"])
    rel = Path(target)
    if rel.is_absolute() or ".." in rel.parts or rel.suffix != ".py":
        raise PermissionError("implementation_target unsafe")
    command = [str(x) for x in parameters["verify_command"]]
    trace, content, last_verify, proposal = [], "", None, None
    started = time.perf_counter()
    tool_calls = 0
    for index, step in enumerate(candidate.steps):
        spec = registry.resolve(str(step["opcode"]))
        t0 = time.perf_counter()
        row: dict[str, Any] = {"index": index, "opcode": spec.opcode, "tool_id": step["tool_id"]}
        if spec.opcode == "worktree.inspect":
            content = (root / rel).read_text(encoding="utf-8")
            row["sha256"] = sha256_bytes(content.encode())
        elif spec.opcode == "worktree.bind":
            if worktree.exists():
                raise PermissionError("worktree already exists")
            shutil.copytree(root, worktree)
        elif spec.opcode == "worktree.verify":
            last_verify = _run_verify(command, worktree)
            ok = (last_verify["returncode"] != 0) if step["expect"] == "fail" else (last_verify["returncode"] == 0)
            row.update(returncode=last_verify["returncode"], expect=step["expect"], tests_run=last_verify["tests_run"])
            if not ok:
                row["refused"] = f"verify expectation {step['expect']!r} not met"
                trace.append(row)
                return {"ok": False, "reason": "expectation_failed", "trace": trace, "tool_calls": tool_calls + 1}
        elif spec.opcode == "repair.resolve_constant":
            proposal = resolve_constant(last_verify["output"] if last_verify else "", content)
            if not proposal:
                trace.append({**row, "refused": "no unique constant resolution"})
                return {"ok": False, "reason": "not_applicable", "trace": trace, "tool_calls": tool_calls}
            row["edit"] = {"old_text": proposal["old_text"], "new_text": proposal["new_text"]}
        elif spec.opcode == "worktree.replace_exact":
            path = worktree / rel
            text = path.read_text(encoding="utf-8")
            if text.count(proposal["old_text"]) != 1:
                raise PermissionError("replace_exact target is not unique")
            path.write_text(text.replace(proposal["old_text"], proposal["new_text"], 1), encoding="utf-8")
        elif spec.opcode == "crystal.complete":
            pass
        if step["tool_id"]:
            tool_calls += 1
        row["ms"] = round((time.perf_counter() - t0) * 1000, 3)
        trace.append(row)
    return {"ok": True, "trace": trace, "tool_calls": tool_calls, "model_calls": 0,
            "edit": trace and next((r["edit"] for r in trace if "edit" in r), None),
            "wall_ms": round((time.perf_counter() - started) * 1000, 3)}


def check_postcondition(worktree: Path, postcondition: Mapping[str, Any]) -> dict[str, Any]:
    result = _run_verify([str(x) for x in postcondition["verify_command"]], worktree)
    target = worktree / str(postcondition["implementation_target"])
    digest = sha256_bytes(target.read_bytes()) if target.is_file() else ""
    checks = {"returncode": result["returncode"] == int(postcondition.get("expect_returncode", 0)),
              "tests_run": result["tests_run"] == int(postcondition["tests_run"])}
    if postcondition.get("target_sha256_after"):
        checks["target_sha256_after"] = digest == postcondition["target_sha256_after"]
    if postcondition.get("files_sha256_after"):  # multi-file crystals (rename/toolchain): every changed file pinned
        files = {rel: (sha256_bytes((worktree / rel).read_bytes()) if (worktree / rel).is_file() else "")
                 for rel in postcondition["files_sha256_after"]}
        checks["files_sha256_after"] = files == dict(postcondition["files_sha256_after"])
    return {"passed": all(checks.values()), "checks": checks, "returncode": result["returncode"],
            "tests_run": result["tests_run"], "target_sha256": digest, "verify_ms": result["ms"]}


# -- child process ------------------------------------------------------------------------------------------------
class NetworkGuard:
    """Count every network attempt in this process; HTTP client sends are refused outright."""

    def __init__(self) -> None:
        self.counts = {"inet_sockets": 0, "connects": 0, "dns_lookups": 0, "http_sends": 0}

    def install(self) -> NetworkGuard:
        def hook(event: str, args: tuple) -> None:
            if event == "socket.__new__" and len(args) > 1 and args[1] in (socket.AF_INET, socket.AF_INET6):
                self.counts["inet_sockets"] += 1
            elif event == "socket.connect":
                self.counts["connects"] += 1
            elif event in {"socket.getaddrinfo", "socket.gethostbyname"}:
                self.counts["dns_lookups"] += 1

        sys.addaudithook(hook)
        try:
            import httpx

            guard = self

            def refuse(*_a: Any, **_k: Any) -> Any:
                guard.counts["http_sends"] += 1
                raise PermissionError("model/provider call attempted during capsule replay")

            httpx.Client.send = refuse  # type: ignore[method-assign]
            httpx.AsyncClient.send = refuse  # type: ignore[method-assign]
        except ImportError:
            pass
        return self


def net_dev() -> dict[str, dict[str, int]]:
    rows = {}
    try:
        for line in Path("/proc/self/net/dev").read_text().splitlines()[2:]:
            name, data = line.split(":", 1)
            fields = [int(x) for x in data.split()]
            rows[name.strip()] = {"rx_bytes": fields[0], "rx_packets": fields[1], "tx_bytes": fields[8],
                                  "tx_packets": fields[9]}
    except OSError:
        pass
    return rows


def _replay_payload(manifest, payload, stats, out):
    """One hydration, interpreter and postcondition path for both transports."""
    from app.kernel.compute.coding_crystals import CodingCrystalCandidate

    out["capsule"] = {**stats, "payload_sha256_child": manifest["payload_sha256"],
                      "manifest_digest": manifest["manifest_digest"]}
    t_parse = time.perf_counter()
    body = json.loads(bytes(payload))  # one userland parse copy, counted below
    out["capsule"]["payload_bytes_parse_copy"] = payload.nbytes
    if body["crystal"].get("kind") == "family_crystal":  # separate reviewed families catalog
        from app.kernel.compute.family_crystals import FamilyCrystal, replay_family, replay_stage

        candidate, replayer = FamilyCrystal.from_dict(body["crystal"]), replay_family
        stage = body["parameters"].get("lattice_stage")
        if stage:  # one child of a lattice composite; the composite (validated) fixes the stage contract
            composite = FamilyCrystal.from_dict(stage["composite"])
            out["lattice_stage"] = {"composite_id": composite.crystal_id, "index": int(stage["index"])}

            def replayer(c, p, r, w, _comp=composite, _i=int(stage["index"])):
                return replay_stage(_comp, c, _i, p, r, w)
    else:
        candidate, replayer = CodingCrystalCandidate.from_dict(body["crystal"]), replay_crystal
    if candidate.crystal_id != manifest["crystal_id"] or candidate.digest != manifest["crystal_digest"]:
        raise PermissionError("capsule crystal does not match its manifest")
    out["hydrate_ms"] = round((time.perf_counter() - t_parse) * 1000, 3)
    root, worktree = Path(body["binding"]["root"]), Path(body["binding"]["worktree"])
    replay = replayer(candidate, body["parameters"], root, worktree)
    out["replay"] = replay
    out["postcondition"] = check_postcondition(worktree, body["postcondition"]) if replay["ok"] else {"passed": False}
    out["ok"] = bool(replay["ok"] and out["postcondition"]["passed"])


def _child(sock_fd: int) -> int:
    guard = NetworkGuard().install()
    before = net_dev()
    started = time.perf_counter()
    with socket.socket(fileno=sock_fd) as sock:
        msg, fds, flags, _addr = socket.recv_fds(sock, 65536, 1)
        out: dict[str, Any] = {"pid": os.getpid(), "fds_received": len(fds),
                               "fd_pass_message_bytes": len(msg)}
        try:
            if flags & (socket.MSG_CTRUNC | socket.MSG_TRUNC) or len(fds) != 1:
                raise PermissionError("expected exactly one capsule fd")
            offer = json.loads(msg)
            out["admit_token_echo"] = offer.get("admit_token")
            peer = struct.unpack("3i", sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
            out["peer_pid_is_parent"] = peer[0] == os.getppid() or peer[0] == offer.get("parent_pid")
            opened = time.perf_counter()
            manifest, payload, keep, stats = open_capsule(fds[0], expected_manifest_digest=offer["manifest_digest"])
            out["receive_and_frame_ms"] = round((time.perf_counter() - started) * 1000, 3)
            out["open_and_verify_frame_ms"] = round((time.perf_counter() - opened) * 1000, 3)
            try:
                _replay_payload(manifest, payload, stats, out)
            finally:
                payload.release()
                keep[0].release()
                keep[1].close()
        except Exception as exc:  # noqa: BLE001 - refusals must reach the parent
            out.update(ok=False, refused=f"{type(exc).__name__}: {exc}")
        finally:
            for fd in fds:
                os.close(fd)
        out["child_wall_ms"] = round((time.perf_counter() - started) * 1000, 3)
        out["network"] = {**guard.counts, "net_dev_before": before, "net_dev_after": net_dev()}
        sock.sendall(_canon(out))
    return 0


def _pipe_replay_child(expected_manifest_digest: str) -> int:
    guard = NetworkGuard().install()
    before = net_dev()
    started = time.perf_counter()
    out: dict[str, Any] = {"pid": os.getpid()}
    try:
        frame = sys.stdin.buffer.read(MAX_CAPSULE + 1)
        out["pipe_bytes_read"] = len(frame)
        opened = time.perf_counter()
        with memoryview(frame) as base:
            manifest, payload, length = _decode_frame(base, expected_manifest_digest)
            out["receive_and_frame_ms"] = round((time.perf_counter() - started) * 1000, 3)
            out["open_and_verify_frame_ms"] = round((time.perf_counter() - opened) * 1000, 3)
            with payload:
                _replay_payload(manifest, payload, {"capsule_bytes": len(frame), "mmaps": 0,
                                "manifest_header_bytes_copied": length}, out)
    except Exception as exc:  # noqa: BLE001 - refusals must reach the parent
        out.update(ok=False, refused=f"{type(exc).__name__}: {exc}")
    out["child_wall_ms"] = round((time.perf_counter() - started) * 1000, 3)
    out["network"] = {**guard.counts, "net_dev_before": before, "net_dev_after": net_dev()}
    print(json.dumps(out))
    return 0


def _pipe_child() -> int:
    started = time.perf_counter()
    data = sys.stdin.buffer.read()
    print(json.dumps({"bytes_read": len(data), "sha256": sha256_bytes(data),
                      "ms": round((time.perf_counter() - started) * 1000, 3)}))
    return 0


def isolation_prefix() -> list[str]:
    """``unshare -rn`` gives the child an empty network namespace when unprivileged user namespaces are allowed."""
    tool = shutil.which("unshare")
    if not tool:
        return []
    probe = subprocess.run([tool, "-rn", "true"], capture_output=True, check=False)
    return [tool, "-rn"] if probe.returncode == 0 else []


def handoff_to_replay_child(fd: int, manifest: Mapping[str, Any], *, admit_token: str,
                            python: str | None = None, isolate: bool = True) -> dict[str, Any]:
    parent_sock, child_sock = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    prefix = isolation_prefix() if isolate else []
    cmd = [*prefix, python or sys.executable, "-m", "app.kernel.compute.crystal_memfd_capsule", "replay-child",
           "--sock-fd", str(child_sock.fileno())]
    started = time.perf_counter()
    child = subprocess.Popen(cmd, cwd=REPO_ROOT, pass_fds=(child_sock.fileno(),))
    child_sock.close()
    offer = _canon({"manifest_digest": manifest["manifest_digest"], "admit_token": admit_token,
                    "parent_pid": os.getpid()})
    sent = socket.send_fds(parent_sock, [offer], [fd])
    chunks = []
    while True:
        chunk = parent_sock.recv(1 << 16)
        if not chunk:
            break
        chunks.append(chunk)
    parent_sock.close()
    child.wait(timeout=180)
    result = json.loads(b"".join(chunks) or b"{}")
    result["parent_observed"] = {"fd_pass_bytes_sent": sent, "child_returncode": child.returncode,
                                 "isolation": "unshare -rn (empty netns)" if prefix else "none",
                                 "end_to_end_ms": round((time.perf_counter() - started) * 1000, 3)}
    return result


def handoff_to_pipe_replay_child(payload: bytes, manifest: Mapping[str, Any], *,
                                 python: str | None = None, isolate: bool = True) -> dict[str, Any]:
    """Send the real capsule frame through stdin and execute the same replay worker."""
    _require()
    header = _canon(dict(manifest))
    frame_size = HEADER.size + len(header) + len(payload)
    if frame_size > MAX_CAPSULE:
        raise PermissionError("capsule size out of bounds")
    t_prepare = time.perf_counter()
    frame = b"".join((HEADER.pack(len(header)), header, payload))
    prepare_ms = round((time.perf_counter() - t_prepare) * 1000, 3)
    prefix = isolation_prefix() if isolate else []
    started = time.perf_counter()
    child = subprocess.run([*prefix, python or sys.executable, "-m", "app.kernel.compute.crystal_memfd_capsule",
                            "pipe-replay-child", "--manifest-digest", manifest["manifest_digest"]],
                           cwd=REPO_ROOT, input=frame, stdout=subprocess.PIPE, timeout=180, check=True)
    result = json.loads(child.stdout)
    result["parent_observed"] = {"pipe_bytes_sent": min(frame_size, result["pipe_bytes_read"]),
                                 "frame_prepare_ms": prepare_ms, "child_returncode": child.returncode,
                                 "isolation": "unshare -rn (empty netns)" if prefix else "none",
                                 "end_to_end_ms": round((time.perf_counter() - started) * 1000, 3)}
    return result


def pipe_copy_baseline(capsule: bytes, *, python: str | None = None) -> dict[str, Any]:
    """Baseline: push the same capsule bytes through a pipe to a child (write copy + read copy)."""
    started = time.perf_counter()
    child = subprocess.Popen([python or sys.executable, "-m", "app.kernel.compute.crystal_memfd_capsule",
                              "pipe-child"], cwd=REPO_ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    out, _ = child.communicate(capsule, timeout=60)
    got = json.loads(out)
    return {"bytes_written_to_pipe": len(capsule), "bytes_read_from_pipe": got["bytes_read"],
            "transport_copies_bytes": len(capsule) + got["bytes_read"], "sha256_child": got["sha256"],
            "end_to_end_ms": round((time.perf_counter() - started) * 1000, 3)}


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="crystal_memfd_capsule")
    sub = parser.add_subparsers(dest="cmd", required=True)
    child = sub.add_parser("replay-child")
    child.add_argument("--sock-fd", type=int, required=True)
    sub.add_parser("pipe-child")
    pipe_replay = sub.add_parser("pipe-replay-child")
    pipe_replay.add_argument("--manifest-digest", required=True)
    args = parser.parse_args(argv)
    if args.cmd == "replay-child":
        return _child(args.sock_fd)
    if args.cmd == "pipe-replay-child":
        return _pipe_replay_child(args.manifest_digest)
    return _pipe_child()


__all__ = ["CAPSULE_ENV", "NetworkGuard", "build_manifest", "build_payload", "capsule_enabled", "check_postcondition",
           "handoff_to_replay_child", "handoff_to_pipe_replay_child", "open_capsule", "pipe_copy_baseline", "replay_crystal", "seal_capsule",
           "seal_names", "write_attempt_refused"]

if __name__ == "__main__":
    raise SystemExit(main())
