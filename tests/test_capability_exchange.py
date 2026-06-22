import json

import httpx
import pytest

from app.kernel.capability_exchange import CapabilityExchange


def evidence(exchange, capability_id, *, task_class="coding", role="patch", verified=True, useful=True, latency=10, scope="local"):
    return exchange.prepare(
        {"capability_id": capability_id, "kind": "tool", "version": "1.0", "schema_hash": "sha256:" + "a" * 64},
        {
            "task_class": task_class, "role": role, "verified": verified, "useful": useful,
            "hidden_clean": verified, "rescued": not verified, "safe": True,
            "tokens": 20, "cost_usd": 0.001, "latency_ms": latency,
            "evidence_scope": scope,
            "prompt": "this field is intentionally ignored",
        },
    )


def test_exchange_prepare_is_allowlisted_and_hash_verified(tmp_path):
    exchange = CapabilityExchange(enabled=False, data_dir=str(tmp_path))
    item = evidence(exchange, "tool.read")

    assert item["privacy"]["allowlisted_fields_only"] is True
    assert "this field is intentionally ignored" not in json.dumps(item)
    assert item["evidence_hash"].startswith("sha256:")
    assert exchange.contribute(item)["reason"] == "dry_run"

    item["outcome"]["verified"] = False
    with pytest.raises(ValueError, match="hash mismatch"):
        exchange.contribute(item)


def test_exchange_requires_opt_in_and_approval_before_any_write(tmp_path):
    disabled = CapabilityExchange(enabled=False, data_dir=str(tmp_path / "disabled"))
    disabled_item = evidence(disabled, "tool.read")

    result = disabled.contribute(disabled_item, approved=True, dry_run=False)

    assert result["submitted"] is False
    assert result["reason"] == "capability exchange opt-in is disabled"
    assert not (tmp_path / "disabled" / "outbox.jsonl").exists()


def test_exchange_submits_opted_in_approved_evidence(tmp_path):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(202, json={"accepted": True})

    exchange = CapabilityExchange(
        enabled=True,
        endpoint="https://commons.example",
        data_dir=str(tmp_path / "enabled"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    item = evidence(exchange, "tool.read")

    result = exchange.contribute(item, approved=True, dry_run=False)

    assert result["submitted"] is True
    assert result["status_code"] == 202
    assert requests[0].url.path == "/v1/evidence"
    assert (tmp_path / "enabled" / "outbox.jsonl").exists()


def test_exchange_rankings_are_contextual_not_universal(tmp_path):
    exchange = CapabilityExchange(enabled=False, data_dir=str(tmp_path))
    rows = [
        evidence(exchange, "tool.fast", task_class="coding", role="patch", latency=5),
        evidence(exchange, "tool.fast", task_class="coding", role="patch", latency=7),
        evidence(exchange, "skill.docs", task_class="documentation", role="writer", latency=3),
    ]

    ranking = exchange.rank(rows, task_class="coding", role="patch")

    assert ranking["ranking_policy"] == "contextual_global_prior_local_posterior"
    assert ranking["count"] == 1
    assert ranking["rankings"][0]["capability_id"] == "tool.fast"
    assert ranking["rankings"][0]["sample_size"] == 2


def test_exchange_uses_global_prior_and_stronger_local_posterior(tmp_path):
    exchange = CapabilityExchange(enabled=False, data_dir=str(tmp_path))
    rows = [
        evidence(exchange, "tool.shared", verified=False, useful=False, scope="global"),
        evidence(exchange, "tool.shared", verified=False, useful=False, scope="global"),
        evidence(exchange, "tool.shared", verified=True, useful=True, scope="local"),
    ]

    ranking = exchange.rank(rows, task_class="coding", role="patch")["rankings"][0]

    assert ranking["global_samples"] == 2
    assert ranking["local_samples"] == 1
    assert ranking["score"] > 0.3


def test_exchange_rejects_exact_sensitive_fields(tmp_path):
    exchange = CapabilityExchange(enabled=False, data_dir=str(tmp_path))
    item = evidence(exchange, "tool.read")
    item["prompt"] = "leak"
    canonical = dict(item)
    canonical.pop("evidence_hash")
    canonical.pop("signature")
    # Privacy validation runs before hash validation.
    with pytest.raises(ValueError, match="forbidden evidence field"):
        exchange.contribute(item)
