# BEAST PGEC Phase 2

This package freezes and runs the 450-observation controlled matrix described in the Proof-Governed Experiential Compilation working paper.

## Install

Copy the patch into the BEAST repository root:

```bash
unzip -o BEAST_PGEC_450_Phase2_Patch_v1.zip -d /tmp/beast-pgec-450
cp -a /tmp/beast-pgec-450/BEAST_PGEC_450_Phase2_Patch_v1/. ~/EdgeK-BEAST/
cd ~/EdgeK-BEAST
```

## Validate the frozen protocol

```bash
PYTHONPATH=. pytest -q tests/proof/test_pgec_450_protocol.py
python scripts/proof/run_pgec_450_matrix.py plan
```

## Configure Ollama

```bash
ollama serve
ollama pull qwen2.5-coder:7b
export BEAST_OLLAMA_MODEL=qwen2.5-coder:7b
export OLLAMA_OPENAI_BASE_URL=http://127.0.0.1:11434/v1
export OLLAMA_API_KEY=ollama-local
```

## Configure external routes

Set only credentials for routes you intend to execute:

```bash
export NVIDIA_API_KEY=...
export MISTRAL_API_KEY=...
export COHERE_API_KEY=...
export GROQ_API_KEY=...
```

Use the preflight command to see what is configured:

```bash
python scripts/proof/run_pgec_450_matrix.py preflight
```

## Execute in deterministic batches

A batch size of 15 corresponds to one family-provider-occurrence block across all three lanes. Thirty batches cover all 450 observations.

```bash
python scripts/proof/run_pgec_450_matrix.py run --batch-size 15 --batch-index 0
```

Resume with the next index only after the current batch writes a valid integrity manifest.

## Ollama-first pilot

The preregistration remains frozen, but an operational pilot may run only Ollama before the full matrix:

```bash
python scripts/proof/run_pgec_450_matrix.py run \
  --providers ollama \
  --batch-size 18 \
  --batch-index 0 \
  --pilot
```

Pilot outputs are marked exploratory and cannot be substituted for missing confirmatory cells.

## Analyse completed batches

```bash
python scripts/proof/analyze_pgec_450_matrix.py \
  --input benchmarks/results/pgec_450_runs \
  --output benchmarks/results/pgec_450_analysis
```
