from app.kernel.agents.background_forge import BackgroundForgeCoordinator


class FakeNode:
    def watch_repo(self, repo_path, target_paths=None):
        return {"fingerprint_hash": "sha256:fingerprint", "target_paths": target_paths}

    def update_test_impact_map(self, repo_path, test_paths):
        return {"test_paths": test_paths, "impact": "prepared"}

    def perform_secret_scan(self, repo_path):
        return {"secrets_found": 0, "status": "passed"}

    def prepare_handoff_packet(self, task_class, route_card, context_packet):
        return {"task_class": task_class, "reduction_pct": 42.0}


class FakeScheduler:
    def submit_work(self, work_type, repo_path, priority=5, metadata=None):
        return {"work_type": work_type, "repo_path": repo_path, "priority": priority, "metadata": metadata}


def test_background_forge_prepares_only_read_side_artifacts():
    result = BackgroundForgeCoordinator(FakeNode()).prepare(
        repo_path="/workspace",
        target_paths=["pricing.py"],
        test_paths=["tests/test_pricing.py"],
        task_class="test_repair",
        route_card={"route_id": "local"},
        context_packet={"packet_id": "ctx-1"},
    )

    assert result["preparation_digest"].startswith("sha256:")
    assert result["foreground_authority"] is False
    assert result["mutation_applied"] is False
    assert result["receipts"]["handoff"]["reduction_pct"] == 42.0


def test_background_forge_submission_is_explicitly_background_only():
    result = BackgroundForgeCoordinator(FakeNode(), FakeScheduler()).submit(
        work_type="fingerprint_repo", repo_path="/workspace"
    )

    assert result["status"] == "queued"
    assert result["work_item"]["metadata"]["background_only"] is True
    assert result["foreground_authority"] is False
