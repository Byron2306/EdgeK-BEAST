import json

import httpx

from app.kernel.otel_connector import OTLPConfig, OpenTelemetryConnector


def test_otel_connector_compiles_all_beast_evidence_as_spans():
    connector = OpenTelemetryConnector(OTLPConfig(endpoint="http://tempo:4318"))

    payload = connector.compile(
        chronicles=[{"record": {"task_id": "tsk_1", "provider": "xai", "category": "verified", "secret": "do-not-export"}}],
        route_cards=[{"route_id": "route_1", "provider": "xai", "task_class": "coding"}],
        packet_evidence=[{
            "evidence_id": "net_1", "status": "passed",
            "summary": {"mode": "af_packet", "interface": "lo", "packets": 2, "latency_ms": 3.5},
        }],
        provider_fitness=[{
            "provider": "xai", "recommended_role": "clean_patch_candidate",
            "score": 0.67, "hidden_clean_rate": 0.5,
        }],
    )
    spans = payload["resourceSpans"][0]["scopeSpans"][0]["spans"]

    assert [span["name"] for span in spans] == [
        "beast.chronicle", "beast.route_card", "beast.packet_probe", "beast.provider_fitness"
    ]
    assert len(spans[0]["traceId"]) == 32
    assert len(spans[0]["spanId"]) == 16
    task_attribute = next(item for item in spans[0]["attributes"] if item["key"] == "beast.task_id")
    assert task_attribute["value"]["stringValue"] == "tsk_1"
    assert "do-not-export" not in json.dumps(payload)
    packet_duration = int(spans[2]["endTimeUnixNano"]) - int(spans[2]["startTimeUnixNano"])
    assert packet_duration == 3_500_000


def test_otel_export_is_dry_run_and_approval_gated():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={})

    connector = OpenTelemetryConnector(
        OTLPConfig(endpoint="http://jaeger:4318"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    payload = connector.compile(chronicles=[{"task_id": "tsk_1"}])

    dry = connector.export(payload)
    unapproved = connector.export(payload, approved=False, dry_run=False)
    live = connector.export(payload, approved=True, dry_run=False)

    assert dry["exported"] is False
    assert unapproved["exported"] is False
    assert live["exported"] is True
    assert live["backend_hint"] == "jaeger"
    assert requests[0].url.path == "/v1/traces"
    assert len(requests) == 1


def test_otel_state_recognizes_grafana_tempo():
    state = OpenTelemetryConnector(OTLPConfig(endpoint="https://tempo.grafana.example/otlp")).state()

    assert state["configured"] is True
    assert state["backend_hint"] == "grafana_tempo"
    assert state["endpoint"].endswith("/v1/traces")


def test_otel_rejects_non_http_destination():
    connector = OpenTelemetryConnector(OTLPConfig(endpoint="file:///tmp/traces"))

    try:
        connector.state()
    except ValueError as exc:
        assert "absolute http(s) URL" in str(exc)
    else:
        raise AssertionError("non-http OTLP endpoint should be rejected")
