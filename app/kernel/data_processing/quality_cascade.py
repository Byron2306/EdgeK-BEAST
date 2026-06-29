"""
EdgeK BEAST Quality Cascade.

Reusable local checks that route cards can orchestrate before model escalation.
"""

import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.kernel.storage.evidence_envelope import EvidenceEnvelopeFactory


PROVIDER_ENV_VARS = {
    "openai": ["OPENAI_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    "google": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "huggingface": ["HF_TOKEN", "HUGGINGFACE_API_KEY"],
    "tgi": ["TGI_BASE_URL"],
    "litellm": ["LITELLM_API_KEY", "LITELLM_BASE_URL"],
    "nvidia_nim": ["NVIDIA_API_KEY"],
    "openrouter": ["OPENROUTER_API_KEY"],
    "cerebras": ["CEREBRAS_API_KEY"],
    "cohere": ["COHERE_API_KEY"],
    "groq": ["GROQ_API_KEY"],
    "mistral": ["MISTRAL_API_KEY"],
    "together": ["TOGETHER_API_KEY"],
    "perplexity": ["PERPLEXITY_API_KEY"],
    "fireworks": ["FIREWORKS_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY"],
    "xai": ["XAI_API_KEY"],
    "replicate": ["REPLICATE_API_TOKEN"],
    "fal": ["FAL_KEY"],
    "hyperbolic": ["HYPERBOLIC_API_KEY"],
    "novita": ["NOVITA_API_KEY"],
    "nscale": ["NSCALE_API_KEY"],
    "ovhcloud": ["OVHCLOUD_APP_KEY", "OVHCLOUD_APP_SECRET", "OVHCLOUD_CONSUMER_KEY"],
    "deepinfra": ["DEEPINFRA_API_KEY"],
    "featherless": ["FEATHERLESS_API_KEY"],
}


@dataclass
class CascadeCheck:
    name: str
    status: str
    summary: str
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class QualityCascade:
    """Run deterministic local checks for a task route."""

    def __init__(
        self,
        policies: Optional[Dict[str, Any]] = None,
        runtime_governor: Any = None,
    ):
        self.policies = policies or {}
        self.runtime_governor = runtime_governor
        self.evidence_factory = EvidenceEnvelopeFactory(self.policies)

    def run(
        self,
        envelope: Dict[str, Any],
        route_card: Dict[str, Any],
        workspace_root: str,
    ) -> Dict[str, Any]:
        provider = route_card.get("provider") or envelope.get("inputs", {}).get("provider") or "unknown"
        workspace = Path(workspace_root)
        checks = self.run_steps(
            steps=route_card.get("preferred_order", []),
            provider=provider,
            workspace=workspace,
        )
        executed = [check.name for check in checks]
        failed = [check for check in checks if check.status == "failed"]
        warnings = [check for check in checks if check.status == "warning"]
        evidence_records = [
            self._check_evidence(check, provider, envelope, route_card)
            for check in checks
        ]
        return {
            "beast_object_type": "quality_cascade_report",
            "version": "1.0",
            "task_id": envelope.get("task_id"),
            "task_class": envelope.get("task_class"),
            "route_id": route_card.get("route_id"),
            "provider": provider,
            "local_only": True,
            "status": "failed" if failed else "warning" if warnings else "passed",
            "checks": [check.to_dict() for check in checks],
            "route_execution": {
                "source": "route_card.preferred_order",
                "preferred_order": route_card.get("preferred_order", []),
                "executed_order": executed,
                "unsupported_steps": [
                    step for step in route_card.get("preferred_order", [])
                    if step not in set(executed) and step not in {"failure_category", "recommendations", "chronicle"}
                ],
                "post_check_steps": [
                    step for step in route_card.get("preferred_order", [])
                    if step in {"failure_category", "recommendations", "chronicle"}
                ],
            },
            "evidence_records": evidence_records,
            "summary": {
                "check_count": len(checks),
                "failed": len(failed),
                "warnings": len(warnings),
                "passed": len([check for check in checks if check.status == "passed"]),
                "skipped": len([check for check in checks if check.status == "skipped"]),
            },
        }

    def run_steps(self, steps: List[str], provider: str, workspace: Path) -> List[CascadeCheck]:
        check_map = {
            "provider_policy": lambda: self.check_provider_policy(provider),
            "credentials": lambda: self.check_credentials(provider),
            "runtime_circuit": lambda: self.check_runtime_circuit(provider),
            "recent_attempts": lambda: self.check_recent_attempts(provider),
            "log_scan": lambda: self.check_logs(provider, workspace),
            "git_status": lambda: self.check_git_status(workspace),
            "py_compile": lambda: self.check_py_compile(workspace),
            "pytest_collect": lambda: self.check_pytest_collect(workspace),
            "dependency_check": lambda: self.check_dependencies(workspace),
            "markdown_summary": lambda: self.check_markdown_summary(workspace),
            "extension_check": lambda: self.check_extension_assets(workspace),
        }
        checks = []
        for step in steps:
            if step in check_map:
                checks.append(check_map[step]())
        return checks

    def run_maintenance(
        self,
        workspace_root: str,
        run_tests: bool = False,
        pytest_args: Optional[List[str]] = None,
        include_extension_checks: bool = True,
        include_markdown: bool = True,
        run_packaging: bool = False,
        python_versions: Optional[List[str]] = None,
        timeout_seconds: int = 60,
    ) -> Dict[str, Any]:
        """Run repo hygiene checks that agent clients can call after edits."""
        workspace = Path(workspace_root or ".").resolve()
        checks = [
            self.check_git_status(workspace),
            self.check_language_inventory(workspace),
            self.check_py_compile(workspace),
            self.check_pytest_collect(workspace, timeout_seconds=timeout_seconds),
            self.check_dependencies(workspace, timeout_seconds=timeout_seconds),
            self.check_html_syntax(workspace),
            self.check_javascript_syntax(workspace, timeout_seconds=timeout_seconds),
            self.check_python_package_build(
                workspace,
                run_packaging=run_packaging,
                python_versions=python_versions or [],
                timeout_seconds=timeout_seconds,
            ),
            self.check_django_project(workspace, timeout_seconds=timeout_seconds),
            self.check_jekyll_docker_build(workspace, run_packaging=run_packaging, timeout_seconds=timeout_seconds),
            self.check_dotnet_project(workspace, run_packaging=run_packaging, timeout_seconds=timeout_seconds),
            self.check_java_project(workspace, run_packaging=run_packaging, timeout_seconds=timeout_seconds),
        ]
        if include_extension_checks:
            checks.append(self.check_extension_assets(workspace, timeout_seconds=timeout_seconds))
        if include_markdown:
            checks.append(self.check_markdown_summary(workspace))
        if run_tests:
            checks.append(self.check_pytest(workspace, pytest_args or ["-q"], timeout_seconds=timeout_seconds))
        else:
            checks.append(CascadeCheck(
                "pytest",
                "skipped",
                "Full pytest run disabled; pass run_tests=true to execute it.",
                {"recommended_args": pytest_args or ["-q"]},
            ))

        failed = [check for check in checks if check.status == "failed"]
        warnings = [check for check in checks if check.status == "warning"]
        return {
            "beast_object_type": "maintenance_cascade_report",
            "version": "1.0",
            "workspace": str(workspace),
            "local_only": True,
            "status": "failed" if failed else "warning" if warnings else "passed",
            "checks": [check.to_dict() for check in checks],
            "summary": {
                "check_count": len(checks),
                "failed": len(failed),
                "warnings": len(warnings),
                "passed": len([check for check in checks if check.status == "passed"]),
                "skipped": len([check for check in checks if check.status == "skipped"]),
            },
            "next_actions": self._maintenance_next_actions(checks),
        }

    def check_provider_policy(self, provider: str) -> CascadeCheck:
        providers = self.policies.get("providers", {})
        config = providers.get(provider) or providers.get(self.provider_alias(provider), {})
        if not config:
            return CascadeCheck(
                "provider_policy",
                "warning",
                f"No provider policy found for {provider}",
                {"known_providers": sorted(providers.keys())},
            )
        enabled = bool(config.get("enabled", False))
        return CascadeCheck(
            "provider_policy",
            "passed" if enabled else "failed",
            f"Provider policy is {'enabled' if enabled else 'disabled'}",
            {
                "base_url": config.get("base_url"),
                "default_model": config.get("default_model"),
                "backend": config.get("backend"),
            },
        )

    def check_credentials(self, provider: str) -> CascadeCheck:
        env_vars = PROVIDER_ENV_VARS.get(provider) or PROVIDER_ENV_VARS.get(self.provider_alias(provider), [])
        if not env_vars:
            return CascadeCheck("credentials", "warning", "No credential rule is registered", {})
        present = [name for name in env_vars if bool(os.environ.get(name))]
        return CascadeCheck(
            "credentials",
            "passed" if present else "failed",
            "Required environment credential is present" if present else "No expected credential environment variable is set",
            {"expected_env": env_vars, "present_env": present},
        )

    def check_runtime_circuit(self, provider: str) -> CascadeCheck:
        if not self.runtime_governor:
            return CascadeCheck("runtime_circuit", "skipped", "Runtime governor unavailable", {})
        state = self.runtime_governor.circuit_state(provider)
        status = "passed" if state.get("state") in ("closed", "half_open") else "failed"
        return CascadeCheck(
            "runtime_circuit",
            status,
            f"Runtime circuit is {state.get('state')}",
            state,
        )

    def check_recent_attempts(self, provider: str) -> CascadeCheck:
        if not self.runtime_governor:
            return CascadeCheck("recent_attempts", "skipped", "Runtime governor unavailable", {})
        attempts = self.runtime_governor.recent_attempts(provider=provider, limit=8)
        failures = [item for item in attempts if item.get("status") in ("failed", "rejected", "abandoned")]
        summary = "No recent attempts found"
        status = "warning"
        if attempts:
            status = "passed" if not failures else "warning"
            summary = f"{len(attempts)} recent attempts, {len(failures)} non-successful"
        return CascadeCheck(
            "recent_attempts",
            status,
            summary,
            {"attempts": attempts, "failure_count": len(failures)},
        )

    def check_logs(self, provider: str, workspace: Path) -> CascadeCheck:
        snippets = []
        for log_name in ("gateway.log", "server.log", "ollama.log"):
            path = workspace / log_name
            if not path.exists():
                continue
            text = self.tail_text(path)
            hits = self.log_hits(text, provider)
            if hits:
                snippets.append({"file": log_name, "hits": hits[:5]})

        if not snippets:
            return CascadeCheck(
                "log_scan",
                "warning",
                "No provider-specific failures found in local log tails",
                {"searched_logs": ["gateway.log", "server.log", "ollama.log"]},
            )
        return CascadeCheck(
            "log_scan",
            "warning",
            "Provider-related log evidence found",
            {"snippets": snippets},
        )

    def check_language_inventory(self, workspace: Path) -> CascadeCheck:
        suffixes = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".html": "html",
            ".css": "css",
            ".cs": "csharp",
            ".java": "java",
            ".rb": "ruby",
            ".md": "markdown",
            ".yml": "yaml",
            ".yaml": "yaml",
            ".json": "json",
        }
        counts: Dict[str, int] = {}
        for suffix, language in suffixes.items():
            count = sum(1 for _ in self._iter_repo_files(workspace, suffix))
            if count:
                counts[language] = counts.get(language, 0) + count
        return CascadeCheck(
            "language_inventory",
            "passed",
            f"Detected {len(counts)} language/artifact family(ies)",
            {"languages": dict(sorted(counts.items()))},
        )

    def check_git_status(self, workspace: Path, timeout_seconds: int = 20) -> CascadeCheck:
        result = self._run_command(["git", "status", "--short"], workspace, timeout_seconds)
        if result["status"] == "skipped":
            return CascadeCheck("git_status", "skipped", result["summary"], result)
        lines = [line for line in result.get("stdout", "").splitlines() if line.strip()]
        status = "passed" if result["returncode"] == 0 else "warning"
        summary = "Working tree clean" if not lines else f"{len(lines)} changed path(s) in working tree"
        return CascadeCheck(
            "git_status",
            status,
            summary,
            {"changed_paths": lines[:80], "change_count": len(lines), "command": result["command"]},
        )

    def check_py_compile(self, workspace: Path, max_files: int = 800) -> CascadeCheck:
        files = list(self._iter_repo_files(workspace, ".py"))[:max_files]
        errors: List[Dict[str, str]] = []
        for path in files:
            try:
                py_compile.compile(str(path), doraise=True)
            except py_compile.PyCompileError as exc:
                errors.append({
                    "path": str(path.relative_to(workspace)),
                    "error": str(exc)[:1200],
                })
                if len(errors) >= 12:
                    break
        return CascadeCheck(
            "py_compile",
            "failed" if errors else "passed",
            f"{len(errors)} compile error(s) across {len(files)} Python file(s)" if errors else f"Compiled {len(files)} Python file(s)",
            {"files_checked": len(files), "errors": errors},
        )

    def check_pytest_collect(self, workspace: Path, timeout_seconds: int = 60) -> CascadeCheck:
        if not (workspace / "tests").exists():
            return CascadeCheck("pytest_collect", "skipped", "No tests directory found", {})
        result = self._run_command([sys.executable, "-m", "pytest", "--collect-only", "-q"], workspace, timeout_seconds)
        if result["status"] == "skipped":
            return CascadeCheck("pytest_collect", "skipped", result["summary"], result)
        status = "passed" if result["returncode"] == 0 else "failed"
        collected = self._pytest_collected_count(result.get("stdout", "") + "\n" + result.get("stderr", ""))
        summary = f"Pytest collected {collected} test(s)" if status == "passed" else "Pytest collection failed"
        return CascadeCheck("pytest_collect", status, summary, {**result, "collected": collected})

    def check_pytest(self, workspace: Path, pytest_args: List[str], timeout_seconds: int = 120) -> CascadeCheck:
        if not (workspace / "tests").exists():
            return CascadeCheck("pytest", "skipped", "No tests directory found", {})
        args = [str(item) for item in pytest_args if str(item).strip()]
        result = self._run_command([sys.executable, "-m", "pytest", *args], workspace, timeout_seconds)
        if result["status"] == "skipped":
            return CascadeCheck("pytest", "skipped", result["summary"], result)
        status = "passed" if result["returncode"] == 0 else "failed"
        return CascadeCheck(
            "pytest",
            status,
            "Pytest completed successfully" if status == "passed" else "Pytest failed",
            result,
        )

    def check_dependencies(self, workspace: Path, timeout_seconds: int = 45) -> CascadeCheck:
        evidence: Dict[str, Any] = {"files": {}}
        for rel in ("requirements.txt", "pyproject.toml", "package.json", "vscode-extension/package.json"):
            path = workspace / rel
            evidence["files"][rel] = path.exists()
            if path.suffix == ".json" and path.exists():
                try:
                    json.loads(path.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    return CascadeCheck("dependency_check", "failed", f"Invalid JSON in {rel}", {"error": str(exc), **evidence})
        pip_result = self._run_command([sys.executable, "-m", "pip", "check"], workspace, timeout_seconds)
        evidence["pip_check"] = pip_result
        if pip_result.get("status") == "skipped":
            return CascadeCheck("dependency_check", "warning", "pip check could not run", evidence)
        status = "passed" if pip_result.get("returncode") == 0 else "warning"
        summary = "Dependency metadata looks sane" if status == "passed" else "pip check reported dependency issues"
        return CascadeCheck("dependency_check", status, summary, evidence)

    def check_html_syntax(self, workspace: Path, max_files: int = 120) -> CascadeCheck:
        files = list(self._iter_repo_files(workspace, ".html"))[:max_files]
        if not files:
            return CascadeCheck("html_syntax", "skipped", "No HTML files found", {})
        errors: List[Dict[str, str]] = []
        for path in files:
            parser = HTMLParser()
            try:
                parser.feed(path.read_text(encoding="utf-8", errors="replace"))
                parser.close()
            except Exception as exc:
                errors.append({"path": str(path.relative_to(workspace)), "error": str(exc)[:800]})
                if len(errors) >= 12:
                    break
        return CascadeCheck(
            "html_syntax",
            "failed" if errors else "passed",
            f"{len(errors)} HTML parse issue(s)" if errors else f"Parsed {len(files)} HTML file(s)",
            {"files_checked": len(files), "errors": errors},
        )

    def check_javascript_syntax(self, workspace: Path, timeout_seconds: int = 45, max_files: int = 80) -> CascadeCheck:
        files = [
            path for path in self._iter_repo_files(workspace, ".js")
            if "node_modules" not in path.relative_to(workspace).parts
        ][:max_files]
        if not files:
            return CascadeCheck("javascript_syntax", "skipped", "No JavaScript files found", {})
        if not shutil.which("node"):
            return CascadeCheck("javascript_syntax", "skipped", "node executable not found", {"files_detected": len(files)})
        errors: List[Dict[str, Any]] = []
        for path in files:
            result = self._run_command(["node", "--check", str(path)], workspace, timeout_seconds)
            if result.get("returncode") != 0:
                errors.append({"path": str(path.relative_to(workspace)), "result": result})
                if len(errors) >= 12:
                    break
        return CascadeCheck(
            "javascript_syntax",
            "failed" if errors else "passed",
            f"{len(errors)} JavaScript syntax issue(s)" if errors else f"Checked {len(files)} JavaScript file(s)",
            {"files_checked": len(files), "errors": errors},
        )

    def check_python_package_build(
        self,
        workspace: Path,
        run_packaging: bool,
        python_versions: List[str],
        timeout_seconds: int = 120,
    ) -> CascadeCheck:
        has_package_manifest = any((workspace / name).exists() for name in ("pyproject.toml", "setup.py", "setup.cfg"))
        if not has_package_manifest:
            return CascadeCheck("python_package_build", "skipped", "No Python package manifest found", {})
        interpreters = python_versions or [sys.executable]
        if not run_packaging:
            return CascadeCheck(
                "python_package_build",
                "skipped",
                "Python package manifest found; pass run_packaging=true to build wheels/sdists.",
                {"interpreters": interpreters},
            )
        results = []
        with tempfile.TemporaryDirectory(prefix="beast-package-build-") as out_dir:
            for interpreter in interpreters:
                exe = shutil.which(interpreter) or interpreter
                if not Path(exe).exists() and shutil.which(exe) is None:
                    results.append({"python": interpreter, "status": "skipped", "summary": "interpreter not found"})
                    continue
                command = [exe, "-m", "build", "--sdist", "--wheel", "--outdir", out_dir]
                result = self._run_command(command, workspace, timeout_seconds)
                results.append({"python": interpreter, **result})
        failures = [item for item in results if item.get("returncode") not in (0, None) or item.get("status") == "failed"]
        skipped = [item for item in results if item.get("status") == "skipped"]
        status = "failed" if failures else "warning" if skipped else "passed"
        return CascadeCheck(
            "python_package_build",
            status,
            f"{len(failures)} package build failure(s), {len(skipped)} skipped interpreter(s)",
            {"results": results},
        )

    def check_django_project(self, workspace: Path, timeout_seconds: int = 60) -> CascadeCheck:
        manage = workspace / "manage.py"
        if not manage.exists():
            return CascadeCheck("django_check", "skipped", "No Django manage.py found", {})
        result = self._run_command([sys.executable, str(manage), "check", "--deploy"], workspace, timeout_seconds)
        status = "passed" if result.get("returncode") == 0 else "warning"
        return CascadeCheck(
            "django_check",
            status,
            "Django deploy check passed" if status == "passed" else "Django check reported warnings/errors",
            result,
        )

    def check_jekyll_docker_build(self, workspace: Path, run_packaging: bool, timeout_seconds: int = 180) -> CascadeCheck:
        has_jekyll = any((workspace / name).exists() for name in ("_config.yml", "_config.yaml", "Gemfile"))
        if not has_jekyll:
            return CascadeCheck("jekyll_docker_build", "skipped", "No Jekyll config/Gemfile found", {})
        if not run_packaging:
            return CascadeCheck(
                "jekyll_docker_build",
                "skipped",
                "Jekyll project detected; pass run_packaging=true to run jekyll/builder.",
                {"image": "jekyll/builder"},
            )
        if not shutil.which("docker"):
            return CascadeCheck("jekyll_docker_build", "skipped", "docker executable not found", {"image": "jekyll/builder"})
        command = [
            "docker", "run", "--rm",
            "-v", f"{workspace}:/srv/jekyll",
            "jekyll/builder",
            "jekyll", "build",
        ]
        result = self._run_command(command, workspace, timeout_seconds)
        status = "passed" if result.get("returncode") == 0 else "failed"
        return CascadeCheck("jekyll_docker_build", status, "Jekyll Docker build passed" if status == "passed" else "Jekyll Docker build failed", result)

    def check_dotnet_project(self, workspace: Path, run_packaging: bool, timeout_seconds: int = 180) -> CascadeCheck:
        projects = list(self._iter_repo_files(workspace, ".csproj"))
        solutions = list(self._iter_repo_files(workspace, ".sln"))
        if not projects and not solutions:
            return CascadeCheck("dotnet_build", "skipped", "No .NET project or solution found", {})
        if not run_packaging:
            return CascadeCheck(
                "dotnet_build",
                "skipped",
                ".NET project detected; pass run_packaging=true to run dotnet build/test.",
                {"projects": [str(path.relative_to(workspace)) for path in projects[:20]], "solutions": [str(path.relative_to(workspace)) for path in solutions[:20]]},
            )
        if not shutil.which("dotnet"):
            return CascadeCheck("dotnet_build", "skipped", "dotnet executable not found", {"project_count": len(projects), "solution_count": len(solutions)})
        target = str((solutions or projects)[0].relative_to(workspace))
        result = self._run_command(["dotnet", "build", target, "--nologo"], workspace, timeout_seconds)
        status = "passed" if result.get("returncode") == 0 else "failed"
        return CascadeCheck("dotnet_build", status, ".NET build passed" if status == "passed" else ".NET build failed", result)

    def check_java_project(self, workspace: Path, run_packaging: bool, timeout_seconds: int = 180) -> CascadeCheck:
        has_maven = (workspace / "pom.xml").exists()
        has_gradle = any((workspace / name).exists() for name in ("build.gradle", "build.gradle.kts", "gradlew"))
        java_files = list(self._iter_repo_files(workspace, ".java"))[:40]
        if not has_maven and not has_gradle and not java_files:
            return CascadeCheck("java_build", "skipped", "No Java project files found", {})
        if not run_packaging:
            return CascadeCheck(
                "java_build",
                "skipped",
                "Java project detected; pass run_packaging=true to run Maven/Gradle or javac checks.",
                {"maven": has_maven, "gradle": has_gradle, "java_files": len(java_files)},
            )
        if has_maven and shutil.which("mvn"):
            result = self._run_command(["mvn", "test", "-q"], workspace, timeout_seconds)
        elif has_gradle and ((workspace / "gradlew").exists() or shutil.which("gradle")):
            command = [str(workspace / "gradlew"), "test"] if (workspace / "gradlew").exists() else ["gradle", "test"]
            result = self._run_command(command, workspace, timeout_seconds)
        elif java_files and shutil.which("javac"):
            with tempfile.TemporaryDirectory(prefix="beast-javac-") as out_dir:
                result = self._run_command(["javac", "-d", out_dir, *[str(path) for path in java_files]], workspace, timeout_seconds)
        else:
            return CascadeCheck("java_build", "skipped", "No Maven/Gradle/javac executable found", {"java_files": len(java_files)})
        status = "passed" if result.get("returncode") == 0 else "failed"
        return CascadeCheck("java_build", status, "Java build/test passed" if status == "passed" else "Java build/test failed", result)

    def check_extension_assets(self, workspace: Path, timeout_seconds: int = 30) -> CascadeCheck:
        extension = workspace / "vscode-extension" / "extension.js"
        package = workspace / "vscode-extension" / "package.json"
        evidence: Dict[str, Any] = {
            "extension_js": extension.exists(),
            "package_json": package.exists(),
        }
        if package.exists():
            try:
                json.loads(package.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                return CascadeCheck("extension_check", "failed", "VS Code extension package.json is invalid", {"error": str(exc), **evidence})
        if not extension.exists():
            return CascadeCheck("extension_check", "skipped", "No VS Code extension entrypoint found", evidence)
        if not shutil.which("node"):
            return CascadeCheck("extension_check", "skipped", "node executable not found", evidence)
        result = self._run_command(["node", "--check", str(extension)], workspace, timeout_seconds)
        status = "passed" if result.get("returncode") == 0 else "failed"
        return CascadeCheck(
            "extension_check",
            status,
            "VS Code extension syntax is valid" if status == "passed" else "VS Code extension syntax check failed",
            {**evidence, "node_check": result},
        )

    def check_markdown_summary(self, workspace: Path) -> CascadeCheck:
        markdown_files = [
            path for path in self._iter_repo_files(workspace, ".md")
            if "node_modules" not in path.parts and "site-packages" not in path.parts
        ][:80]
        missing: List[Dict[str, str]] = []
        headings: Dict[str, List[str]] = {}
        for path in markdown_files:
            rel = str(path.relative_to(workspace))
            text = path.read_text(encoding="utf-8", errors="replace")
            if self._looks_binary_text(text):
                continue
            headings[rel] = [line.strip("# ").strip() for line in text.splitlines() if line.startswith("#")][:12]
            for link in re.findall(r"\]\(([^)]+)\)", text):
                target = link.strip()
                if not target or target.startswith(("#", "http://", "https://", "mailto:", "app://")):
                    continue
                target_path = target.split("#", 1)[0].strip()
                if not target_path:
                    continue
                resolved = (path.parent / target_path).resolve()
                try:
                    resolved.relative_to(workspace)
                except ValueError:
                    continue
                if not resolved.exists():
                    missing.append({"file": rel, "target": target_path})
                    if len(missing) >= 20:
                        break
            if len(missing) >= 20:
                break
        status = "warning" if missing else "passed"
        return CascadeCheck(
            "markdown_summary",
            status,
            f"{len(missing)} missing local markdown link(s)" if missing else f"Scanned {len(markdown_files)} markdown file(s)",
            {"files_scanned": len(markdown_files), "missing_links": missing, "headings": headings},
        )

    def provider_alias(self, provider: str) -> str:
        aliases = {"hf": "huggingface", "gemini": "google", "google_ai_studio": "google"}
        return aliases.get(provider, provider)

    def tail_text(self, path: Path, max_bytes: int = 12000) -> str:
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            pos = f.tell()
            bytes_to_read = min(pos, max_bytes)
            f.seek(pos - bytes_to_read)
            data = f.read(bytes_to_read)
        return data.decode("utf-8", errors="replace")

    def log_hits(self, text: str, provider: str) -> List[str]:
        terms = [provider, self.provider_alias(provider), "429", "quota", "rate limit", "unauthorized", "timeout", "error"]
        hits = []
        for line in text.splitlines():
            lower = line.lower()
            if any(term and term.lower() in lower for term in terms):
                hits.append(re.sub(r"\s+", " ", line).strip()[:260])
        return hits

    def _iter_repo_files(self, workspace: Path, suffix: str) -> Iterable[Path]:
        skip_dirs = {
            ".git",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            ".venv",
            "venv",
            "__pycache__",
            "node_modules",
            "dist",
            "build",
            "htmlcov",
        }
        for path in workspace.rglob(f"*{suffix}"):
            if not path.is_file():
                continue
            if any(part in skip_dirs for part in path.relative_to(workspace).parts):
                continue
            yield path

    def _run_command(self, command: List[str], workspace: Path, timeout_seconds: int) -> Dict[str, Any]:
        executable = command[0]
        if executable not in {sys.executable, "git"} and not shutil.which(executable):
            return {
                "status": "skipped",
                "summary": f"{executable} executable not found",
                "command": command,
            }
        try:
            completed = subprocess.run(
                command,
                cwd=str(workspace),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=max(1, int(timeout_seconds)),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "status": "failed",
                "summary": f"Command timed out after {timeout_seconds}s",
                "command": command,
                "stdout": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
                "stderr": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
                "returncode": 124,
            }
        return {
            "status": "completed",
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-8000:],
            "stderr": completed.stderr[-8000:],
        }

    def _pytest_collected_count(self, text: str) -> int:
        matches = re.findall(r"collected\s+(\d+)\s+items?", text)
        if matches:
            return int(matches[-1])
        per_file_counts = re.findall(r":\s+(\d+)\s*$", text, flags=re.MULTILINE)
        if per_file_counts:
            return sum(int(item) for item in per_file_counts)
        return len([line for line in text.splitlines() if "::" in line and not line.startswith("<")])

    def _looks_binary_text(self, text: str) -> bool:
        if "\ufffd" in text[:4000]:
            return True
        sample = text[:4000]
        if not sample:
            return False
        controls = sum(1 for char in sample if ord(char) < 32 and char not in "\n\r\t")
        return controls / max(1, len(sample)) > 0.02

    def _maintenance_next_actions(self, checks: List[CascadeCheck]) -> List[str]:
        actions: List[str] = []
        for check in checks:
            if check.status == "failed":
                if check.name == "py_compile":
                    actions.append("Fix Python syntax/import-time compile errors before any provider handoff.")
                elif check.name.startswith("pytest"):
                    actions.append("Inspect pytest output and rerun the targeted failing test slice.")
                elif check.name == "extension_check":
                    actions.append("Fix VS Code extension syntax or manifest errors before packaging.")
                else:
                    actions.append(f"Resolve failed maintenance check: {check.name}.")
            elif check.status == "warning":
                actions.append(f"Review warning from maintenance check: {check.name}.")
        return actions or ["Repo hygiene checks are clean enough for the next governed action."]

    def _check_evidence(
        self,
        check: CascadeCheck,
        provider: str,
        envelope: Dict[str, Any],
        route_card: Dict[str, Any],
    ) -> Dict[str, Any]:
        severity = {
            "failed": "high",
            "warning": "medium",
            "skipped": "low",
            "passed": "info",
        }.get(check.status, "info")
        confidence = {
            "failed": 0.85,
            "warning": 0.65,
            "skipped": 0.35,
            "passed": 0.6,
        }.get(check.status, 0.5)
        relevance = 0.85 if check.status in ("failed", "warning") else 0.45
        verification_strength = 0.75 if check.status == "failed" else 0.55 if check.status == "warning" else 0.35
        capability_id = self._check_capability_id(check.name)
        family = "diagnostics" if check.name in {"provider_policy", "credentials", "runtime_circuit", "recent_attempts", "log_scan"} else "quality"
        return self.evidence_factory.build(
            source_type="quality_verifier",
            source_uri=f"quality://{route_card.get('route_id') or provider}/{check.name}",
            scope="provider",
            artifact_type=f"quality_check:{check.name}",
            task_id=envelope.get("task_id"),
            provider=provider,
            severity=severity,
            confidence=confidence,
            relevance=relevance,
            risk=0.55 if check.status == "failed" else 0.35,
            blast_radius=0.35,
            repeat_count=1,
            verification_strength=verification_strength,
            signals=[f"quality_{check.status}", check.name],
            relationships=[
                {"type": "provider", "id": provider},
                {"type": "route", "id": route_card.get("route_id")},
                {"type": "quality_check", "id": check.name},
            ],
            recommended_actions=self._check_recommendations(check),
            recommended_capability_id=capability_id,
            capability_family=family,
            summary=check.summary,
        )

    def _check_capability_id(self, check_name: str) -> str:
        if check_name in {"provider_policy", "credentials", "runtime_circuit", "recent_attempts", "log_scan"}:
            return "workflow:provider_diagnostic"
        return "workflow:quality_cascade"

    def _check_recommendations(self, check: CascadeCheck) -> List[str]:
        if check.status == "passed":
            return ["Keep this local check as supporting evidence."]
        if check.name == "credentials":
            return ["Fix credential mapping before retrying provider calls."]
        if check.name == "runtime_circuit":
            return ["Check provider circuit before cloud handoff or retry."]
        if check.name == "log_scan":
            return ["Use local log evidence to categorize the failure before escalation."]
        return ["Resolve or explain this local quality check before cloud handoff."]
