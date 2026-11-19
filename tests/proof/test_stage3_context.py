from scripts.proof.retrieval_ablation import build_retrieval
from scripts.proof.run_coder_efficiency_matrix import make_plan, project_diagnostic


def test_stage3_boundaries_keep_small_function_together(tmp_path):
    lines = ["# preamble"] * 12 + ["@decorator", "def dependency():", "    return 'hello'"]
    (tmp_path / "sample.py").write_text("\n".join(lines))
    fixed = build_retrieval(tmp_path, ["sample.py"], "lexical", "dependency")
    syntax = build_retrieval(tmp_path, ["sample.py"], "lexical", "dependency", chunking="syntax")
    assert fixed["corpus_sha256"] != syntax["corpus_sha256"]
    assert any(x["line"] == 13 and x["excerpt"] == "\n".join(lines[12:]) for x in syntax["chunks"])


def test_stage3_invalid_python_falls_back_to_fixed(tmp_path):
    (tmp_path / "broken.py").write_text("def broken(")
    fixed = build_retrieval(tmp_path, ["broken.py"], "lexical", "broken")
    syntax = build_retrieval(tmp_path, ["broken.py"], "lexical", "broken", chunking="syntax")
    assert fixed["corpus_sha256"] == syntax["corpus_sha256"]


def test_stage3_sgr_and_checkpoint_whitespace_are_independent():
    raw = "\x1b[31mERROR alpha-01\x1b[0m\n  actual = '  '\n\x1b[2J\ncontract runner checkpoint: stage3   \t\n"
    ansi, _ = project_diagnostic(raw, "ansi_sgr", "native", {})
    whitespace, _ = project_diagnostic(raw, "checkpoint_padding", "native", {})
    assert ansi == raw.replace("\x1b[31m", "").replace("\x1b[0m", "")
    assert whitespace == raw.replace("stage3   \t", "stage3")
    assert project_diagnostic("context\n  +    code  \n \t\n", "checkpoint_padding", "native", {})[0] == "context\n  +    code  \n \t\n"


def test_stage3_plan_is_paired_and_keeps_bm25_fixed():
    plan = make_plan(("sample",), 1, 71, experiment="retrieval-chunking")
    assert {(r["arm"], r["retrieval"], r["retrieval_chunking"]) for r in plan} == {
        ("fixed", "lexical", "fixed"), ("syntax", "lexical", "syntax")}
    plan = make_plan(("sample",), 1, 71, experiment="diagnostic-filters")
    assert {(r["arm"], r["compression"]) for r in plan} == {
        ("raw", "none"), ("ansi_sgr", "ansi_sgr"), ("checkpoint_padding", "checkpoint_padding")}


def test_stage3_filters_render_only_assigned_changes(tmp_path, monkeypatch):
    import json
    from scripts.proof.run_coder_efficiency_matrix import main

    monkeypatch.chdir(tmp_path)
    out = tmp_path / "results"
    assert main(["--out", str(out), "--experiment", "diagnostic-filters", "--tasks", "retry"]) == 0
    for arm, expected in [("raw", 0), ("ansi_sgr", 38), ("checkpoint_padding", 148)]:
        events = [json.loads(line) for line in (out / "events" / f"retry-01-{arm}.jsonl").read_text().splitlines()]
        projections = [event["payload"] for event in events
                       if event.get("event_type") == "agent.efficiency.compression_prompt"]
        assert projections
        assert all(p["bytes_saved"] == expected and p["applied"] == bool(expected) for p in projections)
    rows = [json.loads(line) for line in (out / "attempts.jsonl").read_text().splitlines()]
    assert len(rows) == 3 and all(row["verified"] and row["diagnostic_preflight"] for row in rows)
    assert all(row["compression_provider_deliveries"] == 0 for row in rows)
