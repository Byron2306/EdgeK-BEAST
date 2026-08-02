from app.kernel.adapters.vector_memory import VectorMemoryFabric


def test_vector_memory_normalizes_records_without_external_backends(tmp_path):
    fabric = VectorMemoryFabric(tmp_path, dimensions=16)

    result = fabric.ingest([
        {
            "id": "semantic_chunk:example:1",
            "content": "Vector memory keeps workspace retrieval advisory.",
            "metadata": {"file": "app/example.py", "start_line": 1},
        },
        {"id": "empty", "content": ""},
    ])

    assert result["beast_object_type"] == "vector_memory_ingest"
    assert result["record_count"] == 1
    assert result["projections"] == []
    assert result["memory_layer"] == "L2"
    assert result["purpose"] == "workspace_source"
    assert len(fabric._embedding("workspace vector retrieval")) == 16


def test_cloud_operational_records_reject_raw_workspace_material(tmp_path):
    config = tmp_path / ".beast"
    config.mkdir()
    (config / "vector.env").write_text(
        "BEAST_VECTOR_MEMORY_CLOUD_OPERATIONAL_ENABLED=1\n",
        encoding="utf-8",
    )
    fabric = VectorMemoryFabric(tmp_path, dimensions=16)

    result = fabric.ingest([
        {
            "id": "unsafe-repair",
            "summary": "A verified repair succeeded.",
            "code": "def private_implementation(): pass",
            "metadata": {"verified": True, "receipt_id": "receipt-1"},
        }
    ], purpose="verified_skill")

    assert result["record_count"] == 0
    assert result["rejected"]
    assert "forbidden" in result["rejected"][0]["reason"]


def test_cloud_operational_records_require_verified_receipt(tmp_path):
    config = tmp_path / ".beast"
    config.mkdir()
    (config / "vector.env").write_text(
        "BEAST_VECTOR_MEMORY_CLOUD_OPERATIONAL_ENABLED=1\n",
        encoding="utf-8",
    )
    fabric = VectorMemoryFabric(tmp_path, dimensions=16)

    result = fabric.ingest([
        {"id": "unverified", "summary": "A short operational outcome.", "metadata": {"verified": False}}
    ], purpose="forensic_summary")

    assert result["record_count"] == 0
    assert "verified=true" in result["rejected"][0]["reason"]


def test_workspace_graph_exports_rebuildable_projection_records(tmp_path):
    from app.kernel.data_processing.workspace_graph import WorkspaceGraph

    root = tmp_path / "repo"
    root.mkdir()
    (root / "example.py").write_text("def vector_memory():\n    return 'context'\n", encoding="utf-8")
    graph = WorkspaceGraph(str(tmp_path / "graph.db"))

    indexed = graph.semantic_index_repository(str(root), max_files=5, max_chunks=10)
    records = graph.semantic_projection_records()

    assert indexed["indexed_chunks"] >= 1
    assert records
    assert records[0]["id"].startswith("semantic_chunk:")
    assert records[0]["metadata"]["file"] == "example.py"
