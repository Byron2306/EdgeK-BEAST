# Physical Crystal Fabric — Swarm specialist runner, cascade-gated admit, PSI shrink, RTK cascade compression

Date: 2026-11-16. Follows the Compute Governor spine. Papers: IEI v0.9 §3.4 (cascades), §4 (governor
position), Table 3 (false suppression redline), §7.12.1/Table 15 (specialist band 0.80–0.95 proposes only).

## Root cause: why the local Ollama swarm runners are broken (read-only survey)

Live probe `curl 127.0.0.1:11434/api/tags` (2026-11-16): server up; models `qwen3:4b`, `granite3.2:2b`,
`granite3.3:2b`. No `beast-specialist-*` model exists.

1. **No runner executes anything.** `SwarmKernel` (app/kernel/networking/swarm.py) is a deterministic role
   state machine: Hermes can reach `MODEL_RESIDUAL_REQUIRED` / route `ollama_residual`, but `run()` never
   dispatches it, every role reports `model_call_executed: False`, and `SwarmKernelServices.residual_solver`
   is never bound by `from_runtime()` or by main.py. The "swarm runner" is plan-only.
2. **The specialist nominator can never match.** `AdaptiveDispatcher._find_best_lattice_node` expects lattice
   nodes with `node_id`, `task_class`, `capability_contract_digest` and five path fingerprints. The real
   artifact (`benchmarks/results/crystal_to_adapter_distillation/capability_lattice_latest.json`, 16 nodes)
   carries `task_family`, `fingerprint_hashes`, labels — no node id, no contract digest, no fingerprints, and
   no producer anywhere in app/ emits `capability_contract_digest`. So `route()` always returns None.
3. **The nominated model does not exist.** Even on a match it nominates `ollama://beast-specialist-<node_id>`;
   no such model is installed (the distiller only writes Modelfiles; nothing runs `ollama create`).
4. **Nothing consumes the proposal.** Before D9 the proposal leaked into a provider rewrite (closed in D9);
   after D9 nothing dispatches a `local_specialist_adapter` proposal, so it always falls back to the provider.

## Fix

- `app/kernel/agents/swarm_specialist.py`: `OllamaSwarmRunner` (native `/api/tags`, `/api/generate`,
  `think:false` for qwen3, `<think>` stripped), model resolution (exact specialist model if installed, else an
  explicitly configured/installed base model, recorded as a substitution; else no dispatch), and
  `SwarmSpecialistDispatch`: governor `admit` (strict ADMIT) → runner → Quality Cascade gate → Output
  Governor gate → verifiers. Any failure discards the output (provider fallback) and records negative evidence.
  Output is marked `proposal_only`, never `execution_granted`. Default-off flag `BEAST_SWARM_SPECIALIST`.
- Executor: after cheaper rungs (deterministic, reuse, durable replay, crystal), before runtime admission.
- `AdaptiveDispatcher`: normalise the real lattice schema (node id / task family) while keeping the contract
  digest + fingerprint requirement (fail-closed).
- `SwarmKernelServices.specialist_runner` bound in `from_runtime()` (no network at construction).
- Quality Cascade → admit: `QualityCascade.run` attests its own reports (digest file under
  `.beast/governor/`); `InferenceComputeInterceptor.begin` passes `cascade_admission_input(metadata)` into
  `evaluate()`. Only attested, fresh reports count; client-claimed `{"passed": true}` is ignored. Operator skip
  is server-side only (`BEAST_QUALITY_CASCADE_SKIP=<reason>`).
- PSI: `RuntimeGovernor.begin_execution` never refuses on pressure alone; it returns `pressure_factor` from
  the governor's single pressure policy and the executor shrinks `max_tokens` by it.
- RTK for cascade output: `cascade_output_compressor.compress_cascade_output` uses the real `rtk` binary
  (`rtk pipe --filter <kind>` / `rtk log`) when present, else the native stand-in; exact-preservation
  post-check re-appends any failing-assertion, `file:line`, traceback or edit-target line the compressor
  dropped. Raw stdout/stderr tails are kept for parsers. sqz stays reserved for Perceive transcript compaction.

## Install commands (documented only — not run)

- RTK (Rust Token Killer, rtk-ai/rtk): `curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/master/install.sh | sh`
  (installs to ~/.local/bin) or `brew install rtk-ai/tap/rtk`, or
  `cargo install --git https://github.com/rtk-ai/rtk --branch master rtk` (plain `cargo install rtk` may install
  the unrelated Rust Type Kit). Verify with `rtk --version` and `rtk gain`.
- sqz: verify the upstream project/binary name with Byron before installing; BEAST only probes `shutil.which("sqz")`.

## Tasks
1. Plan + ledger. 2. RED tests (mocked Ollama; optional live smoke). 3. GREEN specialist runner + executor
wiring. 4. Cascade→admit. 5. PSI shrink. 6. RTK cascade compression. 7. Verification.
