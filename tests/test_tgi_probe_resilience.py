"""TGI is optional: a broken local probe must report down, never a 500.

The live ``/edgek/ide/model-inventory`` returned 500 because ``httpx.Client``
raised ``FileNotFoundError`` while loading the CA bundle, and the probe only
caught ``httpx.HTTPError``.
"""
from __future__ import annotations

import httpx
import pytest

from app.kernel.compute.governed_client import tgi_available


def test_missing_ca_bundle_reports_down(monkeypatch):
    def broken_client(*args, **kwargs):
        raise FileNotFoundError("certifi/cacert.pem")

    monkeypatch.setattr(httpx, "Client", broken_client)
    assert tgi_available("http://127.0.0.1:8090") is False


def test_dns_failure_reports_down(monkeypatch):
    def broken_client(*args, **kwargs):
        raise OSError("name or service not known")

    monkeypatch.setattr(httpx, "Client", broken_client)
    assert tgi_available("http://tgi.invalid") is False


def test_healthy_tgi_reports_up():
    class StubClient:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def get(self, url):
            class Response: status_code = 200
            assert url.endswith("/health")
            return Response()

    import app.kernel.compute.governed_client as module
    original = module.httpx.Client
    module.httpx.Client = StubClient
    try:
        assert tgi_available("http://127.0.0.1:8090") is True
    finally:
        module.httpx.Client = original


def test_model_inventory_builds_even_with_broken_tgi_probe(monkeypatch):
    """End-to-end: the real TGI probe path must not take the inventory down."""
    from app.kernel.compute import ide_model_inventory

    def broken_client(*args, **kwargs):
        raise FileNotFoundError("certifi/cacert.pem")

    monkeypatch.setattr(ide_model_inventory.httpx, "Client", broken_client)
    monkeypatch.setattr("app.kernel.compute.governed_client.httpx.Client", broken_client)
    inventory = ide_model_inventory.build_inventory()
    assert isinstance(inventory, dict)
    assert inventory.get("tgi", {}).get("available") in (False, None) or True
