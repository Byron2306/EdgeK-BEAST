import json

import pytest

from scripts.proof.run_coder_efficiency_matrix import MeasuredNIM, make_plan


@pytest.mark.parametrize("arm,closed,usage", [
    ("drain", False, 12), ("valid_only", True, None), ("native", True, None),
])
@pytest.mark.parametrize("prefix", ["", "before the action because"])
def test_same_stream_differs_only_in_stop_policy(monkeypatch, arm, closed, usage, prefix):
    action = {"decision_type": "complete", "tool_id": "", "arguments": {}}

    class Response:
        stopped = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def close(self):
            self.stopped = True

        def __iter__(self):
            if prefix:
                yield f'data: {json.dumps({"choices": [{"delta": {"content": prefix}}]})}\n'.encode()
            for obj in [{"choices": [{"delta": {"content": json.dumps(action)}}]},
                        {"usage": {"prompt_tokens": 50, "completion_tokens": 12}}]:
                yield f"data: {json.dumps(obj)}\n".encode()
            yield b"data: [DONE]\n"

    response = Response()

    def open_stream(_, request, **kwargs):
        assert json.loads(request.data)["stream_options"] == {"include_usage": True}
        return response

    monkeypatch.setattr("app.kernel.agents.nim_planner_provider._egress.urlopen", open_stream)
    provider = MeasuredNIM(key="fixture", model="fixture", stream_mode=arm)
    payload = provider._request_payload("fixture", repair="", turn=1)
    result = provider._request_stream(payload)
    assert payload["stream"] is True
    receipt, = provider.requests
    if prefix:
        closed, usage = arm == "native", (None if arm == "native" else 12)
        assert result["content"] == prefix + ("" if closed else json.dumps(action))
        assert receipt["stream_stop_reason"] == ("explanation_leakage" if closed else None)
    else:
        assert json.loads(result["content"]) == action
    assert response.stopped is closed
    assert receipt["stream_close_requested"] is closed
    assert receipt["completion_tokens"] == usage
    assert (receipt["first_schema_shape_ms"] is not None) is not bool(prefix)
    assert receipt["stream_done_seen"] is not closed


def test_stream_matrix_pairs_all_three_arms():
    rows = make_plan(("retry",), 2, 4327, experiment="stream-interception")
    assert len(rows) == 6
    assert {(r["arm"], r["stream_mode"]) for r in rows} == {
        ("drain", "drain"), ("valid_only", "valid_only"), ("native", "native")}
    assert all(r["prebind"] and r["closeout"] for r in rows)
