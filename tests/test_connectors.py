import json

import httpx

from app.kernel.networking.github_pr_connector import GitHubPRConnector
from app.kernel.networking.network_chronicle import NetworkChronicleConnector
from app.kernel.execution.task_envelope import TaskEnvelopeBuilder


def test_network_chronicle_attaches_metadata_without_packet_payloads(tmp_path):
    connector = NetworkChronicleConnector()
    diagnostic = {
        "task_id": "tsk_network", "provider": "openrouter",
        "failure_category": "timeout_or_network", "confidence": 0.8,
        "cloud_escalation_needed": False, "local_only": True,
        "envelope": {"task_class": "provider_debugging"}, "route_card": {},
        "checks": [], "recommendations": [],
    }
    probe = {
        "opened": True, "captured": True, "mode": "af_packet_raw_capture",
        "interface": "lo", "packets_seen": 3,
        "samples": [{"payload_preview_hex": "super-secret-payload"}],
    }
    builder = TaskEnvelopeBuilder(data_dir=str(tmp_path / "data"))

    result = connector.attach_provider_diagnostic(
        diagnostic, probe, chronicle_builder=builder, persist=True
    )
    evidence = result["network_evidence"]
    stored = json.loads((tmp_path / "data" / "chronicles" / "tsk_network_openrouter_diagnostic.json").read_text())

    assert evidence["status"] == "passed"
    assert evidence["summary"]["sample_count"] == 1
    assert evidence["privacy"]["payload_bytes_retained"] is False
    assert "super-secret-payload" not in json.dumps(evidence)
    assert stored["network_evidence"]["evidence_id"] == evidence["evidence_id"]


def test_network_chronicle_attaches_evidence_to_benchmark_rows():
    connector = NetworkChronicleConnector()
    report = {"live_results": [{"provider": "xai", "output_evidence": {}}]}

    attached = connector.attach_benchmark_report(
        report, {"opened": True, "captured": True, "mode": "af_packet_raw_capture", "packets": 1}
    )

    evidence_id = attached["network_chronicle"]["evidence_id"]
    assert attached["live_results"][0]["output_evidence"]["network_probe_evidence_id"] == evidence_id
    assert "network_chronicle" not in report


def _github_handler(published):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST":
            published.append(json.loads(request.content))
            return httpx.Response(201, json={"id": 99, "html_url": "https://github.test/comment/99"})
        if path.endswith("/pulls/7"):
            return httpx.Response(200, json={
                "title": "Fix async route", "body": "Make timeout fallback deterministic",
                "html_url": "https://github.test/acme/demo/pull/7", "user": {"login": "dev"},
                "base": {"ref": "main"}, "head": {"ref": "fix", "sha": "abc123"}, "draft": False,
            })
        if path.endswith("/pulls/7/files"):
            return httpx.Response(200, json=[{
                "filename": "app/runtime.py", "status": "modified", "additions": 4,
                "deletions": 2, "patch": "@@ -1 +1 @@\n-old\n+new",
            }])
        if path.endswith("/pulls/7/comments"):
            return httpx.Response(200, json=[{
                "user": {"login": "reviewer"}, "path": "app/runtime.py", "line": 8,
                "body": "Please preserve cancellation.", "html_url": "https://github.test/review/1",
            }])
        if path.endswith("/issues/7/comments"):
            return httpx.Response(200, json=[])
        if path.endswith("/commits/abc123/check-runs"):
            return httpx.Response(200, json={"check_runs": [{
                "name": "pytest", "status": "completed", "conclusion": "failure",
                "html_url": "https://github.test/check/1", "output": {"summary": "1 failed"},
            }]})
        return httpx.Response(404, json={"message": path})
    return handler


def test_github_pr_connector_builds_task_envelope_from_pr_evidence():
    published = []
    client = httpx.Client(transport=httpx.MockTransport(_github_handler(published)))
    connector = GitHubPRConnector(token="test-token", client=client)

    packet = connector.ingest("acme/demo", 7)

    assert packet["beast_object_type"] == "github_pr_task_packet"
    assert packet["counts"] == {"changed_files": 1, "checks": 1, "failed_checks": 1, "review_comments": 1}
    assert packet["task_envelope"]["task_class"] == "github_pr_remediation"
    assert packet["task_envelope"]["risk_level"] == "high"
    assert packet["evidence"]["changed_files"][0]["filename"] == "app/runtime.py"
    assert "pytest" in packet["task_envelope"]["inputs"]["user_request"]


def test_github_pr_chronicle_publish_is_dry_run_and_approval_gated():
    published = []
    client = httpx.Client(transport=httpx.MockTransport(_github_handler(published)))
    connector = GitHubPRConnector(token="test-token", client=client)
    chronicle = {
        "task_id": "tsk_pr", "provider": "openrouter", "category": "tests_failed",
        "summary": "Patch verified after repair.",
        "verification": {"local_checks_completed": True},
        "recommendations": ["Merge after CI passes."],
    }

    dry = connector.publish_chronicle("acme/demo", 7, chronicle)
    unapproved = connector.publish_chronicle("acme/demo", 7, chronicle, approved=False, dry_run=False)
    live = connector.publish_chronicle("acme/demo", 7, chronicle, approved=True, dry_run=False)

    assert dry["published"] is False
    assert unapproved["published"] is False
    assert live["published"] is True
    assert live["comment_id"] == 99
    assert len(published) == 1
    assert "BEAST Chronicle Summary" in published[0]["body"]

