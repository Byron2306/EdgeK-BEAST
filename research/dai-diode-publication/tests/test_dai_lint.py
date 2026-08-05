from __future__ import annotations

from pathlib import Path

import dai_lint
import dai_publication_core as core


def test_lint_rejects_production_assert_private_key_and_placeholder(tmp_path: Path) -> None:
    (tmp_path / "source").mkdir()
    (tmp_path / "source" / "verifier.py").write_text(
        "def verify(value):\n    assert value\n",
        encoding="utf-8",
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README.md").write_text("TODO replace-with result\n", encoding="utf-8")
    (tmp_path / "keys").mkdir()
    (tmp_path / "keys" / "bad.pem").write_text(
        "-----BEGIN PRIVATE KEY-----\nnot-real\n-----END PRIVATE KEY-----\n",
        encoding="utf-8",
    )
    report = dai_lint.lint_candidate(tmp_path, stage="final")
    assert report["passed"] is False
    assert any("production assert" in error for error in report["errors"])
    assert any("private key" in error for error in report["errors"])
    assert any("placeholder" in error for error in report["errors"])


def test_lint_allows_test_assert_and_valid_metrics(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (tmp_path / "arena").mkdir()
    core.write_canonical_json(
        tmp_path / "arena" / "RESULTS.json",
        {
            "total_case_count": 9,
            "answer_case_count": 6,
            "refusal_case_count": 3,
            "unresolved_case_count": 0,
            "answer_case_correct_count": 6,
            "refusal_case_correct_count": 3,
            "unresolved_case_correct_count": 0,
            "production_authority_allowed": False,
            "execution_authority_allowed": False,
        },
    )
    report = dai_lint.lint_candidate(tmp_path, stage="rc")
    assert report["passed"] is True


def test_lint_rejects_dishonest_metric_denominators(tmp_path: Path) -> None:
    (tmp_path / "arena").mkdir()
    core.write_canonical_json(
        tmp_path / "arena" / "RESULTS.json",
        {
            "total_case_count": 9,
            "answer_case_count": 6,
            "refusal_case_count": 3,
            "unresolved_case_count": 0,
            "answer_case_correct_count": 9,
            "refusal_case_correct_count": 9,
            "unresolved_case_correct_count": 0,
            "production_authority_allowed": False,
            "execution_authority_allowed": False,
        },
    )
    report = dai_lint.lint_candidate(tmp_path, stage="final")
    assert report["passed"] is False
    assert any("exceeds" in error for error in report["errors"])


def test_lint_rejects_authority_true_anywhere_in_json(tmp_path: Path) -> None:
    core.write_canonical_json(
        tmp_path / "receipt.json",
        {
            "nested": {"production_authority_allowed": True},
            "execution_authority_allowed": False,
        },
    )
    report = dai_lint.lint_candidate(tmp_path, stage="rc")
    assert report["passed"] is False
    assert any("authority must be explicitly false" in error for error in report["errors"])
