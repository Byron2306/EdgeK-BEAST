import importlib.util
from pathlib import Path


def _load_benchmark_module():
    path = Path(__file__).resolve().parent / "benchmarks" / "edge_metrics_benchmark.py"
    spec = importlib.util.spec_from_file_location("edge_metrics_benchmark", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_edge_metrics_cost_and_tool_laziness_sections_run():
    module = _load_benchmark_module()

    cost = module.benchmark_cost_efficiency()
    tool = module.benchmark_tool_laziness()

    assert cost["combined_token_reduction_percent"] > 0
    assert tool["final_recommendation"]["decision"] == "skip"
