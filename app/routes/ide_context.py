"""Shared state and pure helpers for the IDE route family.

This module owns framework-independent behaviour that was formerly captured in
the closure of ``build_ide_router``.  Route modules receive one explicit
``IdeRouteContext`` instead of depending on a 4,000-line lexical scope.
"""

from __future__ import annotations
import concurrent.futures
import asyncio
import ast
import difflib
import hashlib
import inspect
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, List
from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from app.cli.api import ActionResult, BeastApiClient
from app.kernel.compute.action_ir import ACTION_IR_KIND, ActionIR
from app.kernel.compute.action_resolver import build_file_references, resolve_action_ir
from app.kernel.compute.crystal_ir import CrystalIRValidationError, compile_crystal_ir
from app.kernel.agents.patch_compiler import ResidualPatchCompiler
from app.kernel.adapters.provider_handoff import build_provider_handoff, render_provider_handoff_prompt
from app.kernel.data_processing.semantic_raid import SemanticRaidStore
from app.kernel.compute.mission_crystal_lattice import MissionCrystalLattice
from app.kernel.evidence.evidence_bus import EvidenceBus
from app.kernel.policy.architecture_decisions import architecture_decision_register
from app.kernel.security.safety_governor import SafetyGovernor
from app.kernel.workspaces import system_inspector
from app.kernel.workspaces.agent_session_store import AgentSessionStore
from app.kernel.workspaces.mission_cockpit import MissionCockpit
from app.kernel.workspaces.worktree_forge import WorktreeForge
from app.kernel.execution.task_envelope import TaskEnvelopeBuilder
from app.kernel.execution.conductor_workflow import ConductorWorkflowBuilder
from app.kernel.registry.canon_registry import CanonRegistry
from app.kernel.data_processing.tool_laziness import ToolLazinessLearner
from app.kernel.data_processing.tool_laziness_plugin import ToolLazinessPlugin
from app.kernel.capability.skill_tree import SkillTree
from app.kernel.data_processing.insight_compiler import InsightCompiler
from app.routes.ide_support.common import bounded_workspace_files as _bounded_workspace_files, extract_json_object as _extract_json_object, hash_text as _hash_text, is_compact_local_coder as _is_compact_local_coder, pair_programmer_limits as _pair_programmer_limits, raw_hash_text as _raw_hash_text, safe_relative as _safe_relative


class IdeRouteContext:
    """Explicit dependency capsule shared by all IDE route registrars."""

    _ANSI_ESCAPE = re.compile(r"(?:\x1B\[[0-?]*[ -/]*[@-~]|\x1B\][^\x07]*(?:\x07|\x1B\\))")

    def __init__(self, default_root: str | Path, *, code_cortex_router: Any, crystal_gateway: Any = None, context_packet_builder: Any = None, execution_gateway: Any = None, compute_governor: Any = None, pressure_controller: Any = None) -> None:
        self.fallback_root = Path(default_root).expanduser().resolve()
        self.code_cortex_router = code_cortex_router
        # Keep IDE planner runs on the application composition root's shared
        # reuse plane instead of creating an isolated cache per run.
        self.crystal_gateway = crystal_gateway
        self.context_packet_builder = context_packet_builder
        self.execution_gateway = execution_gateway
        self.compute_governor = compute_governor
        self.pressure_controller = pressure_controller
        self.handlers: dict[str, Any] = {}

    def _root(self, value: Any=None) -> Path:
        fallback_root = self.fallback_root
        return Path(value or fallback_root).expanduser().resolve()

    def _action_ir_anchor_hints(self, root: Path | None, allowed_files: list[str]) -> str:
        if root is None or not allowed_files:
            return ''
        try:
            refs = build_file_references(root, allowed_files[:8])
        except Exception:
            return ''
        chunks: list[str] = []
        for ref in refs:
            anchors = list((ref.anchors or {}).items())[:8]
            if not anchors:
                continue
            chunks.append(f'{ref.path}:')
            for anchor_id, snippet in anchors:
                compact = str(snippet).strip()
                if compact:
                    chunks.append(f'[{anchor_id}] {compact[:500]}')
        hints = '\n'.join(chunks).strip()
        return hints[:5000]

    def _action_ir_retry_prompt(self, objective: str, previous_output: str, allowed_files: list[str], diagnostics: str='', root: Path | None=None) -> str:
        _action_ir_anchor_hints = self._action_ir_anchor_hints
        allowed = '\n'.join((f'- {path}' for path in allowed_files)) or '- provide one allowed file first'
        bounded_previous = str(previous_output or '')[:8000]
        bounded_diagnostics = str(diagnostics or '')[:4000]
        anchor_hints = _action_ir_anchor_hints(root, allowed_files)
        return f'''Return BEAST Action IR JSON only. Do not include markdown, prose, or explanation.\n\nObjective: {objective or 'Convert the prior answer into a governed file edit.'}\nAllowed files:\n{allowed}\n\nSchema:\n{{"kind": "{ACTION_IR_KIND}", "objective": "...", "actions": [{{"type": "replace_exact", "target": {{"path": "relative/file.py", "anchor_ref": "A1"}}, "old": "exact old snippet", "new": "replacement for the complete anchor"}}]}}\n\nRules:\n1. Use only allowed files.\n2. Every source-edit action must include resolvable old/new snippets.\n3. Copy old exactly from the current file, or use one supplied target.anchor_ref and make new replace that complete anchor.\n4. If a short old snippet appears more than once, use one of the supplied target.anchor_ref values; never guess which duplicate occurrence to change.\n5. Emit the complete valid set of replace_exact actions required by the objective, including directly affected tests, callers, and configuration when they are in scope. Do not omit a required edit merely to keep the patch small.\n6. Emit at most one source-edit action per file. If a file needs several changes, use one complete anchor replacement that incorporates all of them; sequential edits to the same file are not accepted.\n7. Never return advice, markdown, placeholders, ellipses, or "rest unchanged" text.\n8. Return one JSON object and nothing else.\n9. Correct every validation diagnostic below without expanding scope.\n\n''' + (f'Validation diagnostics from the proposed files:\n{bounded_diagnostics}\n\n' if bounded_diagnostics else '') + (f'Exact snippets available in the allowed files. Prefer these snippets as old anchors:\n{anchor_hints}\n\n' if anchor_hints else '') + f'Previous answer to convert:\n{bounded_previous}'

    def _reject_incomplete_function_replacements(self, actions: list[Any]) -> str:
        """Reject a common model failure before it is rendered as a patch.

            A bare ``def …:`` old snippet plus a full replacement function only
            replaces the header, leaving the old body behind.  It is not a
            reviewable refactor even if it happens to parse, and is exactly the
            shape emitted when a model runs out of room while rewriting a method.
            """
        for index, raw in enumerate(actions):
            if not isinstance(raw, dict):
                continue
            old = str(raw.get('old') or '').strip()
            new = str(raw.get('new') or '').strip()
            if re.fullmatch('(?:async\\s+)?def\\s+[A-Za-z_]\\w*\\s*\\([^\\n]*\\)\\s*(?:->[^\\n:]+)?\\s*:', old) and re.match('(?:async\\s+)?def\\s+[A-Za-z_]\\w*\\s*\\(', new) and ('\n' in new):
                return f"action {raw.get('id') or raw.get('op_id') or f'a{index + 1}'} uses only a function header as its old anchor. The model must replace the complete anchored function, not append a new body after its header."
        return ''

    def _extract_single_replacement_from_advisory(self, output: str) -> str:
        text = str(output or '').strip()
        fences = re.findall(r"```[A-Za-z0-9_+.-]*\n([\s\S]*?)```", text)
        candidates = [candidate.strip('\n') for candidate in fences if candidate.strip()]
        if len(candidates) == 1:
            return candidates[0]
        return ''

    def _compile_selection_fallback_sourceplan(self, root: Path, *, output: str, provider: str, selection: dict[str, Any], objective: str='') -> dict[str, Any]:
        path = str(selection.get('path') or '').strip()
        old = str(selection.get('text') or '')
        if not path or not old.strip():
            return {'ok': False, 'status': 'selection_fallback_unavailable', 'error': 'No exact selected range was supplied.'}
        target = _safe_relative(root, path)
        if target is None or not target.is_file():
            return {'ok': False, 'status': 'selection_fallback_unavailable', 'error': f'Selected file is unavailable: {path}'}
        try:
            original = target.read_text(encoding='utf-8')
        except Exception as exc:
            return {'ok': False, 'status': 'selection_fallback_unavailable', 'error': str(exc)}
        match_count = original.count(old)
        if match_count != 1:
            return {'ok': False, 'status': 'selection_fallback_ambiguous', 'error': f'Selected text matched {match_count} time(s); fallback requires one exact selected range.'}
        new = self._extract_single_replacement_from_advisory(output)
        if not new or new == old:
            return {'ok': False, 'status': 'selection_fallback_unavailable', 'error': 'The advisory response did not contain exactly one replacement code block.'}
        expected_hash = 'sha256:' + hashlib.sha256(original.encode('utf-8')).hexdigest()
        plan_id = 'ide_sel_' + hashlib.sha256(f'{root}|{provider}|{path}|{time.time()}'.encode('utf-8')).hexdigest()[:12]
        operation = {
            'op_id': 'selection_001',
            'op': 'replace_exact',
            'path': path,
            'old': old,
            'new': new,
            'description': 'Compiled from one exact editor selection and one replacement code block',
            'beast_managed': False,
            'source_edit': True,
            'provider_generated': True,
            'selected': True,
            'expected_hash': expected_hash,
            'resolver': 'selection.exact_range_fallback',
            'selection': selection.get('range') if isinstance(selection.get('range'), dict) else {},
        }
        plan = {
            'plan_id': plan_id,
            'kind': 'beast_ide_agent_selection_sourceplan',
            'status': 'draft_requires_approval',
            'objective': str(objective or 'Apply agent response to exact selected range'),
            'provider': provider,
            'workspace': str(root),
            'risk_level': 'high',
            'approval_required': True,
            'provider_generated': True,
            'requires_operator_translation': False,
            'output_evidence': {
                'contract': 'selection_exact_fallback.v1',
                'selection_unique': True,
                'single_replacement_code_block': True,
                'diff_compiled': True,
                'compiled_operation_count': 1,
            },
            'context_files': [{'path': path}],
            'files_allowed': [path],
            'files_blocked': [],
            'operations': [operation],
            'selected_operations': ['selection_001'],
            'apply_policy': {
                'source_edits_require': ['unique selected range', 'expected hash', 'approval', 'verification', 'rollback'],
                'rollback_required': True,
                'run_py_compile': True,
                'run_tests': False,
            },
            'created_at': int(time.time()),
        }
        receipt = EvidenceBus(root).register(
            artifact_type='beast_ide_agent_selection_sourceplan',
            artifact_path=root / '.beast' / 'ide' / 'agent-selection-fallback',
            artifact_hash=self._json_hash(plan),
            source='desktop_ide',
            task_id=plan_id,
            status='compiled_selection_fallback',
            summary='Compiled one exact selected-range operation from agent advisory output',
            metadata={'operation_count': 1, 'provider': provider, 'path': path},
        )
        return {'ok': True, 'status': 'compiled_selection_fallback', 'plan': plan, 'operation_count': 1, 'evidence_receipt': receipt}

    def _compile_crystal_ir_sourceplan(self, root: Path, *, parsed: dict[str, Any], provider: str, objective: str = '') -> dict[str, Any]:
        """Translate validated Crystal IR into the existing IDE review boundary."""
        try:
            ir = compile_crystal_ir(parsed)
        except (CrystalIRValidationError, TypeError, ValueError) as exc:
            return {'ok': False, 'status': 'crystal_ir_rejected', 'error': str(exc), 'requires_operator_translation': True}
        target = _safe_relative(root, ir.target_file)
        if target is None or not target.is_file():
            return {'ok': False, 'status': 'crystal_ir_target_unavailable', 'error': f'Crystal IR target is unavailable: {ir.target_file}', 'requires_operator_translation': True}
        source = target.read_text(encoding='utf-8')
        residual = parsed.get('residual') if isinstance(parsed.get('residual'), dict) else {}
        old = str(parsed.get('old') or residual.get('old') or '')
        resolved = parsed.get('resolved_fields') if isinstance(parsed.get('resolved_fields'), dict) else {}
        new = str(parsed.get('new') or resolved.get('new') or residual.get('new') or '')
        if not old or not new:
            return {
                'ok': True,
                'status': 'crystal_ir_needs_residual',
                'crystal_ir': ir.to_dict(),
                'crystal_ir_digest': ir.digest(),
                'residual_request': {
                    'target': {'path': ir.target_file, 'symbol': ir.target_symbol},
                    'old': old,
                    'unresolved_fields': ['new'],
                    'slot_type': 'bounded_source_fragment',
                    'authority': ir.model_authority,
                },
                'mutation_authorized': False,
                'requires_operator_translation': False,
            }
        if source.count(old) != 1:
            return {'ok': False, 'status': 'crystal_ir_old_ambiguous', 'error': f'Crystal IR old snippet matched {source.count(old)} time(s)', 'crystal_ir_digest': ir.digest(), 'mutation_authorized': False}
        compiled = ResidualPatchCompiler().compile_crystal_ir(ir, old=old, new=new)
        action_ir = compiled['action_ir']
        action_ir['actions'][0]['target']['sha256'] = 'sha256:' + hashlib.sha256(source.encode('utf-8')).hexdigest()
        operation = {'op_id': 'crystal_001', 'op': 'replace_exact', 'path': ir.target_file, 'old': old, 'new': new, 'description': ir.objective, 'beast_managed': True, 'source_edit': True, 'provider_generated': False, 'selected': True, 'expected_hash': action_ir['actions'][0]['target']['sha256'], 'action_ir_type': 'crystal_ir.v1', 'symbol': ir.target_symbol, 'resolver': 'crystal_ir.patch_compiler'}
        plan_id = 'ide_crystal_' + hashlib.sha256(f'{root}|{provider}|{ir.digest()}|{time.time()}'.encode('utf-8')).hexdigest()[:12]
        plan = {'plan_id': plan_id, 'kind': 'beast_ide_crystal_ir_sourceplan', 'status': 'draft_requires_approval', 'objective': ir.objective or objective, 'provider': provider, 'workspace': str(root), 'risk_level': 'high', 'approval_required': True, 'provider_generated': False, 'requires_operator_translation': False, 'crystal_ir': ir.to_dict(), 'crystal_ir_digest': ir.digest(), 'action_ir': action_ir, 'operations': [operation], 'selected_operations': ['crystal_001'], 'files_allowed': list(ir.writable_files), 'files_blocked': [], 'output_evidence': {'contract': 'crystal.ir.v1', 'schema_valid': True, 'exact_old_unique': True, 'model_authority': ir.model_authority, 'mutation_authorized': False}, 'apply_policy': {'source_edits_require': ['approval', 'expected hash', 'syntax preflight', 'verification', 'rollback'], 'rollback_required': True, 'run_py_compile': True, 'run_tests': True}, 'created_at': int(time.time())}
        receipt = EvidenceBus(root).register(artifact_type='beast_ide_crystal_ir_sourceplan', artifact_path=root / '.beast' / 'ide' / 'crystal-ir-sourceplan', artifact_hash=self._json_hash(plan), source='desktop_ide', task_id=plan_id, status='compiled_crystal_ir', summary='Compiled validated Crystal IR into an approval-gated bounded SourcePlan', metadata={'provider': provider, 'crystal_ir_digest': ir.digest(), 'operation_count': 1})
        return {'ok': True, 'status': 'compiled_crystal_ir', 'plan': plan, 'operation_count': 1, 'evidence_receipt': receipt}

    def _normalize_execution_target(self, execution_target: str='', execution_target_payload: dict[str, Any] | None=None) -> dict[str, Any]:
        target = str(execution_target or 'local').strip().lower() or 'local'
        payload = execution_target_payload if isinstance(execution_target_payload, dict) else {}
        normalized: dict[str, Any] = {'kind': target, 'label': target.upper() if target != 'local' else 'Local workspace'}
        if target == 'ssh':
            normalized['host'] = str(payload.get('host') or '').strip()
            normalized['remote_root'] = str(payload.get('remoteRoot') or payload.get('remote_root') or payload.get('path') or '').strip()
            normalized['label'] = f"SSH {normalized['host'] or 'target'}".strip()
        elif target == 'container':
            normalized['container_id'] = str(payload.get('containerId') or payload.get('container_id') or payload.get('id') or payload.get('name') or '').strip()
            normalized['workspace_folder'] = str(payload.get('workspaceFolder') or payload.get('workspace_folder') or payload.get('path') or '').strip()
            normalized['label'] = f"Container {normalized['container_id'] or 'target'}".strip()
        else:
            normalized['kind'] = 'local'
            normalized['workspace_root'] = str(payload.get('root') or payload.get('workspace_root') or '').strip()
        if payload:
            normalized['payload'] = dict(payload)
        return normalized

    def _execution_target_validation_strategy(self, execution_target: str='', execution_target_payload: dict[str, Any] | None=None) -> dict[str, Any]:
        normalized = self._normalize_execution_target(execution_target, execution_target_payload)
        kind = str(normalized.get('kind') or 'local')
        strategy = {
            'execution_target': kind,
            'target': normalized,
            'isolated_workspace': True,
            'repair_prefers_existing_verifier_context': True,
            'mutations_still_require_sourceplan_apply': True,
        }
        if kind == 'ssh':
            strategy.update({
                'mode': 'isolated_remote_shadow',
                'summary': 'Validation replays requested checks in a temporary isolated workspace while preserving SSH target intent for later target-side verify/apply.',
                'target_side_followup_required': True,
            })
        elif kind == 'container':
            strategy.update({
                'mode': 'isolated_container_shadow',
                'summary': 'Validation replays requested checks in a temporary isolated workspace while preserving devcontainer target intent for later target-side verify/apply.',
                'target_side_followup_required': True,
            })
        else:
            strategy.update({
                'mode': 'isolated_local',
                'summary': 'Validation runs requested allowlisted checks in a temporary isolated local workspace before any governed apply.',
                'target_side_followup_required': False,
            })
        return strategy

    def _compile_agent_action_ir_sourceplan(self, root: Path, *, output: str, provider: str, requested_files: list[str], active_file: str='', objective: str='', expected_handoff_hash: str='', selection: dict[str, Any] | None=None, execution_target: str='local', execution_target_payload: dict[str, Any] | None=None) -> dict[str, Any]:
        _json_hash = self._json_hash
        _reject_incomplete_function_replacements = self._reject_incomplete_function_replacements
        allowed = [str(item) for item in requested_files if item]
        if active_file:
            allowed.insert(0, str(active_file))
        allowed = list(dict.fromkeys(allowed))
        parsed = _extract_json_object(output)
        if str(parsed.get('version') or '') == 'crystal.ir.v1':
            return self._compile_crystal_ir_sourceplan(root, parsed=parsed, provider=provider, objective=objective)
        is_action_ir = str(parsed.get('kind') or '') == ACTION_IR_KIND or isinstance(parsed.get('actions'), list)
        if not is_action_ir:
            if selection:
                fallback = self._compile_selection_fallback_sourceplan(root, output=output, provider=provider, selection=selection, objective=objective)
                if fallback.get('ok'):
                    return fallback
            return {'ok': False, 'status': 'not_action_ir', 'error': 'Agent output did not contain BEAST Action IR JSON. BEAST will ask the model for exact anchored old/new snippets; if one exact editor selection and one replacement code block are present, it can compile a selection-bounded patch automatically.', 'requires_operator_translation': True, 'missing_context_questions': ['Which exact file path and symbol/range should be edited?', 'What exact old snippet or anchor should be replaced?', 'Should BEAST draft a SourcePlan from the current editor selection instead?'], 'retry_options': [{'id': 'ask_for_action_ir', 'label': 'Ask agent for exact anchored old/new snippets'}, {'id': 'narrow_selection', 'label': 'Narrow editor selection and retry'}, {'id': 'sourceplan_from_selection', 'label': 'Use SourcePlan from selection'}], 'action_ir_schema': {'kind': ACTION_IR_KIND, 'actions': [{'type': 'replace_exact', 'target': {'path': 'relative/file.py'}, 'old': 'exact old snippet', 'new': 'replacement'}]}}
        raw_actions = parsed.get('actions') if isinstance(parsed.get('actions'), list) else []
        if not raw_actions:
            return {'ok': False, 'status': 'empty_action_ir', 'error': 'Agent returned Action IR without any file-edit actions.', 'requires_operator_translation': True, 'allowed_files': allowed, 'retry_options': [{'id': 'require_file_edit', 'label': 'Retry with at least one exact file edit'}]}
        raw_target_keys: list[str] = []
        for action in raw_actions:
            if not isinstance(action, dict):
                continue
            target = action.get('target') if isinstance(action.get('target'), dict) else action
            if not isinstance(target, dict):
                continue
            path = str(target.get('path') or '').strip()
            file_ref = str(target.get('file_ref') or target.get('ref') or '').strip()
            if path:
                raw_target_keys.append(f'path:{path}')
            elif file_ref:
                raw_target_keys.append(f'ref:{file_ref}')
        repeated_raw_targets = sorted({key for key in raw_target_keys if raw_target_keys.count(key) > 1})
        if repeated_raw_targets:
            labels = [key.split(':', 1)[1] for key in repeated_raw_targets]
            return {'ok': False, 'status': 'multiple_actions_same_file', 'error': 'Action IR contains sequential edits for the same file target: ' + ', '.join(labels[:5]) + '. Return one complete anchor replacement per file.', 'requires_operator_translation': True, 'allowed_files': allowed, 'retry_options': [{'id': 'consolidate_file_actions', 'label': 'Retry with one complete replacement per file'}]}
        incomplete_function_error = _reject_incomplete_function_replacements(raw_actions)
        if incomplete_function_error:
            return {'ok': False, 'status': 'incomplete_function_replacement', 'error': incomplete_function_error, 'requires_operator_translation': True, 'allowed_files': allowed, 'retry_options': [{'id': 'retry_complete_anchor', 'label': 'Retry with a complete function anchor'}]}
        if not allowed:
            return {'ok': False, 'status': 'no_allowed_files', 'error': 'No allowed context files were provided for Action IR resolution.', 'missing_context_questions': ['Select or open the file the agent is allowed to edit.'], 'retry_options': [{'id': 'include_active_file', 'label': 'Include active file and retry'}]}
        try:
            handoff_hash_bound_by_gateway = False
            if expected_handoff_hash and (not str(parsed.get('provider_handoff_hash') or parsed.get('handoff_hash') or '')):
                parsed['provider_handoff_hash'] = expected_handoff_hash
                parsed['handoff_hash'] = expected_handoff_hash
                handoff_hash_bound_by_gateway = True
            file_refs = build_file_references(root, allowed)
            action_ir = ActionIR.from_dict(parsed)
            resolved, non_mutating = resolve_action_ir(root, action_ir, file_refs, allowed, expected_handoff_hash=expected_handoff_hash)
            for item in resolved:
                target = _safe_relative(root, item.path)
                if target is None or not target.is_file():
                    continue
                try:
                    current_size = target.stat().st_size
                except OSError:
                    current_size = 0
                old_size = len(str(item.old).encode("utf-8"))
                new_size = len(str(item.new).encode("utf-8"))
                if current_size >= 1200 and old_size >= current_size * 0.80 and new_size >= current_size * 0.80:
                    raise ValueError(
                        f"{item.path}: whole-file replacement rejected; return one bounded symbol or statement edit instead"
                    )
            source_paths = [item.path for item in resolved]
            duplicate_paths = sorted({path for path in source_paths if source_paths.count(path) > 1})
            if duplicate_paths:
                return {'ok': False, 'status': 'multiple_actions_same_file', 'error': 'Action IR contains sequential edits for the same file: ' + ', '.join(duplicate_paths[:5]) + '. Return one complete anchor replacement per file so validation can preserve exact anchors.', 'requires_operator_translation': True, 'allowed_files': allowed, 'retry_options': [{'id': 'consolidate_file_actions', 'label': 'Retry with one complete replacement per file'}]}
            operations = []
            for index, item in enumerate(resolved):
                action = item.action
                operations.append({'op_id': str(action.id or f'a{index + 1}'), 'op': 'replace_exact', 'path': item.path, 'old': item.old, 'new': item.new, 'description': action.intent or f'Action IR {action.type} for {item.path}', 'beast_managed': False, 'source_edit': True, 'provider_generated': True, 'selected': True, 'expected_hash': item.expected_sha256, 'action_ir_id': action.id, 'action_ir_type': action.type, 'anchor_ref': action.target.anchor_ref, 'symbol': action.target.symbol, 'resolver': 'action_ir.resolve_action_ir'})
            if not operations:
                return {'ok': False, 'status': 'no_resolved_edits', 'error': 'Action IR did not resolve to any reviewable file edits.', 'requires_operator_translation': True, 'allowed_files': allowed, 'retry_options': [{'id': 'require_exact_edit', 'label': 'Retry against the current file contents'}]}
            plan_id = 'ide_air_' + hashlib.sha256(f'{root}|{provider}|{time.time()}'.encode('utf-8')).hexdigest()[:12]
            plan = {'plan_id': plan_id, 'kind': 'beast_ide_agent_action_ir_sourceplan', 'status': 'draft_requires_approval', 'objective': str(action_ir.objective or objective or 'Apply agent Action IR through BEAST IDE'), 'provider': provider, 'provider_handoff_hash': expected_handoff_hash, 'workspace': str(root), 'risk_level': 'high', 'approval_required': True, 'provider_generated': True, 'requires_operator_translation': False, 'action_ir': action_ir.to_dict(), 'execution_target': str(execution_target or 'local'), 'execution_target_payload': dict(execution_target_payload or {}), 'output_evidence': {'contract': ACTION_IR_KIND, 'schema_valid': True, 'path_valid': True, 'operation_valid': True, 'diff_compiled': True, 'compiled_operation_count': len(operations), 'provider_handoff_hash_bound_by_gateway': handoff_hash_bound_by_gateway, 'execution_target_validation_strategy': self._execution_target_validation_strategy(execution_target, execution_target_payload)}, 'non_mutating_requests': [item.to_dict() for item in non_mutating], 'context_files': [{'path': path} for path in allowed], 'files_allowed': allowed, 'files_blocked': [], 'operations': operations, 'selected_operations': [op['op_id'] for op in operations], 'apply_policy': {'source_edits_require': ['selected file', 'expected hash', 'approval', 'verification', 'rollback'], 'rollback_required': True, 'run_py_compile': True, 'run_tests': False}, 'created_at': int(time.time())}
            receipt = EvidenceBus(root).register(artifact_type='beast_ide_agent_action_ir_sourceplan', artifact_path=root / '.beast' / 'ide' / 'agent-action-ir', artifact_hash=_json_hash(plan), source='desktop_ide', task_id=plan_id, status='compiled_action_ir', summary=f'Compiled {len(operations)} Action IR operation(s) from agent output', metadata={'operation_count': len(operations), 'provider': provider, 'provider_handoff_hash': expected_handoff_hash, 'provider_handoff_hash_bound_by_gateway': handoff_hash_bound_by_gateway})
            return {'ok': True, 'status': 'compiled_action_ir', 'plan': plan, 'operation_count': len(operations), 'evidence_receipt': receipt}
        except Exception as exc:
            if selection:
                fallback = self._compile_selection_fallback_sourceplan(root, output=output, provider=provider, selection=selection, objective=objective)
                if fallback.get('ok'):
                    fallback['recovered_from'] = {'status': 'action_ir_rejected', 'error': str(exc)}
                    return fallback
            return {'ok': False, 'status': 'action_ir_rejected', 'error': str(exc), 'requires_operator_translation': True, 'allowed_files': allowed, 'missing_context_questions': ['Does the Action IR old snippet exactly match the current file?', 'Is the target file included in the allowed context files?', 'Would a symbol-scoped range avoid stale or ambiguous context?'], 'retry_options': [{'id': 'reload_context', 'label': 'Reload file/context and retry'}, {'id': 'ask_for_exact_old', 'label': 'Ask agent for exact old/new snippets'}, {'id': 'sourceplan_from_selection', 'label': 'Draft from current selection'}]}

    def _validate_agent_sourceplan(self, root: Path, plan: dict[str, Any], *, run_isolated_verifier: bool=False, execution_target: str='local', execution_target_payload: dict[str, Any] | None=None) -> dict[str, Any]:
        """Validate proposed source text without mutating or executing the workspace."""
        _agent_validation_commands = self._agent_validation_commands
        _run_isolated_agent_verifiers = self._run_isolated_agent_verifiers
        target_kind = str(execution_target or plan.get('execution_target') or 'local')
        target_payload = execution_target_payload if isinstance(execution_target_payload, dict) else plan.get('execution_target_payload') if isinstance(plan.get('execution_target_payload'), dict) else {}
        validation_strategy = self._execution_target_validation_strategy(target_kind, target_payload)
        operations = plan.get('operations') if isinstance(plan.get('operations'), list) else []
        proposed: dict[str, str] = {}
        checks: list[dict[str, Any]] = []
        failures: list[str] = []
        for operation in operations[:100]:
            rel = str(operation.get('path') or '')
            target = _safe_relative(root, rel)
            if target is None or not target.is_file():
                failures.append(f"{rel or '<missing>'}: target file is unavailable")
                continue
            if rel not in proposed:
                try:
                    proposed[rel] = target.read_text(encoding='utf-8')
                except Exception as exc:
                    failures.append(f'{rel}: {exc}')
                    continue
            old = str(operation.get('old') if operation.get('old') is not None else operation.get('old_text') or '')
            new = str(operation.get('new') if operation.get('new') is not None else operation.get('new_text') or '')
            if not old or proposed[rel].count(old) != 1:
                failures.append(f"{rel}: operation {operation.get('op_id') or '?'} no longer has one exact anchor")
                continue
            proposed[rel] = proposed[rel].replace(old, new, 1)
        node = shutil.which('node')
        syntax_checked = 0
        for rel, source in proposed.items():
            content_errors = []
            if '\x00' in source:
                content_errors.append('NUL byte present')
            if re.search('^(?:<<<<<<< |=======\\s*$|>>>>>>> )', source, re.MULTILINE):
                content_errors.append('unresolved conflict marker present')
            content_passed = not content_errors
            checks.append({'path': rel, 'kind': 'content-safety', 'passed': content_passed, 'message': '; '.join(content_errors) or 'No binary or conflict markers'})
            if not content_passed:
                failures.extend((f'{rel}: {item}' for item in content_errors))
            suffix = Path(rel).suffix.lower()
            try:
                if suffix == '.py':
                    ast.parse(source, filename=rel)
                    checks.append({'path': rel, 'kind': 'python-ast', 'passed': True, 'message': 'Python syntax parsed'})
                    syntax_checked += 1
                elif suffix == '.json':
                    json.loads(source)
                    checks.append({'path': rel, 'kind': 'json-parse', 'passed': True, 'message': 'JSON parsed'})
                    syntax_checked += 1
                elif suffix in {'.js', '.cjs', '.mjs'} and node:
                    with tempfile.NamedTemporaryFile('w', suffix=suffix, encoding='utf-8', delete=False) as handle:
                        handle.write(source)
                        temp_name = handle.name
                    try:
                        result = subprocess.run([node, '--check', temp_name], text=True, capture_output=True, timeout=8, check=False)
                    finally:
                        Path(temp_name).unlink(missing_ok=True)
                    if result.returncode != 0:
                        raise SyntaxError((result.stderr or result.stdout or 'JavaScript syntax check failed').strip()[:1000])
                    checks.append({'path': rel, 'kind': 'node-check', 'passed': True, 'message': 'JavaScript syntax parsed'})
                    syntax_checked += 1
            except (SyntaxError, json.JSONDecodeError, subprocess.SubprocessError, OSError) as exc:
                message = str(exc).replace('\n', ' ')[:1000]
                kind = 'python-ast' if suffix == '.py' else 'json-parse' if suffix == '.json' else 'node-check'
                checks.append({'path': rel, 'kind': kind, 'passed': False, 'message': message})
                failures.append(f'{rel}: {message}')
        requested = [str(item) for item in (plan.get('action_ir') or {}).get('verify') or [] if item]
        for item in plan.get('non_mutating_requests') or []:
            if not isinstance(item, dict) or str(item.get('type') or '') != 'run_verifier':
                continue
            parameters = item.get('parameters') if isinstance(item.get('parameters'), dict) else {}
            command = str(parameters.get('command') or item.get('command') or '').strip()
            if command:
                requested.append(command)
        if run_isolated_verifier:
            isolated = _run_isolated_agent_verifiers(root, proposed, requested)
        else:
            commands = _agent_validation_commands(root, proposed, requested)
            rows = [{'path': '', 'kind': 'isolated-verifier', 'passed': True, 'status': 'approval_required', 'command': str(command.get('display') or '<verifier>'), 'message': 'Awaiting operator approval for an isolated verifier run', 'isolated': True} for command in commands[:6]]
            isolated = {'checks': rows, 'failures': [], 'summary': {'status': 'approval_required' if rows else 'skipped', 'passed': 0, 'failed': 0, 'skipped': 0, 'commands': [{'command': row['command'], 'status': row['status'], 'message': row['message']} for row in rows]}}
        checks.extend(isolated['checks'])
        failures.extend(isolated['failures'])
        status = 'failed' if failures else 'passed' if syntax_checked == len(proposed) and proposed else 'partial'
        return {'ok': not failures and bool(proposed), 'status': status, 'file_count': len(proposed), 'syntax_checked': syntax_checked, 'check_count': len(checks), 'checks': checks, 'failures': failures[:20], 'requested_verifiers': requested[:20], 'isolated_verifiers': isolated['summary'], 'execution_target': target_kind, 'execution_target_payload': dict(target_payload), 'validation_strategy': validation_strategy, 'command_policy': f"allowlisted verifier commands run only after operator approval and only in a temporary isolated workspace; unsupported commands are recorded as skipped. target strategy: {validation_strategy.get('mode')}"}

    def _run_isolated_agent_verifiers(self, root: Path, proposed: dict[str, str], requested: list[str]) -> dict[str, Any]:
        _agent_validation_commands = self._agent_validation_commands
        _copy_agent_verifier_input = self._copy_agent_verifier_input
        checks: list[dict[str, Any]] = []
        failures: list[str] = []
        if not proposed:
            return {'checks': checks, 'failures': failures, 'summary': {'status': 'skipped', 'passed': 0, 'failed': 0, 'skipped': 0, 'commands': []}}
        commands = _agent_validation_commands(root, proposed, requested)
        if not commands:
            return {'checks': checks, 'failures': failures, 'summary': {'status': 'skipped', 'passed': 0, 'failed': 0, 'skipped': 0, 'commands': []}}
        with tempfile.TemporaryDirectory(prefix='beast-ide-agent-verify-') as temp_name:
            temp_root = Path(temp_name)
            for rel, source in proposed.items():
                target = _safe_relative(temp_root, rel)
                if target is None:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(source, encoding='utf-8')
            for command in commands[:6]:
                for rel in command.get('extra_inputs') or []:
                    _copy_agent_verifier_input(root, temp_root, str(rel))
                if command.get('skipped'):
                    checks.append({'path': '', 'kind': 'isolated-verifier', 'passed': True, 'status': 'skipped', 'command': command['display'], 'message': command['skipped'], 'isolated': True})
                    continue
                try:
                    result = subprocess.run(command['argv'], cwd=temp_root, text=True, capture_output=True, timeout=command.get('timeout', 12), check=False, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
                    output = ((result.stdout or '') + ('\n' if result.stdout and result.stderr else '') + (result.stderr or '')).strip()
                    passed = result.returncode == 0
                    check = {'path': '', 'kind': 'isolated-verifier', 'passed': passed, 'status': 'passed' if passed else 'failed', 'command': command['display'], 'returncode': result.returncode, 'message': (output or 'Verifier completed')[:1600], 'isolated': True}
                    checks.append(check)
                    if not passed:
                        failures.append(f"{command['display']}: {(output or f'exited {result.returncode}')[:800]}")
                except (subprocess.SubprocessError, OSError) as exc:
                    message = str(exc).replace('\n', ' ')[:800]
                    checks.append({'path': '', 'kind': 'isolated-verifier', 'passed': False, 'status': 'failed', 'command': command['display'], 'message': message, 'isolated': True})
                    failures.append(f"{command['display']}: {message}")
        passed = sum((1 for item in checks if item.get('kind') == 'isolated-verifier' and item.get('status') == 'passed'))
        failed = sum((1 for item in checks if item.get('kind') == 'isolated-verifier' and item.get('status') == 'failed'))
        skipped = sum((1 for item in checks if item.get('kind') == 'isolated-verifier' and item.get('status') == 'skipped'))
        status = 'failed' if failed else 'passed' if passed else 'skipped'
        return {'checks': checks, 'failures': failures, 'summary': {'status': status, 'passed': passed, 'failed': failed, 'skipped': skipped, 'commands': [{'command': item.get('command'), 'status': item.get('status'), 'message': item.get('message', '')[:240]} for item in checks if item.get('kind') == 'isolated-verifier'][:6]}}

    def _agent_validation_commands(self, root: Path, proposed: dict[str, str], requested: list[str]) -> list[dict[str, Any]]:
        _normalize_agent_verifier_command = self._normalize_agent_verifier_command
        commands: list[dict[str, Any]] = []
        py_files = [rel for rel in proposed if Path(rel).suffix.lower() == '.py']
        js_files = [rel for rel in proposed if Path(rel).suffix.lower() in {'.js', '.cjs', '.mjs'}]
        if py_files:
            commands.append({'display': 'python -m py_compile ' + ' '.join(py_files[:24]), 'argv': [sys.executable, '-m', 'py_compile', *py_files[:24]], 'timeout': 12, 'extra_inputs': []})
        node = shutil.which('node')
        for rel in js_files[:8]:
            if node:
                commands.append({'display': f'node --check {rel}', 'argv': [node, '--check', rel], 'timeout': 8, 'extra_inputs': []})
        for command in requested[:4]:
            commands.append(_normalize_agent_verifier_command(root, proposed, command))
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for command in commands:
            key = str(command.get('display') or command.get('argv'))
            if key in seen:
                continue
            seen.add(key)
            unique.append(command)
        return unique

    def _normalize_agent_verifier_command(self, root: Path, proposed: dict[str, str], command: str) -> dict[str, Any]:
        _bounded_pytest_verifier = self._bounded_pytest_verifier
        display = ' '.join(str(command or '').split())[:500]
        try:
            parts = shlex.split(command)
        except ValueError as exc:
            return {'display': display or '<invalid verifier>', 'skipped': f'could not parse verifier command: {exc}', 'extra_inputs': []}
        if not parts:
            return {'display': '<empty verifier>', 'skipped': 'empty verifier command', 'extra_inputs': []}
        executable = Path(parts[0]).name
        if executable in {'python', 'python3'} and len(parts) >= 4 and (parts[1] == '-m') and (parts[2] == 'py_compile'):
            paths = [item for item in parts[3:] if _safe_relative(root, item) is not None]
            if paths and all((path in proposed for path in paths)):
                return {'display': display, 'argv': [sys.executable, '-m', 'py_compile', *paths[:24]], 'timeout': 12, 'extra_inputs': []}
            return {'display': display, 'skipped': 'py_compile verifier must target proposed files only', 'extra_inputs': []}
        if executable in {'node', 'nodejs'} and len(parts) == 3 and (parts[1] == '--check'):
            node = shutil.which('node') or shutil.which('nodejs')
            rel = parts[2]
            if node and rel in proposed and (_safe_relative(root, rel) is not None):
                return {'display': display, 'argv': [node, '--check', rel], 'timeout': 8, 'extra_inputs': []}
            return {'display': display, 'skipped': 'node --check verifier must target one proposed JavaScript file', 'extra_inputs': []}
        if executable in {'pytest', 'py.test'} or (executable in {'python', 'python3'} and len(parts) >= 3 and (parts[1] == '-m') and (parts[2] == 'pytest')):
            normalized = _bounded_pytest_verifier(root, proposed, parts)
            return {**normalized, 'display': display}
        return {'display': display, 'skipped': 'verifier command is outside the BEAST IDE isolated allowlist', 'extra_inputs': []}

    def _bounded_pytest_verifier(self, root: Path, proposed: dict[str, str], parts: list[str]) -> dict[str, Any]:
        pytest = shutil.which('pytest')
        prefix = [sys.executable, '-m', 'pytest'] if parts[:3] == [parts[0], '-m', 'pytest'] else [pytest] if pytest else [sys.executable, '-m', 'pytest']
        args = parts[3:] if len(parts) >= 3 and parts[1] == '-m' and (parts[2] == 'pytest') else parts[1:]
        allowed_flags = {'-q', '-x', '-s', '--tb=short', '--disable-warnings', '--maxfail=1'}
        targets: list[str] = []
        filtered: list[str] = []
        for arg in args:
            if arg in allowed_flags:
                filtered.append(arg)
                continue
            if arg.startswith('-'):
                return {'skipped': f'pytest option {arg} is not allowed in isolated validation', 'extra_inputs': []}
            safe = _safe_relative(root, arg)
            if safe is None or not safe.exists():
                return {'skipped': f'pytest target {arg} is unavailable or unsafe', 'extra_inputs': []}
            if safe.is_dir():
                return {'skipped': f'pytest target {arg} is too broad; choose explicit test files', 'extra_inputs': []}
            targets.append(arg)
            filtered.append(arg)
        if not targets:
            return {'skipped': 'pytest verifier requires explicit test file targets', 'extra_inputs': []}
        extras = list(dict.fromkeys([*targets, *proposed.keys(), 'pytest.ini', 'pyproject.toml', 'setup.cfg', 'conftest.py']))
        return {'argv': [*prefix, *filtered], 'timeout': 20, 'extra_inputs': extras}

    def _copy_agent_verifier_input(self, root: Path, temp_root: Path, rel: str) -> None:
        source = _safe_relative(root, rel)
        target = _safe_relative(temp_root, rel)
        if source is None or target is None or (not source.exists()) or (not source.is_file()):
            return
        if target.exists() or source.stat().st_size > 300000:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    def _request_base_url(self, request: Request) -> str:
        try:
            base = request.base_url
            hostname = str(getattr(base, "hostname", "") or "").strip().lower()
            scheme = str(getattr(base, "scheme", "http") or "http")
            port = int(getattr(base, "port", 0) or (443 if scheme == "https" else 80))
            if hostname in {"127.0.0.1", "localhost", "::1"}:
                return str(base).rstrip('/')
            return f"{scheme}://127.0.0.1:{port}"
        except Exception:
            return "http://127.0.0.1:8000"

    def _agent_related_context(self, root: Path, objective: str, selected_files: list[str], limit: int=12) -> list[str]:
        """Return a small, workspace-bounded context expansion for an IDE agent.

            The renderer's context picker is useful for explicit scope, but a coding
            agent also needs the directly related implementation/test files that a
            VS Code user expects it to inspect.  This remains advisory context: all
            returned paths must already exist under the workspace and every edit is
            still constrained to this resulting allow-list and SourcePlan review.
            """
        code_cortex_router = self.code_cortex_router
        discovered: list[str] = []

        def add(value: Any) -> None:
            candidate = str(value or '').replace('\\', '/').strip()
            target = _safe_relative(root, candidate)
            if target is None or not target.is_file():
                return
            relative = target.relative_to(root).as_posix()
            if relative not in discovered:
                discovered.append(relative)
        for path in selected_files:
            add(path)
        try:
            editing = code_cortex_router.get_editing_context(root, objective, limit=max(1, min(limit, 24)))
            for row in editing.get('files') or editing.get('results') or []:
                add(row if isinstance(row, str) else row.get('path') if isinstance(row, dict) else '')
            for row in editing.get('symbols') or []:
                if isinstance(row, dict):
                    add(row.get('path') or row.get('file'))
            for path in selected_files[:4]:
                dependents = code_cortex_router.get_dependents(root, path, limit=max(1, min(limit, 24)))
                for row in dependents.get('dependents') or dependents.get('related_files') or dependents.get('files') or dependents.get('results') or []:
                    add(row if isinstance(row, str) else row.get('path') or row.get('file') or row.get('dependent') if isinstance(row, dict) else '')
        except Exception:
            pass
        return discovered[:max(1, min(limit, 24))]

    def _sanitize_model_history(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Remove terminal control bytes from conversational history only.

            Exact source files and Action-IR anchors are deliberately not touched:
            altering them would make otherwise valid patch anchors unsafe.
            """
        _ANSI_ESCAPE = self._ANSI_ESCAPE
        cleaned: list[dict[str, Any]] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            item = dict(row)
            content = item.get('content')
            if isinstance(content, str):
                item['content'] = _ANSI_ESCAPE.sub('', content).replace('\r', '')
            cleaned.append(item)
        return cleaned

    def _skill_recipe_suggestions(self, root: Path, objective: str, *, limit: int=3) -> list[dict[str, Any]]:
        """Return small, verified-recipe metadata for an optional model hint.

            Skills are never executable instructions on this path.  This function
            intentionally returns only identifiers, quality signals, and a short
            description; a model cannot use a historical skill to widen files,
            tools, or write authority.
            """
        terms = {item.lower() for item in re.findall('[A-Za-z_][A-Za-z0-9_/-]*', objective) if len(item) > 2}
        try:
            skills = SkillTree(data_dir=str(root / '.beast' / 'intelligence' / 'skills')).list_skills(limit=100)
        except Exception:
            return []
        ranked: list[tuple[int, dict[str, Any]]] = []
        for skill in skills:
            metadata = skill.get('metadata') if isinstance(skill.get('metadata'), dict) else {}
            validation = metadata.get('validation') if isinstance(metadata.get('validation'), dict) else {}
            verified = validation.get('status') in {'passed', 'passed_with_warnings'} or metadata.get('verified') is True
            if not verified or float(skill.get('success_rate') or 0.0) < 0.8:
                continue
            text = ' '.join((str(skill.get('name') or ''), str(skill.get('category') or ''), str(metadata.get('description') or ''))).lower()
            overlap = sum((1 for term in terms if term in text))
            if overlap:
                ranked.append((overlap, {'skill_id': str(skill.get('id') or ''), 'name': str(skill.get('name') or ''), 'category': str(skill.get('category') or ''), 'success_rate': round(float(skill.get('success_rate') or 0.0), 3), 'usage_count': int(skill.get('usage_count') or 0), 'description': str(metadata.get('description') or '')[:280], 'verified': True, 'authority': 'advisory_recipe_only'}))
        return [item for _score, item in sorted(ranked, key=lambda row: (-row[0], -row[1]['success_rate'], -row[1]['usage_count']))[:max(1, min(limit, 8))]]

    def _classify_related(self, path: str) -> str:
        lowered = path.lower()
        if any((part in lowered for part in ('test', 'spec', '__tests__'))):
            return 'test'
        if any((part in lowered for part in ('route', 'router', 'endpoint', 'api'))):
            return 'route'
        if any((part in lowered for part in ('controller', 'handler', 'view', 'page'))):
            return 'surface'
        if any((part in lowered for part in ('model', 'schema', 'entity'))):
            return 'model'
        return 'related'

    def _symbol_outline_for_text(self, path: str, text: str, max_symbols: int=300) -> list[dict[str, Any]]:
        symbols: list[dict[str, Any]] = []
        suffix = Path(path).suffix.lower()
        if suffix == '.py':
            try:
                tree = ast.parse(text)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                        kind = 'class' if isinstance(node, ast.ClassDef) else 'async_function' if isinstance(node, ast.AsyncFunctionDef) else 'function'
                        symbols.append({'name': node.name, 'kind': kind, 'line_start': int(getattr(node, 'lineno', 1)), 'line_end': int(getattr(node, 'end_lineno', getattr(node, 'lineno', 1))), 'col_start': int(getattr(node, 'col_offset', 0)) + 1, 'signature': ''})
            except Exception:
                symbols = []
        if not symbols:
            patterns = [('class', re.compile('^\\s*class\\s+([A-Za-z_][\\w]*)', re.MULTILINE)), ('function', re.compile('^\\s*(?:async\\s+def|def|function)\\s+([A-Za-z_][\\w]*)', re.MULTILINE)), ('export', re.compile('^\\s*export\\s+(?:async\\s+)?(?:function|class|const|let)\\s+([A-Za-z_][\\w]*)', re.MULTILINE))]
            line_offsets = [0]
            for match in re.finditer('\\n', text):
                line_offsets.append(match.end())

            def line_for_offset(offset: int) -> int:
                line = 1
                for index, start in enumerate(line_offsets):
                    if start > offset:
                        break
                    line = index + 1
                return line
            for kind, pattern in patterns:
                for match in pattern.finditer(text):
                    line = line_for_offset(match.start())
                    symbols.append({'name': match.group(1), 'kind': kind, 'line_start': line, 'line_end': line, 'col_start': max(1, match.start(1) - text.rfind('\n', 0, match.start(1))), 'signature': match.group(0).strip()})
        symbols.sort(key=lambda item: (int(item.get('line_start') or 0), str(item.get('name') or '')))
        return symbols[:max(1, min(int(max_symbols), 1000))]

    def _timeline_entry(self, kind: str, title: str, timestamp: Any, *, status: str='', detail: str='', ref: str='', payload: dict[str, Any] | None=None) -> dict[str, Any]:
        try:
            ts = float(timestamp or 0)
        except (TypeError, ValueError):
            ts = 0.0
        return {'kind': kind, 'title': title, 'status': status, 'detail': detail, 'ref': ref, 'timestamp': ts, 'payload': payload or {}}

    def _json_hash(self, payload: Any) -> str:
        body = json.dumps(payload, sort_keys=True, default=str)
        return 'sha256:' + hashlib.sha256(body.encode('utf-8', errors='replace')).hexdigest()

    def _sourceplan_action_contract(self, plan: dict[str, Any], scorecard: dict[str, Any]) -> dict[str, Any]:
        operations = plan.get('operations') if isinstance(plan.get('operations'), list) else []
        files = sorted({str(op.get('path') or '') for op in operations if isinstance(op, dict) and op.get('path')})
        policy = plan.get('apply_policy') if isinstance(plan.get('apply_policy'), dict) else {}
        return {'beast_object_type': 'beast_ide_action_contract_summary', 'version': '1.0', 'plan_id': str(plan.get('plan_id') or ''), 'intent': str(plan.get('objective') or ''), 'risk': str(plan.get('risk_level') or scorecard.get('risk') or scorecard.get('risk_level') or 'unknown'), 'status': str(plan.get('status') or 'draft'), 'approval_required': bool(plan.get('approval_required', True)), 'sandbox_or_worktree_first': bool(plan.get('requires_worktree') or plan.get('worktree_task_id') or policy.get('worktree_required')), 'allowed_write_roots': [str(plan.get('workspace') or '')], 'files_allowed': list(plan.get('files_allowed') or files), 'blocked_actions': ['direct_file_write', 'git_push', 'deploy', 'direct_crystalization_write', 'ungoverned_shell'], 'verification_required': True, 'rollback_required': bool(policy.get('rollback_required', True)), 'evidence_required': True, 'rules': ['Approval records operator intent; it does not bypass SourcePlan checks.', 'Apply requires selected operations, expected hashes, verification, rollback, and evidence closure.', 'Workspace graph context is advisory; receipts and rollback snapshots are authoritative.']}

    def _operation_ledger(self, plan: dict[str, Any], preview: dict[str, Any], verification: dict[str, Any]) -> dict[str, Any]:
        _json_hash = self._json_hash
        plan_ops = plan.get('operations') if isinstance(plan.get('operations'), list) else []
        preview_ops = preview.get('operations') if isinstance(preview.get('operations'), list) else []
        selected_ids = {str(item) for item in (plan.get('selected_operations') if isinstance(plan.get('selected_operations'), list) else [])}
        if not selected_ids:
            selected_ids = {str(op.get('op_id') or f'op_{index + 1}') for index, op in enumerate(plan_ops) if isinstance(op, dict) and op.get('selected', True) is not False}
        preview_by_id = {str(op.get('op_id') or op.get('operation_id') or f'op_{index + 1}'): op for index, op in enumerate(preview_ops) if isinstance(op, dict)}
        verify_errors = verification.get('errors') if isinstance(verification.get('errors'), list) else []
        rows = []
        for index, op in enumerate(plan_ops):
            if not isinstance(op, dict):
                continue
            op_id = str(op.get('op_id') or op.get('operation_id') or f'op_{index + 1}')
            preview_op = preview_by_id.get(op_id, {})
            before = str(op.get('old') or op.get('old_text') or preview_op.get('old_text') or '')
            after = str(op.get('new') or op.get('new_text') or op.get('content') or preview_op.get('new_text') or '')
            stale_reason = str(preview_op.get('stale_reason') or op.get('stale_reason') or '')
            selected = op_id in selected_ids
            rows.append({'operation_id': op_id, 'selected': selected, 'status': 'stale' if stale_reason else 'selected' if selected else 'skipped', 'path': str(op.get('path') or preview_op.get('path') or ''), 'operation': str(op.get('op') or op.get('type') or preview_op.get('op') or 'edit'), 'description': str(op.get('description') or preview_op.get('description') or ''), 'before_sha256': _hash_text(before) if before else str(op.get('expected_hash') or ''), 'after_sha256': _hash_text(after) if after else '', 'stale_reason': stale_reason, 'rollback_required': True, 'verification_status': 'blocked' if stale_reason or verify_errors else 'pending' if not verification else 'passed', 'evidence_status': 'pending', 'hunk_count': len(preview_op.get('hunks') or preview_op.get('diff_lines') or [])})
        blocked = preview.get('blocked') if isinstance(preview.get('blocked'), list) else []
        return {'beast_object_type': 'beast_ide_sourceplan_operation_ledger', 'version': '1.0', 'plan_id': str(plan.get('plan_id') or ''), 'operation_count': len(rows), 'selected_count': len([row for row in rows if row.get('selected')]), 'stale_count': len([row for row in rows if row.get('stale_reason')]), 'blocked_count': len(blocked), 'operations': rows, 'blocked_operations': blocked, 'ledger_hash': _json_hash({'plan_id': plan.get('plan_id'), 'operations': rows, 'blocked': blocked})}

    def _receipt_command(self, receipt: dict[str, Any], action: str) -> str:
        receipt_id = str(receipt.get('receipt_id') or '')
        task_id = str(receipt.get('task_id') or '')
        templates = {'sourceplan.apply': f'Use receipt {receipt_id} as evidence before SourcePlan apply.', 'sourceplan.rollback': f'Use receipt {receipt_id} to inspect rollback/evidence before rollback.', 'worktree.promote': f"Use receipt {receipt_id} while promoting worktree task {task_id or '<task-id>'}.", 'terminal.execute': f"Use receipt {receipt_id} as command evidence for task {task_id or '<task-id>'}."}
        return templates.get(action, f'Inspect receipt {receipt_id}')

    def _render_runbook_markdown(self, data: dict[str, Any]) -> str:
        lines = [f"# BEAST Mission Runbook: {data.get('runbook_id')}", '', f"- Workspace: `{data.get('workspace_root')}`", f"- Objective: {data.get('objective') or 'BEAST desktop mission'}", f"- Created: {data.get('created_at')}", f"- Active file: `{data.get('active_file') or 'none'}`", '', '## Summary', '']
        summary = data.get('summary') if isinstance(data.get('summary'), dict) else {}
        for key, value in summary.items():
            lines.append(f'- {key}: {value}')
        contract = data.get('action_contract') if isinstance(data.get('action_contract'), dict) else {}
        if contract:
            lines.extend(['', '## Action Contract', ''])
            for key in ('plan_id', 'intent', 'risk', 'status', 'approval_required', 'rollback_required', 'evidence_required'):
                lines.append(f'- {key}: {contract.get(key)}')
        ledger = data.get('operation_ledger') if isinstance(data.get('operation_ledger'), dict) else {}
        rows = ledger.get('operations') if isinstance(ledger.get('operations'), list) else []
        lines.extend(['', '## SourcePlan Operations', ''])
        if rows:
            for row in rows:
                lines.append(f"- `{row.get('operation_id')}` {row.get('status')} `{row.get('path')}` {row.get('operation')}")
        else:
            lines.append('- No SourcePlan operations captured.')
        lines.extend(['', '## Evidence Tail', ''])
        evidence = data.get('evidence') if isinstance(data.get('evidence'), dict) else {}
        for item in evidence.get('recent') or evidence.get('receipts') or []:
            if isinstance(item, dict):
                lines.append(f"- `{item.get('receipt_id')}` {item.get('source')} {item.get('artifact_type')} {item.get('status')}")
        return '\n'.join(lines) + '\n'

    def _read_json_file(self, path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _latest_child_dir(self, parent: Path) -> Path | None:
        if not parent.exists():
            return None
        dirs = [path for path in parent.iterdir() if path.is_dir()]
        if not dirs:
            return None
        return sorted(dirs, key=lambda path: path.stat().st_mtime, reverse=True)[0]

    def _mission_route_plan(self, objective: str, active_file: str='', risk: str='') -> dict[str, Any]:
        text = f'{objective} {active_file} {risk}'.lower()
        route = ['Mission']
        if any((term in text for term in ('model', 'provider', 'nim', 'ollama', 'route'))):
            route.append('Models')
        if any((term in text for term in ('agent', 'session', 'prompt', 'tool'))):
            route.append('Agents')
        if any((term in text for term in ('code', 'file', 'edit', 'patch', 'sourceplan', 'worktree', 'test'))) or active_file:
            route.append('Tools')
        if any((term in text for term in ('review', 'verify', 'risk', 'approval', 'apply', 'rollback', 'test'))):
            route.append('Review')
        if any((term in text for term in ('evidence', 'receipt', 'runbook', 'audit', 'proof'))):
            route.append('Evidence')
        if any((term in text for term in ('crystal', 'lattice', 'memory', 'learn', 'promote'))):
            route.append('Crystalization')
        if 'Evidence' not in route and 'Crystalization' in route:
            route.insert(route.index('Crystalization'), 'Evidence')
        route = list(dict.fromkeys(route + ['Evidence']))
        mcp_map = {'Mission': ['mission_cockpit'], 'Models': ['provider_registry', 'capability_plane'], 'Agents': ['agent_sessions'], 'Tools': ['code_cortex', 'sourceplan', 'worktree_forge'], 'Review': ['policy_gate', 'verifier'], 'Evidence': ['evidence_bus', 'runbook'], 'Crystalization': ['mission_lattice', 'memory_hull']}
        return {'beast_object_type': 'beast_ide_mission_route', 'version': '1.0', 'objective': objective, 'active_file': active_file, 'risk': risk, 'active_face': route[0] if route else 'Mission', 'route': [{'step': index + 1, 'face': face, 'status': 'active' if index == 0 else 'planned', 'tools': mcp_map.get(face, [])} for index, face in enumerate(route)], 'approval_required': any((term in text for term in ('edit', 'write', 'apply', 'execute', 'promote', 'rollback'))) or risk in {'high', 'critical'}, 'direct_mutation_allowed': False}

    def _ide_action_manifest(self) -> list[dict[str, Any]]:

        def action(action_id: str, label: str, page: str, description: str, *, surface: str='desktop', risk: str='low', handler: str='', endpoint: str='', method: str='GET', tags: list[str] | None=None, approval_required: bool=False, sourceplan_required: bool=False, worktree_recommended: bool=False, provider_required: bool=False, local_fallback: bool=True) -> dict[str, Any]:
            return {'id': action_id, 'label': label, 'page': page, 'surface': surface, 'description': description, 'risk': risk, 'client_handler': handler or action_id.replace('.', '_'), 'endpoint': endpoint, 'method': method, 'tags': tags or [], 'approval_required': approval_required, 'sourceplan_required': sourceplan_required, 'worktree_recommended': worktree_recommended, 'provider_required': provider_required, 'local_fallback': local_fallback, 'direct_mutation_allowed': False}
        return [action('mission.refresh_snapshot', 'Refresh Mission Snapshot', 'mission', 'Reload cockpit, policy, evidence, sessions, worktrees, and context.', handler='refreshSnapshot', endpoint='/edgek/ide/snapshot', tags=['mission', 'status']), action('mission.route', 'Plan Mission Route', 'mission', 'Map the current objective through BEAST faces and governance steps.', handler='refreshMissionRoute', endpoint='/edgek/ide/mission-route', tags=['mission', 'route']), action('editor.save_sourceplan', 'Save Via SourcePlan', 'source', 'Draft and apply staged editor changes through SourcePlan, approval, rollback, and evidence.', handler='saveViaSourcePlan', tags=['editor', 'save', 'sourceplan'], risk='high', approval_required=True, sourceplan_required=True, local_fallback=False), action('editor.revert_buffer', 'Revert Editor Buffer', 'source', 'Discard staged editor changes and return to the last loaded file content.', handler='revertEditorBuffer', tags=['editor', 'buffer'], approval_required=True), action('editor.reload_file', 'Reload Active File', 'source', 'Reload the active file from disk and clear stale editor/SourcePlan state.', handler='reloadActiveFileFromDisk', tags=['editor', 'reload'], approval_required=True), action('sourceplan.draft_editor', 'Draft SourcePlan From Editor', 'source', 'Compile the active staged editor buffer into a governed SourcePlan draft.', handler='sourcePlanDraft', endpoint='/edgek/ide/sourceplan/from-editor', method='POST', tags=['sourceplan', 'editor'], sourceplan_required=True), action('sourceplan.draft_selection', 'Draft SourcePlan From Selection', 'source', 'Use the current editor selection as the seed for a SourcePlan-safe change.', handler='sourcePlanSelectionDraft', endpoint='/edgek/ide/sourceplan/from-selection', method='POST', tags=['sourceplan', 'selection'], sourceplan_required=True), action('sourceplan.lifecycle', 'Refresh SourcePlan Lifecycle', 'source', 'Rebuild the scorecard, action contract, operation ledger, and preview.', handler='refreshSourcePlanLifecycle', endpoint='/edgek/ide/sourceplan/lifecycle', method='POST', tags=['sourceplan', 'policy']), action('sourceplan.verify', 'Verify SourcePlan', 'source', 'Run the verifier before any apply attempt.', handler='verifySourcePlan', endpoint='/edgek/sourceplan/verify', method='POST', tags=['sourceplan', 'verify'], approval_required=True, sourceplan_required=True), action('sourceplan.apply', 'Apply SourcePlan', 'source', 'Apply only after approval, hash checks, verification, rollback capture, and evidence closure.', handler='applySourcePlan', endpoint='/edgek/sourceplan/apply', method='POST', tags=['sourceplan', 'apply'], risk='high', approval_required=True, sourceplan_required=True, worktree_recommended=True, local_fallback=False), action('sourceplan.export_runbook', 'Export Mission Runbook', 'source', 'Export a Markdown runbook from the current SourcePlan, selected receipts, and verification state.', handler='exportMissionRunbook', endpoint='/edgek/ide/mission-runbook/export', method='POST', tags=['runbook', 'evidence']), action('sourceplan.verify_runbook', 'Verify Runbook', 'source', 'Check runbook completeness before handoff or promotion.', handler='verifyMissionRunbook', endpoint='/edgek/ide/mission-runbook/verify', method='POST', tags=['runbook', 'verify']), action('sourceplan.handoff_package', 'Create Handoff Package', 'source', 'Bundle SourcePlan, runbook, receipts, and action ledger for operator review.', handler='createHandoffPackage', endpoint='/edgek/ide/sourceplan/handoff-package', method='POST', tags=['handoff', 'evidence']), action('sourceplan.propose_learning', 'Propose Learning', 'source', 'Queue a verified SourcePlan pattern for Crystal/Lattice learning without auto-promotion.', handler='proposeLearning', endpoint='/edgek/ide/learning-queue/propose', method='POST', tags=['lattice', 'learning'], approval_required=True), action('code.symbol_search', 'Search Workspace Symbols', 'source', 'Find functions/classes/routes across the workspace and open them as symbol-sized ranges.', handler='runSymbolSearch', endpoint='/edgek/ide/symbol-search', tags=['code', 'symbol', 'cortex']), action('code.intel', 'Refresh Code Intelligence', 'source', 'Load symbols, diagnostics, stale-context guidance, and related tests/routes from Code Cortex.', handler='refreshCodeIntelligence', endpoint='/edgek/ide/code-intel', tags=['code', 'diagnostics', 'references', 'cortex']), action('agents.create', 'Create Agent Session', 'agents', 'Start a persistent governed session with mode, budget, tools, files, provider, and model.', handler='createAgentSession', endpoint='/edgek/ide/agent-sessions/create', method='POST', tags=['agent', 'session'], provider_required=True), action('agents.send_prompt', 'Send Agent Request', 'agents', 'Send the current prompt and context pack to the selected provider route.', handler='sendAgentPrompt', endpoint='/edgek/ide/agent-sessions/{session_id}/run-events', tags=['agent', 'provider'], provider_required=True), action('agents.output_to_sourceplan', 'Convert Agent Output To SourcePlan', 'agents', 'Compile selected agent output into SourcePlan operations or a blocked translation note.', handler='agentOutputToSourcePlan', endpoint='/edgek/ide/agent-sessions/sourceplan-draft', method='POST', tags=['agent', 'sourceplan'], sourceplan_required=True), action('agents.output_action_ir', 'Compile Agent Action IR', 'agents', 'Resolve BEAST Action IR from agent output into exact SourcePlan operations when safe.', handler='agentOutputToSourcePlan', endpoint='/edgek/ide/agent-sessions/action-ir-sourceplan', method='POST', tags=['agent', 'action_ir', 'sourceplan'], sourceplan_required=True), action('agents.verify_requested_checks', 'Run Agent Requested Checks', 'agents', 'Run allowlisted verifier commands requested by the coding agent in an isolated temporary workspace.', handler='verifyAgentRequestedChecks', endpoint='/edgek/ide/agent-sessions/verify-sourceplan', method='POST', tags=['agent', 'verify', 'sourceplan'], approval_required=True, sourceplan_required=True), action('worktrees.create', 'Create Mission Worktree', 'worktrees', 'Create an isolated mission workspace for high-risk or multi-file work.', handler='createWorktreeMission', endpoint='/edgek/ide/worktree-mission/create', method='POST', tags=['worktree', 'mission'], worktree_recommended=True), action('worktrees.verify', 'Verify Worktree Mission', 'worktrees', 'Run verification inside the selected mission worktree and save evidence.', handler='testWorktreeMission', endpoint='/edgek/ide/worktree-mission/test', method='POST', tags=['worktree', 'verify'], approval_required=True), action('worktrees.diff', 'Browse Worktree Diff', 'worktrees', 'Inspect the selected mission worktree diff before promotion.', handler='browseWorktreeDiff', endpoint='/edgek/ide/worktree-mission/diff', method='POST', tags=['worktree', 'diff']), action('worktrees.sourceplan_draft', 'Draft Worktree Promotion SourcePlan', 'worktrees', 'Convert a bounded worktree diff into a SourcePlan promotion draft.', handler='draftWorktreeSourcePlan', endpoint='/edgek/ide/worktree-mission/sourceplan-draft', method='POST', tags=['worktree', 'sourceplan'], sourceplan_required=True), action('worktrees.close', 'Close Worktree Mission', 'worktrees', 'Close the selected mission worktree only after evidence and promotion status are visible.', handler='closeWorktreeMission', endpoint='/edgek/ide/worktree-mission/close', method='POST', tags=['worktree', 'cleanup'], approval_required=True), action('evidence.search', 'Search Evidence Bus', 'evidence', 'Filter receipts by source, artifact type, status, task, plan, receipt, or relation.', handler='searchEvidenceDrawer', endpoint='/edgek/evidence-bus/query', tags=['evidence', 'search']), action('evidence.choose_receipts', 'Choose Evidence Receipts', 'evidence', 'Attach receipts to a governed action before export, apply, or handoff.', handler='chooseReceiptsForAction', endpoint='/edgek/ide/receipts/chooser', tags=['evidence', 'receipt']), action('terminal.classify', 'Classify Terminal Command', 'terminal', 'Ask Safety Governor for policy before running any workspace command.', handler='classifyTerminalCommand', endpoint='/edgek/safety-governor/classify-command', method='POST', tags=['terminal', 'policy']), action('terminal.execute', 'Execute Governed Command', 'terminal', 'Run only after Safety Governor classification and capture stdout/stderr as evidence.', handler='executeTerminalCommand', endpoint='/edgek/safety-governor/execute-command', method='POST', tags=['terminal', 'evidence'], risk='high', approval_required=True, local_fallback=False), action('terminal.stream', 'Stream Governed Command', 'terminal', 'Run after Safety Governor classification and stream stdout/stderr into evidence on close.', handler='executeTerminalCommand', endpoint='/edgek/ide/terminal/stream', tags=['terminal', 'streaming', 'evidence'], risk='high', approval_required=True, local_fallback=False), action('providers.refresh', 'Refresh Provider Setup', 'providers', 'Reload selected provider, registry, secret route, and live smoke readiness.', handler='refreshProviderSetup', endpoint='/edgek/providers/registry', tags=['provider', 'setup']), action('providers.smoke_nvidia', 'Smoke NVIDIA NIM', 'providers', 'Run an explicit NVIDIA NIM readiness check for the selected model.', handler='smokeNvidiaProvider', endpoint='/edgek/providers/nvidia-nim/live-smoke', method='POST', tags=['provider', 'nvidia'], provider_required=True, local_fallback=False), action('tooling.refresh', 'Refresh Tooling Plane', 'tooling', 'Check syntax, lint scripts, MCP, plugins, extensions, and local environment readiness.', handler='refreshToolingSnapshot', endpoint='/edgek/ide/tooling-snapshot', tags=['tooling', 'lint', 'syntax', 'mcp', 'plugins', 'environment']), action('tooling.syntax', 'Syntax Check Active File', 'tooling', 'Run the active file through the available syntax checker.', handler='runSyntaxToolingCheck', endpoint='/edgek/ide/tooling-snapshot', tags=['tooling', 'syntax']), action('tooling.lint', 'Show Lint Contract', 'tooling', 'Show lint scripts and governed terminal guidance.', handler='showLintToolingContract', endpoint='/edgek/ide/tooling-snapshot', tags=['tooling', 'lint']), action('tooling.mcp', 'Inspect MCP', 'tooling', 'Inspect MCP config, routes, approvals, executions, and schema-pin surfaces.', handler='focusMcpTooling', endpoint='/edgek/ide/tooling-snapshot', tags=['tooling', 'mcp']), action('tooling.plugins', 'Inspect Plugins And Extensions', 'tooling', 'Inspect plugin marketplace, VS Code extension, and desktop shell surfaces.', handler='focusPluginTooling', endpoint='/edgek/ide/tooling-snapshot', tags=['tooling', 'plugins', 'extensions']), action('tooling.mcp_ops', 'Refresh MCP Operations', 'tooling', 'Load MCP state, servers, approvals, audit, executions, and schema pins.', handler='refreshMcpOps', endpoint='/edgek/mcp/state', tags=['tooling', 'mcp', 'approvals', 'schema']), action('tooling.plugin_ops', 'Refresh Plugin Operations', 'tooling', 'Load installed plugins and plugin validation/install surfaces.', handler='refreshPluginOps', endpoint='/edgek/plugins', tags=['tooling', 'plugins', 'extensions']), action('tooling.grade_benchmark_packet', 'Run Benchmark Grading Daemon', 'tooling', 'Trigger the public benchmark grading daemon for the full blind packet and load provisional plus structural verdicts.', handler='runBenchmarkGradingDaemon', endpoint='/edgek/benchmarks/public-grading-daemon', method='POST', tags=['tooling', 'benchmark', 'grading']), action('tooling.environment', 'Inspect Environment', 'tooling', 'Inspect Python, Node, npm, git, and workspace package scripts.', handler='focusEnvironmentTooling', endpoint='/edgek/ide/tooling-snapshot', tags=['tooling', 'environment']), action('system.refresh', 'Refresh System Plane', 'system', 'Load listening ports, processes, environment, packages, and extensions.', handler='refreshSystemSnapshot', endpoint='/edgek/ide/system-snapshot', tags=['system', 'ports', 'processes', 'environment', 'packages']), action('system.ports', 'List Listening Ports', 'system', 'Show listening TCP/UDP ports with owning PID and process.', handler='refreshSystemPorts', endpoint='/edgek/ide/ports', tags=['system', 'ports']), action('system.processes', 'Explore Processes', 'system', 'Find running processes by name/PID with CPU and memory.', handler='refreshSystemProcesses', endpoint='/edgek/ide/processes', tags=['system', 'processes']), action('system.kill', 'Kill Process', 'system', 'Signal a process by PID after Safety Governor classification, approval, and evidence.', handler='killSystemProcess', endpoint='/edgek/ide/system/kill', method='POST', tags=['system', 'processes', 'kill'], risk='high', approval_required=True, local_fallback=False), action('system.free_port', 'Free Port', 'system', 'Terminate the process holding a port after Safety Governor classification, approval, and evidence.', handler='freeSystemPort', endpoint='/edgek/ide/ports/free', method='POST', tags=['system', 'ports', 'kill'], risk='high', approval_required=True, local_fallback=False), action('system.environment', 'Inspect Environment', 'system', 'Show Python/Node/venv interpreters, versions, PATH, and non-secret env vars.', handler='refreshSystemEnvironment', endpoint='/edgek/ide/environment', tags=['system', 'environment']), action('system.packages', 'Manage Packages', 'system', 'List Python/Node dependencies, scripts, install state, and governed install commands.', handler='refreshSystemPackages', endpoint='/edgek/ide/packages', tags=['system', 'packages']), action('system.extensions', 'Inspect Extensions', 'system', 'Inspect VS Code extension commands, desktop shell, plugins, and MCP servers.', handler='refreshSystemExtensions', endpoint='/edgek/ide/extensions', tags=['system', 'extensions', 'plugins']), action('system.catalog', 'Browse Recommended Catalog', 'system', 'Browse curated MCP servers, CLI tools, and editor extensions with live install state.', handler='refreshSystemCatalog', endpoint='/edgek/ide/catalog', tags=['system', 'catalog', 'mcp', 'extensions', 'tools']), action('doctor.restart_gateway', 'Restart Gateway', 'doctor', 'Restart the active BEAST gateway and preserve diagnostics if startup fails.', handler='restartGateway', tags=['doctor', 'gateway'], approval_required=True), action('doctor.copy_report', 'Copy Doctor Report', 'doctor', 'Copy active gateway URL, command, PID, health, route capability, and log tail.', handler='copyDoctorReport', tags=['doctor', 'diagnostic']), action('settings.release_readiness', 'Check IDE Readiness', 'settings', 'Run the release-readiness checklist for packaging, gateway startup, and core desktop features.', handler='checkReleaseReadiness', endpoint='/edgek/ide/release-readiness/check', method='POST', local_fallback=True, tags=['settings', 'readiness'])]

    def _sourceplan_repo_patch(self, root: Path, plan: dict[str, Any]) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        operations = plan.get('operations') if isinstance(plan.get('operations'), list) else []
        chunks: list[str] = []
        compiled: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        for index, op in enumerate(operations):
            if not isinstance(op, dict):
                continue
            op_id = str(op.get('op_id') or f'op_{index + 1}')
            rel = str(op.get('path') or '')
            target = _safe_relative(root, rel)
            if target is None:
                blocked.append({'operation_id': op_id, 'path': rel, 'reason': 'unsafe_path'})
                continue
            lower = rel.lower()
            if any((secret in lower for secret in ('.env', 'id_rsa', 'id_ed25519', 'secrets', 'credentials'))):
                blocked.append({'operation_id': op_id, 'path': rel, 'reason': 'secrets_like_path'})
                continue
            before = target.read_text(encoding='utf-8', errors='replace') if target.exists() and target.is_file() else str(op.get('old') or op.get('old_text') or '')
            after = str(op.get('new') or op.get('new_text') or op.get('content') or '')
            if not after and op.get('op') == 'replace_exact':
                blocked.append({'operation_id': op_id, 'path': rel, 'reason': 'empty_after_text'})
                continue
            diff = ''.join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True), fromfile=f'a/{rel}', tofile=f'b/{rel}', lineterm=''))
            if diff and (not diff.endswith('\n')):
                diff += '\n'
            chunks.append(diff)
            compiled.append({'operation_id': op_id, 'path': rel, 'before_sha256': _hash_text(before), 'after_sha256': _hash_text(after), 'added_lines': sum((1 for line in diff.splitlines() if line.startswith('+') and (not line.startswith('+++')))), 'removed_lines': sum((1 for line in diff.splitlines() if line.startswith('-') and (not line.startswith('---'))))})
        return ('\n'.join((chunk for chunk in chunks if chunk)), compiled, blocked)

    def _gather_ide_state(self, root: Path, query: str, phase: str, risk: str, evidence_limit: int) -> dict[str, Any]:
        code_cortex_router = self.code_cortex_router
        bounded_limit = max(1, min(int(evidence_limit), 50))

        def _generic_query(value: str) -> bool:
            normalized = " ".join(str(value or "").strip().lower().split())
            return normalized in {
                "",
                "beast ide mission",
                "desktop health",
                "gateway ready",
            }

        def _timeout_payload(name: str, *, seconds: float, detail: str) -> dict[str, Any]:
            return {
                "status": "degraded",
                "timeout_seconds": seconds,
                "error": f"{name} timed out after {seconds:.1f}s",
                "detail": detail,
            }

        def _bounded(name: str, fn, *, timeout: float, fallback):
            pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = pool.submit(fn)
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                future.cancel()
                return fallback()
            except Exception as error:
                payload = fallback()
                if isinstance(payload, dict):
                    payload = dict(payload)
                    payload.setdefault("status", "degraded")
                    payload["error"] = str(error)
                return payload
            finally:
                pool.shutdown(wait=False, cancel_futures=True)

        cockpit_timeout = 3.0
        code_cortex_timeout = 1.5 if _generic_query(query) else 3.0
        cockpit = _bounded(
            "mission_cockpit",
            lambda: MissionCockpit(root).summary(objective=query, phase=phase, risk=risk),
            timeout=cockpit_timeout,
            fallback=lambda: {
                "beast_object_type": "beast_mission_cockpit_summary",
                "version": "1.0",
                "workspace_root": str(root),
                "objective": query,
                "phase": phase,
                "risk": risk,
                "status": "degraded",
                "cards": [],
                "blockers": [],
                "mode_route": {},
                "worktrees": {},
                "scheduler": {},
                "mission_lattice": {},
                "evidence_bus": {},
                "safety": _timeout_payload(
                    "mission_cockpit.safety_scan",
                    seconds=cockpit_timeout,
                    detail="Safety Governor scan exceeded the live snapshot budget.",
                ),
                "reintegration_health": {},
                "sourceplan_queue": [],
                "evidence_stream": [],
                "spec_covenant": {},
                "code_cortex": {},
                "capability_plane": {},
                "timestamp": time.time(),
            },
        )
        code_cortex = _bounded(
            "code_cortex",
            lambda: code_cortex_router.get_editing_context(root, query, limit=12),
            timeout=code_cortex_timeout,
            fallback=lambda: {
                "ok": False,
                "adapter": "deferred",
                "status": "degraded",
                "query": query,
                "symbols": [],
                "files": [],
                "receipt": {
                    "beast_object_type": "code_cortex_adapter_receipt",
                    "version": "1.0",
                    "adapter": "deferred",
                    "method": "get_editing_context",
                    "ok": False,
                    "latency_ms": code_cortex_timeout * 1000,
                    "fallback_used": False,
                    "command": [],
                    "error": f"Code Cortex timed out after {code_cortex_timeout:.1f}s",
                    "result_count": 0,
                },
                "detail": "Editing context exceeded the live snapshot budget.",
            },
        )
        if isinstance(code_cortex, dict):
            code_cortex = {"front_door": "code_cortex", **code_cortex}
        evidence = EvidenceBus(root).summary(limit=bounded_limit)
        lattice = MissionCrystalLattice(root).summary(limit=8)
        agent_sessions = AgentSessionStore(root).list()
        architecture = architecture_decision_register()
        return {'cockpit': cockpit, 'code_cortex': code_cortex, 'evidence': evidence, 'lattice': lattice, 'agent_sessions': agent_sessions, 'architecture': architecture}

    def _event(self, event_type: str, payload: dict[str, Any]) -> str:
        data = {'beast_object_type': 'beast_ide_event', 'version': '1.0', 'event_type': event_type, 'created_at': int(time.time()), 'payload': payload}
        return f'event: {event_type}\ndata: {json.dumps(data, sort_keys=True)}\n\n'

    def _tool_event(self, session_id: str, *, tool: str, text: str, phase: str='observe', status: str='completed', authority: str='read-only/governed', result: dict[str, Any] | None=None) -> dict[str, Any]:
        return {'session_id': session_id, 'type': 'tool_result', 'tool': tool, 'phase': phase, 'status': status, 'authority': authority, 'text': text, 'result': result or {}}

    def _tool_call_event(self, session_id: str, *, tool: str, text: str, phase: str='observe', authority: str='read-only/governed', parameters: dict[str, Any] | None=None) -> dict[str, Any]:
        return {'session_id': session_id, 'type': 'tool_call', 'tool': tool, 'phase': phase, 'status': 'started', 'authority': authority, 'text': text, 'parameters': parameters or {}}

    def _register_system_evidence(self, root: Path, result: dict[str, Any], *, context: str, task_id: str, approved: bool, operator_override: str) -> dict[str, Any]:
        payload = {'beast_object_type': 'beast_ide_system_action', 'version': '1.0', 'context': context, 'approved': approved, 'operator_override': operator_override, 'result': result, 'created_at': int(time.time())}
        out_dir = root / '.beast' / 'evidence' / 'system'
        out_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode('utf-8')).hexdigest()[:16]
        out_path = out_dir / f'system_{int(time.time())}_{digest}.json'
        out_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + '\n', encoding='utf-8')
        receipt = EvidenceBus(root).register(artifact_type='beast_ide_system_action', artifact_path=out_path, artifact_hash='sha256:' + hashlib.sha256(out_path.read_bytes()).hexdigest(), source='ide_system_plane', task_id=task_id or '', status='ok' if result.get('ok') else 'failed', summary=f"{context}: {result.get('command') or result.get('status')}", metadata={'pid': result.get('pid'), 'signal': result.get('signal'), 'status': result.get('status'), 'context': context})
        result['evidence_receipt'] = receipt
        result['evidence_path'] = str(out_path)
        return receipt

    async def _governed_kill(self, root: Path, pid: int, sig: str, *, approved: bool, operator_override: str, task_id: str, dry_run: bool, context: str) -> dict[str, Any]:
        _register_system_evidence = self._register_system_evidence
        preview = await asyncio.to_thread(system_inspector.describe_kill_target, pid, sig)
        receipt = await asyncio.to_thread(SafetyGovernor(root).classify_command, preview['command'], mode='ide_system_kill', task_id=task_id, operator_override=operator_override)
        decision = str(receipt.get('decision') or 'allow')
        preview['safety'] = receipt
        preview['decision'] = decision
        preview['context'] = context
        if preview['protected']:
            return {'ok': False, 'error': 'protected_process', 'reason': preview['protected_reason'], **preview}
        if not preview['exists']:
            return {'ok': False, 'error': 'no_such_process', **preview}
        if dry_run:
            return {'ok': True, 'status': 'dry_run', **preview}
        if decision == 'block':
            return {'ok': False, 'error': 'blocked_by_safety_governor', **preview}
        if not approved:
            return {'ok': False, 'error': 'approval_required', **preview}
        result = await asyncio.to_thread(system_inspector.kill_process, pid, sig)
        result['safety'] = receipt
        result['decision'] = decision
        result['context'] = context
        _register_system_evidence(root, result, context=context, task_id=task_id, approved=approved, operator_override=operator_override)
        return result
