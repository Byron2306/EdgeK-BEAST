# Step 2 — Heal fixed: selective by default (closure 2026-11-16)

## Changes
- `app/kernel/execution/heal_guard.py` (new):
  - Protected ports {8101, 8131} plus `BEAST_HEAL_PROTECTED_PORTS`.
  - `pid_protection()` protects: arda/seraph processes; ollama (marked system_ollama); foreign uid; system.slice / docker / containerd /
    libpod / machine.slice cgroups; pid 1; self. `filter_killable` keeps only BEAST-spawned processes.
  - `systemd_unit_state`; `ollama_is_system_service`. When Ollama is down, heal reports the operator command and never spawns a second daemon.
  - `nginx_check(port=80)`: ok only on HTTP 200 /health. On a 404 it diagnoses `nginx_listening_without_beast_health_route` and prints the operator install command.
- `bin/beast` (backup `.before-closure-20261116`):
  - `command_heal` is now **selective by default**: it restarts only failed BEAST-owned services and never touches protected ports/pids.
  - The destructive mode needs explicit `--restart-all true` (also `--kill-address-pids true`) and reports `mode=full_restart`.
  - Defaults: `--restart-all false`, `--kill-address-pids false`, `--nginx-port 80`.
  - `start_ollama_daemon` refuses when Ollama is a system service (`system_service_not_started`).
  - **`beast ide` calls heal with `dry_run=true` only.**
  - The nginx stack check now probes :80 through heal_guard; up/start default to nginx :80.
- `app/proxy/server.py`: **/proxy/health no longer advertises :8000.** It uses `BEAST_PUBLIC_BASE_URL`, otherwise the request's own base URL.
- `app/kernel/deployment/deployment.py`: the nginx template gains `location = /health` and `location /proxy/`, and a
  `deploy/generated/nginx.edgek.80.conf` (listen 80) is generated.
- `tests/test_heal_guard.py` (new): **16/16 pass**. Covers protected ports, protected pids (arda/seraph/ollama/foreign uid/system cgroups),
  selective vs full mode, no second Ollama, nginx 200/404/down, and the proxy-health base URL.

## Live dry run (`bin/beast --agent heal --dry-run true`) → `heal-dry-run-selective.json`
- Every BEAST service is OK except nginx. Port 80 answers **404**: that is the Debian default_server, and the BEAST site isn't installed.
  (dio-local is on 127.0.0.1:8088.)
- Protected ports reported: [8101, 8131]. Ollama detected as a system service (pid 2426, `ollama.service`). Nothing would be killed.
- Only planned action: nginx `would_generate_config`, plus this operator command.

## Commands Byron must run (operator)
```
cd /home/byron/GitHub/EdgeK-BEAST
sudo install -m 644 deploy/generated/nginx.edgek.80.conf /etc/nginx/sites-available/edgek-beast \
 && sudo ln -sf /etc/nginx/sites-available/edgek-beast /etc/nginx/sites-enabled/edgek-beast \
 && sudo nginx -t && sudo systemctl reload nginx
curl -s http://127.0.0.1/health        # expect 200
```
If the Debian `default` site still wins on `server_name localhost`, also run `sudo rm /etc/nginx/sites-enabled/default` (it is only a symlink)
and reload. /proxy/health on 8101 keeps showing :8000 until 8101 runs the new code (see step 3).

## Not touched
8101, 8131, ARDA, seraph, beast-tgi, system Ollama: none were restarted, killed or spawned.
