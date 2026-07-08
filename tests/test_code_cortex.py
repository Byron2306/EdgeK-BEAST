import sys

from app.cli.api import BeastApiClient
from app.kernel.data_processing.code_cortex import CodeCortexRouter, GortexAdapter, LocalCodeCortexAdapter


def test_local_code_cortex_finds_symbols_and_dependents(tmp_path):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "__init__.py").write_text("", encoding="utf-8")
    (app_dir / "service.py").write_text(
        "def value():\n"
        "    return 1\n",
        encoding="utf-8",
    )
    (app_dir / "api.py").write_text(
        "from app.service import value\n\n"
        "def route():\n"
        "    return value()\n",
        encoding="utf-8",
    )
    adapter = LocalCodeCortexAdapter()

    symbols = adapter.search_symbols(tmp_path, "value")
    dependents = adapter.get_dependents(tmp_path, "app/service.py")

    assert symbols["ok"] is True
    assert symbols["results"][0]["name"] == "value"
    assert dependents["ok"] is True
    assert "app/api.py" in [item["path"] for item in dependents["results"]]
    assert dependents["receipt"]["beast_object_type"] == "code_cortex_adapter_receipt"


def test_symbol_surgeon_builds_previewable_sourceplan(tmp_path):
    target = tmp_path / "service.py"
    target.write_text(
        "def value():\n"
        "    return 1\n\n"
        "def other():\n"
        "    return 0\n",
        encoding="utf-8",
    )
    client = BeastApiClient("http://offline", workspace=tmp_path)

    result = client.build_symbol_surgeon_plan(
        "service.py",
        "value",
        "def value():\n    return 2\n",
        objective="Update value return",
    )
    preview = client.preview_patch_plan(result.data)

    assert result.ok is True
    assert result.data["kind"] == "beast_symbol_surgeon_source_patch_plan"
    assert result.data["operations"][0]["action_ir_type"] == "modify_symbol"
    assert result.data["operations"][0]["resolver"] == "code_cortex.local_symbol_surgeon"
    assert result.data["code_cortex"]["receipt"]["ok"] is True
    assert preview.ok is True
    assert "return 1" in preview.data["operations"][0]["old_text"]
    assert "return 2" in preview.data["operations"][0]["new_text"]


def test_gortex_adapter_wraps_optional_json_cli(tmp_path):
    fake = tmp_path / "fake_gortex.py"
    fake.write_text(
        "#!" + sys.executable + "\n"
        "import sys\n"
        "import json\n"
        "assert sys.argv[1:4] == ['query', 'symbol', 'value']\n"
        "assert '--index' in sys.argv\n"
        "assert '--format' in sys.argv\n"
        "print(json.dumps({'results': [{'name': 'external_value', 'file': 'app.py'}]}))\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    adapter = GortexAdapter(binary=str(fake), timeout=2.0)

    result = adapter.search_symbols(tmp_path, "value")

    assert result["ok"] is True
    assert result["adapter"] == "gortex"
    assert result["results"][0]["name"] == "external_value"
    assert result["receipt"]["command"][0] == str(fake)
    assert result["receipt"]["command"][1:4] == ["query", "symbol", "value"]


def test_gortex_adapter_status_wraps_plain_cli_output(tmp_path):
    fake = tmp_path / "fake_gortex.py"
    fake.write_text(
        "#!" + sys.executable + "\n"
        "import sys\n"
        "assert sys.argv[1:] == ['status']\n"
        f"print('tracked repos:\\n  test {tmp_path.as_posix()} (1 files, 1 nodes, 0 edges)')\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    adapter = GortexAdapter(binary=str(fake), timeout=2.0)

    result = adapter.status(tmp_path)

    assert result["ok"] is True
    assert result["available"] is True
    assert result["tracked"] is True
    assert "tracked repos" in result["data"]["text"]


def test_code_cortex_router_falls_back_to_local_when_gortex_missing(tmp_path):
    target = tmp_path / "module.py"
    target.write_text("def fallback_symbol():\n    return True\n", encoding="utf-8")
    router = CodeCortexRouter(adapters=[GortexAdapter(binary=str(tmp_path / "missing-gortex")), LocalCodeCortexAdapter()])

    result = router.search_symbols(tmp_path, "fallback_symbol")

    assert result["ok"] is True
    assert result["adapter"] == "local_code_cortex"
    assert result["fallback_from"] == "gortex"
