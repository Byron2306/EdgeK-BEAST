from pathlib import Path
import json
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from beast_full_system_census import (
    apply_compute_module_dispositions,
    apply_overrides,
    load_overrides,
    render_markdown,
    scan_repository,
)


def test_scans_mixed_repository_and_preserves_runtime_unknown(tmp_path):
    (tmp_path / "app/kernel/agents").mkdir(parents=True)
    (tmp_path / "app/kernel/data_processing").mkdir(parents=True)
    (tmp_path / "desktop-ide/renderer/js/ai").mkdir(parents=True)
    (tmp_path / ".github/workflows").mkdir(parents=True)

    (tmp_path / "app/kernel/agents/planner.py").write_text(
        "import json\nfrom app.kernel.data_processing.context_packet import ContextPacket\n",
        encoding="utf-8",
    )
    (tmp_path / "app/kernel/data_processing/context_packet.py").write_text(
        "class ContextPacket: pass\n", encoding="utf-8"
    )
    (tmp_path / "desktop-ide/renderer/js/ai/agent-client.js").write_text(
        "import { run } from './runner.js';\nconst x = require('../mode-controller.js');\n",
        encoding="utf-8",
    )
    (tmp_path / ".github/workflows/agentic-loop-endurance.yml").write_text(
        "name: endurance\n", encoding="utf-8"
    )

    report = scan_repository(tmp_path)
    paths = [item["path"] for item in report["components"]]

    assert paths == sorted(paths)
    assert "app/kernel/agents/planner.py" in paths
    assert "desktop-ide/renderer/js/ai/agent-client.js" in paths
    assert ".github/workflows/agentic-loop-endurance.yml" in paths

    planner = next(x for x in report["components"] if x["path"].endswith("planner.py"))
    assert planner["layer"] == "agency_planning"
    assert "app.kernel.data_processing.context_packet.ContextPacket" in planner["imports"]
    assert planner["runtime"]["constructed"] == "unverified"
    assert planner["runtime"]["invoked"] == "unverified"
    assert planner["authority"] == "unverified"

    client = next(x for x in report["components"] if x["path"].endswith("agent-client.js"))
    assert client["layer"] == "interface_ingress"
    assert "./runner.js" in client["imports"]
    assert "../mode-controller.js" in client["imports"]

    workflow = next(x for x in report["components"] if x["path"].endswith(".yml"))
    assert workflow["layer"] == "ci_proof"

    md = render_markdown(report)
    assert "# BEAST Full System Census" in md
    assert "Runtime status is not inferred from imports" in md


def test_ignores_generated_and_backup_trees(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "node_modules/pkg").mkdir(parents=True)
    (tmp_path / ".beast_backups/x").mkdir(parents=True)
    (tmp_path / "app/live.py").write_text("x=1\n", encoding="utf-8")
    (tmp_path / "node_modules/pkg/nope.js").write_text("x=1\n", encoding="utf-8")
    (tmp_path / ".beast_backups/x/nope.py").write_text("x=1\n", encoding="utf-8")

    report = scan_repository(tmp_path)
    paths = [item["path"] for item in report["components"]]
    assert paths == ["app/live.py"]


def test_ignores_canonical_census_output_from_its_own_inventory(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "docs/evidence").mkdir(parents=True)
    (tmp_path / "app/live.py").write_text("x=1\n", encoding="utf-8")
    (tmp_path / "docs/evidence/BEAST_FULL_SYSTEM_CENSUS.json").write_text(
        '{"beast_object_type":"beast_full_system_census"}\n', encoding="utf-8"
    )

    report = scan_repository(tmp_path)
    paths = [item["path"] for item in report["components"]]

    assert paths == ["app/live.py"]


def test_override_overlay_classifies_components_without_mutating_runtime_truth(tmp_path):
    (tmp_path / "app/kernel/compute").mkdir(parents=True)
    (tmp_path / "app/kernel/data_processing").mkdir(parents=True)
    authoritative = "app/kernel/compute/compute_plane.py"
    offline = "app/kernel/compute/benchmark.py"
    cortex = "app/kernel/data_processing/code_cortex.py"
    for rel in (authoritative, offline, cortex):
        (tmp_path / rel).write_text("x=1\n", encoding="utf-8")

    override_path = tmp_path / "overrides.json"
    override_path.write_text(
        json.dumps(
            {
                "components": {
                    authoritative: {
                        "disposition": "online_authoritative",
                        "agent_relevance": "direct",
                        "composition_roots": ["app/kernel/compute/compute_plane.py"],
                        "claimed_responsibilities": ["compute_composition"],
                    },
                    offline: {
                        "disposition": "supervised_offline",
                        "agent_relevance": "supporting",
                    },
                    cortex: {
                        "disposition": "duplicate_candidate",
                        "claimed_responsibilities": ["context_selection"],
                        "overlap_candidates": ["app/kernel/data_processing/context_packet.py"],
                    },
                    "app/kernel/missing.py": {
                        "disposition": "stranded",
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    report = scan_repository(tmp_path)
    overlaid = apply_overrides(report, load_overrides(override_path))
    by_path = {item["path"]: item for item in overlaid["components"]}

    assert by_path[authoritative]["disposition"] == "online_authoritative"
    assert by_path[authoritative]["composition_roots"] == ["app/kernel/compute/compute_plane.py"]
    assert by_path[offline]["disposition"] == "supervised_offline"
    assert by_path[cortex]["overlap_candidates"] == ["app/kernel/data_processing/context_packet.py"]
    assert by_path[authoritative]["runtime"]["constructed"] == "unverified"
    assert by_path[authoritative]["runtime"]["invoked"] == "unverified"
    assert overlaid["overlay"]["stale_paths"] == ["app/kernel/missing.py"]


def test_override_loader_rejects_invalid_disposition(tmp_path):
    override_path = tmp_path / "overrides.json"
    override_path.write_text(
        json.dumps(
            {
                "components": {
                    "app/kernel/compute/compute_plane.py": {
                        "disposition": "definitely_online_trust_me"
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid disposition"):
        load_overrides(override_path)


def test_compute_disposition_registry_is_source_evidence_not_runtime_proof(tmp_path):
    compute_dir = tmp_path / "app/kernel/compute"
    compute_dir.mkdir(parents=True)
    for name in ("compute_plane", "benchmark", "crystal_hypergraph", "legacy"):
        (compute_dir / f"{name}.py").write_text("x=1\n", encoding="utf-8")
    (compute_dir / "module_dispositions.py").write_text(
        "ONLINE_ENFORCEMENT = frozenset({'compute_plane'})\n"
        "SUPERVISED_EVIDENCE = frozenset({'benchmark'})\n"
        "OFFLINE_LIBRARY = frozenset({'crystal_hypergraph'})\n"
        "RETIRED = {'legacy': 'replaced'}\n",
        encoding="utf-8",
    )

    report = apply_compute_module_dispositions(scan_repository(tmp_path), tmp_path)
    by_path = {item["path"]: item for item in report["components"]}

    assert by_path["app/kernel/compute/compute_plane.py"]["disposition"] == "online_supporting"
    assert by_path["app/kernel/compute/benchmark.py"]["disposition"] == "supervised_offline"
    assert by_path["app/kernel/compute/crystal_hypergraph.py"]["disposition"] == "stranded"
    assert by_path["app/kernel/compute/legacy.py"]["disposition"] == "retired"
    assert "source_disposition:ONLINE_ENFORCEMENT" in by_path["app/kernel/compute/compute_plane.py"]["notes"]
    assert "source_disposition:OFFLINE_LIBRARY" in by_path["app/kernel/compute/crystal_hypergraph.py"]["notes"]
    assert by_path["app/kernel/compute/compute_plane.py"]["runtime"]["constructed"] == "unverified"
    assert by_path["app/kernel/compute/compute_plane.py"]["runtime"]["invoked"] == "unverified"


def test_missing_retired_compute_module_is_a_tombstone_not_a_stale_live_reference(tmp_path):
    compute_dir = tmp_path / "app/kernel/compute"
    compute_dir.mkdir(parents=True)
    (compute_dir / "compute_plane.py").write_text("x=1\n", encoding="utf-8")
    (compute_dir / "module_dispositions.py").write_text(
        "ONLINE_ENFORCEMENT = frozenset({'compute_plane'})\n"
        "SUPERVISED_EVIDENCE = frozenset()\n"
        "OFFLINE_LIBRARY = frozenset()\n"
        "RETIRED = {'removed_duplicate': 'duplicate removed'}\n",
        encoding="utf-8",
    )

    report = apply_compute_module_dispositions(scan_repository(tmp_path), tmp_path)
    overlay = report["overlay"]["compute_module_dispositions"]

    assert overlay["stale_modules"] == []
    assert overlay["retired_tombstones"] == [
        {"module": "removed_duplicate", "reason": "duplicate removed"}
    ]
