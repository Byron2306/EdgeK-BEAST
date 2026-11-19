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

## RTK and SQZ diagnostic ablation

`--experiment diagnostic-compression` runs three arms per shuffled task/repeat
block: closeout only (raw diagnostics), closeout + RTK, and closeout + SQZ.
RepoRelay and the default integration suite stay off. The fixed public verifier
runs once in the bound worktree before the agent edits, generating a real
failure with deliberately repeated output and two similar but distinct diagnostic
markers. The objective, fixture, verifier, and held-out checks are identical
across arms. This is an exposure-controlled synthetic pilot, not a replay of
the navigation matrix or a claim about ordinary diagnostic distributions.

Only failed verification stdout/stderr are candidates. Source reads, test exit
codes, raw tool receipts, and pass criteria are unchanged. The harness retains
exact failure lines and falls back to raw on failed fidelity, no byte reduction,
or if the rendered prompt clips evidence. The per-prompt event binds raw and
sent hashes and bytes. The live provider receipt records the exact user-message
hash and serialized request-body size at the transport boundary. Join them to
distinguish rendered savings from payloads actually submitted to the adapter.
Adapter invocations, parsed responses, and provider-reported token usage are
different observations. Unknown usage is never imputed. Compare verification,
NIM attempts, input/output tokens and wall time, including failed trials, before
claiming an end-to-end win.

Default `--compression-backend native` measures BEAST's named stand-ins.
`--compression-backend upstream` requires both version-identified binaries
before any live requests and records their hashes and versions. If either
upstream tool fails to produce an admissible result, that field stays raw.
Do not pool upstream and native runs or credit an upstream result from native
controls. First check actual provider delivery counts per arm. Zero deliveries
mean the corresponding arm did not test a delivered transform.

```bash
run_dir=$(mktemp -d "$HOME/beast-output-compression.XXXXXX")
python -m scripts.proof.run_coder_efficiency_matrix \
  --experiment diagnostic-compression --out "$run_dir/controls"
(cd "$run_dir/controls" && sha256sum -c SHA256SUMS)

# Optional first live pilot, after verifying the controls.
python -m scripts.proof.run_coder_efficiency_matrix \
  --experiment diagnostic-compression --provider nim \
  --seed 4319 --repeats 1 --max-turns 8 --request-cap 72 \
  --out "$run_dir/live"
(cd "$run_dir/live" && sha256sum -c SHA256SUMS)
```

### Live provider rejection guard

The runner seals a partial batch and exits with status 3 when two consecutive
trials from different arms hit the same first-turn HTTP 4xx rejection, before
any tool starts. It fingerprints bounded, redacted provider error details.
It saves the two attempted trials and marks all unstarted cells `not_run`
with `verified: null`. Those cells are excluded from arm outcome denominators
and paired contrasts. The checksum manifest still covers the plan, the recorded
attempts, the summary, and the provider/event receipts that actually exist.
Read the top-level `batch` record to distinguish a sealed partial batch from a
fully executed plan. Ordinary coding failures, unrelated errors, and rejections
after tools have started do not trigger this guard.

## LongCodeZip-style source-context ablation

`--experiment source-compression` pairs full source packets with BEAST-native
LongCodeZip-style AST projection. Both arms retain deterministic closeout and
receive the exact same editable file and nominated dependency paths, once on the
first post-bind prompt. Only support-file bodies can be stubbed. RepoRelay,
RTK, SQZ and other integrations are off. A failed fidelity check falls back
to the raw file. The nominal dependency budget ratio is 0.55, not a hard byte
ceiling. It is subordinate to the compressor's fidelity constraints.

The three synthetic tasks cover regional tariffs, profile-specific labels,
and channel-specific retry indexing. The public and independent tests must
fail before editing, pass after editing, and only the target file may change.
Receipt data joins the exact user-message hash at the provider boundary.
Check `source_packet_provider_compressed_deliveries`, rereads, request counts,
provider usage, and verified outcomes. A smaller rendered packet on its own
does not demonstrate fewer tokens or equivalent model performance.

```bash
run_dir=$(mktemp -d "$HOME/beast-longcodezip.XXXXXX")
python -m scripts.proof.run_coder_efficiency_matrix \
  --experiment source-compression --out "$run_dir/controls"
(cd "$run_dir/controls" && sha256sum -c SHA256SUMS)
# Six live trials, at most 48 attempts; set NVIDIA_API_KEY first.
python -m scripts.proof.run_coder_efficiency_matrix \
  --experiment source-compression --provider nim \
  --seed 4321 --repeats 1 --max-turns 8 --request-cap 48 --out "$run_dir/live"
(cd "$run_dir/live" && sha256sum -c SHA256SUMS)
```

See [the ablation and evidence roadmap](BEAST_ABLATION_ROADMAP.md) for the later
retrieval, transport, recovery, and crystal comparison lanes.

### Prebound comparison

The original `source-compression` mode remains unchanged. The separate
`source-compression-prebound` experiment uses the same fixtures, compressor,
two arms, and deterministic closeout, but binds a fresh worktree mechanically
before the first model decision. Both arms receive the same paths at turn 1.
Only the dependency bytes differ. No model can index or read a file before
receiving its treatment. Rereads after delivery remain available in both arms.
Neither arm lists bind as a model tool, but the actual bind still produces
a scoped approval and causal receipt. The plan records the binding policy.

Check that each arm's `source_packet_first_turn_provider_delivered` count
matches its attempted trials, and that the treatment's compressed-delivery
count is nonzero. Compare paired token, tool-read, request, and verification
deltas. Report the original model-managed-bind pilot separately. Binding is
included in elapsed time but does not consume a model request. The provider
fail-fast rule still works if the first request is rejected after mechanical
setup but before the model returns any decision.

```bash
run_dir=$(mktemp -d "$HOME/beast-longcodezip-prebound.XXXXXX")
python -m scripts.proof.run_coder_efficiency_matrix \
  --experiment source-compression-prebound --seed 4322 --out "$run_dir/controls"
(cd "$run_dir/controls" && sha256sum -c SHA256SUMS)
# Requires NVIDIA_API_KEY. 30 live trials, at most 240 adapter requests.
python -m scripts.proof.run_coder_efficiency_matrix \
  --experiment source-compression-prebound --provider nim --seed 4322 \
  --repeats 5 --max-turns 8 --request-cap 240 --out "$run_dir/live"
(cd "$run_dir/live" && sha256sum -c SHA256SUMS)
```

## Worktree navigation

Use `--experiment worktree-navigation` to run prebound file-list, symbol
outline, and symbol-plus-dependency arms. These are full-source coding runs
with real BEAST index hints only. Closeout and source reads are unchanged.
The initial hint does not replace source bodies. The provider-facing packet
metrics reuse the `source_packet_*` receipt fields. There are separate paired
comparisons against the file list and from symbols to graph. The no-cloud
controls use the default scripted provider. The first live block across all
three task families requires `--request-cap 72` at eight turns and one repeat.

## Held-out navigation on upstream package source

`--experiment real-repo-navigation` keeps the graph and file-list arms only.
It uses the Python source packages and licenses from two external pinned Git
commits, with one controlled seeded regression each. The upstream package
code is real, but these are not historical issue resolutions, whole-repository
benchmarks, or tasks guaranteed unseen in training. These tasks are held out
from BEAST's earlier synthetic navigation experiments.

| Fixture | Pin | Seeded behavior regression |
| --- | --- | --- |
| [packaging](https://github.com/pypa/packaging) | `d8e3b31b734926ebbcaff654279f6855a73e052f` (24.2) | Periods dropped from project-name normalization |
| [ItsDangerous](https://github.com/pallets/itsdangerous) | `096c8d42545d3b68ea21a4f890fb2b2d8979c0bd` (2.2.0) | Compact JSON escapes Unicode by default |

Pass `--repo-fixtures` pointing at a parent containing Git directories named
`packaging` and `itsdangerous`. The harness reads only Python blobs from the
pinned package trees and the pinned licenses. It verifies that each pristine
fixture passes its public and independent tests and that each seeded defect
fails both before any live requests. The plan records the upstream commit
and file digests. The model can edit only the one nominated implementation
file and never sees the independent checks through its worktree.

The graph arm uses paths, ranked symbols and actual local-import edges under
the same 8,000-byte packet ceiling. The file list arm can still read all the
same files. Each graph trial starts with a new index. The report separates
cold index construction and snapshot lookup against that already-built index,
both included in wall time. The lookup measurement is not a warm
end-to-end model run and does not measure cache reuse between worktrees.

One repeat across both packages is four trials with a 32-request ceiling
at eight turns. Three repeats are twelve live trials with a 96-request ceiling.
Always run scripted controls first. Keep RAG off for the paired comparison.

## Stage 1: graph lookup on demand

`--experiment graph-on-demand` compares the same first-turn file list and
standard read/closeout tools in both arms. Only the treatment also advertises
`worktree.graph_lookup`. There is no upfront graph context or indexing in
either arm. A valid lookup lazily builds one isolated index of the initial
bound worktree. Later lookups reuse it. The tool accepts an exact tracked
Python path or symbol, returns local one-hop dependency edges and a few
symbol locations (up to 1,200 bytes of result JSON), and accepts at most
three handler calls per trial. The handler refuses after any edit, instead
of returning a stale index. The regular tool receipt records its outcome.
RAG, compression, and crystal replay stay off.

The trial set reuses the pinned package-name and compact Unicode fixtures
and adds a compatible-release identity defect that crosses the Requirement
and Specifier layers. The plain package-name case is an easy counterexample
where a graph lookup need not be useful. These are seeded defects on pinned
upstream source, not historical bug resolutions. Scripted smoke checks wiring
by using lookup for the two dependency cases and skipping it for package-name.
The live treatment is free to choose. Report all trials, including no-call
ones, with lookup decisions, invocations, results, builds, request counts,
tokens, reads, and verified outcomes. No-call trials avoid graph query/build
cost, not the overhead of advertising the extra tool.

Use the same `--repo-fixtures` as upstream navigation. One scripted repeat
is six trials and three live repeats are eighteen trials. At eight turns
their live request ceiling is 144. Cold build and cumulative snapshot lookup
time are included in the graph-arm wall time and reported separately.
