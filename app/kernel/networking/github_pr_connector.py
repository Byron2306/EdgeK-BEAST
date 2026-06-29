"""Governed GitHub pull-request ingestion and Chronicle publication."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.kernel.execution.task_envelope import TaskEnvelopeBuilder


class GitHubPRConnector:
    """Convert PR evidence into task envelopes and publish bounded summaries."""

    API_ROOT = "https://api.github.com"
    REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

    def __init__(
        self,
        task_envelope_builder: Optional[TaskEnvelopeBuilder] = None,
        token: Optional[str] = None,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self.task_envelope_builder = task_envelope_builder or TaskEnvelopeBuilder()
        self.token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        self.client = client or httpx.Client(timeout=20.0)

    def ingest(self, repo: str, pr_number: int, *, max_files: int = 20, max_comments: int = 30) -> Dict[str, Any]:
        repo, pr_number = self._validate_target(repo, pr_number)
        pr = self._get(f"/repos/{repo}/pulls/{pr_number}")
        files = self._get(f"/repos/{repo}/pulls/{pr_number}/files", {"per_page": min(max_files, 100)})
        review_comments = self._get(
            f"/repos/{repo}/pulls/{pr_number}/comments", {"per_page": min(max_comments, 100)}
        )
        issue_comments = self._get(
            f"/repos/{repo}/issues/{pr_number}/comments", {"per_page": min(max_comments, 100)}
        )
        sha = str((pr.get("head") or {}).get("sha") or "")
        checks = self._get(f"/repos/{repo}/commits/{sha}/check-runs") if sha else {"check_runs": []}

        changed_files = []
        patch_budget = 16000
        for item in self._as_list(files)[:max_files]:
            compact = self._compact_file(item, min(4000, patch_budget))
            changed_files.append(compact)
            patch_budget = max(0, patch_budget - len(compact["patch"]))
        comments = []
        comment_budget = 12000
        comment_sources = [
            *[(item, "review") for item in self._as_list(review_comments)],
            *[(item, "conversation") for item in self._as_list(issue_comments)],
        ]
        for item, kind in comment_sources[:max_comments]:
            compact = self._compact_comment(item, kind, min(2000, comment_budget))
            comments.append(compact)
            comment_budget = max(0, comment_budget - len(compact["body"]))
        check_runs = [self._compact_check(item) for item in self._as_list(checks.get("check_runs"))]
        failed_checks = [
            item for item in check_runs if item["conclusion"] not in {"success", "neutral", "skipped", None}
        ]
        pr_evidence = {
            "repository": repo,
            "pr_number": pr_number,
            "url": pr.get("html_url"),
            "title": pr.get("title"),
            "body": str(pr.get("body") or "")[:6000],
            "author": (pr.get("user") or {}).get("login"),
            "base_ref": (pr.get("base") or {}).get("ref"),
            "head_ref": (pr.get("head") or {}).get("ref"),
            "head_sha": sha,
            "draft": bool(pr.get("draft")),
            "changed_files": changed_files,
            "failed_checks": failed_checks,
            "checks": check_runs,
            "review_comments": comments,
        }
        envelope = self.task_envelope_builder.build({
            "user_request": self._task_request(pr_evidence),
            "task_class": "github_pr_remediation",
            "project": repo,
            "risk_level": "high" if failed_checks or len(changed_files) > 8 else "medium",
            "privacy_class": "repository",
            "max_files": max(1, min(max_files, 50)),
        }, dry_run=True)
        envelope["inputs"]["github_pr"] = pr_evidence
        return {
            "beast_object_type": "github_pr_task_packet",
            "version": "1.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "repository": repo,
            "pr_number": pr_number,
            "task_envelope": envelope,
            "evidence": pr_evidence,
            "counts": {
                "changed_files": len(changed_files),
                "checks": len(check_runs),
                "failed_checks": len(failed_checks),
                "review_comments": len(comments),
            },
        }

    def publish_chronicle(
        self,
        repo: str,
        pr_number: int,
        chronicle: Dict[str, Any],
        *,
        approved: bool = False,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        repo, pr_number = self._validate_target(repo, pr_number)
        body = self.render_chronicle_summary(chronicle)
        packet = {
            "beast_object_type": "github_pr_chronicle_publish",
            "version": "1.0",
            "repository": repo,
            "pr_number": pr_number,
            "approved": bool(approved),
            "dry_run": bool(dry_run),
            "body": body,
        }
        if dry_run or not approved:
            packet.update({
                "published": False,
                "reason": "Dry-run projection; live publication requires approved=true and dry_run=false.",
            })
            return packet
        response = self._post(f"/repos/{repo}/issues/{pr_number}/comments", {"body": body})
        packet.update({
            "published": True,
            "comment_id": response.get("id"),
            "comment_url": response.get("html_url"),
        })
        return packet

    def render_chronicle_summary(self, chronicle: Dict[str, Any]) -> str:
        record = chronicle.get("record") if isinstance(chronicle.get("record"), dict) else chronicle
        verification = record.get("verification") if isinstance(record.get("verification"), dict) else {}
        recommendations = record.get("recommendations") if isinstance(record.get("recommendations"), list) else []
        lines = [
            "## BEAST Chronicle Summary",
            "",
            str(record.get("summary") or "Governed BEAST run completed."),
            "",
            f"- Task: `{record.get('task_id', 'unknown')}`",
            f"- Provider: `{record.get('provider', 'unknown')}`",
            f"- Category: `{record.get('category', 'unknown')}`",
            f"- Verification: `{'passed' if verification.get('local_checks_completed') else 'recorded'}`",
        ]
        if recommendations:
            lines.extend(["", "### Recommendations", *[f"- {str(item)[:500]}" for item in recommendations[:8]]])
        lines.extend(["", "_Published through the governed BEAST GitHub PR connector._"])
        return "\n".join(lines)[:12000]

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        response = self.client.get(f"{self.API_ROOT}{path}", headers=self._headers(), params=params)
        response.raise_for_status()
        return response.json()

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = self.client.post(f"{self.API_ROOT}{path}", headers=self._headers(), json=payload)
        response.raise_for_status()
        return response.json()

    def _headers(self) -> Dict[str, str]:
        if not self.token:
            raise ValueError("GITHUB_TOKEN or GH_TOKEN is required for GitHub PR connector calls")
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _validate_target(self, repo: str, pr_number: int) -> tuple[str, int]:
        normalized = str(repo or "").strip()
        number = int(pr_number)
        if not self.REPO_PATTERN.fullmatch(normalized):
            raise ValueError("repo must use the owner/name form")
        if number <= 0:
            raise ValueError("pr_number must be positive")
        return normalized, number

    @staticmethod
    def _as_list(value: Any) -> List[Dict[str, Any]]:
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    @staticmethod
    def _compact_file(item: Dict[str, Any], patch_limit: int = 4000) -> Dict[str, Any]:
        return {
            "filename": item.get("filename"), "status": item.get("status"),
            "additions": item.get("additions"), "deletions": item.get("deletions"),
            "patch": str(item.get("patch") or "")[:patch_limit],
        }

    @staticmethod
    def _compact_comment(item: Dict[str, Any], kind: str, body_limit: int = 2000) -> Dict[str, Any]:
        return {
            "kind": kind, "author": (item.get("user") or {}).get("login"), "path": item.get("path"),
            "line": item.get("line") or item.get("original_line"),
            "body": str(item.get("body") or "")[:body_limit], "url": item.get("html_url"),
        }

    @staticmethod
    def _compact_check(item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "name": item.get("name"), "status": item.get("status"), "conclusion": item.get("conclusion"),
            "url": item.get("html_url") or item.get("details_url"),
            "summary": str(((item.get("output") or {}).get("summary")) or "")[:2000],
        }

    @staticmethod
    def _task_request(evidence: Dict[str, Any]) -> str:
        failed = ", ".join(str(item.get("name")) for item in evidence["failed_checks"]) or "none"
        reviewed = [item["body"] for item in evidence["review_comments"] if item.get("body")]
        return (
            f"Review and remediate PR #{evidence['pr_number']} in {evidence['repository']}: "
            f"{evidence.get('title')}. Failed checks: {failed}. Review feedback: "
            f"{' | '.join(reviewed[:5]) or 'none'}"
        )[:10000]
