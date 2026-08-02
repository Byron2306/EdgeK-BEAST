import json
from pathlib import Path

from app.kernel.governance.output_governor import output_gate, provider_output_profile
from app.kernel.compute.action_ir import ActionIR
from app.kernel.compute.action_resolver import build_file_references, resolve_actions


def test_file_reference_anchors_expand_duplicate_lines_to_unique_context(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text(
        "def first():\n    return value\n\n\ndef second():\n    return value\n",
        encoding="utf-8",
    )

    refs = build_file_references(tmp_path, ["app.py"])

    assert refs[0].anchors
    assert all(target.read_text(encoding="utf-8").count(anchor) == 1 for anchor in refs[0].anchors.values())
from app.kernel.adapters.provider_handoff import build_provider_handoff, output_skeleton, render_provider_handoff_prompt
from benchmarks.coding_task_completion_harness import API_BROKEN, PROVIDER_REGISTRY_BROKEN


def test_provider_handoff_mirrors_input_and_output_governance(tmp_path: Path):
    target = tmp_path / "app" / "main.py"
    target.parent.mkdir(parents=True)
    target.write_text("def main():\n    return 'old'\n", encoding="utf-8")

    handoff = build_provider_handoff(
        tmp_path,
        "Update app/main.py return value",
        ["app/main.py"],
        "nvidia_nim",
        task_name="unit",
        include_scout=False,
    )

    assert handoff["kind"] == "beast.provider_handoff.v1"
    assert handoff["input"]["context_packet"]["beast_object_type"] == "context_packet"
    assert handoff["input"]["context_packet_id"].startswith("pkt_")
    assert handoff["output"]["schema"]["kind"] == "beast.action_intent.v1"
    assert handoff["output"]["profile"]["refs_only"] is True
    assert any(item["type"] == "add_provider_record" for item in handoff["output"]["local_transforms"])
    assert handoff["trace"]["input_handoff_hash"].startswith("sha256:")

    prompt = render_provider_handoff_prompt(handoff)
    assert "beast.provider_handoff.v1" in prompt
    assert "Return only the output.schema object" in prompt
    assert "STRICT OUTPUT MODE" in prompt
    assert prompt.index("JSON skeleton to copy") < prompt.index("Provider handoff:")
    skeleton = output_skeleton(handoff)
    assert skeleton["kind"] == "beast.action_intent.v1"
    assert skeleton["provider_handoff_hash"] == handoff["trace"]["provider_handoff_hash"]
    assert skeleton["handoff_hash"] == handoff["trace"]["input_handoff_hash"]
    assert skeleton["actions"][0]["target"]["file_ref"] == "F1"


def test_provider_handoff_open_profile_keeps_bounded_file_content(tmp_path: Path):
    target = tmp_path / "app" / "main.py"
    target.parent.mkdir(parents=True)
    target.write_text("print('open profile context')\n", encoding="utf-8")

    handoff = build_provider_handoff(
        tmp_path,
        "Inspect app/main.py",
        ["app/main.py"],
        "openrouter",
        include_scout=False,
    )

    evidence = handoff["input"]["context_packet"]["included_evidence"]
    assert any("open profile context" in str(item.get("content") or "") for item in evidence)
    assert handoff["output"]["profile"]["refs_only"] is False


def test_provider_wiring_handoff_uses_semantic_action_skeleton(tmp_path: Path):
    registry = tmp_path / "app" / "kernel" / "provider_registry.py"
    api = tmp_path / "app" / "cli" / "api.py"
    registry.parent.mkdir(parents=True)
    api.parent.mkdir(parents=True)
    registry.write_text(PROVIDER_REGISTRY_BROKEN, encoding="utf-8")
    api.write_text(API_BROKEN, encoding="utf-8")

    handoff = build_provider_handoff(
        tmp_path,
        "Fix provider/model wiring so beast-auto resolves concrete coding-agent models.",
        ["app/kernel/provider_registry.py", "app/cli/api.py"],
        "nvidia_nim",
        task_name="provider_model_wiring",
        include_scout=False,
    )
    skeleton = output_skeleton(handoff)

    assert skeleton["kind"] == "beast.action_intent.v1"
    assert [action["type"] for action in skeleton["actions"]] == [
        "add_provider_record",
        "add_provider_record",
        "set_default_model",
        "use_provider_registry_model_resolver",
    ]
    assert skeleton["actions"][0]["parameters"]["provider_id"] == "codex"
    assert skeleton["actions"][3]["target"]["path"] == "app/cli/api.py"


def test_output_gate_compiles_semantic_provider_transforms(tmp_path: Path):
    registry = tmp_path / "app" / "kernel" / "provider_registry.py"
    api = tmp_path / "app" / "cli" / "api.py"
    registry.parent.mkdir(parents=True)
    api.parent.mkdir(parents=True)
    registry.write_text(PROVIDER_REGISTRY_BROKEN, encoding="utf-8")
    api.write_text(API_BROKEN, encoding="utf-8")
    profile = provider_output_profile("nvidia_nim")
    raw_text = json.dumps({
        "kind": "beast.action_intent.v1",
        "provider_handoff_hash": "sha256:test",
        "objective": "wire providers",
        "actions": [
            {
                "id": "a1",
                "type": "add_provider_record",
                "target": {"path": "app/kernel/provider_registry.py"},
                "parameters": {
                    "provider_id": "codex",
                    "backend": "openai_compatible",
                    "default_model": "gpt-5-codex",
                    "env": ["OPENAI_API_KEY"],
                },
            },
            {
                "id": "a2",
                "type": "add_provider_record",
                "target": {"path": "app/kernel/provider_registry.py"},
                "parameters": {
                    "provider_id": "local_nim",
                    "backend": "openai_compatible",
                    "default_model": "local-nim-model",
                    "env": ["LOCAL_NIM_BASE_URL", "LOCAL_NIM_API_KEY"],
                },
            },
            {
                "id": "a3",
                "type": "set_default_model",
                "target": {"path": "app/kernel/provider_registry.py"},
                "parameters": {"provider_id": "openai", "default_model": "gpt-4o-mini"},
            },
            {
                "id": "a4",
                "type": "use_provider_registry_model_resolver",
                "target": {"path": "app/cli/api.py"},
            },
        ],
    })

    result = output_gate(
        tmp_path,
        raw_text,
        ["app/kernel/provider_registry.py", "app/cli/api.py"],
        profile,
    )

    assert result.ok is True
    by_path = {item["path"]: item["content"] for item in result.operations}
    assert '"codex"' in by_path["app/kernel/provider_registry.py"]
    assert '"local_nim"' in by_path["app/kernel/provider_registry.py"]
    assert '"default_model": "gpt-4o-mini"' in by_path["app/kernel/provider_registry.py"]
    assert "ProviderAdapterRegistry" in by_path["app/cli/api.py"]


def test_resolver_rejects_stale_file_ref_hash(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("value = 'old'\n", encoding="utf-8")
    refs = build_file_references(tmp_path, ["app.py"])
    target.write_text("value = 'changed'\n", encoding="utf-8")
    action_ir = ActionIR.from_dict({
        "kind": "beast.action_intent.v1",
        "provider_handoff_hash": "sha256:test",
        "actions": [
            {
                "id": "a1",
                "type": "replace_anchor",
                "target": {"file_ref": refs[0].ref, "anchor_ref": "A1"},
                "new": "value = 'new'",
            }
        ],
    })

    try:
        resolve_actions(tmp_path, action_ir, refs, ["app.py"])
    except ValueError as exc:
        assert "changed since handoff" in str(exc)
    else:
        raise AssertionError("stale file ref hash should fail")


def test_resolver_compiles_provider_alias_transform(tmp_path: Path):
    registry = tmp_path / "app" / "kernel" / "provider_registry.py"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        "class ProviderRegistry:\n"
        "    DEFAULTS = {\n"
        "        \"openai\": {\n"
        "            \"backend\": \"openai_compatible\",\n"
        "            \"env\": [\"OPENAI_API_KEY\"],\n"
        "            \"proxy_path\": \"/proxy/openai\",\n"
        "            \"litellm_model_prefix\": \"openai/\",\n"
        "            \"default_model\": \"gpt-4o-mini\",\n"
        "            \"openai_compatible\": True,\n"
        "        },\n"
        "    }\n",
        encoding="utf-8",
    )
    action_ir = ActionIR.from_dict({
        "kind": "beast.action_intent.v1",
        "provider_handoff_hash": "sha256:test",
        "actions": [
            {
                "id": "a1",
                "type": "add_provider_alias",
                "target": {"path": "app/kernel/provider_registry.py"},
                "parameters": {"alias": "github_models", "target_provider": "openai", "default_model": "gpt-4o"},
            }
        ],
    })

    resolved = resolve_actions(tmp_path, action_ir, [], ["app/kernel/provider_registry.py"])

    assert len(resolved) == 1
    assert '"github_models"' in resolved[0].new
    assert '"provider_alias_of": "openai"' in resolved[0].new
    assert '"default_model": "gpt-4o"' in resolved[0].new


def test_resolver_rejects_stale_direct_path_hash(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("value = 'old'\n", encoding="utf-8")
    refs = build_file_references(tmp_path, ["app.py"])
    target.write_text("value = 'changed'\n", encoding="utf-8")
    action_ir = ActionIR.from_dict({
        "kind": "beast.action_intent.v1",
        "provider_handoff_hash": "sha256:test",
        "actions": [
            {
                "id": "a1",
                "type": "replace_anchor",
                "target": {"path": "app.py", "sha256": refs[0].sha256},
                "old": "value = 'changed'",
                "new": "value = 'new'",
            }
        ],
    })

    try:
        resolve_actions(tmp_path, action_ir, refs, ["app.py"])
    except ValueError as exc:
        assert "changed since handoff" in str(exc)
    else:
        raise AssertionError("stale direct path hash should fail")


def test_output_gate_rejects_handoff_hash_mismatch(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("value = 'old'\n", encoding="utf-8")
    profile = provider_output_profile("nvidia_nim")
    raw_text = json.dumps({
        "kind": "beast.action_intent.v1",
        "provider_handoff_hash": "sha256:wrong",
        "actions": [
            {
                "id": "a1",
                "type": "replace_anchor",
                "target": {"path": "app.py"},
                "old": "value = 'old'",
                "new": "value = 'new'",
            }
        ],
    })

    result = output_gate(tmp_path, raw_text, ["app.py"], profile, expected_handoff_hash="sha256:right")

    assert result.ok is False
    assert "handoff_hash did not match" in result.error


def test_output_gate_rejects_path_escape(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("value = 'old'\n", encoding="utf-8")
    profile = provider_output_profile("nvidia_nim")
    raw_text = json.dumps({
        "kind": "beast.action_intent.v1",
        "provider_handoff_hash": "sha256:test",
        "actions": [
            {
                "id": "a1",
                "type": "replace_anchor",
                "target": {"path": "../app.py"},
                "old": "value = 'old'",
                "new": "value = 'new'",
            }
        ],
    })

    result = output_gate(tmp_path, raw_text, ["../app.py"], profile)

    assert result.ok is False
    assert "unsafe path" in result.error


def test_semantic_provider_values_are_escaped(tmp_path: Path):
    registry = tmp_path / "app" / "kernel" / "provider_registry.py"
    registry.parent.mkdir(parents=True)
    registry.write_text(PROVIDER_REGISTRY_BROKEN, encoding="utf-8")
    profile = provider_output_profile("nvidia_nim")
    raw_text = json.dumps({
        "kind": "beast.action_intent.v1",
        "provider_handoff_hash": "sha256:test",
        "actions": [
            {
                "id": "a1",
                "type": "add_provider_record",
                "target": {"path": "app/kernel/provider_registry.py"},
                "parameters": {
                    "provider_id": "quoted",
                    "backend": 'openai_"compatible',
                    "default_model": 'model"withquote',
                    "env": ['TOKEN"VALUE'],
                },
            }
        ],
    })

    result = output_gate(tmp_path, raw_text, ["app/kernel/provider_registry.py"], profile)

    assert result.ok is True
    content = result.operations[0]["content"]
    assert '"backend": "openai_\\"compatible"' in content
    assert '"default_model": "model\\"withquote"' in content
    assert '"TOKEN\\"VALUE"' in content


def test_output_gate_preserves_non_mutating_requests(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("value = 'old'\n", encoding="utf-8")
    profile = provider_output_profile("nvidia_nim")
    raw_text = json.dumps({
        "kind": "beast.action_intent.v1",
        "provider_handoff_hash": "sha256:test",
        "actions": [
            {
                "id": "a1",
                "type": "run_verifier",
                "intent": "run focused syntax check",
                "parameters": {"command": "python -m py_compile app.py"},
            },
            {
                "id": "a2",
                "type": "ask_for_context",
                "intent": "need provider registry file",
                "parameters": {"query": "provider registry defaults"},
            },
            {
                "id": "a3",
                "type": "replace_anchor",
                "target": {"path": "app.py"},
                "old": "value = 'old'",
                "new": "value = 'new'",
            },
        ],
    })

    result = output_gate(tmp_path, raw_text, ["app.py"], profile)

    assert result.ok is True
    assert result.operations[0]["content"] == "value = 'new'\n"
    assert [item["type"] for item in result.non_mutating_requests] == ["run_verifier", "ask_for_context"]
    assert result.evidence["non_mutating_request_count"] == 2
    assert result.evidence["non_mutating_requests"][0]["parameters"]["command"] == "python -m py_compile app.py"


def test_non_mutating_request_path_is_still_scoped(tmp_path: Path):
    profile = provider_output_profile("nvidia_nim")
    raw_text = json.dumps({
        "kind": "beast.action_intent.v1",
        "provider_handoff_hash": "sha256:test",
        "actions": [
            {
                "id": "a1",
                "type": "run_verifier",
                "target": {"path": "../outside.py"},
                "intent": "try outside path",
            }
        ],
    })

    result = output_gate(tmp_path, raw_text, ["../outside.py"], profile)

    assert result.ok is False
    assert "unsafe path" in result.error
