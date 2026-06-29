"""
Layered BEAST compression pipeline.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.kernel.compute.ast_compressor import ASTCompressor
from app.kernel.storage.evidence_chronicle import EvidenceChronicleWriter
from app.kernel.storage.evidence_envelope import EvidenceEnvelopeFactory


class CompressionPipeline:
    """Choose compression layers and produce chunk metadata plus evidence."""

    def __init__(self, policies: Optional[Dict[str, Any]] = None, data_dir: Optional[str] = None):
        self.policies = policies or {}
        self.ast_compressor = ASTCompressor()
        self.evidence_factory = EvidenceEnvelopeFactory(self.policies)
        self.chronicle_writer = EvidenceChronicleWriter(
            data_dir=data_dir,
            enabled=bool((self.policies.get("evidence_chronicle") or {}).get("enabled", True)),
        )

    def compress(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        content_type = str(payload.get("content_type") or "").lower()
        source_uri = str(payload.get("source_uri") or "payload://compression")
        max_chunk_chars = max(240, min(int(payload.get("max_chunk_chars") or 1600), 8000))
        value = payload.get("value")
        text = payload.get("text") or payload.get("content") or payload.get("source")
        layers: List[Dict[str, Any]] = []
        chunks: List[Dict[str, Any]] = []

        artifact_type = str(payload.get("artifact_type") or "").lower()
        if value is not None:
            result = self.ast_compressor.compress_json(value).to_dict()
            raw_text = json.dumps(value, sort_keys=True, default=str)
            chunks = self._structured_chunks(value, source_uri, max_chunk_chars, artifact_type=artifact_type)
            layers.append({"name": "lossless_json", "mode": result["mode"], "reduction_percent": result["reduction_percent"]})
        elif isinstance(text, str) and (content_type == "application/python" or payload.get("language") == "python"):
            raw_text = text
            mode = str(payload.get("mode") or "summary")
            if mode == "lossless":
                result = self.ast_compressor.compress_python_source(text).to_dict()
            else:
                result = self.ast_compressor.compress_python_summary(text).to_dict()
            chunks = self._python_chunks(text, source_uri, max_chunk_chars)
            layers.append({"name": "semantic_python_ast", "mode": result["mode"], "reduction_percent": result["reduction_percent"]})
        elif isinstance(text, str):
            raw_text = text
            pruned = self._edge_prune(text)
            result = {
                "algorithm": "edgek_layered_compression_v1",
                "mode": "semantic_text_prune",
                "original_bytes": len(text.encode("utf-8")),
                "compressed_bytes": len(pruned.encode("utf-8")),
                "reduction_percent": self._reduction(len(text.encode("utf-8")), len(pruned.encode("utf-8"))),
                "payload": pruned,
                "metadata": {"content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "reconstructive": False},
            }
            if content_type in {"text/markdown", "application/markdown"} or payload.get("language") == "markdown":
                chunks = self._markdown_chunks(pruned, source_uri, max_chunk_chars)
            elif artifact_type in {"chronicle_record", "route_card_record", "schema_node"}:
                chunks = self._text_chunks(pruned, source_uri, max_chunk_chars, chunk_kind=artifact_type)
            else:
                chunks = self._text_chunks(pruned, source_uri, max_chunk_chars)
            layers.append({"name": "semantic_text_prune", "mode": result["mode"], "reduction_percent": result["reduction_percent"]})
        else:
            raise ValueError("value or text/content/source is required")

        layers.append({"name": "execution_handoff", "mode": "winning_chunks_with_references", "chunk_count": len(chunks)})
        evidence = self.evidence_factory.build(
            source_type="compression_pipeline",
            source_uri=source_uri,
            scope=str(payload.get("scope") or "payload"),
            artifact_type="compression_result",
            severity="info",
            confidence=0.86,
            relevance=float(payload.get("relevance") or 0.68),
            risk=0.12,
            blast_radius=0.25,
            verification_strength=0.55,
            expected_value=max(0.1, min(0.95, float(result.get("reduction_percent") or 0.0) / 100.0 + 0.2)),
            signals=["compression_pipeline", result["mode"], "context_reduced"],
            relationships=[{"type": "source_uri", "id": source_uri}],
            recommended_actions=["Use winning chunks and exact references for handoff instead of raw payload."],
            recommended_capability_id="tool:compression_prune",
            capability_family="tool_bus",
            summary=f"Compressed payload with {result['mode']} and produced {len(chunks)} handoff chunks.",
        )
        chronicle = self.chronicle_writer.maybe_write(evidence, reason="compression_pipeline")
        return {
            "beast_object_type": "compression_pipeline_result",
            "version": "1.0",
            "layers": layers,
            "result": result,
            "chunks": chunks,
            "chunk_count": len(chunks),
            "raw_bytes": len(raw_text.encode("utf-8")),
            "evidence_record": evidence,
            "chronicle": chronicle,
        }

    def _python_chunks(self, source: str, source_uri: str, max_chars: int) -> List[Dict[str, Any]]:
        chunks = []
        pattern = re.compile(r"^(class|def)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
        matches = list(pattern.finditer(source))
        if not matches:
            return self._text_chunks(source, source_uri, max_chars, chunk_kind="code_window", language="python")
        for idx, match in enumerate(matches):
            start = match.start()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(source)
            content = source[start:end].strip()
            chunks.extend(self._window_chunk(content, source_uri, max_chars, "code_unit", "python", symbol=match.group(2)))
        return chunks

    def _structured_chunks(self, value: Any, source_uri: str, max_chars: int, artifact_type: str = "") -> List[Dict[str, Any]]:
        if artifact_type in {"chronicle_record", "route_card_record", "schema_node"}:
            return self._record_chunks(value, source_uri, max_chars, artifact_type)
        if self._looks_like_schema(value):
            return self._record_chunks(value, source_uri, max_chars, "schema_node")
        if self._looks_like_chronicle(value):
            return self._record_chunks(value, source_uri, max_chars, "chronicle_record")
        if self._looks_like_route_card(value):
            return self._record_chunks(value, source_uri, max_chars, "route_card_record")
        if isinstance(value, list):
            return [
                self._chunk(json.dumps(item, sort_keys=True, default=str), source_uri, "structured_record", None, schema_path=f"$[{idx}]")
                for idx, item in enumerate(value[:100])
            ]
        return self._text_chunks(json.dumps(value, sort_keys=True, default=str), source_uri, max_chars, chunk_kind="structured_record")

    def _record_chunks(self, value: Any, source_uri: str, max_chars: int, chunk_kind: str) -> List[Dict[str, Any]]:
        if isinstance(value, list):
            chunks = []
            for idx, item in enumerate(value[:100]):
                chunks.extend(self._window_chunk(json.dumps(item, sort_keys=True, default=str), source_uri, max_chars, chunk_kind, None, schema_path=f"$[{idx}]"))
            return chunks
        return self._window_chunk(json.dumps(value, sort_keys=True, default=str), source_uri, max_chars, chunk_kind, None, schema_path="$")

    def _markdown_chunks(self, text: str, source_uri: str, max_chars: int) -> List[Dict[str, Any]]:
        sections = []
        current: List[str] = []
        heading = "document"
        start_line = 1
        for lineno, line in enumerate(text.splitlines(), start=1):
            if line.startswith("#") and current:
                sections.append((heading, start_line, lineno - 1, "\n".join(current).strip()))
                current = []
                heading = line.strip("# ").strip() or "section"
                start_line = lineno
            elif line.startswith("#"):
                heading = line.strip("# ").strip() or "section"
                start_line = lineno
            current.append(line)
        if current:
            sections.append((heading, start_line, start_line + len(current) - 1, "\n".join(current).strip()))
        chunks = []
        for idx, (section, start, end, content) in enumerate(sections or [("document", 1, 1, text)]):
            chunks.extend(self._window_chunk(
                content,
                source_uri,
                max_chars,
                "markdown_section",
                "markdown",
                symbol=section,
                start_line=start,
                end_line=end,
                schema_path=f"$.sections[{idx}]",
            ))
        return chunks

    def _text_chunks(self, text: str, source_uri: str, max_chars: int, chunk_kind: str = "text_window", language: Optional[str] = None) -> List[Dict[str, Any]]:
        return self._window_chunk(text, source_uri, max_chars, chunk_kind, language)

    def _window_chunk(
        self,
        text: str,
        source_uri: str,
        max_chars: int,
        chunk_kind: str,
        language: Optional[str],
        symbol: Optional[str] = None,
        schema_path: Optional[str] = None,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        chunks = []
        for idx, start in enumerate(range(0, len(text), max_chars)):
            content = text[start:start + max_chars]
            chunks.append(self._chunk(content, source_uri, chunk_kind, language, symbol=symbol, schema_path=schema_path, window_index=idx, start_line=start_line, end_line=end_line))
        return chunks

    def _chunk(
        self,
        content: str,
        source_uri: str,
        chunk_kind: str,
        language: Optional[str],
        symbol: Optional[str] = None,
        schema_path: Optional[str] = None,
        window_index: int = 0,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
    ) -> Dict[str, Any]:
        digest = hashlib.sha256(f"{source_uri}:{chunk_kind}:{symbol}:{schema_path}:{window_index}:{content}".encode("utf-8")).hexdigest()
        return {
            "chunk_id": f"chk_{digest[:16]}",
            "source_uri": source_uri,
            "source_type": "compression_pipeline",
            "artifact_type": "compressed_chunk",
            "task_id": None,
            "provider": None,
            "language": language,
            "chunk_kind": chunk_kind,
            "schema_path": schema_path,
            "symbols": [symbol] if symbol else [],
            "start_line": start_line,
            "end_line": end_line,
            "content_hash": "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "context_header": f"{chunk_kind} from {source_uri}" + (f" symbol {symbol}" if symbol else ""),
            "token_estimate": max(1, len(content) // 4),
            "embedding_model": None,
            "redaction_status": "not_scanned",
            "content": content,
        }

    def _looks_like_chronicle(self, value: Any) -> bool:
        return isinstance(value, dict) and (
            str(value.get("chronicle_type") or "").endswith("summary")
            or value.get("chronicle_type") == "evidence_envelope"
            or ("task_id" in value and "recommendations" in value)
        )

    def _looks_like_route_card(self, value: Any) -> bool:
        return isinstance(value, dict) and ("route_id" in value or value.get("beast_object_type") == "route_card")

    def _looks_like_schema(self, value: Any) -> bool:
        if not isinstance(value, dict):
            return False
        return any(key in value for key in ("columns", "tables", "properties", "definitions", "$schema", "openapi"))

    def _edge_prune(self, text: str) -> str:
        lines = []
        previous = None
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped == previous:
                continue
            lines.append(line.rstrip())
            previous = stripped
        return "\n".join(lines)

    def _reduction(self, original_bytes: int, compressed_bytes: int) -> float:
        if original_bytes <= 0:
            return 0.0
        return round(((original_bytes - compressed_bytes) / original_bytes) * 100.0, 4)
