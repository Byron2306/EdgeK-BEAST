# BEAST Ollama Endpoint Wiring Fix v1

This patch fixes the canonical AgentRun Ollama path by:

1. Passing a dedicated Ollama endpoint into `OllamaPlannerProvider`.
2. Giving `BEAST_OLLAMA_BASE_URL` precedence over the generic `OLLAMA_HOST`.
3. Normalizing accidental `/v1`, `/v1/chat/completions`, and `/api/*` suffixes.
4. Reporting the exact failing URL, status, content type, and a bounded body preview.
5. Adding `--ollama-url` to the canonical closure gauntlet.

## Install

```bash
cd ~/EdgeK-BEAST
unzip -o ~/Downloads/BEAST_Ollama_Endpoint_Wiring_Fix_v1.zip -d /tmp/beast-ollama-endpoint-fix
cp -a /tmp/beast-ollama-endpoint-fix/BEAST_Ollama_Endpoint_Wiring_Fix_v1/. .
```

## Configure

```bash
export BEAST_OLLAMA_BASE_URL="http://127.0.0.1:11434"
export BEAST_OLLAMA_MODEL="qwen2.5-coder:7b"
```

Do not include `/v1`, `/api/generate`, or `/api/chat` in the configured URL. The patch will normalize them defensively, but the server origin is the canonical value.

## Verify transport

```bash
curl -sS http://127.0.0.1:11434/api/tags | jq
```

## Run tests

```bash
PYTHONPATH=. pytest -q tests/test_ollama_endpoint_wiring.py
```

## Run canonical closure

```bash
PYTHONPATH=. python scripts/proof/run_canonical_agent_ollama_closure.py \
  --ollama-url http://127.0.0.1:11434 \
  --model qwen2.5-coder:7b \
  --max-turns 24
```
