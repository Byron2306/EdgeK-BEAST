import asyncio
import importlib

from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.proxy.server import _governed_openai_sse, _governed_openai_sse_live
from app.kernel.compute.perceive import EdgeKIR, ProviderType
from app.kernel.governance.reason import GovernanceDecision, GovernanceResult
from app.kernel.execution.execute import Executor


def test_governed_sse_preserves_openai_frames():
    response = JSONResponse({
        "id": "cmpl-1", "model": "model-1",
        "choices": [{"message": {"content": "governed output"}, "finish_reason": "stop"}],
    })

    async def collect():
        return [item async for item in _governed_openai_sse(response)]

    frames = asyncio.run(collect())
    assert '"content":"governed output"' in frames[0]
    assert '"finish_reason":"stop"' in frames[-2]
    assert frames[-1] == "data: [DONE]\n\n"


def test_governed_live_sse_emits_status_before_completed_response():
    async def delayed_response():
        await asyncio.sleep(0.01)
        return JSONResponse({
            "id": "cmpl-live", "model": "model-1",
            "choices": [{"message": {"content": "governed output"}, "finish_reason": "stop"}],
        })

    async def collect():
        stream = _governed_openai_sse_live(delayed_response(), provider="nvidia_nim")
        first = await anext(stream)
        rest = [item async for item in stream]
        return first, rest

    first, rest = asyncio.run(collect())
    assert first.startswith("event: edgek_status\n")
    assert '"provider":"nvidia_nim"' in first
    assert any('"content":"governed output"' in frame for frame in rest)


def test_executor_relays_structured_provider_deltas_before_final_response():
    async def upstream(_provider_type, _ir):
        yield {"choices": [{"delta": {"content": '{"kind":"beast.'}}]}
        yield {"choices": [{"delta": {"content": 'action_intent.v1"}'}, "finish_reason": "stop"}]}

    async def run():
        executor = Executor()
        executor._route_to_provider_stream = upstream
        received = []

        async def receive(text):
            received.append(text)

        ir = EdgeKIR(
            messages=[{"role": "user", "content": "Return Action IR"}],
            model="nvidia/nemotron-3-super-120b-a12b",
            stream=True,
            metadata={"edgek_provider": "nvidia_nim", "edgek_live_token_callback": receive},
        )
        response = await executor._route_to_provider_with_live_relay(ProviderType.OPENAI_COMPATIBLE, ir)
        return received, response

    received, response = asyncio.run(run())
    assert received == ['{"kind":"beast.', 'action_intent.v1"}']
    assert response["choices"][0]["message"]["content"] == "".join(received)
    assert response["edgek_live_token_relay"] is True


def test_live_token_callback_is_execution_only_not_crystallized(monkeypatch):
    from app.adapters import huggingface_adapter as adapter

    captured = {}

    async def execute(ir, governance_result):
      captured["execute_metadata"] = dict(ir.metadata)
      captured["governance_metadata_after_execute"] = dict((governance_result.modified_ir or ir).metadata)
      return {"choices": [{"message": {"content": "ok"}}]}

    async def crystallize(**kwargs):
      captured["crystallize_ir_metadata"] = dict(kwargs["ir"].metadata)
      captured["crystallize_governance_metadata"] = dict(kwargs["governance_result"].modified_ir.metadata)

    monkeypatch.setattr(adapter.executor, "execute", execute)
    monkeypatch.setattr(adapter.crystallizer, "crystallize", crystallize)
    monkeypatch.setattr(adapter.reasoner, "record_usage", lambda *_args, **_kwargs: None)
    modified = EdgeKIR(messages=[{"role": "user", "content": "hi"}], model="m", stream=True, metadata={"provider": "nvidia_nim"})
    monkeypatch.setattr(adapter.reasoner, "reason", lambda _ir, _session_id: GovernanceResult(
        decision=GovernanceDecision.MODIFY,
        modified_ir=modified,
        reason="ok",
        policies_applied=[],
    ))

    async def receive(_text):
      return None

    asyncio.run(adapter._run_prec({"model": "m", "messages": [{"role": "user", "content": "hi"}], "stream": True}, "nvidia_nim", stream_callback=receive))
    assert callable(captured["execute_metadata"]["edgek_live_token_callback"])
    assert "edgek_live_token_callback" not in captured["governance_metadata_after_execute"]
    assert "edgek_live_token_callback" not in captured["crystallize_ir_metadata"]
    assert "edgek_live_token_callback" not in captured["crystallize_governance_metadata"]


def test_mcp_execution_attaches_interception_after_broker_authorization(monkeypatch):
    main = importlib.import_module("app.main")
    calls = []

    class Broker:
        def execute(self, payload, workspace_root):
            calls.append((payload, workspace_root))
            return {"executed": False, "decision": "deny"}

    class Interceptor:
        def intercept(self, payload, workspace_root):
            assert calls  # broker runs first: denied calls cannot trigger a read first
            return {"intercepted": False, "interception": {"intent": "unsupported"}, "evidence_record": {"id": "ev-1"}}

    class Lifecycle:
        def record_artifact_lifecycle(self, **_kwargs):
            return {"status": "recorded"}

    monkeypatch.setattr(main, "mcp_broker", Broker())
    monkeypatch.setattr(main, "tool_call_interceptor", Interceptor())
    monkeypatch.setattr(main, "prec_lifecycle", Lifecycle())
    monkeypatch.setattr(main, "_prec_summary", lambda value: value)
    result = asyncio.run(main.edgek_mcp_execute({"tool_name": "read_file", "target": "README.md"}))
    assert result["tool_interception"]["evidence_record"]["id"] == "ev-1"
    assert result["prec_lifecycle"]["status"] == "recorded"


def test_governed_gateway_ingress_is_automatically_intercepted():
    main = importlib.import_module("app.main")

    async def run():
        transport = ASGITransport(app=main.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/v1/models")

    response = asyncio.run(run())
    assert response.status_code == 200
    assert response.headers["X-EdgeK-Interception"] == "recorded"
