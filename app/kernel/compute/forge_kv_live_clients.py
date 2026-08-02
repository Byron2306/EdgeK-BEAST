"""Official-SDK client construction with call-scoped credential loading."""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Any
from app.kernel.compute.forge_kv_level7_config import ForgeKVLiveConfig

@contextmanager
def hf_api_client(config: ForgeKVLiveConfig) -> Iterator[Any]:
    config.validate(for_write=True)
    try:
        from huggingface_hub import HfApi
    except ImportError as exc: raise RuntimeError("install huggingface_hub for live publication") from exc
    token=Path(config.hf_token_file).expanduser().read_text(encoding="utf-8").strip()
    if not token: raise PermissionError("Hugging Face token file is empty")
    try: yield HfApi(endpoint=config.hf_endpoint or None, token=token)
    finally: token=""  # narrow lifetime; SDK may retain its private copy until object collection

def s3_client(config: ForgeKVLiveConfig) -> Any:
    try: import boto3
    except ImportError as exc: raise RuntimeError("install boto3 for S3 publication") from exc
    kwargs={}
    if config.s3_endpoint_url: kwargs["endpoint_url"]=config.s3_endpoint_url
    if config.s3_region: kwargs["region_name"]=config.s3_region
    return boto3.client("s3",**kwargs)
