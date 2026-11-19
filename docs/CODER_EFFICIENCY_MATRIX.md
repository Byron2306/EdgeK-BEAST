# Direct coder efficiency pilot

This research runner measures two interventions around BEAST's existing direct coder without changing the production UI or enabling another planner.

| Arm | RepoRelay-style AST navigation map | Deterministic closeout |
| --- | --- | --- |
| direct | off | off |
| reporelay | on | off |
| closeout | off | on |
| both | on | on |

Each task/repeat block contains all four arms in seeded shuffled order. Every attempt starts from a fresh synthetic Git fixture. The tool surface is the same in all four arms. It admits only the fixed public test command and limits edits to the task's implementation file. When closeout is enabled, a qualifying mutation triggers that same command through the real `worktree.verify` tool and completes on a passing receipt tied to the current mutation epoch. A failed check can return to the same bounded coding loop. RepoRelay runs the native AST map, admits only a fidelity-passing result, and records whether it was handed to the actual provider interface.

## Run without a gateway

Run from the repo root with the Python venv you already use for BEAST. Node and the existing Effect dependency must be installed. For a fresh checkout only, use `npm ci --prefix desktop-ide --omit=dev --ignore-scripts` first.

```bash
run_dir="$(mktemp -d "$HOME/beast-efficiency.XXXXXX")"
python -m scripts.proof.run_coder_efficiency_matrix --out "$run_dir/controls"
(cd "$run_dir/controls" && sha256sum -c SHA256SUMS)
```

Scripted mode proves the harness, real Git mutation, receipt path, independent checker, and factor wiring. It does not establish that the navigation map helps an actual model. Three scripted fixture families produce 12 attempts.

A first live block uses one task, four arms, and at most 32 adapter attempts. Export `NVIDIA_API_KEY` without putting it in the command history. Then run:

```bash
run_dir="$(mktemp -d "$HOME/beast-efficiency-live.XXXXXX")"
python -m scripts.proof.run_coder_efficiency_matrix \
  --provider nim --tasks shipping --max-turns 8 --request-cap 32 \
  --out "$run_dir/pilot"
(cd "$run_dir/pilot" && sha256sum -c SHA256SUMS)
```

For a three-task live pilot, omit `--tasks shipping` and use `--request-cap 96`. The cap must cover the full planned matrix. This avoids silently dropping later arms when earlier arms run long. The runner uses nonstreaming NIM, no adapter retry, and a fixed output budget. This setting is held constant across arms and is not identical to the interactive UI configuration.

## Read the evidence

- `plan.json` freezes seeded order, task and verifier anchors, and configuration before any attempt.
- `attempts.jsonl` includes every attempted arm, including failures. A verified result requires a real public test receipt after mutation, an independently executed held-out check, the expected changed path only, an untouched original, and a valid event chain. Public and independent tests must fail at baseline.
- `events/` and `provider/` preserve tool receipts and live request attempts and usage where reported. Missing token usage is not zero. A provider-adapter attempt is not a vendor billing receipt. No local model is requested by this harness.
- `summary.json` compares paired cells against the direct arm and reports within-block main effects and interactions. Costs per verified task include failed attempts with observable costs. Missing measurements are left unknown rather than imputed.
- `SHA256SUMS` binds the report files. It is not a signature or a substitute for independent replication.

This is a synthetic pilot, not SWE-bench, and the held-out tests are withheld from the model's fixture, not blinded to their authors. Git worktrees are not OS sandboxes. Run live mode in a disposable environment if stronger execution isolation is needed. The runner strips inherited credentials from its child environment, retains the NIM key only in the provider object, and never prints it. Do not infer a live performance effect from the scripted control. For manuscript work, preregister independent task families and report uncertainty with task-level pairing.
