import hashlib
import json

from scripts.proof import run_coder_efficiency_matrix as matrix


def test_source_plan_freezes_closeout_with_only_lcz_enabled():
    rows = matrix.make_plan(("shipping", "retry"), 2, 4321, experiment="source-compression")
    assert len(rows) == 8
    for index in range(0, len(rows), 2):
        a, b = rows[index:index + 2]
        assert (a["task"], a["repeat"]) == (b["task"], b["repeat"])
        assert {a["arm"], b["arm"]} == {"closeout", "longcodezip"}
        assert all(row["closeout"] and not row["reporelay"] and "compression" not in row for row in (a, b))


def test_source_matrix_keeps_edit_target_byte_exact_and_compacts_support(tmp_path):
    report = tmp_path / "report"
    assert matrix.main([
        "--experiment", "source-compression", "--out", str(report),
    ]) == 0
    rows = list(map(json.loads, (report / "attempts.jsonl").read_text().splitlines()))
    assert len(rows) == 6
    for row in rows:
        assert row["verified"]
        assert row["baseline_public_exit"] == row["baseline_independent_exit"] == 1
        assert row["source_packet_rendered"] == 1
        events = list(map(json.loads, (report / "events" / f'{row["attempt_id"]}.jsonl').read_text().splitlines()))
        receipts = [event["payload"] for event in events
                    if event["event_type"] == "agent.efficiency.source_packet_prompt"]
        receipt, = receipts
        target, support = receipt["files"]
        assert target["path"] == row["changed_paths"][0]
        assert target["raw_sha256"] == target["sent_sha256"]
        assert support["path"] != target["path"]
        assert target["raw_sha256"] == row["fixture_files_sha256"][target["path"]]
        assert support["raw_sha256"] == row["fixture_files_sha256"][support["path"]]
        if row["arm"] == "longcodezip":
            assert receipt["bytes_saved"] > 0
            assert support["stubbed"]
            assert receipt["raw_prompt_sha256"] != receipt["sent_prompt_sha256"]
        else:
            assert receipt["bytes_saved"] == 0
    summary = json.loads((report / "summary.json").read_text())
    assert len(summary["paired_against_closeout"]) == 3
    assert summary["arms"]["longcodezip"]["source_packet_provider_deliveries"] == 0


def test_source_packet_never_uses_failed_fidelity(monkeypatch, tmp_path):
    task = matrix.SOURCE_TASKS["shipped_tariff"]
    matrix.create_fixture(tmp_path / "fixture", task)
    monkeypatch.setattr(matrix, "long_code_compress", lambda *a, **kw: {
        "content": "broken", "fidelity": {"passed": False}, "stubbed": ["bad"],
    })
    packet = matrix.build_source_packet(tmp_path / "fixture", task, compress=True)
    assert packet["raw"] == packet["sent"]
    assert packet["files"][1]["reason"] == "fidelity_failed"
    assert packet["files"][0]["raw_sha256"] == hashlib.sha256(task.source.encode()).hexdigest()


def test_provider_receipts_join_the_exact_delivered_source_packet(tmp_path, monkeypatch):
    import io

    from app.kernel.agents import nim_planner_provider

    tasks = matrix.SOURCE_TASKS
    target = tasks["shipped_tariff"]
    seen = []
    monkeypatch.setenv("NVIDIA_API_KEY", "fixture-key")

    def respond(_client, request, **kwargs):
        prompt = json.loads(request.data)["messages"][-1]["content"]
        seen.append(prompt)
        if "BOUND WORKTREE SOURCE PACKET." in prompt:
            tool = "worktree.replace_exact"
            arguments = {"path": target.path, "old_text": target.old, "new_text": target.new}
        else:
            tool, arguments = "worktree.bind", {}
        decision = {"decision_type": "tool", "tool_id": tool, "arguments": arguments, "summary": "", "blocker": ""}
        return io.BytesIO(json.dumps({
            "choices": [{"message": {"content": json.dumps(decision)}}],
            "usage": {"prompt_tokens": 200, "completion_tokens": 10},
        }).encode())

    monkeypatch.setattr(nim_planner_provider._egress, "urlopen", respond)
    report = tmp_path / "adapter"
    assert matrix.main([
        "--experiment", "source-compression", "--provider", "nim", "--tasks", "shipped_tariff",
        "--request-cap", "16", "--out", str(report),
    ]) == 0
    summary = json.loads((report / "summary.json").read_text())
    assert len(seen) == 4
    assert sum("BOUND WORKTREE SOURCE PACKET." in prompt for prompt in seen) == 2
    assert sum(matrix.STUB_MARK in prompt for prompt in seen) == 1
    assert all(arm["verified"] == arm["source_packet_provider_deliveries"] == 1
               for arm in summary["arms"].values())
    assert summary["arms"]["longcodezip"]["source_packet_provider_compressed_deliveries"] == 1
