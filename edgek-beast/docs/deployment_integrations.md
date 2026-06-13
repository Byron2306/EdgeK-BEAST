@page { size: 8.5in 11in; margin: 0.79in }
        pre { background: transparent }
        pre.western { font-family: "Liberation Mono", monospace; font-size: 10pt }
        pre.cjk { font-family: "Noto Sans Mono CJK SC", monospace; font-size: 10pt }
        pre.ctl { font-family: "Liberation Mono", monospace: 10pt }
        p { margin-bottom: 0.1in; line-height: 115%; background: transparent }

Nginx/LiteLLM gateway to intercept tool calls directly. Instead of allowing Claude Code to read full source files via local commands, the proxy routes the file read request into a local vector storage tool (like ChromaDB or a basic semantic grep). It swaps out the raw file contents for the top 3 most relevant paragraphs, effectively compressing thousands of lines of code into high-density reference bytes.
Also add in allowing tool calls to github andPostgres DB

# Deployment Integrations

BEAST can generate LiteLLM and Nginx integration files from the active policy and
can manage explicit prompt-cache keepalive registrations.

## Generate Files

```bash
PYTHONPATH=. python3 scripts/generate_deploy_configs.py --out deploy/generated
```

Outputs:

- `deploy/generated/litellm.config.yaml`
- `deploy/generated/nginx.edgek.conf`

Live endpoints:

```bash
curl -sS http://127.0.0.1:8005/edgek/deploy/litellm-config.yaml
curl -sS http://127.0.0.1:8005/edgek/deploy/nginx-config
curl -sS -X POST http://127.0.0.1:8005/edgek/deploy/write-configs
```

## LiteLLM

The generated LiteLLM config maps BEAST policy providers to LiteLLM model
entries and keeps BEAST as the governance layer:

- OpenAI
- Anthropic
- Codex-style OpenAI models
- Gemini / Google AI Studio
- NVIDIA hosted NIM
- OpenRouter
- Cerebras
- Hugging Face router
- TGI / llama.cpp sidecar
- local LiteLLM passthrough

Required environment variables are emitted as `os.environ/...` references in the
YAML so secrets are not written into the config file.

Install the optional LiteLLM package when running a local LiteLLM sidecar:

```bash
pip install -r requirements-litellm.txt
litellm --config deploy/generated/litellm.config.yaml --port 4000
```

BEAST should remain the public ingress for governed traffic:

```bash
curl -sS http://127.0.0.1:8005/litellm/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"litellm/<model-alias>","messages":[{"role":"user","content":"Say BEAST."}]}'
```

## Required Tool-Call Interception

BEAST exposes a required tool-call interception surface for Claude Code,
LiteLLM, and Nginx-routed tool calls:

```bash
curl -sS http://127.0.0.1:8005/edgek/tools/integrations
curl -sS -X POST http://127.0.0.1:8005/edgek/tools/intercept \
  -H 'Content-Type: application/json' \
  -d '{
    "tool_name": "read_file",
    "target": "app/kernel/reason.py",
    "query": "budget and circuit breaker decision",
    "limit": 3
  }'
```

Instead of returning the full source file, the interceptor returns the top
semantic snippets. It uses workspace graph vectors when available and falls
back to deterministic semantic grep when vectors are not ready.

The generated Nginx template routes `/tool-calls/*` into this interceptor:

```nginx
location /tool-calls/ {
    rewrite ^/tool-calls/(.*)$ /edgek/tools/intercept break;
    proxy_pass http://edgek_beast_backend;
}
```

LiteLLM config generation also publishes an `edgek_tool_interceptor` MCP server
entry, so tool-call traffic can enter BEAST before raw bytes reach a model.

Required integration readiness:

- `semantic_tool_interceptor`: local BEAST semantic grep/vector backend.
- `github`: requires `GITHUB_TOKEN`.
- `postgres`: requires `POSTGRES_DSN` and `pip install -r requirements-integrations.txt`.
- `rtk`: requires `rtk` binary on `PATH`.
- `sqz`: requires `sqz` binary on `PATH`.
- `longcodezip`: requires `longcodezip` binary on `PATH`.
- `reporelay`: requires `reporelay` binary on `PATH`.

Token pruning and code filtering enter through:

```bash
curl -sS -X POST http://127.0.0.1:8005/edgek/compression/prune \
  -H 'Content-Type: application/json' \
  -d '{"algorithm":"sqz","text":"...large tool output or source payload..."}'
```

If a required compressor binary is unavailable, the endpoint reports the
`edgek_builtin_prune` backend. The integration is still required and visible as
not-ready in `/edgek/tools/integrations` until the native tool is installed.

## Ollama Scout

BEAST can use Ollama as a local scout/ranker, not as an unrestricted agent.
BEAST retrieves exact context and exposes only a compact packet:

```bash
curl -sS http://127.0.0.1:8005/edgek/ollama/status
curl -sS -X POST http://127.0.0.1:8005/edgek/ollama/packet \
  -H 'Content-Type: application/json' \
  -d '{"task":"Find why login fails after token refresh"}'
curl -sS -X POST http://127.0.0.1:8005/edgek/ollama/scout \
  -H 'Content-Type: application/json' \
  -d '{"task":"Find why login fails after token refresh","use_ollama":true}'
```

The packet includes:

- `retrieved_chunks`: semantic/workspace graph matches.
- `exact_context`: hashed excerpts suitable for cloud handoff.
- `tool_menu`: 3-5 likely tools rather than the entire tool registry.
- `postgres_schema`: local read-only schema summary when available.
- `github_context`: compact authenticated GitHub availability/refs.
- `local_analysis`: structured task/risk/privacy/tool decision.

Ollama is expected to classify, rank, summarize, and build handoff decisions.
BEAST remains responsible for deterministic parsing, policy, execution,
approvals, audit, and cloud escalation.

## Hugging Face, TGI, and llama.cpp

Hugging Face router requests enter through:

```bash
curl -sS http://127.0.0.1:8005/hf/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"hf/openai/gpt-oss-120b","messages":[{"role":"user","content":"Say BEAST."}],"max_tokens":32}'
```

TGI requests enter through:

```bash
curl -sS http://127.0.0.1:8005/tgi/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"tgi/Qwen/Qwen2.5-3B-Instruct","messages":[{"role":"user","content":"Say BEAST."}],"max_tokens":32}'
```

Generate the documented TGI llama.cpp launch plan:

```bash
curl -sS http://127.0.0.1:8005/edgek/deploy/tgi-llamacpp
```

The generated Docker commands follow Hugging Face's TGI llama.cpp backend
pattern: build `Dockerfile_llamacpp`, run the container on port `3000`, pass
`HF_TOKEN` via the environment, and optionally add GPU layers.

## Nginx

The generated Nginx config routes protocol ingress to BEAST:

- `/v1/messages`
- `/v1/chat/completions`
- `/v1beta/models/{model}:generateContent`
- `/v1/models/{model}:generateContent`
- `/edgek/*`
- `/ui`

It also exposes `/litellm/*` as an optional LiteLLM upstream path.

## Prompt-Cache Keepalive

Keepalives are explicit, authorized, and dry-run by default.

Register:

```bash
curl -sS -X POST http://127.0.0.1:8005/edgek/prompt-cache/keepalives \
  -H 'Content-Type: application/json' \
  -d '{
    "provider": "google",
    "model": "gemini-2.5-flash",
    "cache_key": "stable-authorized-prefix",
    "interval_seconds": 240,
    "ttl_seconds": 1800,
    "authorized": true,
    "dry_run": true
  }'
```

Tick due registrations:

```bash
curl -sS -X POST http://127.0.0.1:8005/edgek/prompt-cache/tick \
  -H 'Content-Type: application/json' \
  -d '{"allow_network": false}'
```

Network pings require both:

- registration has `"dry_run": false`
- tick call has `"allow_network": true`

This keeps the feature an auditable cache policy, not an invisible billing or
context-window bypass.

## Additional Integrations

The Nginx/LiteLLM gateway also supports:

- **GitHub Tool Calls**: Allow tool calls to interact with GitHub API for repository operations.
- **Postgres DB Tool Calls**: Enable tool calls to query and modify PostgreSQL databases.
- **RTK (Rust Token Killer)**: Integrated for efficient token pruning in Rust-based workflows.
- **sqz**: Compression tool for reducing prompt size.
- **LongCodeZip**: Handles long code snippets by compressing and referencing.
- **RepoRelay**: Facilitates repository-level context relaying across tool calls.
- **Token Pruning**: Automatic removal of less relevant tokens to stay within context limits.
- **Perplexity Code Filtering**: Filters code based on perplexity scores to retain high-quality, relevant snippets.

These integrations enhance the edgek beast gateway by providing specialized tools for code handling, compression, and external service interactions while maintaining the gateway's role as a governance layer.
