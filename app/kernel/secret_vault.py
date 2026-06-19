"""
Local BEAST provider secret vault.

The vault is intentionally boring: import user-supplied provider tokens into a
chmod 600 env file, load them into the current process, and expose only redacted
presence/fingerprints to diagnostics. It does not put secret values into
Chronicle, workspace graph, or logs.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional


PROVIDER_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GEMINI_API_KEY",
    "huggingface": "HF_TOKEN",
    "nvidia_nim": "NVIDIA_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "cerebras": "CEREBRAS_API_KEY",
    "cohere": "COHERE_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "together": "TOGETHER_API_KEY",
    "perplexity": "PERPLEXITY_API_KEY",
    "fireworks": "FIREWORKS_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "xai": "XAI_API_KEY",
    "replicate": "REPLICATE_API_TOKEN",
    "fal": "FAL_KEY",
    "hyperbolic": "HYPERBOLIC_API_KEY",
    "novita": "NOVITA_API_KEY",
    "nscale": "NSCALE_API_KEY",
    "ovhcloud": "OVHCLOUD_API_KEY",
    "ovhcloud_app_key": "OVHCLOUD_APP_KEY",
    "ovhcloud_app_secret": "OVHCLOUD_APP_SECRET",
    "ovhcloud_consumer_key": "OVHCLOUD_CONSUMER_KEY",
    "deepinfra": "DEEPINFRA_API_KEY",
    "featherless": "FEATHERLESS_API_KEY",
    "litellm": "LITELLM_API_KEY",
}


PROVIDER_HINTS = {
    "openai": ("OPENAI", "SK-"),
    "anthropic": ("ANTHROPIC", "CLAUDE"),
    "google": ("GEMINI", "GOOGLE", "AIza"),
    "huggingface": ("HUGGINGFACE", "HF_", "hf_"),
    "nvidia_nim": ("NVIDIA", "NIM", "nvapi"),
    "openrouter": ("OPENROUTER", "sk-or-"),
    "cerebras": ("CEREBRAS",),
    "cohere": ("COHERE",),
    "groq": ("GROQ", "gsk_"),
    "mistral": ("MISTRAL",),
    "together": ("TOGETHER",),
    "perplexity": ("PERPLEXITY", "PPLX"),
    "fireworks": ("FIREWORKS",),
    "deepseek": ("DEEPSEEK",),
    "xai": ("XAI", "GROK"),
    "replicate": ("REPLICATE", "r8_"),
    "fal": ("FAL",),
    "hyperbolic": ("HYPERBOLIC",),
    "novita": ("NOVITA",),
    "nscale": ("NSCALE",),
    "ovhcloud": ("OVHCLOUD", "OVH"),
    "deepinfra": ("DEEPINFRA",),
    "featherless": ("FEATHERLESS",),
    "litellm": ("LITELLM",),
}


@dataclass
class SecretEntry:
    source_line: int
    env_name: str
    provider: str
    value: str
    source_key: str

    def redacted(self) -> Dict[str, object]:
        return {
            "source_line": self.source_line,
            "env_name": self.env_name,
            "provider": self.provider,
            "source_key": self.source_key,
            "present": bool(self.value),
            "length": len(self.value),
            "fingerprint": hashlib.sha256(self.value.encode("utf-8")).hexdigest()[:12],
        }


class SecretVault:
    """Import and load provider API keys without exposing values."""

    def __init__(self, vault_path: Optional[str] = None):
        if vault_path is None:
            vault_path = Path(__file__).resolve().parents[2] / ".beast" / "provider_secrets.env"
        self.vault_path = Path(vault_path)

    def load(self, override: bool = False) -> Dict[str, object]:
        """Load vault values into os.environ and return a redacted summary."""
        entries = self.read_env_file(self.vault_path)
        loaded = 0
        skipped = 0
        for entry in entries:
            if not override and os.environ.get(entry.env_name):
                skipped += 1
                continue
            os.environ[entry.env_name] = entry.value
            loaded += 1
        return {
            "vault_path": str(self.vault_path),
            "exists": self.vault_path.exists(),
            "loaded": loaded,
            "skipped_existing": skipped,
            "entries": [entry.redacted() for entry in entries],
            "providers": self._provider_counts(entries),
        }

    def import_file(self, source_path: str, overwrite: bool = False, load: bool = True) -> Dict[str, object]:
        """Parse a user secret file and write the normalized env vault."""
        source = Path(source_path).expanduser()
        if not source.exists():
            raise ValueError(f"Secret source not found: {source}")
        if self.vault_path.exists() and not overwrite:
            raise ValueError(f"Vault already exists: {self.vault_path}")

        entries = self.parse_secret_text(source.read_text(encoding="utf-8", errors="replace"))
        if not entries:
            raise ValueError("No importable secret entries found")

        self.vault_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# EdgeK BEAST local provider secret vault",
            "# chmod 600; do not commit; values are loaded only into local process env.",
        ]
        for entry in entries:
            lines.append(f"{entry.env_name}={self._quote_env(entry.value)}")
        self.vault_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.vault_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

        loaded = self.load(override=True) if load else {"loaded": 0, "skipped_existing": 0}
        return {
            "source_path": str(source),
            "vault_path": str(self.vault_path),
            "written": True,
            "mode": oct(self.vault_path.stat().st_mode & 0o777),
            "entries": [entry.redacted() for entry in entries],
            "providers": self._provider_counts(entries),
            "load": loaded,
        }

    def status(self) -> Dict[str, object]:
        entries = self.read_env_file(self.vault_path)
        env_entries = [
            SecretEntry(0, env_name, provider, os.environ[env_name], env_name)
            for provider, env_name in PROVIDER_ENV.items()
            if os.environ.get(env_name)
        ]
        combined = self._merge_by_env(entries + env_entries)
        return {
            "vault_path": str(self.vault_path),
            "exists": self.vault_path.exists(),
            "mode": oct(self.vault_path.stat().st_mode & 0o777) if self.vault_path.exists() else None,
            "entries": [entry.redacted() for entry in combined],
            "providers": self._provider_counts(combined),
        }

    def parse_secret_text(self, text: str) -> List[SecretEntry]:
        entries: List[SecretEntry] = []
        unknown_index = 1
        seen_names: Dict[str, int] = {}
        for line_no, raw in enumerate(text.splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            source_key, value = self._split_line(line)
            for provider, env_name, secret_value in self._expand_provider_line(source_key, value):
                if len(secret_value) < 8:
                    continue
                if provider == "unknown":
                    env_name = f"BEAST_IMPORTED_SECRET_{unknown_index:02d}"
                    unknown_index += 1
                count = seen_names.get(env_name, 0)
                seen_names[env_name] = count + 1
                if count:
                    env_name = f"{env_name}_{count + 1}"
                entries.append(SecretEntry(line_no, env_name, provider, secret_value, source_key))
        return entries

    def read_env_file(self, path: Path) -> List[SecretEntry]:
        if not path.exists():
            return []
        entries: List[SecretEntry] = []
        for line_no, raw in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip("\"'")
            provider = self._provider_for_env(key.strip())
            entries.append(SecretEntry(line_no, key.strip(), provider, value, key.strip()))
        return entries

    def _split_line(self, line: str) -> tuple[str, str]:
        match = re.match(r"(?:export\s+)?([A-Za-z_][A-Za-z0-9_\- ]{1,80})\s*[:=]\s*(.+)$", line)
        if match:
            return match.group(1).strip().replace(" ", "_").upper(), match.group(2).strip()
        return "UNSTRUCTURED", line

    def _expand_provider_line(self, source_key: str, value: str) -> List[tuple[str, str, str]]:
        value = value.strip().strip("\"'")
        label_match = re.match(r"^\s*([A-Za-z][A-Za-z0-9 _-]{1,40})\s+-\s+(.+)$", value)
        if label_match and source_key == "UNSTRUCTURED":
            label = label_match.group(1).strip().replace(" ", "_").lower()
            rest = label_match.group(2).strip()
            provider = self._provider_alias(label)
            if provider == "ovhcloud" or label.startswith("ovhcloud"):
                ovh_entries = []
                patterns = [
                    ("ovhcloud_app_key", "OVHCLOUD_APP_KEY", r"APP\s+KEY\s*-\s*([^,]+)"),
                    ("ovhcloud_app_secret", "OVHCLOUD_APP_SECRET", r"APP\s+SECRET\s*-\s*([^,]+)"),
                    ("ovhcloud_consumer_key", "OVHCLOUD_CONSUMER_KEY", r"CONSUMER\s+KEY\s*-\s*([^,]+)"),
                ]
                full = value
                for ovh_provider, env_name, pattern in patterns:
                    match = re.search(pattern, full, flags=re.IGNORECASE)
                    if match:
                        ovh_entries.append((ovh_provider, env_name, match.group(1).strip()))
                if ovh_entries:
                    return ovh_entries
            return [(provider, PROVIDER_ENV.get(provider, ""), rest)]
        provider = self._infer_provider(source_key, value)
        return [(provider, PROVIDER_ENV.get(provider, ""), value)]

    def _infer_provider(self, key: str, value: str) -> str:
        hay = f"{key} {value[:16]}".upper()
        for provider, hints in PROVIDER_HINTS.items():
            if any(hint.upper() in hay for hint in hints):
                return provider
        return self._provider_alias(key.lower())

    def _provider_alias(self, provider: str) -> str:
        aliases = {
            "hf": "huggingface",
            "hf_token": "huggingface",
            "gemini": "google",
            "google_ai_studio": "google",
            "ovh": "ovhcloud",
            "ovh_cloud": "ovhcloud",
            "ovhcloud_app_key": "ovhcloud_app_key",
            "ovhcloud_app_secret": "ovhcloud_app_secret",
            "ovhcloud_consumer_key": "ovhcloud_consumer_key",
        }
        normalized = provider.strip().replace("-", "_").replace(" ", "_").lower()
        return aliases.get(normalized, normalized if normalized in PROVIDER_ENV else "unknown")

    def _provider_for_env(self, env_name: str) -> str:
        for provider, candidate in PROVIDER_ENV.items():
            if candidate == env_name:
                return provider
        return "unknown"

    def _provider_counts(self, entries: Iterable[SecretEntry]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for entry in entries:
            counts[entry.provider] = counts.get(entry.provider, 0) + 1
        return dict(sorted(counts.items()))

    def _merge_by_env(self, entries: List[SecretEntry]) -> List[SecretEntry]:
        merged: Dict[str, SecretEntry] = {}
        for entry in entries:
            merged[entry.env_name] = entry
        return [merged[key] for key in sorted(merged)]

    def _quote_env(self, value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
