import json
from pathlib import Path

from benchmarks import public_economic_thesis_harness as harness


def test_public_economic_thesis_harness_writes_template_and_verdict(tmp_path: Path):
    rows = [
        {
            "source_path": "benchmarks/results/demo/governed.json",
            "task": "task_a",
            "lane_class": "governed",
            "lane": "x_full_beast",
            "provider": "demo",
            "model": "demo-model",
            "completed": True,
            "latency_ms": 120.0,
            "prompt": "Fix task A",
            "output_text": "answer a",
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
            "cost_usd": 0.03,
            "verification": {},
            "output_evidence": {},
        },
        {
            "source_path": "benchmarks/results/demo/baseline.json",
            "task": "task_b",
            "lane_class": "baseline",
            "lane": "x_raw",
            "provider": "demo",
            "model": "demo-model",
            "completed": False,
            "latency_ms": 95.0,
            "prompt": "Fix task B",
            "output_text": "answer b",
            "prompt_tokens": 8,
            "completion_tokens": 16,
            "total_tokens": 24,
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
    template_info = harness.write_grader_template(tmp_path)
    cost_info = harness.write_cost_accounting(rows, tmp_path)
    harness.write_summary(packet, blind_info, cost_info, tmp_path)
    harness.write_manifest(packet, blind_info, cost_info, tmp_path, [])

    assert Path(blind_info["packet_path"]).exists()
    assert Path(template_info["template_path"]).exists()

    blinded = harness.load_jsonl(tmp_path / "blind_grading.jsonl")
    key = json.loads((tmp_path / "blind_grading_key.json").read_text(encoding="utf-8"))
    assert len(blinded) == len(rows)
    assert {item["blind_id"] for item in blinded} == set(key.keys())

    graded_rows = []
    for item in blinded:
        graded_rows.append({
            "blind_id": item["blind_id"],
            "passes_task": key[item["blind_id"]]["lane_class"] == "governed",
            "quality_score": 0.9 if key[item["blind_id"]]["lane_class"] == "governed" else 0.2,
            "notes": "synthetic",
        })
    grades_path = tmp_path / "grades.jsonl"
    grades_path.write_text("".join(json.dumps(item) + "\n" for item in graded_rows), encoding="utf-8")

    verdict = harness.build_verdict(tmp_path, [str(grades_path)])
    verdict_info = harness.write_verdict(tmp_path, verdict)

    assert verdict["claim_status"] == "supported"
    assert Path(verdict_info["path"]).exists()
    assert Path(verdict_info["summary_path"]).exists()


def test_alpha_packet_filters_to_human_graded_balanced_rows():
    rows = [
        {
            "source_path": "a.json",
            "task": "g1",
            "lane_class": "governed",
            "lane": "live_full_beast",
            "provider": "demo",
            "model": "demo",
            "completed": True,
            "latency_ms": 10,
            "prompt": "task",
            "output_text": "",
            "provider_text_excerpt": "governed excerpt 1",
            "prompt_tokens": 1,
            "completion_tokens": 2,
            "total_tokens": 3,
            "cost_usd": 0.01,
            "verification": {},
            "output_evidence": {},
        },
        {
            "source_path": "b.json",
            "task": "g2",
            "lane_class": "governed",
            "lane": "live_full_beast",
            "provider": "demo",
            "model": "demo",
            "completed": True,
            "latency_ms": 11,
            "prompt": "task",
            "output_text": "governed output 2",
            "prompt_tokens": 1,
            "completion_tokens": 2,
            "total_tokens": 3,
            "cost_usd": 0.01,
            "verification": {},
            "output_evidence": {},
        },
        {
            "source_path": "c.json",
            "task": "b1",
            "lane_class": "baseline",
            "lane": "live_raw",
            "provider": "demo",
            "model": "demo",
            "completed": False,
            "latency_ms": 12,
            "prompt": "task",
            "output_text": "baseline output 1",
            "prompt_tokens": 1,
            "completion_tokens": 2,
            "total_tokens": 3,
            "cost_usd": 0.01,
            "verification": {},
            "output_evidence": {},
        },
        {
            "source_path": "d.json",
            "task": "meta",
            "lane_class": "candidate",
            "lane": "",
            "provider": "",
            "model": "",
            "completed": False,
            "latency_ms": None,
            "prompt": "",
            "output_text": "",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost_usd": None,
            "verification": {},
            "output_evidence": {},
        },
    ]

    normalized = [
        harness.normalize_row(row, Path(row["source_path"]), index)
        for index, row in enumerate(rows)
    ]
    packet = harness.build_alpha_packet(normalized, lane_size=1, seed=7)

    assert packet["alpha"]["enabled"] is True
    assert packet["row_count"] == 2
    assert {row["lane_class"] for row in packet["rows"]} == {"governed", "baseline"}
    assert all(row["output_text"] for row in packet["rows"])