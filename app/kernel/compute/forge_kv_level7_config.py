"""Fail-closed configuration for live Forge dataset publication."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import os, stat

@dataclass(frozen=True)
class ForgeKVLiveConfig:
    enabled: bool = False
    dry_run: bool = True
    hf_dataset_id: str = ""
    hf_endpoint: str = ""
    hf_token_file: str = ""
    s3_bucket: str = ""
    s3_prefix: str = "forge-kv"
    s3_endpoint_url: str = ""
    s3_region: str = ""
    receipt_root: str = "~/.local/state/beast/forge-publication"
    evidence_root: str = "~/.local/state/beast/forge-evidence"
    require_private_dataset: bool = True

    @classmethod
    def from_env(cls) -> "ForgeKVLiveConfig":
        truth=lambda k,d=False: str(os.getenv(k,"1" if d else "0")).lower() in {"1","true","yes","on"}
        return cls(
            enabled=truth("BEAST_FORGE_KV_ONLINE",False), dry_run=truth("BEAST_FORGE_KV_DRY_RUN",True),
            hf_dataset_id=os.getenv("BEAST_FORGE_KV_HF_DATASET","").strip(),
            hf_endpoint=os.getenv("BEAST_FORGE_KV_HF_ENDPOINT","").strip(),
            hf_token_file=os.getenv("BEAST_FORGE_KV_HF_TOKEN_FILE","").strip(),
            s3_bucket=os.getenv("BEAST_FORGE_KV_S3_BUCKET","").strip(),
            s3_prefix=os.getenv("BEAST_FORGE_KV_S3_PREFIX","forge-kv").strip("/"),
            s3_endpoint_url=os.getenv("BEAST_FORGE_KV_S3_ENDPOINT","").strip(),
            s3_region=os.getenv("BEAST_FORGE_KV_S3_REGION","").strip(),
            receipt_root=os.getenv("BEAST_FORGE_KV_RECEIPTS","~/.local/state/beast/forge-publication"),
            evidence_root=os.getenv("BEAST_FORGE_KV_EVIDENCE","~/.local/state/beast/forge-evidence"),
            require_private_dataset=truth("BEAST_FORGE_KV_REQUIRE_PRIVATE",True),
        )

    def validate(self, *, for_write: bool=False) -> None:
        if for_write and (not self.enabled or self.dry_run): raise PermissionError("live publication is disabled or dry-run")
        if self.enabled and not self.hf_dataset_id: raise ValueError("BEAST_FORGE_KV_HF_DATASET is required")
        if self.enabled and not self.hf_token_file: raise ValueError("BEAST_FORGE_KV_HF_TOKEN_FILE is required")
        if self.hf_token_file:
            p=Path(self.hf_token_file).expanduser()
            if not p.is_file(): raise FileNotFoundError("configured Hugging Face token file is missing")
            mode=stat.S_IMODE(p.stat().st_mode)
            if mode & 0o077: raise PermissionError("token file must not be accessible by group or others")

    def public_state(self) -> dict:
        d=asdict(self); d.pop("hf_token_file",None)
        d["credential_source_configured"]=bool(self.hf_token_file)
        return {"beast_object_type":"forge_kv_live_config","version":"1.0",**d}
