"""
AST and structural payload compression.

The compressor supports lossless schema-row compression for JSON telemetry and
semantic Python AST compression for code-heavy agentic payloads.
"""

import ast
import base64
import hashlib
import json
import zlib
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass
class CompressionResult:
    algorithm: str
    mode: str
    original_bytes: int
    compressed_bytes: int
    reduction_percent: float
    payload: str
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(data: str) -> bytes:
    return base64.b64decode(data.encode("ascii"))


def _reduction(original: int, compressed: int) -> float:
    if not original:
        return 0.0
    return round(((original - compressed) / original) * 100.0, 4)


class ASTCompressor:
    """Production-oriented compressor for telemetry and agentic payloads."""

    def compress_json(self, value: Any) -> CompressionResult:
        raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
        if self._is_schema_rows_candidate(value):
            columns = list(value[0].keys())
            structural = {
                "columns": columns,
                "rows": [[record.get(column) for column in columns] for record in value],
            }
            mode = "lossless_json_schema_rows"
        else:
            structural = value
            mode = "lossless_json_zlib"

        structural_bytes = json.dumps(structural, separators=(",", ":"), sort_keys=True).encode("utf-8")
        compressed = zlib.compress(structural_bytes, 9)
        return CompressionResult(
            algorithm="edgek_ast_compressor_v1",
            mode=mode,
            original_bytes=len(raw),
            compressed_bytes=len(compressed),
            reduction_percent=_reduction(len(raw), len(compressed)),
            payload=_b64(compressed),
            metadata={
                "content_sha256": hashlib.sha256(raw).hexdigest(),
                "columns": structural.get("columns") if isinstance(structural, dict) else None,
                "record_count": len(value) if isinstance(value, list) else None,
            },
        )

    def decompress_json(self, result: CompressionResult | Dict[str, Any]) -> Any:
        result = self._coerce(result)
        data = json.loads(zlib.decompress(_unb64(result.payload)).decode("utf-8"))
        if result.mode == "lossless_json_schema_rows":
            columns = data["columns"]
            return [dict(zip(columns, row)) for row in data["rows"]]
        return data

    def compress_python_source(self, source: str) -> CompressionResult:
        raw = source.encode("utf-8")
        tree = ast.parse(source)
        canonical = ast.unparse(tree)
        summary = self.python_ast_summary(source)
        ast_payload = {
            "canonical_source": canonical,
            "summary": summary,
        }
        ast_bytes = json.dumps(ast_payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        compressed = zlib.compress(ast_bytes, 9)
        return CompressionResult(
            algorithm="edgek_ast_compressor_v1",
            mode="semantic_python_ast",
            original_bytes=len(raw),
            compressed_bytes=len(compressed),
            reduction_percent=_reduction(len(raw), len(compressed)),
            payload=_b64(compressed),
            metadata={
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "canonical_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
                "node_count": sum(summary["node_counts"].values()),
                "function_count": summary["node_counts"].get("FunctionDef", 0),
            },
        )

    def compress_python_summary(self, source: str) -> CompressionResult:
        """Compress Python source into a non-reconstructive semantic AST summary."""
        raw = source.encode("utf-8")
        summary = self.python_ast_summary(source)
        summary_bytes = json.dumps(summary, separators=(",", ":"), sort_keys=True).encode("utf-8")
        compressed = zlib.compress(summary_bytes, 9)
        return CompressionResult(
            algorithm="edgek_ast_compressor_v1",
            mode="semantic_python_ast_summary",
            original_bytes=len(raw),
            compressed_bytes=len(compressed),
            reduction_percent=_reduction(len(raw), len(compressed)),
            payload=_b64(compressed),
            metadata={
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "node_count": sum(summary["node_counts"].values()),
                "function_count": summary["node_counts"].get("FunctionDef", 0),
                "reconstructive": False,
            },
        )

    def decompress_python_source(self, result: CompressionResult | Dict[str, Any]) -> str:
        result = self._coerce(result)
        if result.mode != "semantic_python_ast":
            raise ValueError(f"Not a Python AST payload: {result.mode}")
        data = json.loads(zlib.decompress(_unb64(result.payload)).decode("utf-8"))
        return data["canonical_source"]

    def python_ast_summary(self, source: str) -> Dict[str, Dict[str, int]]:
        tree = ast.parse(source)
        node_counts: Dict[str, int] = {}
        names: Dict[str, int] = {}
        constants: Dict[str, int] = {}
        for node in ast.walk(tree):
            node_counts[type(node).__name__] = node_counts.get(type(node).__name__, 0) + 1
            if isinstance(node, ast.Name):
                names[node.id] = names.get(node.id, 0) + 1
            elif isinstance(node, ast.arg):
                names[node.arg] = names.get(node.arg, 0) + 1
            elif isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool)):
                key = repr(node.value)
                constants[key] = constants.get(key, 0) + 1
        return {
            "node_counts": dict(sorted(node_counts.items())),
            "names": dict(sorted(names.items())),
            "constants": dict(sorted(constants.items())),
        }

    def compress_auto(self, payload: Any, content_type: Optional[str] = None) -> CompressionResult:
        if content_type == "application/python" or isinstance(payload, str):
            return self.compress_python_source(str(payload))
        return self.compress_json(payload)

    def _is_schema_rows_candidate(self, value: Any) -> bool:
        if not isinstance(value, list) or len(value) < 2 or not all(isinstance(item, dict) for item in value):
            return False
        keys = list(value[0].keys())
        return all(list(item.keys()) == keys for item in value)

    def _coerce(self, result: CompressionResult | Dict[str, Any]) -> CompressionResult:
        if isinstance(result, CompressionResult):
            return result
        return CompressionResult(**result)
