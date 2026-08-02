"""Explicit online-client factories for Forge publication.

Factories never read credentials unless called by the operator publication plane.
"""
from __future__ import annotations

from typing import Any, Callable


def build_hf_api(factory: Callable[..., Any], *, endpoint: str = "") -> Any:
    """Construct a Hugging Face compatible API client without embedding tokens."""
    kwargs = {"endpoint": endpoint} if endpoint else {}
    return factory(**kwargs)


def build_s3_client(factory: Callable[..., Any], *, endpoint_url: str = "", region_name: str = "") -> Any:
    """Construct an S3-compatible client from an injected SDK factory."""
    kwargs = {}
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    if region_name:
        kwargs["region_name"] = region_name
    return factory("s3", **kwargs)
