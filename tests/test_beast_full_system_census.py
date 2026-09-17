from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from beast_full_system_census import scan_repository, render_markdown


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
