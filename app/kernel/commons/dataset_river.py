"""Deterministic streamed dataset records with lineage."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib, json
from typing import Iterable, Iterator, Mapping, Any


@dataclass(frozen=True)
class DatasetLineage:
    dataset_digest: str
    shard_index: int
    shard_count: int
    privacy_label: str
    record_count: int


class DatasetCursor(Iterator[Mapping[str, Any]]):
    """Single-pass shard cursor that verifies the full source at exhaustion."""

    def __init__(self, records, *, dataset_digest: str, shard_index: int, shard_count: int, privacy_label: str, verify_digest: bool):
        self._records=iter(records); self.dataset_digest=dataset_digest; self.shard_index=shard_index; self.shard_count=shard_count; self.privacy_label=privacy_label; self.verify_digest=verify_digest
        self._index=0; self._selected=0; self._complete=False; self._first=True; self._hasher=hashlib.sha256(); self._hasher.update(b"[")

    def __iter__(self): return self

    def __next__(self):
        while True:
            try: record=dict(next(self._records))
            except StopIteration:
                if not self._complete:
                    self._hasher.update(b"]"); actual="sha256:"+self._hasher.hexdigest(); self._complete=True
                    if self.verify_digest and actual!=self.dataset_digest: raise ValueError("dataset digest mismatch")
                raise
            if not self._first: self._hasher.update(b",")
            self._first=False; self._hasher.update(json.dumps(record,sort_keys=True,separators=(",",":"),default=str).encode())
            index=self._index; self._index+=1
            if index % self.shard_count == self.shard_index:
                self._selected+=1; return record

    def receipt(self) -> DatasetLineage:
        if not self._complete: raise RuntimeError("dataset cursor must be exhausted before lineage is final")
        return DatasetLineage(self.dataset_digest,self.shard_index,self.shard_count,self.privacy_label,self._selected)


class DatasetRiver:
    PRIVACY_LABELS={"public","internal","restricted","private"}
    def stream(self, records: Iterable[Mapping[str, Any]], *, dataset_digest: str, shard_index: int = 0, shard_count: int = 1, privacy_label: str = "internal", verify_digest: bool = False) -> tuple[Iterator[Mapping[str, Any]], DatasetLineage]:
        if not dataset_digest.startswith("sha256:") or shard_count < 1 or not 0 <= shard_index < shard_count: raise ValueError("invalid dataset lineage")
        if privacy_label not in self.PRIVACY_LABELS: raise ValueError("invalid privacy label")
        material=[dict(record) for record in records]
        if verify_digest:
            digest="sha256:"+hashlib.sha256(json.dumps(material,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
            if digest!=dataset_digest: raise ValueError("dataset digest mismatch")
        selected=[]
        for index, record in enumerate(material):
            if index % shard_count == shard_index: selected.append(dict(record))
        lineage=DatasetLineage(dataset_digest, shard_index, shard_count, privacy_label, len(selected))
        return iter(selected), lineage

    def stream_lazy(self, records: Iterable[Mapping[str, Any]], *, dataset_digest: str, shard_index: int = 0, shard_count: int = 1, privacy_label: str = "internal", verify_digest: bool = True) -> DatasetCursor:
        if not dataset_digest.startswith("sha256:") or len(dataset_digest)!=71 or shard_count<1 or not 0<=shard_index<shard_count: raise ValueError("invalid dataset lineage")
        if privacy_label not in self.PRIVACY_LABELS: raise ValueError("invalid privacy label")
        return DatasetCursor(records,dataset_digest=dataset_digest,shard_index=shard_index,shard_count=shard_count,privacy_label=privacy_label,verify_digest=verify_digest)

    @staticmethod
    def digest(records: Iterable[Mapping[str,Any]]) -> str:
        material=[dict(record) for record in records]
        return "sha256:"+hashlib.sha256(json.dumps(material,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
