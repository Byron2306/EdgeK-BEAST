import json

from scripts.proof.run_coder_efficiency_matrix import build_graph_packet, make_plan


def test_packet_uses_real_symbols_and_local_edges(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "entry.py").write_text("from dependency import choice\n\ndef start():\n    return choice()\n")
    (root / "dependency.py").write_text("def choice():\n    return 1\n")
    (root / "unrelated.py").write_text("def choice():\n    return 99\n")
    paths = ["dependency.py", "entry.py", "unrelated.py"]
    packets = {}
    for arm in ("file_list", "symbols", "graph"):
        packet = build_graph_packet(root, paths, arm, tmp_path / f"{arm}.sqlite3")
        packets[arm] = json.loads(packet["sent"])
        assert packets[arm]["files"] == paths
        assert "return 99" not in packet["sent"]
    assert set(packets["file_list"]) == {"files"}
    assert packets["symbols"]["symbols"] == packets["graph"]["symbols"]
    assert {x["path"] for x in packets["graph"]["symbols"] if x["name"] == "choice"} == {
        "dependency.py", "unrelated.py",
    }
    assert packets["graph"]["edges"] == [{"from": "entry.py", "to": "dependency.py"}]


def test_navigation_plan_all_arms_are_prebound_and_closeout_enabled():
    plan = make_plan(("shipped_tariff",), 3, 4323, experiment="worktree-navigation")
    for i in range(0, 9, 3):
        block = plan[i:i+3]
        assert {row["arm"] for row in block} == {"file_list", "symbols", "graph"}
        assert all(row["prebind"] and row["closeout"] and not row["reporelay"] for row in block)


def test_graph_reports_incremental_paired_comparison(tmp_path):
    from scripts.proof.run_coder_efficiency_matrix import main

    report = tmp_path / "graph"
    assert main(["--experiment", "worktree-navigation", "--tasks", "shipped_tariff",
                 "--out", str(report)]) == 0
    summary = json.loads((report / "summary.json").read_text())
    assert all(arm["verified"] == 1 for arm in summary["arms"].values())
    assert {row["arm"] for row in summary["paired_against_file_list"]} == {"symbols", "graph"}
    graph_vs_symbols, = summary["paired_graph_against_symbols"]
    assert graph_vs_symbols["arm"] == "graph"
    events = [
        json.loads(line) for line in
        (report / "events/shipped_tariff-01-graph.jsonl").read_text().splitlines()
    ]
    event, = [e for e in events if e["event_type"] == "agent.efficiency.navigation_packet_prompt"]
    assert event["payload"]["turn"] == 1
    assert event["payload"]["navigation"]["edges"] >= 1
    assert all(arm["source_packet_provider_compressed_deliveries"] == 0
               for arm in summary["arms"].values())
