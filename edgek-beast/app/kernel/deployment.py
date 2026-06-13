"""
Deployment helpers for BEAST edge gateway integrations.

This module generates LiteLLM and Nginx configuration from BEAST policy and
manages explicit, auditable prompt-cache keepalive registrations. Keepalive
network pings are opt-in and dry-run by default; this is an authorized cache
policy surface, not a hidden billing/context bypass.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import yaml


@dataclass
class KeepaliveRegistration:
    cache_id: str
    provider: str
    model: str
    cache_key_hash: str
    interval_seconds: int
    ttl_seconds: int
    ping_url: str
    enabled: bool
    authorized: bool
    dry_run: bool
    last_ping_at: float
    next_ping_at: float
    expires_at: float
    metadata: Dict[str, Any]


class DeploymentManager:
    """Generate deployment configs and manage cache keepalive state."""

    def __init__(self, policies: Optional[Dict[str, Any]] = None, db_path: Optional[str] = None):
        self.policies = policies or {}
        if db_path is None:
            db_path = Path(__file__).resolve().parents[2] / "data" / "deployment.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(str(self.db_path))

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS prompt_cache_keepalives (
                    cache_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    cache_key_hash TEXT NOT NULL,
                    interval_seconds INTEGER NOT NULL,
                    ttl_seconds INTEGER NOT NULL,
                    ping_url TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    authorized INTEGER NOT NULL,
                    dry_run INTEGER NOT NULL,
                    last_ping_at REAL NOT NULL,
                    next_ping_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_keepalives_next ON prompt_cache_keepalives(next_ping_at)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS prompt_cache_keepalive_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cache_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_keepalive_events_cache ON prompt_cache_keepalive_events(cache_id)")

    def generate_litellm_config(
        self,
        *,
        beast_base_url: str = "http://127.0.0.1:8005",
        include_mcp: bool = True,
    ) -> Dict[str, Any]:
        providers = self.policies.get("providers", {})
        model_list = []
        for name, config in providers.items():
            if not config.get("enabled", False):
                continue
            model = config.get("default_model") or name
            env_name = self._provider_env_name(name)
            litellm_model = self._litellm_model_name(name, model)
            entry = {
                "model_name": self._public_model_alias(name, model),
                "litellm_params": {
                    "model": litellm_model,
                    "api_key": f"os.environ/{env_name}",
                },
            }
            if name in {"nvidia_nim", "openrouter", "cerebras", "litellm", "huggingface", "tgi"} and config.get("base_url"):
                entry["litellm_params"]["api_base"] = config["base_url"]
            if config.get("rate_limit_rpm"):
                entry["rpm"] = int(config["rate_limit_rpm"])
            if config.get("rate_limit_tpm"):
                entry["tpm"] = int(config["rate_limit_tpm"])
            model_list.append(entry)

        config: Dict[str, Any] = {
            "model_list": model_list,
            "litellm_settings": {
                "drop_params": True,
                "set_verbose": False,
                "request_timeout": self.policies.get("meta_rules", {}).get("runtime_provider_timeout_seconds", 120),
            },
            "general_settings": {
                "master_key": "os.environ/EDGEK_LITELLM_MASTER_KEY",
                "database_url": "os.environ/EDGEK_LITELLM_DATABASE_URL",
            },
            "edgek_beast": {
                "gateway_base_url": beast_base_url,
                "governance": "BEAST remains the policy, compression, tool-laziness, and forensic layer.",
                "tool_call_interception": f"{beast_base_url.rstrip('/')}/edgek/tools/intercept",
                "required_integrations": f"{beast_base_url.rstrip('/')}/edgek/tools/integrations",
            },
        }
        if include_mcp:
            config["mcp_servers"] = self._litellm_mcp_servers()
        return config

    def generate_litellm_yaml(self, **kwargs: Any) -> str:
        return yaml.safe_dump(self.generate_litellm_config(**kwargs), sort_keys=False)

    def generate_nginx_config(
        self,
        *,
        server_name: str = "localhost",
        listen_port: int = 8080,
        beast_upstream: str = "127.0.0.1:8005",
        litellm_upstream: str = "127.0.0.1:4000",
    ) -> str:
        return f"""# Generated by EdgeK BEAST. Review before production use.
upstream edgek_beast_backend {{
    server {beast_upstream};
    keepalive 32;
}}

upstream edgek_litellm_backend {{
    server {litellm_upstream};
    keepalive 32;
}}

server {{
    listen {listen_port};
    server_name {server_name};
    client_max_body_size 64m;
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
    proxy_connect_timeout 30s;

    location /edgek/ {{
        proxy_pass http://edgek_beast_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-EdgeK-Gateway "beast";
    }}

    location /tool-calls/ {{
        rewrite ^/tool-calls/(.*)$ /edgek/tools/intercept break;
        proxy_pass http://edgek_beast_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-EdgeK-Gateway "tool-intercept";
    }}

    location /mcp/ {{
        rewrite ^/mcp/(.*)$ /edgek/mcp/$1 break;
        proxy_pass http://edgek_beast_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-EdgeK-Gateway "mcp-governed";
    }}

    location /ui {{
        proxy_pass http://edgek_beast_backend;
        proxy_set_header Host $host;
    }}

    location /v1/messages {{
        proxy_pass http://edgek_beast_backend;
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-EdgeK-Protocol "anthropic";
    }}

    location /v1/chat/completions {{
        proxy_pass http://edgek_beast_backend;
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-EdgeK-Protocol "openai";
    }}

    location ~ ^/v1(beta)?/models/.+:generateContent$ {{
        proxy_pass http://edgek_beast_backend;
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-EdgeK-Protocol "gemini";
    }}

    location /litellm/ {{
        rewrite ^/litellm/(.*)$ /$1 break;
        proxy_pass http://edgek_litellm_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-EdgeK-Gateway "litellm";
    }}
}}
"""

    def generate_tgi_llamacpp_config(
        self,
        *,
        model_id: str = "Qwen/Qwen2.5-3B-Instruct",
        listen_port: int = 3000,
        models_dir: str = "$HOME/models",
        gpu: bool = False,
        n_gpu_layers: int = 99,
        model_gguf: str = "",
    ) -> Dict[str, Any]:
        """Return documented TGI llama.cpp build/run commands."""
        build_command = (
            "docker build -t tgi-llamacpp "
            "https://github.com/huggingface/text-generation-inference.git "
            "-f Dockerfile_llamacpp"
        )
        run_parts = ["docker run"]
        if gpu:
            run_parts.append("--gpus all")
        run_parts.extend([
            f"-p {listen_port}:3000",
            '-e "HF_TOKEN=$HF_TOKEN"',
            f'-v "{models_dir}:/app/models"',
            "tgi-llamacpp",
        ])
        if gpu:
            run_parts.extend(["--n-gpu-layers", str(n_gpu_layers)])
        run_parts.extend(["--model-id", f'"{model_id}"'])
        if model_gguf:
            run_parts.extend(["--model-gguf", f'"{model_gguf}"'])
        return {
            "backend": "llamacpp",
            "model_id": model_id,
            "listen_port": listen_port,
            "base_url": f"http://127.0.0.1:{listen_port}",
            "build_command": build_command,
            "run_command": " ".join(run_parts),
            "beast_env": {
                "TGI_BASE_URL": f"http://127.0.0.1:{listen_port}",
                "TGI_BACKEND": "llamacpp",
                "HF_TOKEN": "set in environment, never commit",
            },
        }

    def register_keepalive(
        self,
        *,
        provider: str,
        model: str,
        cache_key: str,
        interval_seconds: int = 240,
        ttl_seconds: int = 1800,
        ping_url: str = "",
        enabled: bool = True,
        authorized: bool = False,
        dry_run: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
        cache_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not authorized:
            raise ValueError("Prompt-cache keepalive requires explicit authorized=true")
        if interval_seconds < 60:
            raise ValueError("interval_seconds must be >= 60")
        if ttl_seconds < interval_seconds:
            raise ValueError("ttl_seconds must be >= interval_seconds")
        now = time.time()
        registration = KeepaliveRegistration(
            cache_id=cache_id or f"cache_{uuid.uuid4().hex[:16]}",
            provider=provider,
            model=model,
            cache_key_hash=hashlib.sha256(cache_key.encode("utf-8")).hexdigest(),
            interval_seconds=int(interval_seconds),
            ttl_seconds=int(ttl_seconds),
            ping_url=ping_url,
            enabled=bool(enabled),
            authorized=True,
            dry_run=bool(dry_run),
            last_ping_at=0.0,
            next_ping_at=now + int(interval_seconds),
            expires_at=now + int(ttl_seconds),
            metadata=metadata or {},
        )
        self._store_keepalive(registration)
        self._event(registration.cache_id, provider, "registered", "ok", {
            "dry_run": registration.dry_run,
            "enabled": registration.enabled,
            "next_ping_at": registration.next_ping_at,
        })
        return asdict(registration)

    def keepalive_state(self) -> Dict[str, Any]:
        rows = self._keepalive_rows()
        return {
            "enabled": bool(self.policies.get("prompt_cache_keepalive", {}).get("enabled", False)),
            "registrations": len(rows),
            "active": sum(1 for row in rows if row["enabled"] and row["authorized"]),
            "due": sum(1 for row in rows if row["enabled"] and row["authorized"] and row["next_ping_at"] <= time.time()),
            "db": str(self.db_path),
        }

    def list_keepalives(self) -> List[Dict[str, Any]]:
        return self._keepalive_rows()

    def tick_keepalives(self, *, allow_network: bool = False, limit: int = 20) -> Dict[str, Any]:
        now = time.time()
        due = [
            row for row in self._keepalive_rows()
            if row["enabled"] and row["authorized"] and row["next_ping_at"] <= now and row["expires_at"] > now
        ][:max(1, limit)]
        events = []
        for row in due:
            status = "dry_run"
            detail: Dict[str, Any] = {"would_ping": row["ping_url"], "provider": row["provider"]}
            if allow_network and not row["dry_run"]:
                if not row["ping_url"]:
                    status = "skipped"
                    detail = {"reason": "missing ping_url"}
                else:
                    try:
                        response = httpx.post(
                            row["ping_url"],
                            json={
                                "provider": row["provider"],
                                "model": row["model"],
                                "cache_key_hash": row["cache_key_hash"],
                                "edgek_keepalive": True,
                            },
                            timeout=10.0,
                        )
                        status = "ok" if response.status_code < 400 else "http_error"
                        detail = {"status_code": response.status_code}
                    except Exception as exc:  # pragma: no cover - live network path
                        status = "error"
                        detail = {"error": str(exc)}
            self._mark_ping(row["cache_id"], row["interval_seconds"])
            self._event(row["cache_id"], row["provider"], "ping", status, detail)
            events.append({"cache_id": row["cache_id"], "status": status, "detail": detail})
        return {"processed": len(events), "events": events}

    def recent_keepalive_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT cache_id, provider, event_type, status, detail, created_at
                FROM prompt_cache_keepalive_events
                ORDER BY id DESC
                LIMIT ?
            """, (max(1, min(limit, 200)),)).fetchall()
        return [
            {
                "cache_id": row[0],
                "provider": row[1],
                "event_type": row[2],
                "status": row[3],
                "detail": json.loads(row[4] or "{}"),
                "created_at": row[5],
            }
            for row in rows
        ]

    def write_generated_files(self, output_dir: str | Path = "deploy/generated") -> Dict[str, str]:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        litellm_path = output / "litellm.config.yaml"
        nginx_path = output / "nginx.edgek.conf"
        litellm_path.write_text(self.generate_litellm_yaml(), encoding="utf-8")
        nginx_path.write_text(self.generate_nginx_config(), encoding="utf-8")
        return {"litellm_config": str(litellm_path), "nginx_config": str(nginx_path)}

    def _provider_env_name(self, provider: str) -> str:
        return {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GEMINI_API_KEY",
            "huggingface": "HF_TOKEN",
            "tgi": "HF_TOKEN",
            "nvidia_nim": "NVIDIA_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "cerebras": "CEREBRAS_API_KEY",
            "litellm": "LITELLM_API_KEY",
            "codex": "OPENAI_API_KEY",
        }.get(provider, f"{provider.upper()}_API_KEY")

    def _litellm_model_name(self, provider: str, model: str) -> str:
        if provider == "google":
            return f"gemini/{model}"
        if provider == "anthropic":
            return f"anthropic/{model}"
        if provider == "openrouter":
            return model if model.startswith("openrouter/") else f"openrouter/{model}"
        if provider == "huggingface":
            return f"huggingface/{model}"
        if provider == "tgi":
            return f"openai/{model}"
        if provider in {"nvidia_nim", "cerebras", "litellm"}:
            return f"openai/{model}"
        return model

    def _public_model_alias(self, provider: str, model: str) -> str:
        if provider == "google":
            return "gemini-flash"
        if provider == "nvidia_nim":
            return "nvidia-nim"
        if provider == "huggingface":
            return "huggingface"
        if provider == "tgi":
            return "tgi-llamacpp"
        if provider == "litellm":
            return f"litellm-{model}"
        return model

    def _litellm_mcp_servers(self) -> Dict[str, Any]:
        return {
            "edgek_beast": {
                "transport": "http",
                "url": "http://127.0.0.1:8005/edgek/mcp",
                "description": "BEAST-governed MCP broker; individual tools remain policy gated.",
            },
            "edgek_tool_interceptor": {
                "transport": "http",
                "url": "http://127.0.0.1:8005/edgek/tools/intercept",
                "description": "Required BEAST semantic file-read and token-pruning interceptor.",
            }
        }

    def _store_keepalive(self, registration: KeepaliveRegistration):
        now = time.time()
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO prompt_cache_keepalives
                (cache_id, provider, model, cache_key_hash, interval_seconds, ttl_seconds,
                 ping_url, enabled, authorized, dry_run, last_ping_at, next_ping_at,
                 expires_at, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                registration.cache_id,
                registration.provider,
                registration.model,
                registration.cache_key_hash,
                registration.interval_seconds,
                registration.ttl_seconds,
                registration.ping_url,
                1 if registration.enabled else 0,
                1 if registration.authorized else 0,
                1 if registration.dry_run else 0,
                registration.last_ping_at,
                registration.next_ping_at,
                registration.expires_at,
                json.dumps(registration.metadata, sort_keys=True),
                now,
                now,
            ))

    def _keepalive_rows(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT cache_id, provider, model, cache_key_hash, interval_seconds,
                       ttl_seconds, ping_url, enabled, authorized, dry_run,
                       last_ping_at, next_ping_at, expires_at, metadata
                FROM prompt_cache_keepalives
                ORDER BY next_ping_at ASC
            """).fetchall()
        return [
            {
                "cache_id": row[0],
                "provider": row[1],
                "model": row[2],
                "cache_key_hash": row[3],
                "interval_seconds": row[4],
                "ttl_seconds": row[5],
                "ping_url": row[6],
                "enabled": bool(row[7]),
                "authorized": bool(row[8]),
                "dry_run": bool(row[9]),
                "last_ping_at": row[10],
                "next_ping_at": row[11],
                "expires_at": row[12],
                "metadata": json.loads(row[13] or "{}"),
            }
            for row in rows
        ]

    def _mark_ping(self, cache_id: str, interval_seconds: int):
        now = time.time()
        with self._connect() as conn:
            conn.execute("""
                UPDATE prompt_cache_keepalives
                SET last_ping_at = ?, next_ping_at = ?, updated_at = ?
                WHERE cache_id = ?
            """, (now, now + interval_seconds, now, cache_id))

    def _event(self, cache_id: str, provider: str, event_type: str, status: str, detail: Dict[str, Any]):
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO prompt_cache_keepalive_events
                (cache_id, provider, event_type, status, detail, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (cache_id, provider, event_type, status, json.dumps(detail, sort_keys=True), time.time()))
