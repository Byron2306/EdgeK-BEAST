from app.kernel.capability.capability_plane import CapabilityPlane
from app.kernel.capability.capability_registry import CapabilityRegistry
from app.kernel.capability.skill_tree import SkillTree
from app.kernel.deployment.plugin_marketplace import PluginMarketplace
from app.kernel.capability.capability_exchange import CapabilityExchange
from app.kernel.networking.meta_tool_commons import MetaToolCommons


def _plane(tmp_path):
    exchange = CapabilityExchange(enabled=False, data_dir=str(tmp_path / "exchange"))
    skill_tree = SkillTree(data_dir=str(tmp_path / "skills"))
    commons = MetaToolCommons(
        db_path=str(tmp_path / "commons.db"),
        exchange=exchange,
        skill_registry=skill_tree.skill_registry,
    )
    return CapabilityPlane(
        workspace_root=str(tmp_path),
        registry=CapabilityRegistry(),
        skill_tree=skill_tree,
        plugin_marketplace=PluginMarketplace(str(tmp_path / "plugins")),
        exchange=exchange,
        commons=commons,
    )


def test_capability_plane_summarizes_core_sources(tmp_path):
    plane = _plane(tmp_path)

    summary = plane.summary(limit=40)

    assert summary["beast_object_type"] == "capability_plane"
    assert summary["authority"] == "read_only_facade_no_execution_no_install"
    assert summary["capability_count"] >= 1
    assert "capability_registry" in summary["sources"]
    assert "skill_tree" in summary["sources"]
    assert "plugin_marketplace" in summary["sources"]
    assert "capability_exchange" in summary["sources"]
    assert "meta_tool_commons" in summary["sources"]


def test_capability_plane_query_filters_local_reusable_capabilities(tmp_path):
    plane = _plane(tmp_path)

    result = plane.query(text="mcp", local=True, reusable=True, limit=10)

    assert result["beast_object_type"] == "capability_plane_query"
    assert result["query"]["local"] is True
    assert result["query"]["reusable"] is True
    assert all(item["local"] for item in result["capabilities"])
    assert all(item["reusable"] for item in result["capabilities"])


def test_capability_plane_exposes_lazy_least_authority_view(tmp_path):
    plane = _plane(tmp_path)

    result = plane.expose(phase="Observe", include_schemas=False, limit=20)

    assert result["beast_object_type"] == "capability_plane_exposure"
    assert result["schema_mode"] == "lazy"
    assert result["receipt"]["context"]["phase"] == "Observe"
    assert all(item["bucket"] == "Observe" for item in result["capabilities"])
    assert all("metadata" not in item for item in result["capabilities"])
