import json

from app.kernel.agents.ollama_planner_provider import OllamaPlannerProvider


class Decision:
    action = "reuse_answer"
    source = "test"
    decision_id = "d1"
    avoided_tokens_estimate = 42
    payload = {
        "reuse": {
            "payload": {
                "answer": json.dumps({
                    "decision_type": "tool",
                    "tool_id": "worktree.replace_exact",
                    "arguments": {"path": "app/x.py", "old": "a", "new": "b"},
                    "approval_id": "approval-from-old-run",
                    "rationale": "cached verified strategy",
                })
            }
        }
    }


class Gateway:
    def decide(self, request):
        return Decision()


def test_planner_crystal_replay_strips_prior_mutation_approval():
    provider = OllamaPlannerProvider(crystal_gateway=Gateway(), model="test")
    decision = provider._try_crystal_reuse("prompt", run={"run_id": "new-run"}, turn=1)
    assert decision is not None
    assert decision.tool_id == "worktree.replace_exact"
    assert decision.approval_id == ""
    assert provider.last_usage["pressure"]["zero_inference"] is True
