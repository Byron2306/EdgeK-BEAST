import json

from scripts.proof.run_stage5a_semantic_pages import ARMS, main, run_block


def test_5a_exact_identity_reuses_real_graph_and_rejects_stale_or_tampered_pages(tmp_path):
    rows, seed = run_block(tmp_path, size=8, repeat=1, seed=4327)
    cases = {r["arm"]: r for r in rows}
    assert set(cases) == set(ARMS)
    assert all(r["verified"] for r in rows)
    assert seed["source_index_builds"] == 1
    assert cases["reuse_exact"]["source_index_builds"] == 0
    assert cases["reuse_exact"]["page_hit"] and cases["reuse_exact"]["reuse_receipts"] == 1
    assert cases["reuse_exact"]["result_sha256"] == cases["rebuild"]["result_sha256"]
    assert cases["reuse_tampered"]["context_sha256"] == cases["rebuild"]["context_sha256"]
    assert "content_hash_mismatch" in cases["reuse_tampered"]["lookup_errors"]
    assert cases["reuse_stale"]["lookup_reason"] == "identity_or_kind_miss"
    assert cases["reuse_stale"]["result_sha256"] == cases["rebuild_changed"]["result_sha256"]
    assert cases["reuse_stale"]["result_sha256"] != cases["rebuild"]["result_sha256"]
    for name in ("reuse_stale", "reuse_tampered"):
        assert not cases[name]["page_hit"]
        assert cases[name]["reuse_receipts"] == 0 and cases[name]["source_index_builds"] == 1


def test_5a_receipt_keeps_cold_creation_and_no_model_claim_separate(tmp_path):
    out = tmp_path / "report"
    assert main(["--out", str(out), "--sizes", "8", "--repeats", "1"]) == 0
    report = json.loads((out / "summary.json").read_text())
    assert report["verified"] == 5
    assert report["exact_index_builds_avoided"] == 1
    assert report["cold_page_builds"] == 1
    assert report["provider_requests"] == 0
    assert report["preparations"] == 1
    assert (out / "SHA256SUMS").is_file()
