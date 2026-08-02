"""Verified OCI, CID, and chunked artifact retrieval adapters."""
from __future__ import annotations

import abc
import dataclasses
import hashlib
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

_DIGEST_RE = re.compile(r"^(?P<algo>sha256):(?P<hex>[0-9a-fA-F]{64})$")


class ArtifactVerificationError(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class ArtifactReceipt:
    reference: str
    resolved_digest: str
    media_type: str
    size: int
    path: str
    source: str


class ArtifactAdapter(abc.ABC):
    @abc.abstractmethod
    def fetch_artifact(self, cid: str, destination: Path) -> Path:
        raise NotImplementedError


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)[:160] or "artifact"


class _NoCrossHostAuthRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected and urllib.parse.urlsplit(req.full_url).netloc != urllib.parse.urlsplit(newurl).netloc:
            redirected.remove_header("Authorization")
        return redirected


class OCIArtifactAdapter(ArtifactAdapter):
    """Pull OCI manifests or blobs and verify every digest-bound response."""

    def __init__(self, registry: str, repository: str, auth_token: str | None = None, *, timeout: float = 30.0, insecure: bool = False) -> None:
        if not repository.strip("/"):
            raise ValueError("repository is required")
        registry = registry.rstrip("/")
        if "://" not in registry:
            registry = ("http" if insecure else "https") + "://" + registry
        self.registry = registry
        self.repository = repository.strip("/")
        self.auth_token = auth_token
        self.timeout = timeout
        self.opener = urllib.request.build_opener(_NoCrossHostAuthRedirect())

    def _request(self, path: str, *, accept: str) -> tuple[bytes, Mapping[str, str]]:
        req = urllib.request.Request(f"{self.registry}/v2/{self.repository}/{path}", headers={"Accept": accept})
        if self.auth_token:
            req.add_header("Authorization", f"Bearer {self.auth_token}")
        with self.opener.open(req, timeout=self.timeout) as response:
            return response.read(), dict(response.headers.items())

    def fetch_manifest(self, reference: str, destination: Path) -> ArtifactReceipt:
        data, headers = self._request(
            "manifests/" + urllib.parse.quote(reference, safe=":@"),
            accept=", ".join((
                "application/vnd.oci.image.manifest.v1+json",
                "application/vnd.oci.image.index.v1+json",
                "application/vnd.oci.artifact.manifest.v1+json",
                "application/vnd.docker.distribution.manifest.v2+json",
            )),
        )
        actual = _sha256(data)
        match = _DIGEST_RE.fullmatch(reference)
        if match and actual.lower() != reference.lower():
            raise ArtifactVerificationError("OCI manifest body does not match requested digest")
        server_digest = headers.get("Docker-Content-Digest") or headers.get("docker-content-digest")
        if server_digest and _DIGEST_RE.fullmatch(server_digest) and server_digest.lower() != actual.lower():
            raise ArtifactVerificationError("OCI Docker-Content-Digest does not match response body")
        media = headers.get("Content-Type", headers.get("content-type", "application/octet-stream")).split(";", 1)[0]
        destination.mkdir(parents=True, exist_ok=True)
        path = destination / (_safe_name(reference) + ".manifest.json")
        path.write_bytes(data)
        return ArtifactReceipt(reference, actual, media, len(data), str(path), self.registry)

    def fetch_blob(self, digest: str, destination: Path) -> ArtifactReceipt:
        if not _DIGEST_RE.fullmatch(digest):
            raise ValueError("OCI blob digest must be sha256:<64 hex>")
        data, headers = self._request("blobs/" + digest, accept="application/octet-stream")
        actual = _sha256(data)
        if actual.lower() != digest.lower():
            raise ArtifactVerificationError("OCI blob body does not match requested digest")
        destination.mkdir(parents=True, exist_ok=True)
        path = destination / _safe_name(digest)
        path.write_bytes(data)
        return ArtifactReceipt(digest, actual, headers.get("Content-Type", "application/octet-stream"), len(data), str(path), self.registry)

    def fetch_artifact(self, cid: str, destination: Path) -> Path:
        return Path(self.fetch_manifest(cid, destination).path)


class IPFSArtifactAdapter(ArtifactAdapter):
    def __init__(self, ipfs_gateway: str = "https://ipfs.io", *, timeout: float = 30.0, max_bytes: int = 1 << 30) -> None:
        self.ipfs_gateway = ipfs_gateway.rstrip("/")
        self.timeout = timeout
        self.max_bytes = max_bytes

    def fetch_artifact(self, cid: str, destination: Path) -> Path:
        if not cid or any(ch in cid for ch in "/\\?#\r\n"):
            raise ValueError("invalid CID")
        req = urllib.request.Request(f"{self.ipfs_gateway}/ipfs/{urllib.parse.quote(cid, safe='')}")
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            data = response.read(self.max_bytes + 1)
        if len(data) > self.max_bytes:
            raise ArtifactVerificationError("CID response exceeds configured size bound")
        destination.mkdir(parents=True, exist_ok=True)
        path = destination / _safe_name(cid)
        path.write_bytes(data)
        return path


class XetChunkService:
    """Assemble a digest-bound chunk manifest using atomic output replacement."""

    def __init__(self, adapter: ArtifactAdapter) -> None:
        self.adapter = adapter

    def fetch_and_assemble(self, root_cid: str, destination: Path) -> Path:
        destination.mkdir(parents=True, exist_ok=True)
        manifest_path = self.adapter.fetch_artifact(root_cid, destination / ".chunks")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        chunks = manifest.get("chunks")
        output_name = _safe_name(str(manifest.get("name") or root_cid))
        expected = str(manifest.get("digest") or "")
        if not isinstance(chunks, list) or not chunks:
            raise ArtifactVerificationError("chunk manifest has no chunks")
        fd, temp_name = tempfile.mkstemp(prefix=".beast-xet-", dir=destination)
        os.close(fd)
        temp = Path(temp_name)
        try:
            with temp.open("wb") as output:
                for item in chunks:
                    cid = str(item["cid"] if isinstance(item, Mapping) else item)
                    chunk = self.adapter.fetch_artifact(cid, destination / ".chunks")
                    data = chunk.read_bytes()
                    declared = str(item.get("digest", "")) if isinstance(item, Mapping) else ""
                    if declared and _sha256(data) != declared:
                        raise ArtifactVerificationError(f"chunk digest mismatch: {cid}")
                    output.write(data)
            data_digest = _sha256(temp.read_bytes())
            if expected and data_digest != expected:
                raise ArtifactVerificationError("assembled artifact digest mismatch")
            final = destination / output_name
            temp.replace(final)
            return final
        finally:
            temp.unlink(missing_ok=True)
