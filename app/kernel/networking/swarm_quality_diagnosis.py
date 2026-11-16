"""Bounded, evidence-linked post-verification failure diagnosis for BEAST Swarm.

No subprocess, inference, repair, or mutation authority. Reports only executed native
quality checks; a planned check is not a diagnostic receipt.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any


def analyze_quality_failures(report: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(report, dict) or report.get('source') == 'swarm_planning_only':
        return None
    checks = report.get('checks')
    if not isinstance(checks, list):
        return None
    failures = []
    for check in checks:
        if not isinstance(check, dict) or check.get('status') != 'failed':
            continue
        evidence = check.get('evidence') or {}
        if not isinstance(evidence, dict):
            evidence = {}
        name = str(check.get('name') or 'unknown')[:80]
        stdout = str(evidence.get('stdout') or '')[:12000]
        stderr = str(evidence.get('stderr') or '')[:12000]
        errors = evidence.get('errors')
        if isinstance(errors, list):
            details = '\n'.join(str(e) for e in errors[:20])
        else:
            details = ''
        diagnostic = '\n'.join(x for x in (stdout, stderr, details, str(check.get('summary') or '')) if x)[:12000]
        category = ('python_lint' if name == 'ruff' else 'javascript_lint' if name == 'eslint'
                    else 'test_failure' if name == 'pytest' else 'syntax_failure' if name == 'py_compile'
                    else 'tool_failure')
        patterns = [r'\bF\d{3,4}\b', r'\bE\d{3,4}\b', r'\bAssertionError\b',
                    r'\bSyntaxError\b', r'\bno-unused-vars\b']
        markers = sorted(set(m for p in patterns for m in re.findall(p, diagnostic)))[:12]
        target_list = evidence.get('targets')
        if not isinstance(target_list, list):
            target_list = []
        digest = 'sha256:' + hashlib.sha256(json.dumps({
            'name': name, 'status': 'failed', 'returncode': evidence.get('returncode'),
            'diagnostic': diagnostic, 'targets': target_list[:20]
        }, sort_keys=True, default=str).encode()).hexdigest()
        failures.append({
            'check': name, 'category': category, 'returncode': evidence.get('returncode'),
            'targets': [str(x) for x in target_list[:20]],
            'markers': markers, 'diagnostic_excerpt': diagnostic[:2400],
            'evidence_digest': digest, 'reason': str(evidence.get('reason') or ''),
        })
    if not failures:
        return None
    return {
        'decision': 'diagnostics_attested', 'source': 'native_quality_cascade',
        'failure_count': len(failures), 'failures': failures,
        'repair_proposed': False, 'mutation_authorized': False,
        'model_call_executed': False, 'read_only': True,
        'verification_accepted': False,
    }
