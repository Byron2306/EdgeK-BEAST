# BEAST Coding Agent Interview Demo

Status: rehearsal harness for the live Phase 12 acceptance path.

## What this demo proves

This is not a direct Python planner harness. It drives the live BEAST AgentRun HTTP ingress and uses the same governed coding path the IDE uses.

The demonstration is intentionally small and deterministic enough for the local `qwen2.5-coder:1.5b` canary. BEAST, not the model, owns the mechanical lifecycle:

```text
workspace index
  -> isolated worktree bind
  -> failing baseline verification
  -> dependency/exact-source acquisition
  -> local Qwen semantic reasoning
  -> bounded mutation
  -> fresh verification
  -> SourcePlan handoff
  -> stop before promotion
```

The operator workspace must remain clean and unchanged throughout.

## Interview task

The fixture contains:

- `pricing.py` with an existing `percentage_discount()` helper.
- `calculator.py` with a bug: it subtracts the percentage value as if it were currency.
- `test_invoice.py` with one failing percentage-discount test and one passing zero-discount test.

The requested repair is intentionally semantic but bounded: discover the existing helper and use it rather than duplicate percentage arithmetic.

## Rehearsal setup

Use the integration checkout, not the dirty normal Termux runtime checkout:

```bash
cd ~/EdgeK-BEAST-phase12-live

git fetch origin agent/beast-phase12-termux-live-integration
git reset --hard origin/agent/beast-phase12-termux-live-integration
```

The normal BEAST runtime should be started from the integration checkout for the rehearsal so the gateway is serving the exact code being demonstrated.

If an older BEAST runtime is already bound to the ports, stop it first using the repository's normal Termux shutdown command, then start:

```bash
cd ~/EdgeK-BEAST-phase12-live

LD_PRELOAD="$PREFIX/lib/libpython3.14.so" \
PYTHONNOUSERSITE=1 \
./bin/beast termux-up
```

Expected core dependencies:

- BEAST gateway reachable at `http://127.0.0.1:8101`
- Ollama reachable at `http://127.0.0.1:11434`
- `qwen2.5-coder:1.5b` installed
- no cloud provider is required

For the interview canary, do not intentionally configure a cloud fallback. The demo acceptance receipt also refuses a run if it observes a switch to the `strong-cloud` route.

## One-command demo

From a second Termux shell:

```bash
cd ~/EdgeK-BEAST-phase12-live

LD_PRELOAD="$PREFIX/lib/libpython3.14.so" \
PYTHONNOUSERSITE=1 \
PYTHONPATH="$PWD" \
~/EdgeK-BEAST/.venv/bin/python \
  scripts/demo/beast_interview_coding_agent.py \
  --json-out /tmp/beast-interview-proof.json
```

The harness creates a fresh git fixture under `/tmp`, prints the independently failing baseline, creates a real AgentSession and AgentRun, launches the typed planner through the live gateway, automatically grants only one-use approvals for bounded worktree tools, and prints the live event timeline.

It never approves promotion/final-apply.

## Acceptance receipt

A successful run ends with all of these checks green:

```text
PASS  run_completed
PASS  indexed
PASS  worktree_bound
PASS  exact_source_read
PASS  baseline_failed
PASS  bounded_mutation
PASS  fresh_verify_passed
PASS  sourceplan_ready
PASS  operator_workspace_clean
PASS  operator_workspace_unchanged
PASS  no_cloud_switch

Result: PROMOTE-CANDIDATE
Note  : demo intentionally stops before promotion/final apply.
```

`PROMOTE-CANDIDATE` means the coding run satisfied the demonstration gates. It does not automatically apply the worktree change to the operator workspace.

## Suggested interview narration

Keep the explanation shorter than the runtime:

> "The model is deliberately tiny and local. The point of BEAST is not to ask a model to orchestrate its own environment. BEAST discovers the repository, chooses and runs the baseline verifier, controls exact-source authority, isolates mutations in a worktree, verifies the result, and generates the handoff evidence. The LLM is used only for the unresolved semantic reasoning."

When the baseline fails:

> "That failure is useful. BEAST now has an observed defect rather than a prompt-level guess."

When exact reads appear:

> "Semantic indexes can suggest context, but they cannot authorize mutation. BEAST requires the exact editable bytes before a change."

When the edit verifies:

> "The model did not declare success. The verifier did."

At SourcePlan:

> "The result is still not silently pushed into my workspace. BEAST produces a governed handoff and stops at the human/policy promotion boundary."

## Interview safety net

Do not improvise against a large repository on Monday. Use the frozen fixture first.

If the live canary fails during the interview:

1. Keep the failed AgentRun visible. A governed refusal is preferable to hiding the result.
2. Explain which gate stopped it.
3. Show the prior green focused regression suite and the AgentRun event/verification evidence.
4. Do not switch to a larger/cloud model merely to manufacture a pass.

The strongest demonstration is the architecture behaving truthfully, including when it refuses to overclaim.

## Rehearsal target

Run this demo repeatedly before the interview. The target is three consecutive clean runs from fresh fixtures with the same local model and no manual code edits.

Only after that should the coding-agent demo be treated as interview-stable.
