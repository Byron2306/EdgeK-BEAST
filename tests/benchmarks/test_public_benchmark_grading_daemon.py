import json
from pathlib import Path

from app.kernel.compute.public_benchmark_grading_daemon import PublicBenchmarkGradingDaemon
from benchmarks import public_economic_thesis_harness as harness


def _build_packet(tmp_path: Path) -> None:
    rows = [
        {
            "source_path": "demo_governed.json",
            "task": "task_a",
            "lane_class": "governed",
            "lane": "live_full_beast",
            "provider": "demo",
            "model": "demo-model",
            "completed": True,
            "latency_ms": 50.0,
            "prompt": "task a",
            "output_text": '{"kind":"beast.action_intent.v1","actions":[{"id":"a1","type":"replace_anchor","target":{"path":"app/a.py","anchor_ref":"A1"},"intent":"fix task a","new":"return 2"}],"verify":["python -m pytest tests -q"]}',
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
            "cost_usd": 0.03,
            "verification": {},
            "output_evidence": {},
        },
        {
            "source_path": "demo_baseline.json",
            "task": "task_b",
            "lane_class": "baseline",
            "lane": "live_raw",
            "provider": "demo",
            "model": "demo-model",
            "completed": False,
            "latency_ms": 70.0,
            "prompt": "task b",
            "output_text": "try changing the function maybe",
            "prompt_tokens": 9,
            "completion_tokens": 11,
            "total_tokens": 20,
            "cost_usd": 0.02,
            "verification": {},
            "output_evidence": {},
        },
    ]
    packet = {
        "generated_at": harness.utc_now(),
        "claim_status": "open_research_question",
        "claim_scope": "test",
        "row_count": len(rows),
        "rows": rows,
    }
    blind_info = harness.write_blind_grading(rows, tmp_path, seed=7)
    harness.write_grader_template(tmp_path)
    cost_info = harness.write_cost_accounting(rows, tmp_path)
    harness.write_summary(packet, blind_info, cost_info, tmp_path)
    harness.write_manifest(packet, blind_info, cost_info, tmp_path, [])


def test_public_benchmark_grading_daemon_run_once(tmp_path: Path):
    _build_packet(tmp_path)
    daemon = PublicBenchmarkGradingDaemon(tmp_path)
    result = daemon.run_once()

    assert result["ready"] is True
    assert result["claim_status"] == "supported"
    assert result["structural_claim_status"] == "supported"
    assert (tmp_path / "provisional_grades_from_verification.jsonl").exists()
    assert (tmp_path / "structural_grades.jsonl").exists()
    verdict = json.loads((tmp_path / "provisional_verdict.json").read_text(encoding="utf-8"))
    assert verdict["claim_status_basis"] == "provisional_verification_grades"
    structural_verdict = json.loads((tmp_path / "structural_verdict.json").read_text(encoding="utf-8"))
    assert structural_verdict["claim_status_basis"] == "deterministic_structure_grade"


def test_public_benchmark_grading_daemon_run_loop(tmp_path: Path):
    _build_packet(tmp_path)
    daemon = PublicBenchmarkGradingDaemon(tmp_path)
    result = daemon.run_loop(interval_seconds=0.0, max_cycles=2)

    assert result["cycle_count"] == 2
    assert (tmp_path / "grading_daemon_service_run.json").exists()
    state = json.loads((tmp_path / "grading_daemon_service_state.json").read_text(encoding="utf-8"))
    assert state["running"] is False