#!/usr/bin/env python3
"""Package the DAI Phase-2 exact X2 stale-listener proof capsule."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import zipfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RELEASE_ID = "DAI-Diode-Phase-2__Stale-Listener-Exact-X2-Kernel-Witness__2026-08-04"
EXPECTED_SUMMARY_DIGEST = "sha256:33f5ecc2762faa364ca7c8b8c86288d72ca36a5373aefc13a65147d5fd9f7c44"
EXPECTED_EVIDENCE = ROOT / "evidence/dai-diode/phase2-stale-listener-001/x2-exact-ring"
EVIDENCE_RELATIVE_PATH = "evidence/dai-diode/phase2-stale-listener-001/x2-exact-ring"
EXCLUDED_EVIDENCE_NAMES = {"x2_exact_ring_failure.json"}


SOURCE_PATHS = [
    "scripts/run_dai_phase2_x2_exact_ring_buffer.py",
    "scripts/run_dai_phase2_stale_listener_demo.py",
    "scripts/package_dai_phase2_exact_artifact.py",
    "app/kernel/dai",
    "app/kernel/sensorium/bpf",
    "app/kernel/sensorium/bpf_event_contracts.py",
    "app/kernel/sensorium/bpf_loss_receipts.py",
    "app/kernel/sensorium/bpf_ring_adapter.py",
    "app/kernel/compute/deterministic_intelligence.py",
    "app/kernel/execution/process_identity.py",
    "bpf/Makefile",
    "bpf/beast_x1_observer.bpf.c",
    "bpf/libbeast_x2_loader.c",
    "bpf/build/beast_x1_observer.bpf.o",
    "bpf/build/libbeast_x2_loader.so",
    "X2_ATTACH_MANIFEST.json",
    "fixtures/dai_phase2/stale_listener_acquisition_examples.json",
]


TEST_PATHS = [
    "tests/test_dai_phase2_acquisition.py",
    "tests/test_dai_phase2_commons_quorum.py",
    "tests/test_dai_phase2_harmonic.py",
    "tests/test_dai_phase2_sensorium_bpf.py",
    "tests/test_dai_phase2_seraph.py",
    "tests/test_dai_phase2_stale_listener.py",
    "tests/test_dai_phase2_x2_exact_ring_buffer_script.py",
]


DEPENDENCY_PATHS = [
    "pyproject.toml",
    "pytest.ini",
    "requirements.txt",
    "requirements-semantic.txt",
    "requirements.commons-node.txt",
    "Dockerfile.commons-node",
]


SUPPORTING_EVIDENCE = [
    "evidence/commons-ml-kem/physical-truth-commons-mlkem-live-container-helper-001.json",
    "evidence/c4x-physical-truth-certificate/physical_truth_sidecar_harvested.json",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-root", type=Path, default=ROOT / "artifacts")
    parser.add_argument("--evidence", type=Path, default=EXPECTED_EVIDENCE)
    args = parser.parse_args()
    result = package(out_root=args.out_root, evidence=args.evidence)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def package(*, out_root: Path, evidence: Path) -> dict[str, Any]:
    evidence = evidence.resolve()
    summary_path = evidence / "phase2_x2_exact_ring_summary.json"
    summary = _read_json(summary_path)
    if summary.get("summary_digest") != EXPECTED_SUMMARY_DIGEST:
        raise RuntimeError(f"unexpected summary digest: {summary.get('summary_digest')}")
    if not summary.get("green"):
        raise RuntimeError("refusing to package a non-green Phase-2 exact summary")
    if summary.get("sensorium_bpf_authority_level") != "exact_phase2_cgroup_kernel_witness":
        raise RuntimeError("exact cgroup kernel witness authority missing")
    if summary.get("correlated_socket_bind_event_count") != 3:
        raise RuntimeError("expected exactly three correlated socket-bind events")
    if summary.get("provider_calls_used") != 0 or summary.get("production_authority_allowed") is not False:
        raise RuntimeError("authority/provider boundary mismatch")

    out_root.mkdir(parents=True, exist_ok=True)
    bundle = out_root / RELEASE_ID
    if bundle.exists():
        shutil.rmtree(bundle)
    bundle.mkdir(parents=True)

    _copy_evidence(evidence, bundle / EVIDENCE_RELATIVE_PATH)
    _copy_paths(SOURCE_PATHS, bundle / "source")
    _copy_paths(TEST_PATHS, bundle / "tests")
    _copy_paths(DEPENDENCY_PATHS, bundle / "dependencies")
    _copy_paths(SUPPORTING_EVIDENCE, bundle / "supporting-evidence")

    _write_text(bundle / "README.md", _readme(summary))
    _write_text(bundle / "CLAIMS_NONCLAIMS_LIMITATIONS.md", _claims(summary))
    _write_text(bundle / "AUTHORITY_MAP.md", _authority_map(summary))
    _write_text(bundle / "CLEAN_ENVIRONMENT_REPRODUCTION.md", _clean_repro())
    _write_text(bundle / "reproduce_phase2_exact.sh", _reproduce_script())
    os.chmod(bundle / "reproduce_phase2_exact.sh", 0o755)
    _write_text(bundle / "install_source_overlay.sh", _install_source_overlay_script())
    os.chmod(bundle / "install_source_overlay.sh", 0o755)
    _write_text(bundle / "verify_phase2_exact_bundle.py", _verify_script())
    os.chmod(bundle / "verify_phase2_exact_bundle.py", 0o755)

    runtime = _runtime_snapshot(summary)
    _write_json(bundle / "runtime_environment.json", runtime)
    source_state = _source_state()
    _write_json(bundle / "source_state.json", source_state)

    file_manifest = _build_file_manifest(bundle)
    _write_json(bundle / "SHA256_MANIFEST.json", file_manifest)
    _write_text(bundle / "SHA256SUMS.txt", _sha256sums_text(file_manifest))
    release_manifest = _release_manifest(summary, runtime, source_state, file_manifest)
    _write_json(bundle / "RELEASE_MANIFEST.json", release_manifest)

    verifier = subprocess.run(
        [sys.executable, str(bundle / "verify_phase2_exact_bundle.py")],
        cwd=str(bundle),
        text=True,
        capture_output=True,
        check=True,
    )

    zip_path = out_root / f"{RELEASE_ID}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(bundle.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(out_root).as_posix())
    zip_digest = _sha256_file(zip_path)
    (out_root / f"{RELEASE_ID}.zip.sha256").write_text(f"{zip_digest}  {zip_path.name}\n", encoding="utf-8")

    return {
        "release_id": RELEASE_ID,
        "bundle_dir": str(bundle),
        "zip": str(zip_path),
        "zip_digest": zip_digest,
        "expected_summary_digest": EXPECTED_SUMMARY_DIGEST,
        "verifier_stdout": verifier.stdout.strip(),
    }


def _copy_evidence(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for path in sorted(src.iterdir()):
        if not path.is_file() or path.name in EXCLUDED_EVIDENCE_NAMES:
            continue
        shutil.copy2(path, dst / path.name)


def _copy_paths(paths: list[str], dst_root: Path) -> None:
    for rel in paths:
        src = ROOT / rel
        if not src.exists():
            continue
        dst = dst_root / rel
        if src.is_dir():
            ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")
            shutil.copytree(src, dst, ignore=ignore)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def _runtime_snapshot(summary: dict[str, Any]) -> dict[str, Any]:
    commands: dict[str, Any] = {}
    for name, command in {
        "git_head": ["git", "rev-parse", "HEAD"],
        "git_branch": ["git", "branch", "--show-current"],
        "git_status_short": ["git", "status", "--short"],
        "pip_freeze": [str(ROOT / ".venv/bin/python"), "-m", "pip", "freeze"],
        "uname": ["uname", "-a"],
        "bpftool_version": ["bpftool", "version"],
        "clang_version": ["clang", "--version"],
        "cc_version": ["cc", "--version"],
    }.items():
        commands[name] = _run_capture(command)
    return {
        "release_id": RELEASE_ID,
        "created_at_utc": _run_capture(["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"]).get("stdout", "").strip(),
        "python": sys.version,
        "platform": platform.platform(),
        "summary_digest": summary.get("summary_digest"),
        "commands": commands,
    }


def _source_state() -> dict[str, Any]:
    diff = _run_capture(["git", "diff", "--binary", "--", *SOURCE_PATHS, *TEST_PATHS])
    diff_text = diff.get("stdout", "")
    return {
        "git_head": _run_capture(["git", "rev-parse", "HEAD"]).get("stdout", "").strip(),
        "git_branch": _run_capture(["git", "branch", "--show-current"]).get("stdout", "").strip(),
        "working_tree_dirty": bool(_run_capture(["git", "status", "--short"]).get("stdout", "").strip()),
        "selected_source_diff_digest": _sha256_text(diff_text),
        "selected_source_diff": diff_text,
    }


def _build_file_manifest(bundle: Path) -> dict[str, Any]:
    entries = []
    for path in sorted(bundle.rglob("*")):
        if not path.is_file() or path.name in {"SHA256_MANIFEST.json", "SHA256SUMS.txt", "RELEASE_MANIFEST.json"}:
            continue
        rel = path.relative_to(bundle).as_posix()
        entries.append({"path": rel, "size_bytes": path.stat().st_size, "sha256": _sha256_file(path)})
    digest = _sha256_json(entries)
    return {"release_id": RELEASE_ID, "entry_count": len(entries), "entries": entries, "manifest_digest": digest}


def _release_manifest(
    summary: dict[str, Any],
    runtime: dict[str, Any],
    source_state: dict[str, Any],
    file_manifest: dict[str, Any],
) -> dict[str, Any]:
    manifest = {
        "release_id": RELEASE_ID,
        "title": "DAI Diode Phase 2 - Stale Listener Exact X2 Kernel Witness",
        "date": "2026-08-04",
        "beast_object_type": "dai_phase2_exact_kernel_witness_release",
        "expected_summary_digest": EXPECTED_SUMMARY_DIGEST,
        "summary": summary,
        "runtime_environment_digest": _sha256_json(runtime),
        "source_state_digest": _sha256_json(source_state),
        "file_manifest_digest": file_manifest["manifest_digest"],
        "one_command_verify": "python3 verify_phase2_exact_bundle.py",
        "source_overlay_installer": "./install_source_overlay.sh /path/to/EdgeK-BEAST",
        "one_command_live_reproduce": "sudo ./reproduce_phase2_exact.sh",
        "authority_boundary": {
            "provider_calls_used": 0,
            "production_authority_allowed": False,
            "execution_scope": "disposable_localhost_child_processes_only",
            "sensorium_authority": "exact_phase2_cgroup_kernel_witness",
        },
    }
    manifest["release_manifest_digest"] = _sha256_json(manifest)
    return manifest


def _readme(summary: dict[str, Any]) -> str:
    return f"""# {RELEASE_ID}

Frozen identity: **DAI-Diode-Phase-2 — Stale Listener Exact X2 Kernel Witness — 2026-08-04**

This capsule preserves the successful BEAST DAI Phase-2 proof run where a
stale localhost listener was replaced under a bounded world lease, while
Sophia acquisition, Seraph hostile probes, Harmonic transfer scoring, Commons
ML-KEM quorum binding, and Sensorium/X2 kernel ring-buffer observation were
joined into one exact receipt.

Key result:

- Green: `{summary["green"]}`
- Summary digest: `{summary["summary_digest"]}`
- Sensorium authority: `{summary["sensorium_bpf_authority_level"]}`
- Exact kernel events bound: `{summary["sensorium_exact_phase2_kernel_events_bound"]}`
- Correlated socket-bind events: `{summary["correlated_socket_bind_event_count"]}`
- Provider calls used: `{summary["provider_calls_used"]}`
- Production authority allowed: `{summary["production_authority_allowed"]}`

Verify the frozen capsule:

```bash
python3 verify_phase2_exact_bundle.py
```

Install this capsule's source overlay into a clean checkout before attempting a
live rerun if the checkout does not already contain the packaged source state:

```bash
./install_source_overlay.sh /path/to/EdgeK-BEAST
```

Attempt a live privileged rerun from a checked-out repository with matching
source and Linux BPF/cgroup privileges:

```bash
sudo ./reproduce_phase2_exact.sh
```
"""


def _claims(summary: dict[str, Any]) -> str:
    return f"""# Claims, nonclaims and known limitations

## Claims

- The preserved run was green with summary digest `{summary["summary_digest"]}`.
- The exact Sensorium flag was true:
  `sensorium_exact_phase2_kernel_events_bound = true`.
- X2 observed three correlated kernel socket-bind events through the cgroup BPF
  witness path.
- The run used zero provider calls.
- Production authority remained false.
- The bounded live state transition retired only the leased stale listener,
  rebound a replacement listener, and preserved the unrelated control listener.

## Nonclaims

- This is not a grant of production remediation authority.
- This is not a claim that arbitrary host processes may be killed or rebound.
- This is not a claim that every Linux kernel exposes the same BPF attachment
  surface.
- This is not a claim of hermetic hardware-independent reproduction.

## Known limitations

- A live rerun requires sudo or equivalent BPF/cgroup privileges.
- The package includes dependency snapshots and source files, but not a full
  frozen VM image.
- The capsule includes `install_source_overlay.sh` so a clean checkout can be
  brought to the exact packaged source/test state before live reproduction.
- The source tree was packaged from the current workspace state; see
  `source_state.json` for the pinned Git HEAD and selected diff digest.
- Commons is bound to the available local ML-KEM receipt included under
  `supporting-evidence/`.
"""


def _authority_map(summary: dict[str, Any]) -> str:
    return f"""# Authority map

| Layer | Evidence | Authority granted |
| --- | --- | --- |
| Sophia | `phase2_sophia_acquisition_receipt.json` | Candidate acquisition only |
| Seraph | `phase2_seraph_injection_report.json` | Hostile probe / challenge only |
| Harmonic | `phase2_harmonic_transfer_report.json` | Transfer scoring only |
| Commons | `phase2_commons_quorum_packet.json` | Quorum admission for exact proposal |
| Arda/live lab | `phase2_live_replacement_receipt.json` | Disposable localhost child-process transition only |
| Sensorium/X2 | `phase2_sensorium_bpf_exact_witness_report.json`, `x2_runtime_receipt.json`, `phase2_x2_exact_kernel_events.json` | `{summary["sensorium_bpf_authority_level"]}` |
| Production systems | Summary field `production_authority_allowed` | `{summary["production_authority_allowed"]}` |

The important boundary: the proof demonstrates bounded, disposable execution
under observation. It does not authorize production mutation.
"""


def _clean_repro() -> str:
    return """# Clean-environment reproduction guide

1. Start from a Linux host with BTF, bpffs, cgroup v2, clang, libbpf, bpftool,
   Python 3.13-compatible dependencies and sudo/BPF privilege.
2. Unpack this capsule beside a checked-out BEAST repository.
3. Compare `source_state.json` and `SHA256_MANIFEST.json` before running.
4. Install this capsule's source overlay into the clean checkout:

   ```bash
   ./install_source_overlay.sh /path/to/EdgeK-BEAST
   ```

5. Run the non-privileged verifier:

   ```bash
   python3 verify_phase2_exact_bundle.py
   ```

6. From the repository root, rebuild the BPF object/loader if needed:

   ```bash
   make -C bpf build/beast_x1_observer.bpf.o build/libbeast_x2_loader.so
   ```

7. Run the live exact proof:

   ```bash
   sudo .venv/bin/python scripts/run_dai_phase2_x2_exact_ring_buffer.py
   ```

8. Confirm the resulting summary is green and has
   `sensorium_bpf_authority_level = exact_phase2_cgroup_kernel_witness`.
"""


def _reproduce_script() -> str:
    return """#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -n "${BEAST_REPO_ROOT:-}" ]; then
  REPO_ROOT="$BEAST_REPO_ROOT"
elif [ -f "$PWD/scripts/run_dai_phase2_x2_exact_ring_buffer.py" ]; then
  REPO_ROOT="$PWD"
elif [ -f "$SCRIPT_DIR/../../scripts/run_dai_phase2_x2_exact_ring_buffer.py" ]; then
  REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
else
  echo "Set BEAST_REPO_ROOT=/path/to/EdgeK-BEAST before running live reproduction." >&2
  exit 64
fi
cd "$REPO_ROOT"
make -C bpf build/beast_x1_observer.bpf.o build/libbeast_x2_loader.so
PYTHONNOUSERSITE=1 .venv/bin/python -m pytest \\
  tests/test_dai_phase2_x2_exact_ring_buffer_script.py \\
  tests/test_dai_phase2_sensorium_bpf.py \\
  tests/test_dai_phase2_stale_listener.py -q
.venv/bin/python scripts/run_dai_phase2_x2_exact_ring_buffer.py
"""


def _install_source_overlay_script() -> str:
    return """#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -ne 1 ]; then
  echo "Usage: $0 /path/to/EdgeK-BEAST-clean-checkout" >&2
  exit 64
fi
TARGET_ROOT="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ ! -d "$TARGET_ROOT" ]; then
  echo "Target root does not exist: $TARGET_ROOT" >&2
  exit 66
fi
if [ ! -d "$TARGET_ROOT/app" ] || [ ! -d "$TARGET_ROOT/scripts" ]; then
  echo "Target does not look like an EdgeK-BEAST checkout: $TARGET_ROOT" >&2
  exit 65
fi
for tree in source tests dependencies; do
  if [ ! -d "$SCRIPT_DIR/$tree" ]; then
    continue
  fi
  (
    cd "$SCRIPT_DIR/$tree"
    find . -type f -print0
  ) | while IFS= read -r -d '' rel; do
    src="$SCRIPT_DIR/$tree/${rel#./}"
    dst="$TARGET_ROOT/${rel#./}"
    mkdir -p "$(dirname "$dst")"
    cp -p "$src" "$dst"
  done
done
echo "Installed DAI Phase-2 source overlay into $TARGET_ROOT"
"""


def _verify_script() -> str:
    return f'''#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json
from pathlib import Path

EXPECTED_SUMMARY_DIGEST = "{EXPECTED_SUMMARY_DIGEST}"
ROOT = Path(__file__).resolve().parent

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()

def main() -> int:
    manifest = json.loads((ROOT / "SHA256_MANIFEST.json").read_text(encoding="utf-8"))
    for entry in manifest["entries"]:
        path = ROOT / entry["path"]
        if not path.exists():
            raise SystemExit(f"missing {{entry['path']}}")
        digest = sha256_file(path)
        if digest != entry["sha256"]:
            raise SystemExit(f"digest mismatch for {{entry['path']}}: {{digest}} != {{entry['sha256']}}")
    summary_path = ROOT / "{EVIDENCE_RELATIVE_PATH}/phase2_x2_exact_ring_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["summary_digest"] == EXPECTED_SUMMARY_DIGEST
    assert summary["green"] is True
    assert summary["sensorium_exact_phase2_kernel_events_bound"] is True
    assert summary["sensorium_bpf_authority_level"] == "exact_phase2_cgroup_kernel_witness"
    assert summary["correlated_socket_bind_event_count"] == 3
    assert summary["provider_calls_used"] == 0
    assert summary["production_authority_allowed"] is False
    forbidden = ROOT / "{EVIDENCE_RELATIVE_PATH}/x2_exact_ring_failure.json"
    assert not forbidden.exists()
    print(json.dumps({{"verified": True, "summary_digest": summary["summary_digest"], "entry_count": manifest["entry_count"]}}, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
'''


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_json(payload: Any) -> str:
    return _sha256_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _sha256sums_text(manifest: dict[str, Any]) -> str:
    return "".join(f"{entry['sha256'].removeprefix('sha256:')}  {entry['path']}\n" for entry in manifest["entries"])


def _run_capture(command: list[str]) -> dict[str, Any]:
    try:
        result = subprocess.run(command, cwd=str(ROOT), text=True, capture_output=True, timeout=60)
        return {"command": command, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    except Exception as exc:
        return {"command": command, "error": f"{type(exc).__name__}: {exc}"}


if __name__ == "__main__":
    raise SystemExit(main())
