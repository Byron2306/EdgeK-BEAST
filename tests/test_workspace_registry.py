from pathlib import Path

from app.kernel.data_processing.workspace_registry import WorkspaceRegistry, repo_id_for_root


def test_workspace_registry_registers_repos_and_detects_contracts(tmp_path):
    service = tmp_path / "service"
    client = tmp_path / "client"
    service.mkdir()
    client.mkdir()
    (service / "api.py").write_text(
        "import os\n\n"
        "@router.get('/health')\n"
        "def health():\n"
        "    return os.getenv('SERVICE_TOKEN')\n",
        encoding="utf-8",
    )
    (service / "openapi.json").write_text('{"openapi":"3.0.0"}\n', encoding="utf-8")
    (client / "consumer.py").write_text(
        "import os\n"
        "TOKEN = os.environ['CLIENT_TOKEN']\n"
        "topic = 'billing.events'\n",
        encoding="utf-8",
    )
    registry = WorkspaceRegistry(tmp_path / "registry" / "workspaces.json")

    service_result = registry.register(service, role="provider", allowed_edit_scope="read_only")
    client_result = registry.register(client, role="primary", allowed_edit_scope="read_write")
    listed = registry.list()

    service_ws = service_result["workspace"]
    client_ws = client_result["workspace"]
    assert service_ws["repo_id"] == repo_id_for_root(service)
    assert service_ws["allowed_edit_scope"] == "read_only"
    assert service_ws["contract_artifacts"]["counts"]["routes"] == 1
    assert service_ws["contract_artifacts"]["counts"]["openapi_files"] == 1
    assert "SERVICE_TOKEN" in service_ws["contract_artifacts"]["env_vars"]
    assert "CLIENT_TOKEN" in client_ws["contract_artifacts"]["env_vars"]
    assert "billing.events" in client_ws["contract_artifacts"]["message_topics"]
    assert len(listed["workspaces"]) == 2
    assert listed["registry_hash"]


def test_workspace_registry_context_pack_keeps_reference_repo_read_only(tmp_path):
    editable = tmp_path / "editable"
    reference = tmp_path / "reference"
    editable.mkdir()
    reference.mkdir()
    (editable / "app.py").write_text("value = 1\n", encoding="utf-8")
    (reference / "contract.md").write_text("# Contract\nRead me only.\n", encoding="utf-8")
    registry = WorkspaceRegistry(tmp_path / ".beast" / "workspaces.json")
    edit_repo = registry.register(editable, allowed_edit_scope="read_write")["workspace"]["repo_id"]
    ref_repo = registry.register(reference, role="reference", allowed_edit_scope="read_only")["workspace"]["repo_id"]

    pack = registry.build_context_pack(
        edit_repo_id=edit_repo,
        reference_repo_ids=[ref_repo],
        files_by_repo={
            edit_repo: ["app.py"],
            ref_repo: ["contract.md"],
        },
    )

    assert pack["ok"] is True
    assert pack["write_policy"]["allowed_edit_repo_id"] == edit_repo
    assert pack["editable_count"] == 1
    assert pack["read_only_count"] == 1
    by_path = {item["path"]: item for item in pack["records"]}
    assert by_path["app.py"]["read_only"] is False
    assert by_path["contract.md"]["read_only"] is True


def test_workspace_registry_contract_mismatch_receipt_is_advisory(tmp_path):
    provider = tmp_path / "provider"
    consumer = tmp_path / "consumer"
    provider.mkdir()
    consumer.mkdir()
    (provider / "api.py").write_text(
        "import os\n"
        "@app.post('/payments')\n"
        "def payments():\n"
        "    return os.getenv('PAYMENTS_TOKEN')\n",
        encoding="utf-8",
    )
    (consumer / "client.py").write_text(
        "import os\n"
        "token = os.getenv('CLIENT_TOKEN')\n",
        encoding="utf-8",
    )
    registry = WorkspaceRegistry(tmp_path / ".beast" / "workspaces.json")
    provider_id = registry.register(provider, role="provider", allowed_edit_scope="read_only")["workspace"]["repo_id"]
    consumer_id = registry.register(consumer, role="consumer", allowed_edit_scope="read_write")["workspace"]["repo_id"]

    receipt = registry.contract_mismatch_receipt(provider_id, consumer_id)

    assert receipt["advisory"] is True
    assert "PAYMENTS_TOKEN" in receipt["missing_env_in_consumer"]
    assert "CLIENT_TOKEN" in receipt["consumer_references_unknown_env"]
    assert "/payments" in receipt["provider_only_routes"]
    assert receipt["receipt_hash"]


def test_workspace_registry_validates_cross_repo_sourceplan_scope(tmp_path):
    repo_a = tmp_path / "repo_a"
    repo_b = tmp_path / "repo_b"
    repo_a.mkdir()
    repo_b.mkdir()
    registry = WorkspaceRegistry(tmp_path / ".beast" / "workspaces.json")
    repo_a_id = registry.register(repo_a, allowed_edit_scope="read_write")["workspace"]["repo_id"]
    repo_b_id = registry.register(repo_b, role="reference", allowed_edit_scope="read_only")["workspace"]["repo_id"]
    plan = {
        "operations": [
            {"op_id": "a", "path": "app.py", "repo_id": repo_a_id, "source_edit": True, "selected": True},
            {"op_id": "b", "path": "contract.py", "repo_id": repo_b_id, "source_edit": True, "selected": True},
        ]
    }

    result = registry.validate_sourceplan_scope(plan, edit_repo_id=repo_a_id)

    assert result["ok"] is False
    assert any("read_only" in item for item in result["errors"])
    assert any("cross-repo edit requires" in item for item in result["errors"])


def test_workspace_registry_allows_explicit_multi_repo_writes_when_repos_are_writable(tmp_path):
    repo_a = tmp_path / "repo_a"
    repo_b = tmp_path / "repo_b"
    repo_a.mkdir()
    repo_b.mkdir()
    registry = WorkspaceRegistry(tmp_path / ".beast" / "workspaces.json")
    repo_a_id = registry.register(repo_a, allowed_edit_scope="read_write")["workspace"]["repo_id"]
    repo_b_id = registry.register(repo_b, role="peer", allowed_edit_scope="read_write")["workspace"]["repo_id"]
    plan = {
        "operations": [
            {"op_id": "a", "path": "app.py", "repo_id": repo_a_id, "source_edit": True, "selected": True},
            {"op_id": "b", "path": "peer.py", "repo_id": repo_b_id, "source_edit": True, "selected": True},
        ]
    }

    blocked = registry.validate_sourceplan_scope(plan, edit_repo_id=repo_a_id)
    approved = registry.validate_sourceplan_scope(plan, edit_repo_id=repo_a_id, approved_multi_repo=True)

    assert blocked["ok"] is False
    assert "multiple writable repos require explicit multi-repo approval" in blocked["errors"]
    assert approved["ok"] is True
    assert approved["writable_repo_ids"] == sorted([repo_a_id, repo_b_id])
