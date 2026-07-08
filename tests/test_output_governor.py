from pathlib import Path
import json

import pytest

from app.kernel.compute.action_resolver import build_file_references
from app.kernel.governance.output_governor import (
    OutputValidationError,
    compile_provider_output,
    output_contract_schema,
    output_gate,
    output_reference_packet,
    provider_output_profile,
)


def test_nim_profile_forbids_full_file_replacement(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("print('old')\n", encoding="utf-8")
    profile = provider_output_profile("nvidia_nim")

    with pytest.raises(OutputValidationError, match="create_or_replace"):
        compile_provider_output(
            tmp_path,
            {"operations": [{"path": "app.py", "content": "print('new')\n"}]},
            ["app.py"],
            profile,
        )


def test_patch_intent_replace_exact_compiles_to_file_content(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("def main():\n    return 'old'\n", encoding="utf-8")
    profile = provider_output_profile("nvidia_nim")

    operations = compile_provider_output(
        tmp_path,
        {
            "kind": "beast.patch_intent.v1",
            "operations": [
                {
                    "op": "replace_exact",
                    "path": "app.py",
                    "old": "return 'old'",
                    "new": "return 'new'",
                    "why": "update return value",
                }
            ],
        },
        ["app.py"],
        profile,
    )

    assert operations == [
        {
            "path": "app.py",
            "content": "def main():\n    return 'new'\n",
            "description": "update return value",
        }
    ]


def test_patch_intent_requires_unique_anchor(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("value = 1\nvalue = 1\n", encoding="utf-8")
    profile = provider_output_profile("nvidia_nim")

    with pytest.raises(OutputValidationError, match="matched 2 times"):
        compile_provider_output(
            tmp_path,
            {
                "operations": [
                    {"op": "replace_exact", "path": "app.py", "old": "value = 1", "new": "value = 2"}
                ]
            },
            ["app.py"],
            profile,
        )


def test_compile_provider_output_accepts_explicit_legacy_source_patch_profile(tmp_path: Path):
    profile = provider_output_profile("legacy_source")

    operations = compile_provider_output(
        tmp_path,
        {"operations": [{"path": "app.py", "content": "print('ok')\n"}]},
        ["app.py"],
        profile,
    )

    assert operations[0]["content"] == "print('ok')\n"


def test_provider_profiles_cover_constrained_and_open_outputs():
    nim = provider_output_profile("nvidia_nim")
    hf = provider_output_profile("huggingface")
    openrouter = provider_output_profile("openrouter")

    assert nim.role == "refs_only_action_ir_generator"
    assert nim.forbid_full_file_replacement is True
    assert nim.refs_only is True
    assert nim.forbid_old_when_anchor_ref is True
    assert output_contract_schema(nim)["kind"] == "beast.action_intent.v1"

    assert hf.role == "live_action_ir_generator"
    assert hf.forbid_full_file_replacement is True
    assert hf.repair_attempts == 2

    assert openrouter.role == "live_action_ir_generator"
    assert openrouter.forbid_full_file_replacement is True
    assert openrouter.refs_only is False


def test_default_action_ir_profile_rejects_legacy_full_file_output(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("value = 'old'\n", encoding="utf-8")
    profile = provider_output_profile("huggingface")

    with pytest.raises(OutputValidationError, match="create_or_replace"):
        compile_provider_output(
            tmp_path,
            {"operations": [{"path": "app.py", "content": "value = 'full'\n"}]},
            ["app.py"],
            profile,
        )


def test_nim_reference_packet_redacts_exact_anchor_bodies(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("def main():\n    return 'old'\n", encoding="utf-8")
    profile = provider_output_profile("nvidia_nim")

    refs = output_reference_packet(tmp_path, ["app.py"], profile)
    anchors = refs["files"][0]["anchors"]

    assert isinstance(anchors, list)
    assert anchors
    assert all(set(anchor) == {"ref", "label", "chars", "sha256"} for anchor in anchors)
    assert "return 'old'" in {anchor["label"] for anchor in anchors}
    assert all("    return 'old'" != anchor.get("label") for anchor in anchors)


def test_output_gate_records_contract_evidence(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("value = 'old'\n", encoding="utf-8")
    profile = provider_output_profile("openrouter")
    raw_text = json.dumps({
        "kind": "beast.patch_intent.v1",
        "operations": [
            {
                "op": "replace_exact",
                "path": "app.py",
                "old": "value = 'old'",
                "new": "value = 'new'",
                "why": "update value",
            }
        ],
    })

    source_profile = provider_output_profile("legacy_source")
    result = output_gate(tmp_path, raw_text, ["app.py"], source_profile, usage={"prompt_tokens": 10}, latency_ms=12.5)

    assert result.ok is True
    assert result.evidence["contract"] == "beast.source_patch.v1"
    assert result.evidence["json_parse_ok"] is True
    assert result.evidence["diff_compiled"] is True
    assert result.evidence["anchor_match_rate"] == 1.0
    assert result.evidence["policy_gate"]["decision"] == "allow"
    assert result.operations[0]["content"] == "value = 'new'\n"


def test_refs_only_output_gate_requires_action_ir(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("value = 'old'\n", encoding="utf-8")
    profile = provider_output_profile("nvidia_nim")
    raw_text = json.dumps({
        "kind": "beast.patch_intent.v1",
        "operations": [
            {"op": "replace_exact", "path": "app.py", "old": "value = 'old'", "new": "value = 'new'"}
        ],
    })

    result = output_gate(tmp_path, raw_text, ["app.py"], profile)

    assert result.ok is False
    assert "must return BEAST Action IR" in result.error
    assert result.evidence["policy_gate"]["decision"] == "block"


def test_output_gate_compiles_action_ir(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("def main():\n    return 'old'\n", encoding="utf-8")
    profile = provider_output_profile("nvidia_nim")
    raw_text = json.dumps({
        "kind": "beast.action_intent.v1",
        "provider_handoff_hash": "sha256:test",
        "objective": "update return value",
        "actions": [
            {
                "id": "a1",
                "type": "replace_anchor",
                "target": {"file_ref": "F1"},
                "intent": "return new value",
                "old": "return 'old'",
                "new": "return 'new'",
            }
        ],
        "verify": ["python -m py_compile app.py"],
    })

    result = output_gate(tmp_path, raw_text, ["app.py"], profile)

    assert result.ok is True
    assert result.evidence["contract"] == "beast.action_intent.v1"
    assert result.evidence["action_count"] == 1
    assert result.operations[0]["content"] == "def main():\n    return 'new'\n"


def test_output_gate_resolves_anchor_refs_without_copying_old(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("def main():\n    return 'old'\n", encoding="utf-8")
    profile = provider_output_profile("nvidia_nim")
    refs = build_file_references(tmp_path, ["app.py"])
    file_ref = refs[0].ref
    anchor_ref = next(key for key, value in refs[0].anchors.items() if "return 'old'" in value)
    raw_text = json.dumps({
        "kind": "beast.action_intent.v1",
        "provider_handoff_hash": "sha256:test",
        "objective": "update return value",
        "actions": [
            {
                "id": "a1",
                "type": "replace_anchor",
                "target": {"file_ref": file_ref, "anchor_ref": anchor_ref},
                "intent": "return new value",
                "new": "    return 'new'",
            }
        ],
    })

    result = output_gate(tmp_path, raw_text, ["app.py"], profile)

    assert result.ok is True
    assert result.operations[0]["content"] == "def main():\n    return 'new'\n"


def test_output_gate_rejects_anchor_ref_with_copied_old_for_refs_only_provider(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("def main():\n    return 'old'\n", encoding="utf-8")
    profile = provider_output_profile("nvidia_nim")
    refs = build_file_references(tmp_path, ["app.py"])
    anchor_ref = next(key for key, value in refs[0].anchors.items() if "return 'old'" in value)
    raw_text = json.dumps({
        "kind": "beast.action_intent.v1",
        "provider_handoff_hash": "sha256:test",
        "objective": "update return value",
        "actions": [
            {
                "id": "a1",
                "type": "replace_anchor",
                "target": {"file_ref": refs[0].ref, "anchor_ref": anchor_ref},
                "intent": "return new value",
                "old": "    return 'old'",
                "new": "    return 'new'",
            }
        ],
    })

    result = output_gate(tmp_path, raw_text, ["app.py"], profile)

    assert result.ok is False
    assert "copied old despite anchor_ref" in result.error
