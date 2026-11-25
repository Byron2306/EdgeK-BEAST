import io
import json
from urllib.error import HTTPError

from app.kernel.agents import nim_planner_provider
from scripts.proof import run_coder_efficiency_matrix as matrix


def test_repeated_first_turn_http_rejection_seals_partial_matrix(tmp_path, monkeypatch):
    key = "sensitive-test-credential"
    monkeypatch.setenv("NVIDIA_API_KEY", key)
    calls = []

    def reject(_client, request, **kwargs):
        calls.append(request.full_url)
        body = json.dumps({
            "request_id": f"per-request-{len(calls)}",
            "error": {"code": "invalid_model", "message": f"Rejected Bearer {key} and nvapi-hidden-test"},
        }).encode()
        raise HTTPError(request.full_url, 400, "Bad Request", {}, io.BytesIO(body))

    monkeypatch.setattr(nim_planner_provider._egress, "urlopen", reject)
    report = tmp_path / "report"
    assert matrix.main([
        "--experiment", "diagnostic-compression", "--provider", "nim",
        "--seed", "4320", "--repeats", "5", "--request-cap", "360", "--out", str(report),
    ]) == 3
    assert len(calls) == 2
    rows = list(map(json.loads, (report / "attempts.jsonl").read_text().splitlines()))
    assert [(row["state"], row["verified"]) for row in rows] == [
        ("paused", False), ("paused", False),
    ] + [("not_run", None)] * 43
    assert rows[0]["arm"] != rows[1]["arm"]
    assert rows[0]["first_turn_http_rejection"]["status"] == 400
    assert rows[0]["first_turn_http_rejection"]["code"] == "invalid_model"
    assert rows[0]["first_turn_http_rejection"]["fingerprint"] == rows[1]["first_turn_http_rejection"]["fingerprint"]
    summary = json.loads((report / "summary.json").read_text())
    assert summary["batch"]["status"] == "aborted_provider_rejection"
    assert summary["batch"]["attempted"] == 2
    assert summary["batch"]["not_run"] == 43
    assert summary["arms"][rows[2]["arm"]]["verified_rate"] is None
    assert not (report / "provider" / f'{rows[2]["attempt_id"]}.json').exists()
    manifest = (report / "SHA256SUMS").read_text().splitlines()
    for line in manifest:
        sha, path = line.split("  ", 1)
        contents = (report / path).read_bytes()
        assert matrix.digest(contents) == sha
        assert key.encode() not in contents
        assert b"nvapi-hidden-test" not in contents


def test_distinct_first_turn_rejections_do_not_abort(tmp_path, monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    calls = []

    def reject(_client, request, **kwargs):
        calls.append(request.full_url)
        body = json.dumps({"error": {"code": f"error_{len(calls)}", "message": "Rejected"}}).encode()
        raise HTTPError(request.full_url, 400, "Bad Request", {}, io.BytesIO(body))

    monkeypatch.setattr(nim_planner_provider._egress, "urlopen", reject)
    report = tmp_path / "report"
    assert matrix.main([
        "--experiment", "diagnostic-compression", "--provider", "nim", "--tasks", "retry",
        "--request-cap", "24", "--out", str(report),
    ]) == 0
    assert len(calls) == 3
    summary = json.loads((report / "summary.json").read_text())
    assert summary["batch"]["status"] == "completed"
    assert summary["batch"]["not_run"] == 0


def test_ordinary_coder_pause_breaks_rejection_streak(tmp_path, monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "fake-key")
    calls = []

    def respond(_client, request, **kwargs):
        calls.append(request.full_url)
        if len(calls) == 2:
            decision = {"decision_type": "blocked", "tool_id": "", "arguments": {},
                        "blocker": "The model requested help."}
            return io.BytesIO(json.dumps({"choices": [{"message": {"content": json.dumps(decision)}}]}).encode())
        body = b'{"error": {"code": "invalid_model", "message": "Rejected"}}'
        raise HTTPError(request.full_url, 400, "Bad Request", {}, io.BytesIO(body))

    monkeypatch.setattr(nim_planner_provider._egress, "urlopen", respond)
    report = tmp_path / "report"
    assert matrix.main([
        "--experiment", "diagnostic-compression", "--provider", "nim", "--tasks", "retry",
        "--request-cap", "24", "--out", str(report),
    ]) == 0
    assert len(calls) == 3
    rows = list(map(json.loads, (report / "attempts.jsonl").read_text().splitlines()))
    assert rows[1]["first_turn_http_rejection"] is None
    assert rows[0]["first_turn_http_rejection"] == rows[2]["first_turn_http_rejection"]
    assert json.loads((report / "summary.json").read_text())["batch"]["not_run"] == 0
