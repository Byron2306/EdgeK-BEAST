"""BEAST Power Console TUI.

Patch 1: make the existing BEAST runtime power visible before the live coding
chat/session screen is added.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from app.cli.api import ActionResult, BeastApiClient, BackendSnapshot, LiveTurnResult

BEAST_GREEN = '#5CFF95'
BEAST_ACID = '#7CFF4F'
BEAST_PANEL = '#0D1110'
BEAST_BORDER = '#3A4641'
BEAST_MUTED = '#66746E'
BEAST_TEXT = '#E8F2ED'
BEAST_WARN = '#FFBD4A'
BEAST_DANGER = '#FF5F56'
BEAST_INFO = '#5CE1FF'
BEAST_PURPLE = '#B889FF'

PAGES = ['Mission','Session','PREC','Routing','Providers','Capabilities','Chronicle','Deployment','Diagnostics','Settings']
PAGE_LABELS = {
    'Mission': 'Mission Control',
    'Session': 'Live Session',
    'PREC': 'PREC Lifecycle',
    'Routing': 'Routing Fabric',
    'Providers': 'Providers',
    'Capabilities': 'Capabilities',
    'Chronicle': 'Chronicle',
    'Deployment': 'Deployment',
    'Diagnostics': 'Diagnostics',
    'Settings': 'Settings',
}


def val(item: Dict[str, Any], *keys: str, default: str = '') -> str:
    for key in keys:
        current: Any = item
        ok = True
        for part in key.split('.'):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                ok = False
                break
        if ok and current not in (None, ''):
            return str(current)
    return str(default)


def clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(value, hi))


def bool_badge(value: Any) -> str:
    return 'yes' if bool(value) else 'no'


def status_style(value: Any) -> str:
    status = str(value).strip().lower()
    if status in {'ok', 'healthy', 'ready', 'available', 'active', 'done', 'completed', 'promoted', 'allowed', 'true', 'yes', 'running'}:
        return BEAST_GREEN
    if status in {'active'} or 'active' in status:
        return BEAST_ACID
    if any(x in status for x in ['warn', 'approval', 'candidate', 'guarded', 'missing', 'unknown', 'degraded', 'offline', 'wait', 'pending', 'false', 'no']):
        return BEAST_WARN
    if any(x in status for x in ['blocked', 'error', 'deny', 'failed', 'locked']):
        return BEAST_DANGER
    return BEAST_TEXT


def selected_marker(selected: bool) -> Text:
    return Text('▸' if selected else ' ', style=BEAST_ACID)


def selected_text(text: Any, selected: bool) -> Text:
    return Text(str(text), style=f'bold {BEAST_ACID}' if selected else BEAST_TEXT)


def safe_join(values: Any, limit: int = 4) -> str:
    if isinstance(values, dict):
        values = list(values.keys())
    if isinstance(values, list):
        shown = [str(x) for x in values[:limit]]
        if len(values) > limit:
            shown.append(f'+{len(values) - limit}')
        return ', '.join(shown)
    return str(values or '')


def fmt_bytes(value: Any) -> str:
    try:
        size = float(value or 0)
    except Exception:
        return '0 B'
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    unit = 0
    while size >= 1024 and unit < len(units) - 1:
        size /= 1024
        unit += 1
    return f'{size:.1f} {units[unit]}' if unit else f'{int(size)} B'


def mini_mascot() -> Text:
    t = Text()
    for line, style in [
        ('   ▄██▄   ⚡', BEAST_GREEN),
        (' ▄█ >_ █▄  ', BEAST_ACID),
        (' ██ ▰  ██  ', BEAST_TEXT),
        ('  ▀███▀    ', BEAST_GREEN),
        ('  ▄█⚙█▄    ', BEAST_GREEN),
    ]:
        t.append(line + '\n', style=style)
    return t


@lru_cache(maxsize=1)
def mascot_frames() -> Dict[str, Any]:
    path = Path(__file__).with_name('assets') / 'sprites' / 'mascot_frames.json'
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
        states = payload.get('states') if isinstance(payload, dict) else {}
        return states if isinstance(states, dict) else {}
    except Exception:
        return {}


def mascot_state_for(value: Any) -> str:
    state = str(value or 'idle').strip().lower()
    if state in {'working', 'thinking', 'streaming', 'active', 'running', 'queued', 'coding'}:
        return 'working'
    if state in {'alert', 'error', 'failed', 'blocked', 'cancel requested'}:
        return 'alert'
    if state in {'finished', 'complete', 'completed', 'done', 'success'}:
        return 'finished'
    return 'idle'


def sprite_mascot(state: str = 'idle', frame: int = 0) -> Text:
    frames_by_state = mascot_frames()
    frames = frames_by_state.get(mascot_state_for(state)) or frames_by_state.get('idle') or []
    if not frames:
        return mini_mascot()
    frame_data = frames[int(frame or 0) % len(frames)]
    half_rows = frame_data.get('terminal_half') if isinstance(frame_data, dict) else []
    if isinstance(half_rows, list) and half_rows:
        text = Text()
        for row in half_rows:
            if not isinstance(row, list):
                continue
            for cell in row:
                if not isinstance(cell, list):
                    text.append(' ')
                    continue
                top = cell[0] if len(cell) > 0 else None
                bottom = cell[1] if len(cell) > 1 else None
                if top and bottom:
                    text.append('▀', style=f'{top} on {bottom}')
                elif top:
                    text.append('▀', style=str(top))
                elif bottom:
                    text.append('▄', style=str(bottom))
                else:
                    text.append(' ')
            text.append('\n')
        return text
    rows = frame_data.get('terminal') if isinstance(frame_data, dict) else []
    if not isinstance(rows, list):
        return mini_mascot()
    text = Text()
    for row in rows:
        if not isinstance(row, list):
            continue
        for cell in row:
            if isinstance(cell, list) and cell:
                char = str(cell[0] or ' ')
                color = cell[1] if len(cell) > 1 else None
                text.append(char[:1], style=str(color) if color else BEAST_PANEL)
            else:
                text.append(' ')
        text.append('\n')
    return text


def metric(title: str, value: Any, note: str = '', accent: Any = None) -> Panel:
    style = accent or status_style(value)
    return Panel(
        Group(Text(title, style=BEAST_MUTED), Text(str(value), style=f'bold {style}'), Text(str(note), style='#AAB8B2')),
        border_style=BEAST_BORDER,
        style=BEAST_PANEL,
        padding=(0, 1),
    )


def compact_jsonish(item: Any, limit: int = 1800) -> Text:
    text = str(item)
    if len(text) > limit:
        text = text[:limit] + ' …'
    return Text(text, style='#AAB8B2')


def current_plan_summary(plan: Dict[str, Any] | None) -> Dict[str, Any]:
    plan = plan or {}
    evidence = plan.get('output_evidence') if isinstance(plan.get('output_evidence'), dict) else {}
    handoff = plan.get('provider_handoff') if isinstance(plan.get('provider_handoff'), dict) else {}
    trace = handoff.get('trace') if isinstance(handoff.get('trace'), dict) else {}
    packet_stats = handoff.get('packet_stats') if isinstance(handoff.get('packet_stats'), dict) else {}
    operations = [op for op in (plan.get('operations') or []) if isinstance(op, dict)]
    source_ops = [op for op in operations if op.get('source_edit')]
    requests = plan.get('non_mutating_requests') if isinstance(plan.get('non_mutating_requests'), list) else []
    return {
        'plan_id': plan.get('plan_id') or 'none',
        'status': plan.get('status') or 'none',
        'provider': plan.get('provider') or 'n/a',
        'provider_generated': bool(plan.get('provider_generated')),
        'contract': evidence.get('contract') or (handoff.get('output') or {}).get('schema', {}).get('kind') or 'n/a',
        'gate_status': evidence.get('final_status') or 'not run',
        'diff_compiled': bool(evidence.get('diff_compiled')),
        'operations': len(operations),
        'source_operations': len(source_ops),
        'selected': len(plan.get('selected_operations') or []),
        'requests': len(requests),
        'handoff_hash': trace.get('input_handoff_hash') or '',
        'handoff_tokens': packet_stats.get('estimated_tokens'),
        'fallback_reason': plan.get('provider_fallback_reason') or '',
    }


def governance_table(plan: Dict[str, Any] | None) -> Table:
    summary = current_plan_summary(plan)
    table = Table.grid(expand=True)
    table.add_column(width=20)
    table.add_column(ratio=1)
    for key, label in [
        ('plan_id', 'Plan'),
        ('status', 'Status'),
        ('provider', 'Provider'),
        ('contract', 'Contract'),
        ('gate_status', 'Output gate'),
        ('operations', 'Operations'),
        ('requests', 'Requests'),
        ('handoff_tokens', 'Handoff tokens'),
        ('handoff_hash', 'Handoff hash'),
    ]:
        value = summary.get(key)
        style = status_style(value)
        if key == 'handoff_hash' and value:
            value = str(value)[:28] + '…'
        table.add_row(Text(label, style=BEAST_MUTED), Text(str(value), style=style))
    if summary.get('fallback_reason'):
        table.add_row(Text('Fallback', style=BEAST_MUTED), Text(str(summary['fallback_reason'])[:160], style=BEAST_WARN))
    return table


def operations_table(plan: Dict[str, Any] | None, selected_op: str = '') -> Table:
    table = Table(expand=True, box=box.SIMPLE)
    for col in ['Use', 'Op', 'Path', 'Kind', 'Description']:
        table.add_column(col)
    plan = plan or {}
    ops = [op for op in (plan.get('operations') or []) if isinstance(op, dict)]
    selected = set(str(x) for x in (plan.get('selected_operations') or []))
    if not ops:
        table.add_row('—', 'none', 'No source operations compiled', '', '')
    for op in ops[:12]:
        op_id = str(op.get('op_id') or '')
        is_selected = op_id in selected or (not selected and bool(op.get('selected', True)))
        row_style = BEAST_ACID if op_id == selected_op else BEAST_TEXT
        table.add_row(
            Text('●' if is_selected else '○', style=BEAST_GREEN if is_selected else BEAST_MUTED),
            Text(op_id, style=row_style),
            Text(str(op.get('path') or '')[:48], style=row_style),
            'source' if op.get('source_edit') else 'beast',
            str(op.get('description') or '')[:64],
        )
    return table


def requests_table(plan: Dict[str, Any] | None) -> Table:
    table = Table(expand=True, box=box.SIMPLE)
    for col in ['Type', 'Path', 'Intent', 'Parameters']:
        table.add_column(col)
    requests = (plan or {}).get('non_mutating_requests')
    requests = requests if isinstance(requests, list) else []
    if not requests:
        table.add_row('none', '', 'No verifier/context requests from provider', '')
    for item in requests[:8]:
        params = item.get('parameters') if isinstance(item, dict) else {}
        table.add_row(
            Text(str(item.get('type') or ''), style=BEAST_INFO),
            str(item.get('path') or '')[:34],
            str(item.get('intent') or '')[:70],
            json.dumps(params, default=str)[:80] if isinstance(params, dict) else str(params)[:80],
        )
    return table


def provider_key(value: Any) -> str:
    return str(value or '').strip().lower().replace('-', '_')


def _provider_rows(snap: BackendSnapshot) -> List[Dict[str, Any]]:
    return [row for row in snap.providers() if isinstance(row, dict)]


def _adapter_rows(snap: BackendSnapshot) -> List[Dict[str, Any]]:
    return [row for row in (snap.provider_adapters or []) if isinstance(row, dict)]


def provider_record(snap: BackendSnapshot, provider_id: str) -> Dict[str, Any]:
    wanted = provider_key(provider_id)
    for row in _provider_rows(snap):
        pid = provider_key(row.get('provider_id') or row.get('id') or row.get('name'))
        if pid == wanted:
            return row
    return {}


def provider_adapter(snap: BackendSnapshot, provider_id: str) -> Dict[str, Any]:
    wanted = provider_key(provider_id)
    for row in _adapter_rows(snap):
        pid = provider_key(row.get('provider_id') or row.get('id') or row.get('name'))
        if pid == wanted:
            return row
    return {}


def provider_secret_state(snap: BackendSnapshot, provider_id: str) -> str:
    wanted = provider_key(provider_id)
    providers = snap.provider_secrets.get('providers')
    if isinstance(providers, dict):
        if provider_id in providers or wanted in {provider_key(key) for key in providers.keys()}:
            return 'present'
    entries = snap.provider_secrets.get('entries')
    if isinstance(entries, list):
        for item in entries:
            if isinstance(item, dict) and provider_key(item.get('provider') or item.get('provider_id')) == wanted:
                return 'present'
    record = provider_record(snap, provider_id) or provider_adapter(snap, provider_id)
    env = record.get('env') or []
    return 'env' if env else 'none'


def provider_route_summary(snap: BackendSnapshot, provider_id: str, requested_model: str = 'beast-auto') -> Dict[str, str]:
    pid = provider_key(provider_id or 'litellm') or 'litellm'
    record = provider_record(snap, pid)
    adapter = provider_adapter(snap, pid)
    merged: Dict[str, Any] = {}
    merged.update(record)
    merged.update(adapter)
    default_model = str(merged.get('default_model') or record.get('model') or adapter.get('model') or pid)
    resolved_model = str(adapter.get('model') or default_model)
    requested = str(requested_model or 'beast-auto')
    if requested not in {'beast-auto', 'beast_auto', 'auto'}:
        resolved_model = requested
    backend = str(merged.get('backend') or adapter.get('adapter_class') or 'unknown')
    route_provider = str(merged.get('route_provider') or backend)
    adapter_class = str(merged.get('adapter_class') or backend)
    return {
        'provider_id': pid,
        'backend': backend,
        'adapter_class': adapter_class,
        'route_provider': route_provider,
        'requested_model': requested,
        'default_model': default_model,
        'resolved_model': resolved_model,
        'proxy_path': str(merged.get('proxy_path') or merged.get('endpoint') or f'/proxy/{pid.replace("_", "-")}'),
        'base_url': str(merged.get('base_url') or ''),
        'env': safe_join(merged.get('env') or []),
        'secret': provider_secret_state(snap, pid),
        'governed_by_beast': bool_badge(merged.get('governed_by_beast', True)),
        'lane': 'LiteLLM managed' if route_provider == 'litellm' else 'OpenAI compatible' if route_provider == 'openai_compatible' else route_provider,
    }


def provider_route_table(summary: Dict[str, str], compact: bool = False) -> Table:
    table = Table.grid(expand=True)
    table.add_column(width=18 if compact else 22)
    table.add_column(ratio=1)
    keys = [
        ('provider_id', 'Provider'),
        ('backend', 'Backend'),
        ('route_provider', 'Route'),
        ('adapter_class', 'Adapter'),
        ('requested_model', 'Requested model'),
        ('resolved_model', 'Resolved model'),
        ('proxy_path', 'Proxy path'),
    ]
    if not compact:
        keys.extend([
            ('base_url', 'Base URL'),
            ('env', 'Env'),
            ('secret', 'Secret'),
            ('governed_by_beast', 'Governed'),
        ])
    for key, label in keys:
        value = summary.get(key) or ''
        table.add_row(Text(label, style=BEAST_MUTED), Text(str(value)[:96], style=status_style(value) if key in {'secret', 'governed_by_beast'} else BEAST_TEXT))
    return table


def provider_fitness_score(snap: BackendSnapshot, provider_id: str) -> Dict[str, Any]:
    wanted = provider_key(provider_id)
    records = []
    for item in snap.chronicles or []:
        if not isinstance(item, dict):
            continue
        if provider_key(item.get('provider')) == wanted:
            records.append(item)
    if not records:
        return {'score': 'n/a', 'eligible': 'unknown', 'sample_size': 0, 'clean': 0, 'rescued': 0, 'validation_rate': 0.0}
    sample = records[:20]
    total = len(sample)
    verified = sum(1 for item in sample if str(item.get('status') or '').lower() in {'applied_verified_crystallized', 'completed', 'passed', 'success'} or (item.get('verification') or {}).get('ok') is True)
    validation = sum(1 for item in sample if str(item.get('validation_status') or '').lower() in {'compiled', 'valid', 'passed'})
    pytest_pass = sum(1 for item in sample if str(item.get('pytest_status') or '').lower() in {'passed', 'skipped'})
    rescued = sum(1 for item in sample if bool(item.get('canonicalized')) or bool((item.get('output_evidence') or {}).get('repair_attempted')))
    clean = max(0, verified - rescued)
    latencies = [float(item.get('latency_ms')) for item in sample if item.get('latency_ms') not in (None, '')]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    latency_score = 1.0 if not avg_latency else max(0.0, min(1.0, 1.0 - (avg_latency / 120000.0)))
    score = (
        0.45 * (verified / total)
        + 0.25 * (validation / total)
        + 0.15 * (pytest_pass / total)
        + 0.10 * latency_score
        + 0.05 * (clean / total)
    )
    eligible = score >= 0.80 and validation / total >= 0.90 and verified / total >= 0.80
    return {
        'score': round(score * 100),
        'eligible': 'yes' if eligible else 'guarded',
        'sample_size': total,
        'clean': clean,
        'rescued': rescued,
        'validation_rate': round(validation / total, 3),
        'verified_rate': round(verified / total, 3),
        'avg_latency_ms': round(avg_latency, 1) if avg_latency else None,
    }


class HelpScreen(ModalScreen):
    BINDINGS = [
        Binding('escape','app.pop_screen','Close'), Binding('q','app.pop_screen','Close'),
        Binding('?','app.pop_screen','Close'), Binding('h','app.pop_screen','Close'),
    ]
    def compose(self) -> ComposeResult:
        left = Table.grid(expand=True); left.add_column(width=14); left.add_column(ratio=1)
        for key, desc in [
            ('← / →','Previous / next page'),('↑ / ↓','Move selected row'),('1-0','Jump to page'),
            ('? / h','Help overlay'),('r','Refresh backend'),('q','Quit'),
        ]:
            left.add_row(Text(key, style=f'bold {BEAST_ACID}'), Text(desc, style=BEAST_TEXT))
        right = Table.grid(expand=True); right.add_column(width=14); right.add_column(ratio=1)
        for key, desc in [
            ('t','Test selected'),('v','Verify plan / view selected'),('e','Edit/config selected'),
            ('a','Approve/promote'),('b','Block/reject'),('s','Start live session'),('n','Next provider'),('[ / ]','Previous / next provider'),('c','Context picker'),('o','Provider source patch plan'),('f','Preview/select hunks'),('u','Apply selected hunks'),('z','Rollback latest apply'),('l','Approval queue'),('y','Approve latest plan'),
            ('w','Toggle streaming mode'),('k','Cancel current live turn'),('p','Prepare handoff'),('d','Run diagnostics refresh'),('ctrl+k','Command palette'),
        ]:
            right.add_row(Text(key, style=f'bold {BEAST_ACID}'), Text(desc, style=BEAST_TEXT))
        grid = Table.grid(expand=True); grid.add_column(ratio=1); grid.add_column(ratio=1)
        grid.add_row(
            Panel(Group(Text('NAVIGATION', style=f'bold {BEAST_ACID}'), Text(''), left), border_style=BEAST_BORDER),
            Panel(Group(Text('ACTIONS', style=f'bold {BEAST_ACID}'), Text(''), right), border_style=BEAST_BORDER),
        )
        yield Static(Panel(Group(Text('BEAST COMMAND DECK', style=f'bold {BEAST_ACID}'), Text('Esc, q, h, or ? closes this overlay.', style=BEAST_MUTED), Text(''), grid), border_style=BEAST_ACID, padding=(1,2), style=BEAST_PANEL), id='help-panel')


class DetailScreen(ModalScreen):
    BINDINGS = [Binding('escape','app.pop_screen','Close'), Binding('q','app.pop_screen','Close'), Binding('v','app.pop_screen','Close')]

    def __init__(self, title: str, payload: Any):
        super().__init__()
        self.detail_title = title
        self.payload = payload

    def compose(self) -> ComposeResult:
        try:
            body = json.dumps(self.payload, indent=2, default=str)
        except Exception:
            body = str(self.payload)
        if len(body) > 9000:
            body = body[:9000] + '\n... truncated ...'
        yield Static(Panel(Group(Text(self.detail_title, style=f'bold {BEAST_ACID}'), Text('Esc/q/v closes this viewer.', style=BEAST_MUTED), Text(''), Text(body, style=BEAST_TEXT)), border_style=BEAST_ACID, padding=(1,2), style=BEAST_PANEL), id='detail-panel')


class CommandPaletteScreen(ModalScreen):
    BINDINGS = [
        Binding('escape','close_palette','Close'), Binding('q','close_palette','Close'),
        Binding('up','move_up','Up'), Binding('down','move_down','Down'),
        Binding('enter','choose','Run'),
    ]

    def __init__(self, commands: List[Dict[str, Any]]):
        super().__init__()
        self.commands = commands
        self.index = 0

    def compose(self) -> ComposeResult:
        yield Static(self.render_palette(), id='command-palette')

    def render_palette(self):
        table = Table(expand=True, box=box.SIMPLE_HEAVY)
        table.add_column('', width=2)
        table.add_column('Command', ratio=2)
        table.add_column('Scope', ratio=1)
        table.add_column('Key', width=12)
        for i, command in enumerate(self.commands):
            table.add_row(
                selected_marker(i == self.index),
                selected_text(str(command.get('label') or ''), i == self.index),
                Text(str(command.get('scope') or 'BEAST'), style=BEAST_MUTED),
                Text(str(command.get('key') or ''), style=BEAST_ACID),
            )
        return Panel(
            Group(
                Text('BEAST COMMAND PALETTE', style=f'bold {BEAST_ACID}'),
                Text('↑↓ select  Enter run  Esc close', style=BEAST_MUTED),
                Text(''),
                table,
            ),
            border_style=BEAST_ACID,
            padding=(1, 2),
            style=BEAST_PANEL,
        )

    def _refresh(self) -> None:
        try:
            self.query_one('#command-palette', Static).update(self.render_palette())
        except Exception:
            pass

    def action_move_up(self):
        self.index = clamp(self.index - 1, 0, max(0, len(self.commands) - 1))
        self._refresh()

    def action_move_down(self):
        self.index = clamp(self.index + 1, 0, max(0, len(self.commands) - 1))
        self._refresh()

    def action_choose(self):
        if self.commands:
            command_id = str(self.commands[self.index].get('id') or '')
            try:
                self.app.execute_palette_command(command_id)
            except Exception:
                pass
        self.dismiss()

    def action_close_palette(self):
        self.dismiss()


class ContextPickerScreen(ModalScreen):
    BINDINGS = [
        Binding('escape','close_picker','Close'), Binding('q','close_picker','Close'),
        Binding('up','move_up','Up'), Binding('down','move_down','Down'),
        Binding('enter','toggle_file','Toggle'), Binding('c','close_picker','Close'),
    ]

    def __init__(self, files: List[Dict[str, Any]], selected_files: List[str]):
        super().__init__()
        self.files = files
        self.selected_files = set(selected_files)
        self.index = 0

    def compose(self) -> ComposeResult:
        yield Static(self.render_picker(), id='context-picker')

    def render_picker(self):
        table = Table(expand=True, box=box.SIMPLE_HEAVY)
        for col in ['','Use','File','Size','Type']:
            table.add_column(col)
        if not self.files:
            table.add_row('','', 'No file candidates found', '', '')
        for i, item in enumerate(self.files[:80]):
            path = str(item.get('path') or '')
            table.add_row(
                selected_marker(i == self.index),
                Text('●' if path in self.selected_files else '○', style=BEAST_GREEN if path in self.selected_files else BEAST_MUTED),
                selected_text(path, i == self.index),
                str(item.get('size') or ''),
                str(item.get('ext') or ''),
            )
        return Panel(
            Group(
                Text('BEAST CONTEXT PICKER', style=f'bold {BEAST_ACID}'),
                Text('↑↓ select  Enter toggle  c/Esc close. Selected files become bounded live-session context.', style=BEAST_MUTED),
                Text(''), table,
            ),
            border_style=BEAST_ACID, padding=(1,2), style=BEAST_PANEL,
        )

    def refresh_view(self):
        try: self.query_one('#context-picker', Static).update(self.render_picker())
        except Exception: pass

    def action_move_up(self):
        self.index = clamp(self.index - 1, 0, max(0, len(self.files)-1)); self.refresh_view()

    def action_move_down(self):
        self.index = clamp(self.index + 1, 0, max(0, len(self.files)-1)); self.refresh_view()

    def action_toggle_file(self):
        if not self.files: return
        path = str(self.files[self.index].get('path') or '')
        if not path: return
        if path in self.selected_files: self.selected_files.remove(path)
        else: self.selected_files.add(path)
        try: self.app.set_context_files(sorted(self.selected_files))
        except Exception: pass
        self.refresh_view()

    def action_close_picker(self): self.app.pop_screen()


class PatchPlanScreen(ModalScreen):
    BINDINGS = [
        Binding('escape','app.pop_screen','Close'), Binding('q','app.pop_screen','Close'),
        Binding('y','approve','Approve'), Binding('b','reject','Reject'),
        Binding('f','diff','Diff'), Binding('v','verify','Verify'), Binding('u','apply','Apply'),
    ]
    def __init__(self, plan: Dict[str, Any]):
        super().__init__(); self.plan = plan
    def compose(self) -> ComposeResult:
        try: body = json.dumps(self.plan, indent=2, default=str)
        except Exception: body = str(self.plan)
        if len(body) > 7500: body = body[:7500] + '\n... raw plan truncated ...'
        summary = current_plan_summary(self.plan)
        status_line = (
            f"provider_generated={summary['provider_generated']}  "
            f"source_ops={summary['source_operations']}  requests={summary['requests']}  "
            f"gate={summary['gate_status']}"
        )
        top = Table.grid(expand=True); top.add_column(ratio=1); top.add_column(ratio=1)
        top.add_row(
            Panel(Group(Text('OUTPUT GOVERNANCE', style=f'bold {BEAST_ACID}'), Text('Provider Handoff → Action IR → Output Gate → Local Compiler', style=BEAST_MUTED), Text(''), governance_table(self.plan)), border_style='#2A8F5A'),
            Panel(Group(Text('NON-MUTATING REQUESTS', style=f'bold {BEAST_ACID}'), Text('Verifier/context requests are preserved; they are not source writes.', style=BEAST_MUTED), Text(''), requests_table(self.plan)), border_style=BEAST_BORDER),
        )
        yield Static(
            Panel(
                Group(
                    Text('BEAST SOURCE PLAN', style=f'bold {BEAST_ACID}'),
                    Text('y approve/save  f diff/select hunks  v verify  u apply selected  b reject  Esc/q close.', style=BEAST_MUTED),
                    Text(status_line, style=BEAST_GREEN if summary.get('diff_compiled') else BEAST_WARN),
                    Text(''),
                    top,
                    Text(''),
                    Panel(Group(Text('OPERATIONS', style=f'bold {BEAST_ACID}'), operations_table(self.plan)), border_style=BEAST_BORDER),
                    Text(''),
                    Panel(Text(body, style='#AAB8B2'), title='Raw governed plan', border_style=BEAST_BORDER),
                ),
                border_style=BEAST_ACID,
                padding=(1,2),
                style=BEAST_PANEL,
            ),
            id='patch-plan-viewer',
        )
    def action_approve(self):
        try: self.app.approve_current_patch_plan()
        except Exception: pass
    def action_diff(self):
        try: self.app.action_preview_diff()
        except Exception: pass
    def action_verify(self):
        try: self.app.action_verify_patch_plan()
        except Exception: pass
    def action_apply(self):
        try: self.app.apply_current_patch_plan()
        except Exception: pass
    def action_reject(self):
        try: self.app.reject_current_patch_plan()
        except Exception: pass
        self.app.pop_screen()


class DiffPreviewScreen(ModalScreen):
    BINDINGS = [
        Binding('escape','app.pop_screen','Close'), Binding('q','app.pop_screen','Close'),
        Binding('up','move_up','Prev hunk'), Binding('down','move_down','Next hunk'),
        Binding('space','toggle_hunk','Toggle hunk'), Binding('f','refresh_diff','Refresh diff'),
        Binding('u','apply','Apply selected'), Binding('y','apply','Apply selected'), Binding('z','rollback','Rollback'),
    ]
    def __init__(self, diff: Dict[str, Any]):
        super().__init__(); self.diff = diff; self.index = 0
    def compose(self) -> ComposeResult:
        yield Static(self.render_diff(), id='diff-preview')
    def render_diff(self):
        try:
            plan = self.app.current_patch_plan()
            if plan:
                self.diff = BeastApiClient(self.app.base_url).render_patch_diff(plan).data
        except Exception:
            pass
        operations = self.diff.get('operations') or []
        plan = {}
        try:
            plan = self.app.current_patch_plan() or {}
        except Exception:
            plan = {}
        self.index = clamp(self.index, 0, max(0, len(operations)-1))
        table = Table(expand=True, box=box.SIMPLE_HEAVY)
        for col in ['', 'Use', 'Hunk', 'Path', 'Type', 'Description']:
            table.add_column(col)
        if not operations:
            table.add_row('', '', 'none', 'No operations', '', '')
        for i, op in enumerate(operations[:40]):
            table.add_row(
                selected_marker(i == self.index),
                Text('●' if op.get('selected') else '○', style=BEAST_GREEN if op.get('selected') else BEAST_MUTED),
                str(op.get('op_id') or f'op_{i+1:03d}'),
                selected_text(op.get('path',''), i == self.index),
                'source' if op.get('source_edit') else 'beast',
                str(op.get('description') or '')[:70],
            )
        text = str(self.diff.get('diff') or '')
        if len(text) > 13500:
            text = text[:13500] + '\n... diff truncated in preview ...'
        summary = current_plan_summary(plan)
        meta = f"Plan={self.diff.get('plan_id','n/a')}  operations={self.diff.get('operation_count','?')}  selected={self.diff.get('selected_count','?')}  requests={summary.get('requests', 0)}  gate={summary.get('gate_status')}  errors={len(self.diff.get('errors') or [])}"
        return Panel(
            Group(
                Text('BEAST SOURCE DIFF PREVIEW', style=f'bold {BEAST_ACID}'),
                Text('↑↓ select hunk  Space toggle  u/y apply selected  z rollback latest  Esc/q close', style=BEAST_MUTED),
                Text(meta, style=BEAST_GREEN if summary.get('diff_compiled') else BEAST_WARN),
                Text(''),
                table,
                Text(''),
                Panel(Group(Text('NON-MUTATING REQUESTS', style=f'bold {BEAST_ACID}'), requests_table(plan)), border_style=BEAST_BORDER),
                Text(''),
                Text(text or 'No diff rendered.', style=BEAST_TEXT),
            ), border_style=BEAST_ACID, padding=(1,2), style=BEAST_PANEL,
        )
    def refresh_view(self):
        try: self.query_one('#diff-preview', Static).update(self.render_diff())
        except Exception: pass
    def action_move_up(self):
        self.index = max(0, self.index - 1); self.refresh_view()
    def action_move_down(self):
        operations = self.diff.get('operations') or []
        self.index = min(max(0, len(operations)-1), self.index + 1); self.refresh_view()
    def action_toggle_hunk(self):
        try:
            operations = self.diff.get('operations') or []
            if operations:
                self.app.toggle_patch_hunk(str(operations[self.index].get('op_id') or ''))
        except Exception: pass
        self.refresh_view()
    def action_refresh_diff(self): self.refresh_view()
    def action_apply(self):
        try: self.app.apply_current_patch_plan()
        except Exception: pass
    def action_rollback(self):
        try: self.app.rollback_latest_patch()
        except Exception: pass


class ApprovalQueueScreen(ModalScreen):
    BINDINGS = [Binding('escape','app.pop_screen','Close'), Binding('q','app.pop_screen','Close'), Binding('y','approve','Approve'), Binding('b','reject','Reject')]
    def __init__(self, queue: List[Dict[str, Any]]):
        super().__init__(); self.queue = queue
    def compose(self) -> ComposeResult:
        table = Table(expand=True, box=box.SIMPLE_HEAVY)
        for col in ['Plan','Status','Objective','Files']:
            table.add_column(col)
        if not self.queue:
            table.add_row('none','empty','No approvals queued','0')
        for item in self.queue[-12:]:
            table.add_row(str(item.get('plan_id','plan')), str(item.get('status','draft')), str(item.get('objective',''))[:70], str(len(item.get('files_allowed') or [])))
        yield Static(Panel(Group(Text('BEAST APPROVAL QUEUE', style=f'bold {BEAST_ACID}'), Text('y approves latest plan  b rejects latest plan  Esc/q close.', style=BEAST_MUTED), Text(''), table), border_style=BEAST_ACID, padding=(1,2), style=BEAST_PANEL), id='approval-queue')
    def action_approve(self):
        try: self.app.approve_current_patch_plan()
        except Exception: pass
    def action_reject(self):
        try: self.app.reject_current_patch_plan()
        except Exception: pass
        self.app.pop_screen()


class BeastHeader(Static):
    snapshot: BackendSnapshot | None = None
    chat_lines: List[Dict[str, str]] = []
    tool_events: List[str] = []
    session_meta: Dict[str, Any] = {}
    mascot_state: str = 'idle'
    mascot_frame: int = 0
    page: str = 'Mission'

    def render(self):
        snap = self.snapshot
        workspace = Path(os.environ.get('BEAST_WORKSPACE', os.getcwd())).name or 'edgek-beast'
        try:
            app_obj = getattr(self, 'app', None)
        except Exception:
            app_obj = None
        width = getattr(app_obj, 'size', None)
        terminal_width = int(getattr(width, 'width', 140) or 140)
        compact = terminal_width < 110
        brand_grid = Table.grid(expand=True); brand_grid.add_column(width=24); brand_grid.add_column(width=36)
        beast_label = Text('BEAST', style=f'bold {BEAST_ACID}')
        beast_label.stylize('bold')
        brand_group = Group(
            beast_label,
            Text('Power Console', style=BEAST_TEXT),
            Text(PAGE_LABELS.get(self.page, self.page), style=BEAST_MUTED),
        )
        if compact:
            brand_grid.add_row(brand_group, Text('LLM', style=BEAST_GREEN if (snap and snap.deployment_score().get('litellm_running')) else BEAST_WARN))
        else:
            brand_grid.add_row(Group(brand_group, Text(f"Mascot · {mascot_state_for(self.mascot_state).upper()}", style=BEAST_TEXT)), sprite_mascot(self.mascot_state, self.mascot_frame))
        brand = Panel(brand_grid, border_style='#1E2925', style=BEAST_PANEL)

        prec = snap.phase_status() if snap else {}
        deploy = snap.deployment_score() if snap else {}
        selected_provider = provider_key(self.session_meta.get('provider') or os.environ.get('BEAST_PROVIDER') or 'litellm')
        route = provider_route_summary(snap, selected_provider) if snap else {'resolved_model': '…', 'route_provider': '…'}
        model_label = str(route.get('resolved_model') or '…')
        if len(model_label) > 22:
            model_label = model_label[:21] + '…'
        tiles = [
            ('WORKSPACE', '󰉋', workspace, 'OK'),
            ('GATEWAY', '▥', snap.gateway if snap else '…', snap.gateway if snap else '…'),
            ('PROXY', '⬡', snap.proxy if snap else '…', snap.proxy if snap else '…'),
            ('MCP', '◇', snap.mcp if snap else '…', snap.mcp if snap else '…'),
            ('PROVIDER', '▣', selected_provider, 'OK'),
            ('MODEL', 'λ', model_label, 'OK' if snap else 'WAIT'),
            ('PREC', 'P/R/E/C', self._prec_short(prec), 'OK' if snap and prec else 'WAIT'),
            ('NGINX', '⇄', 'READY' if deploy.get('nginx_ready') else 'WAIT', 'OK' if deploy.get('nginx_ready') else 'WARN'),
            ('LITELLM', 'LLM', 'RUN' if deploy.get('litellm_running') else 'OFF', 'OK' if deploy.get('litellm_running') else 'WARN'),
            ('PROVIDERS', '☁', str(len(snap.providers())) if snap else '…', 'OK'),
            ('CAPS', '▦', str(len(snap.capabilities)) if snap else '…', 'OK'),
            ('HANDOFF', '↗', 'READY' if snap and snap.handoff_precheck.get('ready') else 'WAIT', 'OK' if snap and snap.handoff_precheck.get('ready') else 'WARN'),
        ]
        status_grid = Table.grid(expand=True)
        columns = 3 if compact else 5
        for _ in range(columns): status_grid.add_column(ratio=1)
        shown_tiles = tiles[:6] if compact else tiles
        for start in range(0, len(shown_tiles), columns):
            row = [self._tile(title, icon, value, state) for title, icon, value, state in shown_tiles[start:start+columns]]
            while len(row) < columns:
                row.append(Text(''))
            status_grid.add_row(*row)
        layout = Table.grid(expand=True); layout.add_column(width=24 if compact else 66); layout.add_column(ratio=1)
        layout.add_row(brand, status_grid)
        return layout

    def _prec_short(self, phases: Dict[str, str]) -> str:
        if not phases:
            return 'WAIT'
        def mark(name: str) -> str:
            value = phases.get(name, 'WAIT')
            return '✓' if value == 'OK' else '●' if value == 'ACTIVE' else '○'
        return f"P{mark('perceive')} R{mark('reason')} E{mark('economize')} C{mark('crystallize')}"

    def _tile(self, title: str, icon: str, value: Any, state: Any) -> Panel:
        style = status_style(state)
        mini = Table.grid(padding=(0,1)); mini.add_column(); mini.add_column()
        mini.add_row(Text(title, style=BEAST_MUTED), Text('•', style=style))
        mini.add_row(Text(icon, style=BEAST_TEXT), Text(str(value), style=style))
        return Panel(mini, border_style='#1E2925', style=BEAST_PANEL, padding=(0,1))


class ActivityRail(Static):
    def render(self):
        return Text('\n'.join(['󰈙','󰍉','󰘬','▰','◇','⇄','☁','▦','▣','⌁','⚙']), style='#AAB8B2')


class Sidebar(Static):
    selected: reactive[str] = reactive('Mission')
    ITEMS = [('▰','Mission'),('▷','Session'),('◇','PREC'),('⇄','Routing'),('☁','Providers'),('▦','Capabilities'),('▣','Chronicle'),('⚙','Deployment'),('⌁','Diagnostics'),('⚒','Settings')]
    row_pages: List[str] = []

    def render(self):
        table = Table.grid(expand=True); table.add_column(ratio=1)
        self.row_pages = []
        for i, (icon, label) in enumerate(self.ITEMS):
            key = '0' if i == 9 else str(i + 1)
            display = PAGE_LABELS.get(label, label)
            style = f'bold {BEAST_ACID}' if label == self.selected else '#AAB8B2'
            rail = '▌' if label == self.selected else ' '
            cursor = '▶' if label == self.selected else ' '
            table.add_row(Text(f'{rail} {key} {cursor} {icon}  {display}', style=style))
            self.row_pages.append(label)
        footer = Text('\n\n  BEAST v0.2.0\n', style=BEAST_GREEN)
        footer.append('  Governed by design\n', style='#AAB8B2')
        footer.append('  Provider routes visible\n\n', style='#AAB8B2')
        footer.append('  ↑↓ select  ←→ pages\n', style=BEAST_MUTED)
        footer.append('  green steel ', style=BEAST_GREEN); footer.append('>_', style=BEAST_ACID)
        return Panel(Group(Text(''), table, footer), border_style=BEAST_BORDER, padding=(1,1), style=BEAST_PANEL)

    async def on_click(self, event: events.Click) -> None:
        row = int(event.y) - 3
        if 0 <= row < len(self.row_pages):
            event.stop()
            try:
                self.app.set_page(self.row_pages[row])
            except Exception:
                pass


class PageHost(Static):
    page: reactive[str] = reactive('Mission')
    selected_indices: reactive[Dict[str,int]] = reactive({})
    snapshot: BackendSnapshot | None = None

    async def on_click(self, event: events.Click) -> None:
        try:
            if self.page == 'Session':
                self.app.enter_input_mode()
                event.stop()
                return
            row = max(0, int(event.y) - 4)
            self.app.select_page_row(self.page, row)
            event.stop()
        except Exception:
            pass

    def render(self):
        snap = self.snapshot or BackendSnapshot(base_url='offline')
        index = self.selected_indices.get(self.page, 0)
        if self.page == 'Mission': return self.mission_control(snap)
        if self.page == 'Session': return self.live_session_preview(snap)
        if self.page == 'PREC': return self.prec_lifecycle(snap, index)
        if self.page == 'Routing': return self.routing_fabric(snap, index)
        if self.page == 'Providers': return self.providers(snap, index)
        if self.page == 'Capabilities': return self.capabilities(snap, index)
        if self.page == 'Chronicle': return self.chronicle(snap, index)
        if self.page == 'Deployment': return self.deployment(snap, index)
        if self.page == 'Diagnostics': return self.diagnostics(snap, index)
        return self.settings(snap, index)

    def mission_control(self, snap: BackendSnapshot):
        phases = snap.phase_status()
        deploy = snap.deployment_score()
        backend_counts = snap.provider_backend_counts()
        kinds = snap.kinds()
        rows = Table.grid(expand=True); [rows.add_column(ratio=1) for _ in range(4)]
        rows.add_row(
            metric('PREC STATE', f"P:{phases.get('perceive','WAIT')} R:{phases.get('reason','WAIT')} E:{phases.get('economize','WAIT')} C:{phases.get('crystallize','WAIT')}", 'governed lifecycle'),
            metric('PROVIDERS', len(snap.providers()), safe_join(backend_counts, 3), BEAST_GREEN),
            metric('CAPABILITIES', len(snap.capabilities), safe_join(kinds, 4), BEAST_GREEN),
            metric('LITELLM MODELS', deploy.get('litellm_models', 0), f"sidecar {'running' if deploy.get('litellm_running') else 'offline'}", BEAST_GREEN if deploy.get('litellm_models') else BEAST_WARN),
        )
        rows.add_row(
            metric('NGINX EDGE', 'READY' if deploy.get('nginx_ready') else 'WAIT', 'generated config' if deploy.get('nginx_ready') else 'no text returned'),
            metric('CHRONICLE', len(snap.chronicles), 'records loaded'),
            metric('ROUTES', len(snap.routes), 'route cards loaded'),
            metric('HANDOFF', 'READY' if snap.handoff_precheck.get('ready') else 'WAIT', val(snap.handoff_precheck, 'reason', default='precheck')),
        )
        fabric = Table.grid(expand=True); fabric.add_column(ratio=1); fabric.add_column(ratio=1)
        fabric.add_row(self.prec_panel(snap), self.topology_panel(snap))
        lower = Table.grid(expand=True); lower.add_column(ratio=1); lower.add_column(ratio=1)
        lower.add_row(self.recent_prec_panel(snap), self.insight_panel(snap))
        page = Table.grid(expand=True); page.add_column(ratio=1)
        page.add_row(Panel(Group(Text('MISSION CONTROL', style=f'bold {BEAST_ACID}'), Text('The visible power layer: PREC, providers, capabilities, Nginx, LiteLLM, Chronicle, and handoff.', style=BEAST_MUTED), Text(''), rows), border_style=BEAST_ACID, padding=(1,2), style=BEAST_PANEL))
        page.add_row(fabric)
        page.add_row(lower)
        return page

    def prec_panel(self, snap: BackendSnapshot):
        phases = snap.phase_status()
        table = Table.grid(expand=True); table.add_column(width=14); table.add_column(width=10); table.add_column(ratio=1)
        details = {
            'perceive': 'interception, logs, registry, routes',
            'reason': 'insight compiler, evidence scoring',
            'economize': 'handoff packet, selected evidence',
            'crystallize': 'Chronicle, route cards, promotions',
        }
        for phase in ['perceive','reason','economize','crystallize']:
            state = phases.get(phase, 'WAIT')
            table.add_row(Text(phase.upper(), style=BEAST_TEXT), Text(state, style=status_style(state)), Text(details[phase], style='#AAB8B2'))
        return Panel(Group(Text('PREC RIBBON', style=f'bold {BEAST_ACID}'), Text(''), table), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(1,1))

    def topology_panel(self, snap: BackendSnapshot):
        deploy = snap.deployment_score()
        lines = Text()
        for line, style in [
            ('Client / IDE / CLI', BEAST_TEXT),
            ('    ↓', BEAST_MUTED),
            ('Nginx :8080', BEAST_GREEN if deploy.get('nginx_ready') else BEAST_WARN),
            ('    ↓', BEAST_MUTED),
            ('BEAST Gateway :8000', BEAST_GREEN if snap.gateway == 'OK' else BEAST_WARN),
            ('    ├─ Native adapters', BEAST_TEXT),
            ('    ├─ OpenAI-compatible lane', BEAST_TEXT),
            ('    ├─ LiteLLM-managed lane :4000', BEAST_GREEN if deploy.get('litellm_models') else BEAST_WARN),
            ('    └─ Ollama/local scout', BEAST_TEXT),
        ]:
            lines.append(line + '\n', style=style)
        return Panel(Group(Text('ROUTING TOPOLOGY', style=f'bold {BEAST_ACID}'), Text(''), lines), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(1,1))

    def recent_prec_panel(self, snap: BackendSnapshot):
        rows = snap.prec_lifecycles[:6] or snap.prec_recent()[:6]
        table = Table(expand=True, box=box.SIMPLE_HEAVY)
        for col in ['Lifecycle','Kind','Phase','Status']:
            table.add_column(col)
        if not rows:
            table.add_row('none', 'no traces', 'waiting', 'WAIT')
        for row in rows:
            table.add_row(val(row,'lifecycle_id','id',default='prec'), val(row,'kind',default='unknown'), val(row,'current_phase','phase',default='n/a'), Text(val(row,'status',default='unknown'), style=status_style(val(row,'status',default='unknown'))))
        return Panel(Group(Text('RECENT PREC TRACES', style=f'bold {BEAST_ACID}'), Text(''), table), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(1,1))

    def insight_panel(self, snap: BackendSnapshot):
        evidence = snap.insight_packet.get('evidence') or snap.insight_packet.get('ranked_evidence') or []
        table = Table.grid(expand=True); table.add_column(width=22); table.add_column(ratio=1)
        for key, value in [
            ('Insight packet', 'available' if snap.insight_packet else 'missing'),
            ('Evidence records', len(evidence) if isinstance(evidence, list) else 0),
            ('Handoff ready', bool_badge(snap.handoff_precheck.get('ready'))),
            ('Reason', val(snap.handoff_precheck, 'reason', default='precheck active')),
        ]:
            table.add_row(Text(key, style=BEAST_MUTED), Text(str(value), style=status_style(value)))
        return Panel(Group(Text('INSIGHT + HANDOFF', style=f'bold {BEAST_ACID}'), Text(''), table), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(1,1))

    def live_session_preview(self, snap: BackendSnapshot):
        meta = self.session_meta or {}
        provider = meta.get('provider', 'litellm')
        lifecycle = meta.get('lifecycle_id') or 'not started'
        state = meta.get('state', 'idle')
        context_files = getattr(self, 'context_files', [])
        patch_plans = getattr(self, 'patch_plans', [])
        approval_queue = getattr(self, 'approval_queue', [])
        current_plan = approval_queue[-1] if approval_queue else (patch_plans[-1] if patch_plans else {})
        plan_summary = current_plan_summary(current_plan)
        route_summary = provider_route_summary(snap, provider)

        left = Table.grid(expand=True); left.add_column(width=20); left.add_column(ratio=1)
        for k, v in [
            ('Session state', state), ('Provider', route_summary.get('provider_id')), ('Route', route_summary.get('route_provider')),
            ('Model', route_summary.get('resolved_model')), ('PREC lifecycle', lifecycle),
            ('Context files', len(context_files)), ('Patch plans', len(patch_plans)),
            ('Approvals', len(approval_queue)), ('Output gate', plan_summary.get('gate_status', 'not run')),
            ('Requests', plan_summary.get('requests', 0)), ('Handoff ready', 'yes' if snap.handoff_precheck.get('ready') else 'waiting'),
        ]:
            left.add_row(Text(k, style=BEAST_MUTED), Text(str(v), style=status_style(v)))

        provider_rows = Table(expand=True, box=box.SIMPLE)
        for col in ['Provider','Backend','Route','Model','Secret']:
            provider_rows.add_column(col)
        providers = snap.providers()[:8] or [{'provider_id': provider, 'backend': 'selected', 'state': state}]
        for item in providers[:8]:
            pid = val(item, 'provider_id','id','name', default='provider')
            selected = provider_key(pid) == provider_key(provider)
            row_route = provider_route_summary(snap, pid)
            provider_rows.add_row(
                selected_text(pid, selected),
                val(item, 'backend','adapter_class', default=row_route.get('backend', '')),
                row_route.get('route_provider', ''),
                Text(str(row_route.get('resolved_model', ''))[:26], style=BEAST_GREEN if selected else BEAST_TEXT),
                Text(row_route.get('secret', ''), style=status_style(row_route.get('secret'))),
            )

        context_table = Table(expand=True, box=box.SIMPLE)
        for col in ['#','Context file']:
            context_table.add_column(col)
        if not context_files:
            context_table.add_row('0','No files selected. Press c to pick bounded context.')
        for i, path in enumerate(context_files[-8:], 1):
            context_table.add_row(str(i), Text(path, style=BEAST_GREEN))

        plan_table = Table(expand=True, box=box.SIMPLE)
        for col in ['Plan','Status','Gate','Ops','Req']:
            plan_table.add_column(col)
        if not patch_plans:
            plan_table.add_row('none','no plan yet','not run','0','0')
        for plan in patch_plans[-5:]:
            row_summary = current_plan_summary(plan)
            plan_table.add_row(
                str(plan.get('plan_id','plan')),
                Text(str(plan.get('status','draft')), style=status_style(plan.get('status'))),
                Text(str(row_summary.get('gate_status')), style=status_style(row_summary.get('gate_status'))),
                str(row_summary.get('source_operations')),
                str(row_summary.get('requests')),
            )

        transcript = Text()
        lines = self.chat_lines[-12:] if self.chat_lines else [
            {'role':'system', 'content':'Press s to start a BEAST live session, c to pick context, n or [/] to select provider, then type below and press Enter.'},
            {'role':'system', 'content':'Commands: /context, /sourceplan, /diff, /verify, /apply, /rollback, /provider <id>, /handoff <objective>, /quality <objective>.'},
        ]
        for line in lines:
            role = line.get('role','system')
            content = str(line.get('content',''))
            style = BEAST_GREEN if role == 'assistant' else BEAST_TEXT if role == 'user' else BEAST_INFO if role == 'tool' else BEAST_MUTED
            prefix = 'YOU' if role == 'user' else 'BEAST' if role == 'assistant' else 'TOOL' if role == 'tool' else 'SYS'
            transcript.append(f'{prefix}: ', style=f'bold {style}')
            transcript.append(content[:2200] + ('…' if len(content) > 2200 else '') + '\n\n', style=style)

        events = Text()
        if self.tool_events:
            for event in self.tool_events[-11:]:
                events.append(f'• {event}\n', style=BEAST_INFO if 'ok' in event.lower() or 'recorded' in event.lower() or 'saved' in event.lower() else BEAST_WARN if 'error' in event.lower() or 'fallback' in event.lower() or 'reject' in event.lower() else BEAST_TEXT)
        else:
            events.append('No tool events yet. The first turn will run context → task envelope → insight → handoff → provider/local scout.\n', style=BEAST_MUTED)

        left_stack = Table.grid(expand=True); left_stack.add_column(ratio=1)
        left_stack.add_row(Panel(Group(Text('SESSION LAUNCHER', style=f'bold {BEAST_ACID}'), Text('Provider and model are resolved before every governed turn.', style=BEAST_MUTED), Text(''), left), border_style=BEAST_BORDER))
        left_stack.add_row(Panel(Group(Text('ROUTE LOCK', style=f'bold {BEAST_ACID}'), Text('beast-auto → registry default → adapter plan → proxy lane', style=BEAST_MUTED), Text(''), provider_route_table(route_summary, compact=True)), border_style='#2A8F5A'))
        left_stack.add_row(Panel(Group(Text('PROVIDER SELECTOR', style=f'bold {BEAST_ACID}'), Text('[ / ] or n cycles provider', style=BEAST_MUTED), Text(''), provider_rows), border_style=BEAST_BORDER))
        left_stack.add_row(Panel(Group(Text('BOUNDED CONTEXT', style=f'bold {BEAST_ACID}'), Text('c opens picker. Context is passed to live turns.', style=BEAST_MUTED), Text(''), context_table), border_style=BEAST_BORDER))
        left_stack.add_row(Panel(Group(Text('PATCH PLANS / APPROVALS', style=f'bold {BEAST_ACID}'), Text('o sourceplan  f diff  v verify  u apply  y save  l queue', style=BEAST_MUTED), Text(''), plan_table), border_style=BEAST_BORDER))

        governance = Table.grid(expand=True); governance.add_column(ratio=1); governance.add_column(ratio=1)
        governance.add_row(
            Panel(Group(Text('CURRENT OUTPUT GATE', style=f'bold {BEAST_ACID}'), governance_table(current_plan)), border_style='#2A8F5A'),
            Panel(Group(Text('REQUESTS / VERIFIERS', style=f'bold {BEAST_ACID}'), requests_table(current_plan)), border_style=BEAST_BORDER),
        )

        size = getattr(getattr(self, 'app', None), 'size', None)
        terminal_width = int(getattr(size, 'width', 140) or 140)
        layout = Table.grid(expand=True)
        transcript_panel = Panel(Group(Text('LIVE CHAT / CODING TRANSCRIPT', style=f'bold {BEAST_ACID}'), Text(''), transcript), border_style=BEAST_BORDER)
        if terminal_width < 120:
            layout.add_column(ratio=1)
            layout.add_row(transcript_panel)
            layout.add_row(left_stack)
        else:
            layout.add_column(width=42 if terminal_width < 150 else 48)
            layout.add_column(ratio=1)
            layout.add_row(left_stack, transcript_panel)
        bottom = Panel(Group(Text('TOOL / PREC EVENT STREAM', style=f'bold {BEAST_ACID}'), Text(''), events), border_style='#2A8F5A')
        return Panel(Group(Text('BEAST LIVE SESSION COCKPIT', style=f'bold {BEAST_ACID}'), Text('Provider Handoff → Action IR → Output Gate → Diff Preview → Verified Apply → Chronicle.', style=BEAST_MUTED), Text(''), layout, Text(''), governance, Text(''), bottom, Text(''), Text('Input: Enter sends. c context. o sourceplan. f diff. v verify. u apply. y save. n provider. /help commands.', style=BEAST_GREEN)), border_style=BEAST_ACID, padding=(1,2), style=BEAST_PANEL)

    def prec_lifecycle(self, snap: BackendSnapshot, index: int):
        rows = snap.prec_lifecycles or snap.prec_recent() or []
        if not rows:
            rows = [{'lifecycle_id':'no_prec_traces_loaded','kind':'empty','current_phase':'waiting','status':'WAIT','objective':'No PREC records returned yet.'}]
        index = clamp(index, 0, len(rows)-1); selected = rows[index]
        table = Table(expand=True, box=box.SIMPLE_HEAVY)
        for col in ['','Lifecycle','Kind','Phase','Status','Objective']:
            table.add_column(col)
        for i, row in enumerate(rows):
            table.add_row(selected_marker(i==index), selected_text(val(row,'lifecycle_id','id',default='prec'), i==index), val(row,'kind',default='unknown'), val(row,'current_phase','phase',default='n/a'), Text(val(row,'status',default='unknown'), style=status_style(val(row,'status',default='unknown'))), val(row,'objective','task_id',default='n/a')[:48])
        detail = Table.grid(expand=True); detail.add_column(width=20); detail.add_column(ratio=1)
        for key in ['lifecycle_id','kind','objective','scope','status','current_phase','task_id','provider','summary']:
            detail.add_row(Text(key, style=BEAST_MUTED), Text(val(selected,key,default=''), style=BEAST_TEXT))
        counts = snap.prec_counts()
        count_table = Table(expand=True, box=box.SIMPLE)
        for col in ['Kind','Status','Count']:
            count_table.add_column(col)
        for row in counts[:10]:
            count_table.add_row(val(row,'kind',default='unknown'), Text(val(row,'status',default='unknown'), style=status_style(val(row,'status',default='unknown'))), val(row,'count',default='0'))
        bottom = Table.grid(expand=True); bottom.add_column(ratio=1); bottom.add_column(ratio=1)
        bottom.add_row(Panel(Group(Text('SELECTED TRACE', style=f'bold {BEAST_ACID}'), Text(''), detail), border_style='#2A8F5A'), Panel(Group(Text('PREC COUNTS', style=f'bold {BEAST_ACID}'), Text(''), count_table), border_style=BEAST_BORDER))
        page = Table.grid(expand=True); page.add_column(ratio=1)
        page.add_row(Panel(Group(Text('PREC LIFECYCLE INDEX', style=f'bold {BEAST_ACID}'), Text('↑↓ select trace   v view   a crystallize/export', style=BEAST_MUTED), Text(''), table), border_style=BEAST_ACID, padding=(1,2), style=BEAST_PANEL))
        page.add_row(bottom)
        return page

    def routing_fabric(self, snap: BackendSnapshot, index: int):
        adapters = snap.provider_adapters or []
        if not adapters:
            adapters = [{'provider_id': val(p,'provider_id','name',default='provider'), 'backend': val(p,'backend',default='unknown'), 'proxy_path': val(p,'proxy_path','endpoint',default='/proxy'), 'model': val(p,'default_model','model',default='n/a')} for p in snap.providers()]
        if not adapters:
            adapters = [{'provider_id':'no_adapters_loaded','backend':'unknown','proxy_path':'/proxy','model':'n/a'}]
        index = clamp(index, 0, len(adapters)-1); selected = adapters[index]
        size = getattr(getattr(self, 'app', None), 'size', None)
        compact = int(getattr(size, 'width', 140) or 140) < 132
        table = Table(expand=True, box=box.SIMPLE_HEAVY)
        columns = ['','Provider','Backend','Route','Model'] if compact else ['','Provider','Backend','Adapter','Route','Proxy Path','Resolved Model']
        for col in columns:
            table.add_column(col)
        for i, row in enumerate(adapters):
            pid = val(row,'provider_id','name',default='provider')
            route = provider_route_summary(snap, pid)
            base = [
                selected_marker(i==index),
                selected_text(pid, i==index),
                Text(route.get('backend', val(row,'backend','adapter_class',default='unknown')), style=BEAST_INFO),
            ]
            if compact:
                table.add_row(*base, route.get('route_provider', ''), route.get('resolved_model', '')[:34])
            else:
                table.add_row(*base, route.get('adapter_class', ''), route.get('route_provider', ''), route.get('proxy_path', ''), route.get('resolved_model', '')[:42])
        backend_counts = snap.provider_backend_counts()
        bars = Table(expand=True, box=box.SIMPLE)
        for col in ['Backend class','Providers']:
            bars.add_column(col)
        for backend, count in sorted(backend_counts.items(), key=lambda x: (-x[1], x[0])):
            bars.add_row(Text(backend, style=BEAST_TEXT), Text(str(count), style=BEAST_GREEN))
        route_detail = provider_route_summary(snap, val(selected, 'provider_id','name', default='provider'))
        detail = provider_route_table(route_detail, compact=False)
        detail.add_row(Text('Default model', style=BEAST_MUTED), Text(route_detail.get('default_model', ''), style=BEAST_TEXT))
        detail.add_row(Text('Lane', style=BEAST_MUTED), Text(route_detail.get('lane', ''), style=BEAST_INFO))
        bottom = Table.grid(expand=True); bottom.add_column(ratio=1); bottom.add_column(ratio=1)
        bottom.add_row(Panel(Group(Text('BACKEND CLASSES', style=f'bold {BEAST_ACID}'), Text(''), bars), border_style=BEAST_BORDER), Panel(Group(Text('SELECTED ROUTE RESOLUTION', style=f'bold {BEAST_ACID}'), Text('Provider → backend → adapter → route provider → resolved model.', style=BEAST_MUTED), Text(''), detail), border_style='#2A8F5A'))
        page = Table.grid(expand=True); page.add_column(ratio=1)
        page.add_row(Panel(Group(Text('ROUTING FABRIC', style=f'bold {BEAST_ACID}'), Text('Nginx edge → BEAST governance → native/OpenAI-compatible/LiteLLM/Ollama lanes. The model shown is the one beast-auto resolves to.', style=BEAST_MUTED), Text(''), table), border_style=BEAST_ACID, padding=(1,2), style=BEAST_PANEL))
        page.add_row(bottom)
        return page

    def providers(self, snap: BackendSnapshot, index: int):
        providers = snap.providers()
        if not providers:
            providers = [{'provider_id':'no_providers_loaded','backend':'unknown','enabled':False,'proxy_path':'/proxy'}]
        index = clamp(index, 0, len(providers)-1); selected = providers[index]
        size = getattr(getattr(self, 'app', None), 'size', None)
        compact = int(getattr(size, 'width', 140) or 140) < 132
        table = Table(expand=True, box=box.SIMPLE_HEAVY)
        columns = ['','Provider','Enabled','Route','Model','Fitness','Secret'] if compact else ['','Provider','Enabled','Backend','Route','Resolved Model','Fitness','Proxy Path','Secret']
        for col in columns:
            table.add_column(col)
        secrets = snap.provider_secrets.get('providers') if isinstance(snap.provider_secrets.get('providers'), dict) else {}
        for i, row in enumerate(providers):
            pid = val(row,'provider_id','id','name',default='provider')
            enabled = row.get('enabled', row.get('status','available'))
            route = provider_route_summary(snap, pid)
            fitness = provider_fitness_score(snap, pid)
            fitness_label = str(fitness.get('score'))
            if fitness_label != 'n/a':
                fitness_label += '%'
            secret_ready = 'present' if pid in secrets else route.get('secret', 'env')
            base = [selected_marker(i==index), selected_text(pid, i==index), Text(str(enabled), style=status_style(enabled))]
            if compact:
                table.add_row(*base, route.get('route_provider',''), route.get('resolved_model','')[:32], Text(fitness_label, style=status_style(fitness.get('eligible'))), Text(secret_ready, style=status_style(secret_ready)))
            else:
                table.add_row(*base, Text(route.get('backend','unknown'), style=BEAST_INFO), route.get('route_provider',''), route.get('resolved_model','')[:36], Text(fitness_label, style=status_style(fitness.get('eligible'))), route.get('proxy_path',''), Text(secret_ready, style=status_style(secret_ready)))
        selected_pid = val(selected,'provider_id','id','name',default='provider')
        route_detail = provider_route_summary(snap, selected_pid)
        fitness_detail = provider_fitness_score(snap, selected_pid)
        detail = provider_route_table(route_detail, compact=False)
        detail.add_row(Text('Fitness score', style=BEAST_MUTED), Text(str(fitness_detail.get('score')) + ('%' if fitness_detail.get('score') != 'n/a' else ''), style=status_style(fitness_detail.get('eligible'))))
        detail.add_row(Text('Fitness eligible', style=BEAST_MUTED), Text(str(fitness_detail.get('eligible')), style=status_style(fitness_detail.get('eligible'))))
        detail.add_row(Text('Fitness sample', style=BEAST_MUTED), Text(f"{fitness_detail.get('sample_size')} records; clean={fitness_detail.get('clean')} rescued={fitness_detail.get('rescued')}", style=BEAST_TEXT))
        for key in ['managed_by','risk_level','requires_approval','openai_compatible']:
            item = val(selected,key,default='')
            if item:
                detail.add_row(Text(key, style=BEAST_MUTED), Text(item, style=status_style(item)))
        return self.two_part_page('PROVIDERS', '↑↓ select provider   t test   v route/model   e config', table, 'SELECTED PROVIDER ROUTE', detail)

    def capabilities(self, snap: BackendSnapshot, index: int):
        rows = snap.capabilities or [{'capability_id':'no_capabilities_loaded','kind':'empty','risk_level':'low','status':'waiting'}]
        index = clamp(index, 0, len(rows)-1); selected = rows[index]
        table = Table(expand=True, box=box.SIMPLE_HEAVY)
        for col in ['','Capability','Kind','Family','Risk','Approval','Endpoint/Command']:
            table.add_column(col)
        for i, cap in enumerate(rows):
            table.add_row(selected_marker(i==index), selected_text(val(cap,'capability_id','name',default='cap'), i==index), val(cap,'kind',default='unknown'), val(cap,'family',default=''), Text(val(cap,'risk_level',default='low'), style=status_style(val(cap,'risk_level',default='low'))), Text(bool_badge(cap.get('requires_approval')), style=BEAST_WARN if cap.get('requires_approval') else BEAST_GREEN), val(cap,'endpoint','command','test_command',default='local')[:42])
        kinds = snap.kinds(); families = snap.families()
        kinds_table = Table(expand=True, box=box.SIMPLE)
        kinds_table.add_column('Kind'); kinds_table.add_column('Count')
        for k, v in sorted(kinds.items(), key=lambda x: (-x[1], x[0]))[:12]:
            kinds_table.add_row(k, Text(str(v), style=BEAST_GREEN))
        detail = Table.grid(expand=True); detail.add_column(width=22); detail.add_column(ratio=1)
        for key in ['capability_id','name','kind','family','risk_level','requires_approval','read_only','writes_files','network_access','health_check','test_command']:
            value = selected.get(key)
            if value not in (None, '', []):
                detail.add_row(Text(key, style=BEAST_MUTED), Text(safe_join(value), style=status_style(value) if isinstance(value, bool) else BEAST_TEXT))
        bottom = Table.grid(expand=True); bottom.add_column(width=36); bottom.add_column(ratio=1)
        bottom.add_row(Panel(Group(Text('KIND COUNTS', style=f'bold {BEAST_ACID}'), Text(''), kinds_table), border_style=BEAST_BORDER), Panel(Group(Text('SELECTED CAPABILITY', style=f'bold {BEAST_ACID}'), Text(''), detail), border_style='#2A8F5A'))
        page = Table.grid(expand=True); page.add_column(ratio=1)
        page.add_row(Panel(Group(Text('CAPABILITY REGISTRY', style=f'bold {BEAST_ACID}'), Text('Unified tools, providers, MCP tools, workflows, routes, parsers, linters, DBs, plugins, and skills.', style=BEAST_MUTED), Text(''), table), border_style=BEAST_ACID, padding=(1,2), style=BEAST_PANEL))
        page.add_row(bottom)
        return page

    def chronicle(self, snap: BackendSnapshot, index: int):
        rows = snap.chronicles or [{'task_id':'no_chronicle_records_loaded','chronicle_type':'empty','provider':'local','status':'waiting','summary':'No Chronicle records returned yet.'}]
        index = clamp(index, 0, len(rows)-1); selected = rows[index]
        table = Table(expand=True, box=box.SIMPLE_HEAVY)
        for col in ['','Task','Type','Provider','Category','Confidence']:
            table.add_column(col)
        for i, r in enumerate(rows):
            table.add_row(selected_marker(i==index), selected_text(val(r,'task_id','id',default='task'), i==index), val(r,'chronicle_type','type','task_class',default='record'), val(r,'provider',default='local'), val(r,'category','status',default='done'), val(r,'confidence',default=''))
        detail = Table.grid(expand=True); detail.add_column(width=18); detail.add_column(ratio=1)
        for key in ['summary','root_cause','confidence','memory_candidate','created_at']:
            detail.add_row(Text(key, style=BEAST_MUTED), Text(val(selected,key,default=''), style=BEAST_TEXT))
        return self.two_part_page('CHRONICLE VAULT', '↑↓ select record   v view   a promote/export', table, 'CRYSTALLIZED RECORD', detail)

    def deployment(self, snap: BackendSnapshot, index: int):
        deploy = snap.deployment_score()
        rows = [
            {'name':'Nginx config', 'status':'ready' if deploy.get('nginx_ready') else 'waiting', 'value': f"{len(snap.nginx_config.splitlines())} lines", 'action':'render/write guarded'},
            {'name':'LiteLLM sidecar', 'status':'running' if deploy.get('litellm_running') else 'offline', 'value': f"port {deploy.get('litellm_port')}", 'action':'start/status'},
            {'name':'LiteLLM models', 'status':'ready' if deploy.get('litellm_models') else 'waiting', 'value': deploy.get('litellm_models'), 'action':'render config'},
            {'name':'Provider adapters', 'status':'ready' if snap.provider_adapters else 'waiting', 'value': len(snap.provider_adapters), 'action':'sync/test'},
            {'name':'Provider secrets', 'status':'ready' if snap.provider_secret_count() else 'env', 'value': snap.provider_secret_count(), 'action':'presence only'},
        ]
        index = clamp(index, 0, len(rows)-1); selected = rows[index]
        table = Table(expand=True, box=box.SIMPLE_HEAVY)
        for col in ['','Subsystem','Status','Value','Action']:
            table.add_column(col)
        for i, row in enumerate(rows):
            table.add_row(selected_marker(i==index), selected_text(row['name'], i==index), Text(str(row['status']), style=status_style(row['status'])), str(row['value']), row['action'])
        config_preview = snap.nginx_config[:1200] if snap.nginx_config else 'No generated Nginx text returned from /edgek/deploy/nginx-config.'
        model_table = Table(expand=True, box=box.SIMPLE)
        model_table.add_column('LiteLLM model'); model_table.add_column('Provider params')
        for model in snap.litellm_models[:8]:
            params = model.get('litellm_params') if isinstance(model.get('litellm_params'), dict) else {}
            model_table.add_row(val(model,'model_name',default='model'), val(params,'model',default=''))
        bottom = Table.grid(expand=True); bottom.add_column(ratio=1); bottom.add_column(ratio=1)
        bottom.add_row(Panel(Group(Text('NGINX PREVIEW', style=f'bold {BEAST_ACID}'), Text(''), Text(config_preview, style='#AAB8B2')), border_style=BEAST_BORDER), Panel(Group(Text('LITELLM MODELS', style=f'bold {BEAST_ACID}'), Text(''), model_table), border_style=BEAST_BORDER))
        page = Table.grid(expand=True); page.add_column(ratio=1)
        page.add_row(Panel(Group(Text('DEPLOYMENT + EDGE WIRING', style=f'bold {BEAST_ACID}'), Text('Nginx remains the local edge. BEAST stays in front. LiteLLM remains the managed provider lane.', style=BEAST_MUTED), Text(''), table), border_style=BEAST_ACID, padding=(1,2), style=BEAST_PANEL))
        page.add_row(bottom)
        return page

    def diagnostics(self, snap: BackendSnapshot, index: int):
        http = snap.http_telemetry if isinstance(snap.http_telemetry, dict) else {}
        io = http.get('io') if isinstance(http.get('io'), dict) else {}
        bandwidth = http.get('bandwidth') if isinstance(http.get('bandwidth'), dict) else {}
        http_latency = http.get('latency_ms') if isinstance(http.get('latency_ms'), dict) else {}
        status_counts = http.get('status_counts') if isinstance(http.get('status_counts'), dict) else {}
        runtime = snap.runtime_metrics if isinstance(snap.runtime_metrics, dict) else {}
        runtime_health = runtime.get('health') if isinstance(runtime.get('health'), dict) else {}
        runtime_status = str(runtime_health.get('status') or ('OK' if runtime else 'WARN')).upper()
        runtime_latency = runtime.get('latency_ms') if isinstance(runtime.get('latency_ms'), dict) else {}
        provider_counts = runtime.get('provider_counts') if isinstance(runtime.get('provider_counts'), dict) else {}
        recent_failures = runtime.get('recent_failures') if isinstance(runtime.get('recent_failures'), list) else []
        rows = [
            ('Gateway', snap.gateway, snap.base_url), ('Proxy', snap.proxy, '/proxy/health'), ('MCP HTTP', snap.mcp, '/mcp/health'),
            ('Capabilities', 'OK' if snap.capabilities else 'WARN', f'{len(snap.capabilities)} records'),
            ('Provider registry', 'OK' if snap.providers() else 'WARN', f'{len(snap.providers())} providers'),
            ('Provider adapters', 'OK' if snap.provider_adapters else 'WARN', f'{len(snap.provider_adapters)} adapters'),
            ('PREC lifecycle', 'OK' if snap.prec_state else 'WARN', f'{len(snap.prec_lifecycles)} traces'),
            ('Nginx config', 'OK' if snap.nginx_config else 'WARN', f'{len(snap.nginx_config.splitlines())} lines'),
            ('LiteLLM config', 'OK' if snap.litellm_models else 'WARN', f'{len(snap.litellm_models)} models'),
            ('LiteLLM sidecar', 'OK' if snap.litellm_sidecar.get('running') else 'WARN', f"port {snap.litellm_sidecar.get('port', 4000)}"),
            ('Insight compiler', 'OK' if snap.insight_packet else 'WARN', f"{len(snap.insight_packet.get('evidence') or [])} evidence"),
            ('Handoff precheck', 'OK' if snap.handoff_precheck.get('ready') else 'WARN', val(snap.handoff_precheck,'reason',default='not ready')),
            ('HTTP packets', 'OK' if http else 'WARN', f"{http.get('request_count', 0)} requests; recent {val(http, 'packets.recent_window_requests', default='0')}"),
            ('Gateway I/O', 'OK' if http else 'WARN', f"rx {fmt_bytes(io.get('rx_bytes'))} / tx {fmt_bytes(io.get('tx_bytes'))}"),
            ('Bandwidth', 'OK' if http else 'WARN', f"rx {fmt_bytes(bandwidth.get('rx_bytes_per_second'))}/s / tx {fmt_bytes(bandwidth.get('tx_bytes_per_second'))}/s"),
            ('HTTP latency', 'OK' if http_latency else 'WARN', f"avg {http_latency.get('avg', 0)}ms / p95 {http_latency.get('p95', 0)}ms"),
            ('Provider attempts', runtime_status if runtime else 'WARN', f"{runtime.get('sample_size', 0)} sampled; failures {runtime_health.get('failure_count', len(recent_failures))}; rate {runtime_health.get('failure_rate', 0)}"),
            ('Provider latency', 'OK' if runtime_latency else 'WARN', f"avg {runtime_latency.get('avg', 0)}ms / p95 {runtime_latency.get('p95', 0)}ms"),
        ]
        index = clamp(index, 0, len(rows)-1)
        table = Table(expand=True, box=box.SIMPLE_HEAVY)
        for col in ['','Component','Status','Notes']:
            table.add_column(col)
        for i, (name, status, note) in enumerate(rows):
            table.add_row(selected_marker(i==index), selected_text(name, i==index), Text(status, style=status_style(status)), str(note))
        metrics = Table(expand=True, box=box.SIMPLE)
        for col in ['Signal','Value']:
            metrics.add_column(col)
        metrics.add_row('HTTP status', ', '.join(f'{k}:{v}' for k, v in list(status_counts.items())[:8]) or 'none')
        metrics.add_row('Runtime health', json.dumps(runtime_health, default=str)[:220] if runtime_health else 'unknown')
        metrics.add_row('Runtime providers', ', '.join(f'{k}:{sum(v.values()) if isinstance(v, dict) else v}' for k, v in list(provider_counts.items())[:8]) or 'none')
        if recent_failures:
            latest = recent_failures[0]
            metrics.add_row('Latest provider failure', f"{latest.get('provider')} {latest.get('status')}: {str(latest.get('error_message') or latest.get('error_type'))[:140]}")
        else:
            metrics.add_row('Latest provider failure', 'none')
        errors = '\n'.join(f'{k}: {v}' for k,v in snap.errors.items()) or 'No endpoint errors recorded.'
        return Panel(Group(Text('DIAGNOSTICS OVERVIEW', style=f'bold {BEAST_ACID}'), Text('live endpoint health + telemetry + provider runtime metrics', style=BEAST_MUTED), Text(''), table, Text(''), Panel(metrics, title='Telemetry', border_style=BEAST_BORDER), Text(''), Panel(Text(errors[:1800], style='#AAB8B2'), title='Endpoint errors', border_style=BEAST_BORDER)), border_style=BEAST_ACID, padding=(1,2), style=BEAST_PANEL)

    def settings(self, snap: BackendSnapshot, index: int):
        rows = [
            ('Gateway URL', snap.base_url, 'BEAST_GATEWAY_URL or --gateway-url'),
            ('Workspace', os.environ.get('BEAST_WORKSPACE', os.getcwd()), 'BEAST_WORKSPACE'),
            ('Backend mode', 'live' if snap.online else 'offline fallback', 'health based'),
            ('Page model', 'Power Console', 'Patch 1'),
            ('Handoff ready', bool_badge(snap.handoff_precheck.get('ready')), 'current task markup rule'),
            ('Capability count', str(len(snap.capabilities)), '/edgek/capabilities'),
            ('Provider count', str(len(snap.providers())), '/edgek/providers/registry'),
            ('Sprite mode', 'terminal-safe', 'PNG assets reserved for webview/chat'),
        ]
        index = clamp(index, 0, len(rows)-1)
        table = Table(expand=True, box=box.SIMPLE_HEAVY)
        for col in ['','Setting','Value','Source']:
            table.add_column(col)
        for i, row in enumerate(rows):
            table.add_row(selected_marker(i==index), selected_text(row[0], i==index), Text(str(row[1]), style=BEAST_GREEN), row[2])
        return Panel(Group(Text('SETTINGS CORE', style=f'bold {BEAST_ACID}'), Text('↑↓ select   e edit queued   v view', style=BEAST_MUTED), Text(''), table), border_style=BEAST_ACID, padding=(1,2), style=BEAST_PANEL)

    def two_part_page(self, title: str, subtitle: str, table: Table, detail_title: str, detail: Any):
        page = Table.grid(expand=True); page.add_column(ratio=1)
        page.add_row(Panel(Group(Text(title, style=f'bold {BEAST_ACID}'), Text(subtitle, style=BEAST_MUTED), Text(''), table), border_style=BEAST_ACID, padding=(1,2), style=BEAST_PANEL))
        page.add_row(Panel(Group(Text(detail_title, style=f'bold {BEAST_ACID}'), Text(''), detail), border_style='#2A8F5A', padding=(1,2), style=BEAST_PANEL))
        return page


class BeastMissionConsole(App):
    CSS_PATH = 'beast.tcss'
    BINDINGS = [
        Binding('q','quit','Quit'), Binding('r','refresh_backend','Refresh'), Binding('?','help','Help'), Binding('h','help','Help'),
        Binding('escape','leave_input','Nav mode', priority=True), Binding('i','enter_input','Chat input'),
        Binding('left','previous_page','Prev'), Binding('right','next_page','Next'), Binding('up','move_up','Up'), Binding('down','move_down','Down'),
        Binding('1','mission','Mission'), Binding('2','session','Session'), Binding('3','prec','PREC'), Binding('4','routing','Routing'), Binding('5','providers','Providers'), Binding('6','capabilities','Capabilities'), Binding('7','chronicle','Chronicle'), Binding('8','deployment','Deployment'), Binding('9','diagnostics','Diagnostics'), Binding('0','settings','Settings'),
        Binding('s','start_session','Start'), Binding('p','prepare_handoff','Handoff'), Binding('d','doctor','Doctor'), Binding('g','refresh_backend','Gateway'), Binding('m','refresh_backend','MCP'), Binding('x','refresh_backend','Proxy'),
        Binding('t','test_selected','Test'), Binding('v','view_selected','View'), Binding('e','edit_selected','Edit'),
        Binding('n','next_provider','Provider'), Binding(']','next_provider','Next provider'), Binding('[','previous_provider','Prev provider'), Binding('w','toggle_streaming','Streaming'), Binding('k','cancel_turn','Cancel'),
        Binding('c','context_picker','Context'), Binding('o','build_patch_plan','Source patch'), Binding('f','preview_diff','Diff/hunks'), Binding('u','apply_patch_plan','Apply selected'), Binding('z','rollback_patch','Rollback'), Binding('l','approval_queue','Approvals'), Binding('y','approve_patch_plan','Approve plan'), Binding('a','approve_selected','Approve'), Binding('b','block_selected','Block'), Binding('ctrl+k','command_palette','Command'),
    ]
    selected_page: reactive[str] = reactive('Mission')
    input_mode: reactive[bool] = reactive(False)
    selected_indices: reactive[Dict[str,int]] = reactive({})
    snapshot: BackendSnapshot | None = None

    def __init__(self, base_url: str | None = None):
        super().__init__()
        self.base_url = base_url or os.environ.get('BEAST_GATEWAY_URL','http://127.0.0.1:8000')
        self.chat_lines: List[Dict[str, str]] = []
        self.tool_events: List[str] = []
        self.session_meta: Dict[str, Any] = {'state': 'idle', 'provider': provider_key(os.environ.get('BEAST_PROVIDER', 'litellm'))}
        self.context_files: List[str] = []
        self.context_candidates: List[Dict[str, Any]] = []
        self.patch_plans: List[Dict[str, Any]] = []
        self.approval_queue: List[Dict[str, Any]] = []
        self.latest_diff: Dict[str, Any] = {}
        self.current_turn_cancelled = False
        self.streaming_enabled = True
        self.patch_hunk_index: int = 0
        self.terminal_width: int = 140
        self.mascot_state: str = 'idle'
        self.mascot_frame: int = 0
        self.mascot_hold_ticks: int = 0

    def compose(self) -> ComposeResult:
        with Vertical(id='root'):
            yield BeastHeader(id='beast-header')
            with Horizontal(id='body'):
                yield ActivityRail(id='activity-rail')
                yield Sidebar(id='sidebar')
                with Vertical(id='content'):
                    with VerticalScroll(id='page-scroll'):
                        yield PageHost(id='page-host')
                    yield Input(placeholder='NAV MODE: press Enter or i to type. Press / for slash commands. Esc returns to navigation.', id='chat-input')
            yield Static('? Help  ←→ Pages  ↑↓ Select  c Context  o SourcePlan  f Diff  v Verify  u Apply  z Rollback  q Quit', id='terminal-strip')

    async def on_mount(self) -> None:
        self.title = 'BEAST Power Console'
        self._sync()
        try:
            self.set_interval(0.22, self._tick_mascot)
        except Exception:
            pass
        await self.fetch_backend()

    def _set_mascot_state(self, state: str, hold_ticks: int = 0) -> None:
        normalized = mascot_state_for(state)
        if normalized != self.mascot_state:
            self.mascot_frame = 0
        self.mascot_state = normalized
        self.mascot_hold_ticks = max(0, int(hold_ticks or 0))
        self._sync()

    def _tick_mascot(self) -> None:
        frames = mascot_frames().get(mascot_state_for(self.mascot_state)) or []
        if frames:
            self.mascot_frame = (self.mascot_frame + 1) % len(frames)
        if self.mascot_state in {'finished', 'alert'} and self.mascot_hold_ticks > 0:
            self.mascot_hold_ticks -= 1
            if self.mascot_hold_ticks <= 0:
                self.mascot_state = 'idle'
                self.mascot_frame = 0
        try:
            header = self.query_one('#beast-header', BeastHeader)
            header.mascot_state = self.mascot_state
            header.mascot_frame = self.mascot_frame
            header.refresh()
        except Exception:
            pass

    async def on_resize(self, event: events.Resize) -> None:
        try:
            self.terminal_width = int(event.size.width)
        except Exception:
            pass
        try:
            self.query_one('#page-scroll', VerticalScroll).scroll_home(animate=False)
        except Exception:
            pass
        self._sync()

    def _sync(self) -> None:
        try:
            terminal_width = int(self.terminal_width or getattr(getattr(self, 'size', None), 'width', 140) or 140)
            self.query_one('#beast-header', BeastHeader).styles.display = 'block' if terminal_width >= 72 else 'none'
            self.query_one('#activity-rail', ActivityRail).styles.display = 'block' if terminal_width >= 100 else 'none'
            self.query_one('#sidebar', Sidebar).styles.display = 'block' if terminal_width >= 72 else 'none'
            self.query_one('#sidebar', Sidebar).selected = self.selected_page
            host = self.query_one('#page-host', PageHost)
            host.page = self.selected_page
            host.selected_indices = dict(self.selected_indices)
            host.snapshot = self.snapshot
            host.chat_lines = list(self.chat_lines)
            host.tool_events = list(self.tool_events)
            host.session_meta = dict(self.session_meta)
            host.context_files = list(self.context_files)
            host.patch_plans = list(self.patch_plans)
            host.approval_queue = list(self.approval_queue)
            host.refresh()
            chat_input = self.query_one('#chat-input', Input)
            chat_input.display = self.selected_page == 'Session'
            chat_input.disabled = False
            chat_input.placeholder = 'INPUT MODE: type prompt, Enter sends, Esc returns to navigation.' if self.input_mode else 'NAV MODE: press Enter or i to type. Press / for slash commands. Esc returns to navigation.'
            if self.selected_page == 'Session' and self.input_mode:
                chat_input.focus()
            else:
                try:
                    if getattr(chat_input, 'has_focus', False):
                        self.screen.set_focus(None)
                except Exception:
                    pass
            header = self.query_one('#beast-header', BeastHeader)
            header.snapshot = self.snapshot
            header.page = self.selected_page
            header.session_meta = dict(self.session_meta)
            header.mascot_state = self.mascot_state
            header.mascot_frame = self.mascot_frame
            header.refresh()
            try:
                scroll = self.query_one('#page-scroll', VerticalScroll)
                scroll.refresh()
            except Exception:
                pass
        except Exception:
            pass

    async def fetch_backend(self) -> None:
        previous_state = self.mascot_state
        if previous_state == 'idle':
            self._set_mascot_state('working')
        self.snapshot = await BeastApiClient(self.base_url).snapshot()
        if previous_state == 'idle':
            self._set_mascot_state('finished', hold_ticks=8)
        self._sync()
        self.notify('Live BEAST power state refreshed.', title='BEAST')

    def page_rows(self) -> int:
        snap = self.snapshot or BackendSnapshot(base_url=self.base_url)
        if self.selected_page == 'Session': return max(1, len(self.chat_lines) or 1)
        if self.selected_page == 'PREC': return max(1, len(snap.prec_lifecycles or snap.prec_recent()))
        if self.selected_page == 'Routing': return max(1, len(snap.provider_adapters or snap.providers()))
        if self.selected_page == 'Providers': return max(1, len(snap.providers()))
        if self.selected_page == 'Capabilities': return max(1, len(snap.capabilities))
        if self.selected_page == 'Chronicle': return max(1, len(snap.chronicles))
        if self.selected_page == 'Deployment': return 5
        if self.selected_page == 'Diagnostics': return 12
        if self.selected_page == 'Settings': return 8
        return 1

    def set_page(self, page: str) -> None:
        self.selected_page = page
        self._sync()
        self.notify(f'{PAGE_LABELS.get(page,page)} page active.', title='BEAST')

    async def on_click(self, event: events.Click) -> None:
        try:
            page_host = self.query_one('#page-host', PageHost)
            if page_host.region.contains(event.screen_x, event.screen_y):
                if self.selected_page == 'Session':
                    event.stop()
                    self.enter_input_mode()
        except Exception:
            pass

    def action_help(self): self.push_screen(HelpScreen())
    def action_refresh_backend(self): self.run_worker(self.fetch_backend(), exclusive=True)
    def action_previous_page(self):
        if self.input_mode: return
        self.set_page(PAGES[(PAGES.index(self.selected_page)-1) % len(PAGES)])
    def action_next_page(self):
        if self.input_mode: return
        self.set_page(PAGES[(PAGES.index(self.selected_page)+1) % len(PAGES)])
    def _move(self, delta: int):
        current = self.selected_indices.get(self.selected_page,0)
        updated = clamp(current + delta, 0, self.page_rows()-1)
        next_indices = dict(self.selected_indices)
        next_indices[self.selected_page] = updated
        self.selected_indices = next_indices
        self._sync()

    def select_page_row(self, page: str, row: int) -> None:
        if page != self.selected_page:
            self.selected_page = page
        next_indices = dict(self.selected_indices)
        next_indices[page] = clamp(row, 0, self.page_rows() - 1)
        self.selected_indices = next_indices
        self._sync()
    def action_move_up(self):
        if self.input_mode: return
        self._move(-1)
    def action_move_down(self):
        if self.input_mode: return
        self._move(1)
    def action_mission(self): self.set_page('Mission')
    def action_session(self): self.enter_input_mode()
    def action_prec(self): self.set_page('PREC')
    def action_routing(self): self.set_page('Routing')
    def action_providers(self): self.set_page('Providers')
    def action_capabilities(self): self.set_page('Capabilities')
    def action_chronicle(self): self.set_page('Chronicle')
    def action_deployment(self): self.set_page('Deployment')
    def action_diagnostics(self): self.set_page('Diagnostics')
    def action_settings(self): self.set_page('Settings')
    def selected_label(self):
        return f"{PAGE_LABELS.get(self.selected_page,self.selected_page)} row {self.selected_indices.get(self.selected_page,0)+1}"

    def enter_input_mode(self, prefix: str = '') -> None:
        if self.selected_page != 'Session':
            self.selected_page = 'Session'
        self.input_mode = True
        self._sync()
        try:
            chat_input = self.query_one('#chat-input', Input)
            if prefix and not chat_input.value:
                chat_input.value = prefix
                chat_input.cursor_position = len(prefix)
            chat_input.focus()
        except Exception:
            pass

    def exit_input_mode(self) -> None:
        if self.input_mode:
            self.input_mode = False
            self._sync()
            self.notify('Navigation mode active. Use arrows and command keys again.', title='BEAST')

    def action_enter_input(self) -> None:
        self.enter_input_mode()

    def action_slash_input(self) -> None:
        self.enter_input_mode('/')

    def action_leave_input(self) -> None:
        self.exit_input_mode()

    async def on_key(self, event: events.Key) -> None:
        # Do not bind Enter globally. In navigation mode, Enter opens the input.
        # In input mode, the Input widget owns Enter and emits Input.Submitted.
        if self.input_mode:
            if event.key == 'escape':
                event.stop()
                self.exit_input_mode()
            return

        if self.selected_page == 'Session' and event.key == 'enter':
            event.stop()
            self.enter_input_mode()
            return

        if self.selected_page == 'Session' and event.character == '/':
            event.stop()
            self.enter_input_mode('/')
            return

    def selected_item(self) -> Dict[str, Any]:
        snap = self.snapshot or BackendSnapshot(base_url=self.base_url)
        index = self.selected_indices.get(self.selected_page, 0)
        rows: List[Dict[str, Any]] = []
        if self.selected_page == 'Providers': rows = snap.providers()
        elif self.selected_page == 'Routing': rows = snap.provider_adapters or snap.providers()
        elif self.selected_page == 'Capabilities': rows = snap.capabilities
        elif self.selected_page == 'PREC': rows = snap.prec_lifecycles or snap.prec_recent()
        elif self.selected_page == 'Chronicle': rows = snap.chronicles
        elif self.selected_page == 'Deployment':
            deploy = snap.deployment_score()
            rows = [
                {'name': 'Nginx config', 'action': 'nginx_dry_run', 'ready': deploy.get('nginx_ready')},
                {'name': 'LiteLLM sidecar', 'action': 'litellm_start_dry_run', 'running': deploy.get('litellm_running')},
                {'name': 'LiteLLM models', 'action': 'render_litellm_config', 'count': deploy.get('litellm_models')},
                {'name': 'Provider adapters', 'action': 'provider_adapters', 'count': len(snap.provider_adapters)},
                {'name': 'Write generated configs', 'action': 'write_configs'},
            ]
        elif self.selected_page == 'Diagnostics':
            rows = [{'name': 'Diagnostics refresh', 'action': 'refresh'}, {'name': 'Quality cascade', 'action': 'quality'}, {'name': 'PREC state', 'action': 'prec'}, {'name': 'Nginx dry-run', 'action': 'nginx_dry_run'}, {'name': 'LiteLLM dry-run', 'action': 'litellm_start_dry_run'}]
        elif self.selected_page == 'Settings':
            rows = [{'name': 'Settings', 'base_url': self.base_url, 'session': self.session_meta}]
        if self.selected_page == 'Session':
            rows = self.patch_plans or [{'page': 'Session', 'provider': self.session_meta.get('provider'), 'context_files': self.context_files, 'approval_queue': self.approval_queue, 'latest_diff': self.latest_diff, 'streaming_enabled': self.streaming_enabled, 'turn_cancelled': self.current_turn_cancelled}]
        if not rows:
            return {'page': self.selected_page, 'index': index, 'note': 'no selected item available'}
        return rows[clamp(index, 0, len(rows)-1)]

    def selected_provider_id(self) -> str:
        item = self.selected_item()
        return provider_key(item.get('provider_id') or item.get('id') or item.get('name') or self.session_meta.get('provider') or 'litellm')

    def provider_ids(self) -> List[str]:
        snap = self.snapshot or BackendSnapshot(base_url=self.base_url)
        ids: List[str] = []
        for item in snap.providers():
            pid = provider_key(val(item, 'provider_id','id','name', default=''))
            if pid and pid not in ids:
                ids.append(pid)
        for item in snap.provider_adapters:
            pid = provider_key(val(item, 'provider_id','id','name', default=''))
            if pid and pid not in ids:
                ids.append(pid)
        if not ids:
            ids = ['litellm','anthropic','openai','gemini','ollama']
        return ids

    def set_context_files(self, files: List[str]) -> None:
        self.context_files = files[:8]
        self.session_meta['context_files'] = list(self.context_files)
        self.tool_events.append(f'context selected: {len(self.context_files)} file(s)')
        self._sync()

    def action_next_provider(self):
        ids = self.provider_ids(); current = str(self.session_meta.get('provider') or ids[0])
        idx = ids.index(current) if current in ids else -1
        self.session_meta['provider'] = ids[(idx + 1) % len(ids)]
        route = provider_route_summary(self.snapshot or BackendSnapshot(base_url=self.base_url), self.session_meta["provider"])
        self.tool_events.append(f'provider selected: {route["provider_id"]} → {route["route_provider"]} → {route["resolved_model"]}')
        self.set_page('Session')

    def action_previous_provider(self):
        ids = self.provider_ids(); current = str(self.session_meta.get('provider') or ids[0])
        idx = ids.index(current) if current in ids else 0
        self.session_meta['provider'] = ids[(idx - 1) % len(ids)]
        route = provider_route_summary(self.snapshot or BackendSnapshot(base_url=self.base_url), self.session_meta["provider"])
        self.tool_events.append(f'provider selected: {route["provider_id"]} → {route["route_provider"]} → {route["resolved_model"]}')
        self.set_page('Session')

    def action_context_picker(self):
        self.set_page('Session')
        try:
            self.context_candidates = BeastApiClient(self.base_url).workspace_file_candidates(limit=80)
        except Exception:
            self.context_candidates = []
        self.push_screen(ContextPickerScreen(self.context_candidates, self.context_files))

    def action_build_patch_plan(self):
        self.set_page('Session')
        self.run_worker(self._build_source_patch_plan(), exclusive=False)

    async def _build_source_patch_plan(self):
        objective = self.chat_lines[-1]['content'] if self.chat_lines else 'Prepare a governed source patch from selected BEAST context.'
        provider = str(self.session_meta.get('provider') or 'litellm')
        self._set_mascot_state('working')
        self.tool_events.append(f'source patch draft requested via {provider}')
        self._sync()
        result = await BeastApiClient(self.base_url).draft_source_patch_plan(objective, self.context_files, provider=provider)
        if result.ok:
            plan = result.data
            self.patch_plans.append(plan)
            self.approval_queue.append(plan)
            self.tool_events.append(result.brief(260))
            self.chat_lines.append({'role': 'tool', 'content': result.brief(1200)})
            self.push_screen(PatchPlanScreen(plan))
            self._set_mascot_state('finished', hold_ticks=12)
        else:
            self.tool_events.append(result.brief(260))
            self.notify(result.error or 'Could not build source patch plan', title='BEAST source patch', severity='warning')
            self._set_mascot_state('alert', hold_ticks=18)
        self._sync()

    def build_metadata_patch_plan(self):
        self.set_page('Session')
        objective = self.chat_lines[-1]['content'] if self.chat_lines else 'Prepare a governed workspace edit plan from selected BEAST context.'
        provider = str(self.session_meta.get('provider') or 'litellm')
        self._set_mascot_state('working')
        result = BeastApiClient(self.base_url).build_patch_plan(objective, self.context_files, provider=provider)
        if result.ok:
            plan = result.data
            self.patch_plans.append(plan)
            self.approval_queue.append(plan)
            self.tool_events.append(result.brief(240))
            self.chat_lines.append({'role': 'tool', 'content': result.brief(1000)})
            self.push_screen(PatchPlanScreen(plan))
            self._set_mascot_state('finished', hold_ticks=12)
        else:
            self.tool_events.append(result.brief(240))
            self.notify(result.error or 'Could not build metadata patch plan', title='BEAST patch plan', severity='warning')
            self._set_mascot_state('alert', hold_ticks=18)
        self._sync()

    def current_patch_plan(self) -> Dict[str, Any] | None:
        return self.approval_queue[-1] if self.approval_queue else (self.patch_plans[-1] if self.patch_plans else None)

    def toggle_patch_hunk(self, op_id: str):
        plan = self.current_patch_plan()
        if not plan or not op_id:
            return
        ops = plan.get('operations') or []
        all_ids = [str(op.get('op_id') or f'op_{i+1:03d}') for i, op in enumerate(ops) if isinstance(op, dict)]
        selected = set(str(x) for x in (plan.get('selected_operations') or all_ids))
        if op_id in selected:
            selected.remove(op_id)
        else:
            selected.add(op_id)
        plan['selected_operations'] = [x for x in all_ids if x in selected]
        self.latest_diff = BeastApiClient(self.base_url).render_patch_diff(plan).data
        self.tool_events.append(f'hunk {op_id} ' + ('selected' if op_id in selected else 'skipped'))
        self._sync()

    def action_verify_patch_plan(self):
        plan = self.current_patch_plan()
        if not plan:
            self.notify('No patch plan is queued for verification.', title='BEAST verify', severity='warning')
            self._set_mascot_state('alert', hold_ticks=12)
            return
        self._set_mascot_state('working')
        result = BeastApiClient(self.base_url).verify_patch_plan(plan)
        self.tool_events.append(result.brief(320))
        self.chat_lines.append({'role': 'tool', 'content': result.brief(1200)})
        self.notify(result.summary or result.error, title='BEAST verify', severity='information' if result.ok else 'warning')
        self._set_mascot_state('finished' if result.ok else 'alert', hold_ticks=12 if result.ok else 18)
        self._sync()

    def action_preview_diff(self):
        plan = self.current_patch_plan()
        if not plan:
            self.notify('No patch plan available. Press o to build one first.', title='BEAST diff', severity='warning')
            self._set_mascot_state('alert', hold_ticks=12)
            return
        self._set_mascot_state('working')
        result = BeastApiClient(self.base_url).render_patch_diff(plan)
        if result.ok:
            self.latest_diff = result.data
            self.tool_events.append(result.brief(280))
            self.chat_lines.append({'role': 'tool', 'content': result.brief(1200)})
            self.push_screen(DiffPreviewScreen(self.latest_diff))
            self._set_mascot_state('finished', hold_ticks=10)
        else:
            self.latest_diff = result.data or {}
            self.tool_events.append(result.brief(280))
            self.chat_lines.append({'role': 'tool', 'content': result.brief(1200)})
            self.notify(result.error or 'Could not render diff', title='BEAST diff', severity='warning')
            if self.latest_diff:
                self.push_screen(DiffPreviewScreen(self.latest_diff))
            self._set_mascot_state('alert', hold_ticks=18)
        self._sync()

    def apply_current_patch_plan(self):
        plan = self.current_patch_plan()
        if not plan:
            self.notify('No patch plan is queued for apply.', title='BEAST apply', severity='warning')
            self._set_mascot_state('alert', hold_ticks=12)
            return
        self._set_mascot_state('working')
        result = BeastApiClient(self.base_url).apply_patch_plan(plan, approved=True)
        if result.ok:
            saved = result.data.get('plan') or plan
            for existing in self.patch_plans:
                if existing.get('plan_id') == saved.get('plan_id'):
                    existing.update(saved)
            self.approval_queue = [p for p in self.approval_queue if p.get('plan_id') != saved.get('plan_id')]
            self.tool_events.append(result.brief(320))
            self.chat_lines.append({'role': 'tool', 'content': result.brief(1200)})
            self.notify(result.summary, title='BEAST patch applied')
            self._set_mascot_state('finished', hold_ticks=16)
        else:
            self.tool_events.append(result.brief(320))
            self.chat_lines.append({'role': 'tool', 'content': result.brief(1200)})
            self.notify(result.error, title='BEAST patch apply', severity='warning')
            self._set_mascot_state('alert', hold_ticks=20)
        self._sync()

    def action_apply_patch_plan(self):
        self.apply_current_patch_plan()

    def rollback_latest_patch(self):
        self._set_mascot_state('working')
        result = BeastApiClient(self.base_url).rollback_last_patch()
        self.tool_events.append(result.brief(320))
        self.chat_lines.append({'role': 'tool', 'content': result.brief(1200)})
        self.notify(result.summary or result.error, title='BEAST rollback', severity='information' if result.ok else 'warning')
        self._set_mascot_state('finished' if result.ok else 'alert', hold_ticks=14 if result.ok else 18)
        self._sync()

    def action_rollback_patch(self):
        self.rollback_latest_patch()

    def approve_current_patch_plan(self):
        plan = self.current_patch_plan()
        if not plan:
            self.notify('No patch plan is queued for approval.', title='BEAST approvals', severity='warning')
            return
        result = BeastApiClient(self.base_url).save_patch_plan(plan)
        if result.ok:
            saved = result.data.get('plan') or plan
            for existing in self.patch_plans:
                if existing.get('plan_id') == saved.get('plan_id'):
                    existing.update(saved)
            self.approval_queue = [p for p in self.approval_queue if p.get('plan_id') != saved.get('plan_id')]
            self.tool_events.append(result.brief(280))
            self.chat_lines.append({'role': 'tool', 'content': result.brief(900)})
            self.notify(result.summary, title='BEAST plan approved')
        else:
            self.tool_events.append(result.brief(280))
            self.notify(result.error, title='BEAST plan approval', severity='warning')
        self._sync()

    def reject_current_patch_plan(self):
        plan = self.approval_queue.pop() if self.approval_queue else None
        if plan:
            plan['status'] = 'rejected_by_operator'
            self.tool_events.append(f"patch plan rejected: {plan.get('plan_id')}")
            self.chat_lines.append({'role': 'tool', 'content': f"Rejected patch plan {plan.get('plan_id')}."})
        else:
            self.notify('No patch plan queued.', title='BEAST approvals', severity='warning')
        self._sync()

    def action_approval_queue(self):
        self.push_screen(ApprovalQueueScreen(self.approval_queue))

    def action_approve_patch_plan(self):
        self.approve_current_patch_plan()

    def action_test_selected(self):
        self.run_worker(self._run_selected_action('test'), exclusive=False)

    def action_view_selected(self):
        if self.selected_page == 'Session' and self.patch_plans:
            self.action_verify_patch_plan(); return
        item = self.selected_item()
        if self.selected_page in {'Providers', 'Routing'}:
            pid = val(item, 'provider_id', 'id', 'name', default=self.session_meta.get('provider', 'litellm'))
            payload = dict(item)
            payload['resolved_route'] = provider_route_summary(self.snapshot or BackendSnapshot(base_url=self.base_url), pid)
            self.push_screen(DetailScreen(f"{PAGE_LABELS.get(self.selected_page,self.selected_page)} route", payload))
            return
        self.push_screen(DetailScreen(f"{PAGE_LABELS.get(self.selected_page,self.selected_page)} selected item", item))

    def action_edit_selected(self):
        self.run_worker(self._run_selected_action('edit'), exclusive=False)

    def action_approve_selected(self):
        if self.selected_page == 'Session':
            self.approve_current_patch_plan(); return
        self.run_worker(self._run_selected_action('approve'), exclusive=False)

    def action_block_selected(self):
        if self.selected_page == 'Session':
            self.reject_current_patch_plan(); return
        self.run_worker(self._run_selected_action('block'), exclusive=False)

    def action_start_session(self):
        self.set_page('Session')
        self.enter_input_mode()
        self.run_worker(self._start_live_session(), exclusive=True)

    def action_prepare_handoff(self):
        objective = self.chat_lines[-1]['content'] if self.chat_lines else 'Prepare BEAST live session handoff'
        self.run_worker(self._run_handoff(objective), exclusive=False)

    def action_doctor(self):
        self.action_refresh_backend()
        self.run_worker(self._run_selected_action('doctor'), exclusive=False)

    def command_palette_items(self) -> List[Dict[str, Any]]:
        return [
            {'id': 'refresh', 'label': 'Refresh backend state', 'scope': 'Gateway', 'key': 'r'},
            {'id': 'start_session', 'label': 'Start live coding session', 'scope': 'Session', 'key': 's'},
            {'id': 'prepare_handoff', 'label': 'Prepare provider handoff', 'scope': 'Output governance', 'key': 'p'},
            {'id': 'sourceplan', 'label': 'Build governed source patch plan', 'scope': 'SourcePlan', 'key': 'o'},
            {'id': 'preview_diff', 'label': 'Preview/select patch hunks', 'scope': 'SourcePlan', 'key': 'f'},
            {'id': 'apply_patch', 'label': 'Apply selected patch hunks', 'scope': 'SourcePlan', 'key': 'u'},
            {'id': 'rollback', 'label': 'Rollback latest patch apply', 'scope': 'SourcePlan', 'key': 'z'},
            {'id': 'context_picker', 'label': 'Open context picker', 'scope': 'Context', 'key': 'c'},
            {'id': 'approvals', 'label': 'Open approval queue', 'scope': 'Governance', 'key': 'l'},
            {'id': 'doctor', 'label': 'Run diagnostics refresh', 'scope': 'Diagnostics', 'key': 'd'},
            {'id': 'providers', 'label': 'Go to provider fitness', 'scope': 'Routing', 'key': '5'},
            {'id': 'chronicle', 'label': 'Go to Chronicle', 'scope': 'Memory', 'key': '7'},
            {'id': 'settings', 'label': 'Go to settings', 'scope': 'Config', 'key': '0'},
        ]

    def execute_palette_command(self, command_id: str) -> None:
        actions = {
            'refresh': self.action_refresh_backend,
            'start_session': self.action_start_session,
            'prepare_handoff': self.action_prepare_handoff,
            'sourceplan': self.action_build_patch_plan,
            'preview_diff': self.action_preview_diff,
            'apply_patch': self.action_apply_patch_plan,
            'rollback': self.action_rollback_patch,
            'context_picker': self.action_context_picker,
            'approvals': self.action_approval_queue,
            'doctor': self.action_doctor,
            'providers': self.action_providers,
            'chronicle': self.action_chronicle,
            'settings': self.action_settings,
        }
        action = actions.get(command_id)
        if not action:
            self.notify(f'Unknown command: {command_id}', title='BEAST', severity='warning')
            return
        action()
        self.notify(f'Command executed: {command_id}', title='BEAST')

    def action_command_palette(self):
        self.push_screen(CommandPaletteScreen(self.command_palette_items()))

    async def _start_live_session(self) -> None:
        objective = 'BEAST live coding session from CLI/TUI'
        provider = str(self.session_meta.get('provider') or 'litellm')
        self._set_mascot_state('working')
        result = await BeastApiClient(self.base_url).start_live_session(objective, provider=provider, workspace=os.environ.get('BEAST_WORKSPACE', os.getcwd()))
        if result.ok:
            lifecycle_id = str(result.data.get('lifecycle_id') or result.data.get('id') or '')
            self.session_meta.update({'state': 'active', 'provider': provider, 'lifecycle_id': lifecycle_id})
            self.chat_lines.append({'role': 'system', 'content': f'Live BEAST session started. Provider={provider}. PREC={lifecycle_id or "n/a"}. Type a prompt below.'})
            self.tool_events.append(result.brief(200))
            self.notify('Live session started.', title='BEAST')
            self.enter_input_mode()
            self._set_mascot_state('finished', hold_ticks=10)
        else:
            self.session_meta.update({'state': 'error'})
            self.chat_lines.append({'role': 'system', 'content': f'Could not start PREC session: {result.error}'})
            self.notify(result.error, title='BEAST session start', severity='warning')
            self._set_mascot_state('alert', hold_ticks=18)
        self._sync()

    async def _run_handoff(self, objective: str) -> None:
        self._set_mascot_state('working')
        result = await BeastApiClient(self.base_url).prepare_handoff(objective, provider=str(self.session_meta.get('provider') or 'litellm'))
        self.tool_events.append(result.brief(260))
        self.chat_lines.append({'role': 'tool', 'content': result.brief(900)})
        self._set_mascot_state('finished' if result.ok else 'alert', hold_ticks=12 if result.ok else 18)
        await self.fetch_backend()

    async def _run_selected_action(self, mode: str) -> None:
        self._set_mascot_state('working')
        api = BeastApiClient(self.base_url)
        item = self.selected_item()
        page = self.selected_page
        result: ActionResult
        if page in {'Providers', 'Routing'} and mode in {'test', 'doctor'}:
            result = await api.provider_diagnostic(self.selected_provider_id())
        elif page == 'Providers' and mode == 'edit':
            result = await api.provider_route_card(self.selected_provider_id())
        elif page == 'Routing' and mode in {'approve', 'edit'}:
            result = await api.provider_route_card(self.selected_provider_id())
        elif page == 'Deployment':
            action = str(item.get('action') or '')
            if mode == 'approve' and action == 'write_configs': result = await api.write_deploy_configs()
            elif mode == 'approve' and action == 'litellm_start_dry_run': result = await api.litellm_start(approved=True, dry_run=False)
            elif mode == 'block' and action == 'litellm_start_dry_run': result = await api.litellm_stop(approved=True, dry_run=False)
            elif action == 'nginx_dry_run': result = await api.nginx_apply(approved=False, dry_run=True)
            elif action == 'litellm_start_dry_run': result = await api.litellm_start(approved=False, dry_run=True)
            elif action == 'render_litellm_config': result = await api.render_litellm_config()
            elif action == 'write_configs': result = await api.write_deploy_configs()
            else: result = await api.render_nginx_config()
        elif page == 'Capabilities' and mode == 'test':
            name = str(item.get('capability_id') or item.get('name') or 'selected capability')
            result = await api.compile_insight(f'Test capability {name}', provider=str(self.session_meta.get('provider') or 'litellm'))
        elif page == 'PREC' and mode in {'test', 'doctor'}:
            result = await api.action('PREC state', '/edgek/prec/state', method='GET')
        elif page == 'Chronicle' and mode in {'test', 'view'}:
            task_id = str(item.get('task_id') or item.get('id') or '')
            result = await api.action('Chronicle detail', f'/edgek/chronicle/{task_id}', method='GET') if task_id else ActionResult(False, 'Chronicle detail', '', error='No task_id on selected record')
        elif page == 'Diagnostics':
            result = await api.quality_cascade('Run BEAST diagnostic quality cascade', provider=str(self.session_meta.get('provider') or 'litellm'))
        else:
            result = await api.compile_insight(f'{mode} {self.selected_label()}', provider=str(self.session_meta.get('provider') or 'litellm'))
        self.tool_events.append(f'{mode} {page}: ' + ('ok' if result.ok else 'error'))
        self.chat_lines.append({'role': 'tool', 'content': result.brief(1200)})
        self.notify(result.summary or result.error or result.title, title=result.title, severity='information' if result.ok else 'warning')
        self._set_mascot_state('finished' if result.ok else 'alert', hold_ticks=12 if result.ok else 18)
        await self.fetch_backend()

    def action_toggle_streaming(self):
        self.streaming_enabled = not bool(self.streaming_enabled)
        mode = 'ON' if self.streaming_enabled else 'OFF'
        self.tool_events.append(f'streaming mode: {mode}')
        self.notify(f'Streaming mode {mode}.', title='BEAST stream')
        self._sync()

    def action_cancel_turn(self):
        if str(self.session_meta.get('state')) in {'thinking', 'streaming'}:
            self.current_turn_cancelled = True
            self.session_meta['state'] = 'cancel requested'
            self.tool_events.append('cancel requested by operator')
            self.chat_lines.append({'role': 'system', 'content': 'Cancel requested. BEAST will stop at the next safe streaming checkpoint.'})
            self.notify('Cancel requested.', title='BEAST stream', severity='warning')
            self._set_mascot_state('alert', hold_ticks=10)
            self._sync()
        else:
            self.notify('No active live turn to cancel.', title='BEAST stream')

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != 'chat-input':
            return
        event.stop()
        text = event.value.strip()
        event.input.value = ''
        self.input_mode = False
        if not text:
            self._sync()
            return
        if self.selected_page != 'Session':
            self.set_page('Session')
        if text.lower() == '/clear':
            self.chat_lines.clear(); self.tool_events.clear(); self._sync(); return
        if text.lower() in {'/stream', '/streaming'}:
            self.streaming_enabled = True; self.tool_events.append('streaming mode: ON'); self._sync(); return
        if text.lower() in {'/nostream', '/no-stream', '/batch'}:
            self.streaming_enabled = False; self.tool_events.append('streaming mode: OFF'); self._sync(); return
        if text.lower() in {'/cancel', '/stop'}:
            self.action_cancel_turn(); return
        if text.lower().startswith('/provider '):
            provider = provider_key(text.split(maxsplit=1)[1].strip())
            if provider:
                self.session_meta['provider'] = provider
                route = provider_route_summary(self.snapshot or BackendSnapshot(base_url=self.base_url), provider)
                self.tool_events.append(f'provider selected: {route["provider_id"]} → {route["route_provider"]} → {route["resolved_model"]}')
                self.chat_lines.append({'role': 'system', 'content': f'Provider switched to {route["provider_id"]}. beast-auto resolves to {route["resolved_model"]} via {route["route_provider"]}.'})
                self._sync(); return
        if text.lower() == '/context':
            self.action_context_picker(); return
        if text.lower().startswith('/metaplan'):
            self.build_metadata_patch_plan(); return
        if text.lower().startswith(('/plan', '/sourceplan', '/patch')):
            self.action_build_patch_plan(); return
        if text.lower() in {'/diff', '/preview', '/hunks'}:
            self.action_preview_diff(); return
        if text.lower() in {'/verify', '/check'}:
            self.action_verify_patch_plan(); return
        if text.lower() in {'/apply', '/write'}:
            self.action_apply_patch_plan(); return
        if text.lower() in {'/rollback', '/undo'}:
            self.action_rollback_patch(); return
        if not self.session_meta.get('lifecycle_id'):
            await self._start_live_session()
        self.chat_lines.append({'role': 'user', 'content': text})
        self.session_meta['state'] = 'streaming' if self.streaming_enabled else 'thinking'
        self._set_mascot_state('working')
        self.current_turn_cancelled = False
        self.tool_events.append('live turn queued' + (' with streaming' if self.streaming_enabled else ''))
        self.notify('BEAST live turn queued. Streaming is ON.' if self.streaming_enabled else 'BEAST live turn queued. Streaming is OFF.', title='BEAST')
        self._sync()
        self.run_worker(self._process_live_turn(text), exclusive=False)

    async def _process_live_turn(self, text: str) -> None:
        self.session_meta['state'] = 'streaming' if self.streaming_enabled else 'thinking'
        self._set_mascot_state('working')
        self._sync()
        turn_ok = True
        try:
            history = [{'role': line['role'], 'content': line['content']} for line in self.chat_lines if line.get('role') in {'user','assistant'}]

            if not self.streaming_enabled:
                result: LiveTurnResult = await BeastApiClient(self.base_url).live_turn(
                    text,
                    history=history,
                    provider=str(self.session_meta.get('provider') or 'litellm'),
                    lifecycle_id=str(self.session_meta.get('lifecycle_id') or ''),
                    context_files=list(self.context_files),
                )
                if result.assistant_text:
                    self.chat_lines.append({'role': 'assistant', 'content': result.assistant_text})
                if result.tool_events:
                    self.tool_events.extend(result.tool_events)
                if not result.ok and result.error:
                    self.chat_lines.append({'role': 'system', 'content': result.error})
                    turn_ok = False
                return

            assistant_index = len(self.chat_lines)
            self.chat_lines.append({'role': 'assistant', 'content': '▌'})
            accumulated = ''
            token_count = 0
            async for event in BeastApiClient(self.base_url).stream_live_turn(
                text,
                history=history,
                provider=str(self.session_meta.get('provider') or 'litellm'),
                lifecycle_id=str(self.session_meta.get('lifecycle_id') or ''),
                context_files=list(self.context_files),
            ):
                if self.current_turn_cancelled:
                    self.tool_events.append('stream cancelled at safe checkpoint')
                    break

                event_type = str(event.get('type') or '')
                if event_type == 'token':
                    chunk = str(event.get('text') or '')
                    accumulated += chunk
                    token_count += 1
                    self.chat_lines[assistant_index]['content'] = accumulated + '▌'
                    if token_count % 3 == 0:
                        self._sync()
                elif event_type in {'tool', 'stage'}:
                    self.tool_events.append(str(event.get('text') or event_type))
                    self._sync()
                elif event_type == 'error':
                    self.tool_events.append('stream error')
                    self.chat_lines.append({'role': 'system', 'content': str(event.get('error') or 'stream error')})
                    turn_ok = False
                    self._sync()
                elif event_type == 'provider_done':
                    self.tool_events.append(f"provider stream done: {event.get('tokens', 0)} chunk(s)")
                elif event_type == 'done':
                    for item in event.get('tool_events') or []:
                        if str(item) not in self.tool_events[-12:]:
                            self.tool_events.append(str(item))
                    if event.get('lifecycle_id'):
                        self.session_meta['lifecycle_id'] = str(event.get('lifecycle_id'))
                    self._sync()

            if self.current_turn_cancelled:
                self.chat_lines[assistant_index]['content'] = (accumulated or '') + '\n\n[stream cancelled]'
                turn_ok = False
            else:
                self.chat_lines[assistant_index]['content'] = accumulated or '[no streamed response]'
            self.tool_events.append(f'stream chunks: {token_count}')
        except Exception as exc:
            turn_ok = False
            self.tool_events.append('live stream error')
            self.chat_lines.append({'role': 'system', 'content': f'Live stream failed safely: {exc}'})
            self.notify(str(exc), title='BEAST live stream', severity='warning')
        finally:
            self.current_turn_cancelled = False
            self.session_meta['state'] = 'active'
            self._set_mascot_state('finished' if turn_ok else 'alert', hold_ticks=16 if turn_ok else 20)
            await self.fetch_backend()


def run() -> None:
    BeastMissionConsole().run()


if __name__ == '__main__':
    run()
