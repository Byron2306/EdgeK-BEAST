from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest

class StopAfterFirstWait:
    def __init__(self) -> None:
        self.wait_calls = 0

    def is_set(self) -> bool:
        return False

    def wait(self, timeout: float) -> bool:
        self.wait_calls += 1
        return True


class RecordingNode:
    def __init__(self) -> None:
        self.profile = SimpleNamespace(last_activity_at="")
        self.snapshots: list[Path] = []
        self.closed = False

    def persist_snapshot(self, path: Path) -> None:
        self.snapshots.append(path)

    def close(self) -> None:
        self.closed = True


class EdgeboxServiceTests(unittest.TestCase):
    def test_service_stays_alive_until_stop_and_closes_node(self) -> None:
        try:
            from app.kernel.compute.edgebox_service import run_service
        except ModuleNotFoundError:
            self.fail("EdgeBox has no long-running service entrypoint")
        node = RecordingNode()
        stop = StopAfterFirstWait()
        with TemporaryDirectory() as temporary_dir:
            snapshot_path = Path(temporary_dir) / "status.json"

            run_service(
                node=node,
                stop_event=stop,
                snapshot_path=snapshot_path,
                interval_seconds=30.0,
            )

        self.assertEqual(stop.wait_calls, 1)
        self.assertEqual(node.snapshots, [snapshot_path])
        self.assertTrue(node.closed)
        self.assertTrue(node.profile.last_activity_at)


if __name__ == "__main__":
    unittest.main()
