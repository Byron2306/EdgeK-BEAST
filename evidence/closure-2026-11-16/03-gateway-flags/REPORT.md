# Step 3 — Live gateway flags for :8101 (closure 2026-11-16)

**8101 was NOT restarted.** It is still pid 1068209 (started Sun Nov 15 22:31:55 SAST from a terminal, `.venv/bin/python -m uvicorn app.main:app --port 8101`).
It runs pre-closure code with none of the flags set, which is why its /proxy/health still says :8000.

## Artifacts (`deploy/closure-2026-11-16/`)
- `beast-gateway.env`:
  - flags: `BEAST_GOVERNED_INTERCEPTION=1`, `BEAST_CAPABILITY_ROUTER=1`, `BEAST_PROCESS_LIFECYCLE=1`, `BEAST_GPU_SCHEDULER=1`;
  - `TGI_BASE_URL=http://127.0.0.1:8090`, `BEAST_GATEWAY_PORT=8101`, `BEAST_PUBLIC_BASE_URL=http://127.0.0.1:8101`;
  - no keys (BEAST still loads keys from its own store).
- `beast-gateway.service`: a systemd **user** unit that runs the same uvicorn command on 127.0.0.1:8101 with that EnvironmentFile, `Restart=on-failure`.
- `agents.env`: base URLs for agents and IDEs (no keys):
  - `OPENAI_BASE_URL` / `OPENAI_API_BASE=http://127.0.0.1:8101/proxy/v1`;
  - `ANTHROPIC_BASE_URL=http://127.0.0.1:8101/proxy/anthropic`;
  - `GOOGLE_GEMINI_BASE_URL=http://127.0.0.1:8101/proxy/gemini`;
  - `BEAST_GATEWAY=` / `BEAST_DESKTOP_GATEWAY=http://127.0.0.1:8101`.

## Verification on my own test port (8199, now stopped)
- I started a gateway on 127.0.0.1:8199 with the three flags on and isolated state (BEAST_STATE_ROOT, durable dir and evidence path in /tmp), then killed it.
- A request through `/proxy/v1/chat/completions` carrying `metadata.governed_schema` was **accepted by the governed path**
  (`proxy-governed-response.json`):
  - 1 call to NIM nemotron-3.5-lightning-30b-a3b, `openai_json_schema` dialect, 1.1 s, $0;
  - governor receipt present;
  - ranking had TGI second and GPU-Ollama excluded (GPU scheduler).
- Caveat: the governed hook only engages when a request carries `metadata.governed_schema`. Other requests take the existing proxy path.
- Side effect: that call wrote real (not synthetic) outcomes into `.beast/capability_scorecard.json`.

## Commands Byron must run (pick one)
**A. One-off relaunch from a terminal (same shape as today):**
```
kill -TERM 1068209        # the current terminal-launched gateway (BEAST-owned, yours to stop)
cd ~/GitHub/EdgeK-BEAST
set -a; . deploy/closure-2026-11-16/beast-gateway.env; set +a
nohup .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8101 > .beast/gateway-8101.log 2>&1 &
curl -s http://127.0.0.1:8101/proxy/health      # should now advertise :8101 and governed_interception on
```
**B. Persistent user unit (recommended):**
```
mkdir -p ~/.config/systemd/user
cp ~/GitHub/EdgeK-BEAST/deploy/closure-2026-11-16/beast-gateway.service ~/.config/systemd/user/
kill -TERM 1068209
systemctl --user daemon-reload && systemctl --user enable --now beast-gateway
systemctl --user status beast-gateway --no-pager; curl -s http://127.0.0.1:8101/proxy/health
```
Rollback: `systemctl --user disable --now beast-gateway`, then start uvicorn without the env file (flags default off).

## Pointing the IDE and agents at /proxy
- Shell agents (Codex/OpenAI SDK, Claude Code, Gemini CLI, aider, …): `set -a; . ~/GitHub/EdgeK-BEAST/deploy/closure-2026-11-16/agents.env; set +a`
  before launching. Or add that line to `~/.bashrc` / `~/.profile`.
- VS Code / BEAST IDE extension: the setting `edgekBeast.proxyUrl` defaults to `http://127.0.0.1:8000`. Set it to `http://127.0.0.1:8101`
  (Settings → EdgeK Beast → Proxy Url, or `"edgekBeast.proxyUrl": "http://127.0.0.1:8101"` in settings.json). I did not change it.
- To get governed (schema-forced and verified) handling, callers add `metadata.governed_schema` to the request. Everything else is
  proxied and receipted as before.

## Files changed for this step
app/proxy/server.py (proxy health base URL; backup kept), app/kernel/compute/governed_client.py (GPU-scheduler candidate filter;
backup kept), app/kernel/compute/gpu_scheduler.py (new), deploy/closure-2026-11-16/* (new).
