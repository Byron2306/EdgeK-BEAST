from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import pytest

import dai_attack
import dai_publication_core as core


SUBJECT = "sha256:" + "1" * 64


def make_adapter(path: Path) -> None:
    path.write_text(
        "import json,sys\n"
        "value=json.load(open(sys.argv[1],encoding='utf-8'))\n"
        "reasons=[]\n"
        "admission='accept'\n"
        "decision='answer'\n"
        "if value['policy']['production_authority_allowed']:\n"
        "    admission='reject'; decision='refuse'; reasons.append('authority_escalation')\n"
        "elif 'required-fact' not in {x['id'] for x in value['evidence']}:\n"
        "    decision='refuse'; reasons.append('missing_support')\n"
        "elif value['semantic']['declared_digest'] != value['semantic']['recomputed_digest']:\n"
        "    admission='reject'; decision='refuse'; reasons.append('semantic_digest_mismatch')\n"
        "out={'admission':admission,'decision':decision,'reason_codes':reasons," 
        "'production_authority_allowed':False,'execution_authority_allowed':False}\n"
        "json.dump(out,open(sys.argv[2],'w',encoding='utf-8'))\n",
        encoding="utf-8",
    )


def make_plan(tmp_path: Path) -> Path:
    baseline = {
        "policy": {
            "production_authority_allowed": False,
            "execution_authority_allowed": False,
        },
        "evidence": [{"id": "required-fact"}, {"id": "irrelevant-fact"}],
        "semantic": {
            "declared_digest": "sha256:" + "a" * 64,
            "recomputed_digest": "sha256:" + "a" * 64,
        },
    }
    core.write_canonical_json(tmp_path / "baseline.json", baseline)
    plan = {
        "schema": "dai.semantic-attack-plan.v1",
        "baseline_input": "baseline.json",
        "baseline_expected": {
            "returncode": 0,
            "json": {"/admission": "accept", "/decision": "answer"},
        },
        "attacks": [
            {
                "id": "authority-escalation",
                "threat_class": "authority",
                "operations": [
                    {
                        "op": "set_json_pointer",
                        "pointer": "/policy/production_authority_allowed",
                        "value": True,
                    }
                ],
                "expected": {
                    "returncode": 0,
                    "json": {"/admission": "reject", "/decision": "refuse"},
                    "reason_code_contains": "authority_escalation",
                },
            },
            {
                "id": "missing-support",
                "threat_class": "provenance",
                "operations": [
                    {
                        "op": "remove_list_item_by_id",
                        "pointer": "/evidence",
                        "id": "required-fact",
                    }
                ],
                "expected": {
                    "returncode": 0,
                    "json": {"/decision": "refuse"},
                    "reason_code_contains": "missing_support",
                },
            },
            {
                "id": "semantic-digest-substitution",
                "threat_class": "semantic",
                "operations": [
                    {
                        "op": "set_json_pointer",
                        "pointer": "/semantic/declared_digest",
                        "value": "sha256:" + "b" * 64,
                    }
                ],
                "expected": {
                    "returncode": 0,
                    "json": {"/admission": "reject", "/decision": "refuse"},
                    "reason_code_contains": "semantic_digest_mismatch",
                },
            },
        ],
    }
    path = tmp_path / "plan.json"
    core.write_canonical_json(path, plan)
    return path


def test_semantic_attack_plan_requires_specific_rejections(tmp_path: Path) -> None:
    adapter = tmp_path / "adapter.py"
    make_adapter(adapter)
    plan = make_plan(tmp_path)
    output = tmp_path / "report.json"
    report = dai_attack.run_attack_plan(
        plan,
        adapter=f"{shlex.quote(sys.executable)} {shlex.quote(str(adapter))} {{input}} {{output}}",
        output_path=output,
        subject_core_capsule_sha256=SUBJECT,
        timeout=30,
    )
    assert report["passed"] is True
    assert report["attack_count"] == 3
    assert report["passed_count"] == 4
    assert report["production_authority_allowed"] is False


def test_adapter_crash_is_not_accepted_as_rejection(tmp_path: Path) -> None:
    adapter = tmp_path / "crash.py"
    adapter.write_text("raise SystemExit(9)\n", encoding="utf-8")
    plan = make_plan(tmp_path)
    with pytest.raises(dai_attack.AttackError, match="semantic attack plan failed"):
        dai_attack.run_attack_plan(
            plan,
            adapter=f"{shlex.quote(sys.executable)} {shlex.quote(str(adapter))} {{input}} {{output}}",
            output_path=tmp_path / "report.json",
            subject_core_capsule_sha256=SUBJECT,
            timeout=30,
        )


def test_attack_operations_duplicate_and_swap() -> None:
    document = {
        "facts": [{"id": "a", "value": 1}, {"id": "b", "value": 2}],
        "left": "x",
        "right": "y",
    }
    result = dai_attack.apply_operations(
        document,
        [
            {"op": "duplicate_list_item_by_id", "pointer": "/facts", "id": "a"},
            {"op": "swap_json_pointers", "pointer": "/left", "other": "/right"},
        ],
    )
    assert len(result["facts"]) == 3
    assert result["left"] == "y"
    assert result["right"] == "x"
