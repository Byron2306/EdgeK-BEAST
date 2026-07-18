import os
from pathlib import Path

from app.kernel.compute.disk_pressure_cleanup import build_cleanup_manifest
from app.kernel.execution.isolated_disk_cleanup import IsolatedDiskCleanupRunner
from app.kernel.execution.race_free_cgroup_launcher import NativeCgroupLauncherCompiler


def test_native_cleanup_worker_compiles_and_manifest_is_descriptor_format(tmp_path: Path):
    (tmp_path / "cleanup-policy.json").write_text('{"version":"beast.disk-cleanup.v1","cache_roots":["cache"],"min_age_seconds":0,"max_files":2,"max_bytes":100,"approval_threshold_bytes":50}')
    (tmp_path / "cache").mkdir();(tmp_path / "cache/a").write_bytes(b"abc")
    manifest,_=build_cleanup_manifest(tmp_path)
    payload=IsolatedDiskCleanupRunner._manifest_bytes(manifest)
    assert payload.startswith(b"BEAST_DISK_V1\t1\t3\tsha256:")
    worker=NativeCgroupLauncherCompiler().compile_disk_cleanup_worker(tmp_path/"worker")
    assert worker.is_file() and os.access(worker,os.X_OK)
