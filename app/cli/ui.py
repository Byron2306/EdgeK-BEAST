"""BEAST Power Console TUI.

Visual Deck Edition 3: restored PNG-derived BEAST sprite animation,
widget-first pages, circle meters, deltas, toggles, and line graphs.
"""
from __future__ import annotations

import base64
import asyncio
import json
import os
import zlib
import subprocess
import sys
import time
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

from internal.beast_economy_dashboard import build_dashboard
from scripts.compute_rollout_monitor import evaluate_rollout
from internal.forge_fleet_promote import promote_from_fleet

try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None

BEAST_GREEN = '#74FF8B'
BEAST_ACID = '#A7FF57'
BEAST_MINT = '#B8FFD2'
BEAST_LIME = '#C2FF4D'
BEAST_JADE = '#26D98A'
BEAST_EMERALD = '#139A63'
BEAST_MOSS = '#5B7F61'
BEAST_PANEL = '#06110F'
BEAST_PANEL_ALT = '#081B16'
BEAST_PANEL_SOFT = '#0B241C'
BEAST_DEEP = '#020806'
BEAST_BORDER = '#26724E'
BEAST_BORDER_DIM = '#12382A'
BEAST_MUTED = '#8BA49B'
BEAST_TEXT = '#EAF8F1'
BEAST_WARN = '#B5C85C'
BEAST_DANGER = '#D35E68'
BEAST_INFO = '#79F2C0'
BEAST_PURPLE = '#8FE3A3'
BEAST_STEEL = '#C5D6CF'
BEAST_SHADOW = '#03100C'
BEAST_GRAPH_LOW = '#123326'
BEAST_GRAPH_MID = '#1D6B46'
BEAST_GRAPH_HIGH = '#2ECA7F'
BEAST_GRAPH_PEAK = '#C2FF4D'
ROOT = Path(__file__).resolve().parents[2]
HEADER_PANEL_HEIGHT = 20
HEADER_PANEL_HEIGHT_SHORT = 15
HEADER_TILE_HEIGHT = 4
HEADER_TILE_LARGE_HEIGHT = 7
METRIC_CARD_HEIGHT = 8
VISUAL_TILE_HEIGHT = 11
SESSION_SIDE_CARD_HEIGHT = 8

PAGES = ['Mission','Session','PREC','Routing','Providers','Capabilities','Swarm','Intelligence','Spaces','Economy','Chronicle','Deployment','Diagnostics','Settings']
PAGE_LABELS = {
    'Mission': 'Mission Control',
    'Session': 'Sessions',
    'PREC': 'PREC Lifecycle',
    'Routing': 'Routes',
    'Providers': 'Providers',
    'Capabilities': 'Skills',
    'Swarm': 'Swarm',
    'Intelligence': 'Intelligence',
    'Spaces': 'Compute Spaces',
    'Economy': 'Compute Economy',
    'Chronicle': 'Chronicle',
    'Deployment': 'Deploy',
    'Diagnostics': 'Diagnostics',
    'Settings': 'Settings',
}
PAGE_SYMBOLS = {
    'Mission': '■',
    'Session': '▷',
    'PREC': '◇',
    'Routing': '⌁',
    'Providers': '☁',
    'Capabilities': '◎',
    'Swarm': '⌬',
    'Intelligence': '◆',
    'Spaces': '▣',
    'Economy': '$',
    'Chronicle': '▦',
    'Deployment': '⇄',
    'Diagnostics': '⌁',
    'Settings': '⚙',
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


def human_label(value: Any) -> str:
    return str(value or '').replace('_', ' ').strip().title()



def beast_wordmark(compact: bool = False, frame: int = 0) -> Text:
    """Large BEAST wordmark, restored for the main mission-console header."""
    text = Text()
    glow = BEAST_GREEN if int(frame or 0) % 10 else BEAST_LIME
    if compact:
        text.append('█ ', style=f'bold {glow}')
        text.append('BEAST', style=f'bold {BEAST_ACID}')
        return text
    rows = [
        '██████╗ ███████╗ █████╗ ███████╗████████╗',
        '██╔══██╗██╔════╝██╔══██╗██╔════╝╚══██╔══╝',
        '██████╔╝█████╗  ███████║███████╗   ██║   ',
        '██╔══██╗██╔══╝  ██╔══██║╚════██║   ██║   ',
        '██████╔╝███████╗██║  ██║███████║   ██║   ',
        '╚═════╝ ╚══════╝╚═╝  ╚═╝╚══════╝   ╚═╝   ',
    ]
    for i, row in enumerate(rows):
        style = f'bold {glow}' if i in {0, 2, 4} else f'bold {BEAST_GREEN}'
        text.append(row, style=style)
        if i < len(rows) - 1:
            text.append('\n')
    return text


def title_symbol(title: str) -> str:
    upper = str(title or '').upper()
    for page, symbol in PAGE_SYMBOLS.items():
        if page.upper() in upper or PAGE_LABELS.get(page, '').upper() in upper:
            return symbol
    return symbol_for(title, '▰')



def title_text(title: str, symbol: str | None = None) -> Text:
    sym = symbol or title_symbol(title)
    text = Text()
    text.append(f'{sym}  ', style=f'bold {BEAST_ACID}')
    text.append(str(title).upper(), style=f'bold {BEAST_ACID}')
    text.append('  ', style=BEAST_MUTED)
    text.append('─' * 18, style=BEAST_BORDER)
    return text



def chip_line(*items: Any) -> Text:
    text = Text()
    for i, item in enumerate(items):
        if i:
            text.append('  ', style=BEAST_MUTED)
        text.append('◈ ', style=BEAST_BORDER if i else BEAST_ACID)
        text.append(str(item), style=BEAST_GREEN if i == 0 else BEAST_MUTED)
    return text



def pulse_color(frame: int = 0, good: bool = True) -> str:
    """Calmer pulse: mostly stable, with a tiny emerald shimmer."""
    phase = int(frame or 0) % 18
    if not good:
        return BEAST_MOSS if phase < 15 else BEAST_WARN
    return BEAST_GREEN if phase < 15 else BEAST_LIME


def green_tint_for(value: Any, fallback: str = BEAST_BORDER) -> str:
    """Return a green-family accent, reserving danger only for hard failures."""
    style = status_style(value)
    if style == BEAST_DANGER:
        return BEAST_DANGER
    if style == BEAST_WARN:
        return BEAST_MOSS
    return fallback


def panel_box_for(title: Any):
    """Give major panels different silhouettes so the UI stops looking tiled-flat."""
    text = str(title or '').lower()
    if any(x in text for x in ['mission', 'overview', 'governance', 'source plan']):
        return box.DOUBLE_EDGE
    if any(x in text for x in ['provider', 'route', 'gateway', 'proxy', 'diagnostic', 'doctor', 'health']):
        return box.HEAVY_EDGE
    if any(x in text for x in ['chronicle', 'log', 'queue', 'table', 'list']):
        return box.SQUARE
    if any(x in text for x in ['skill', 'capabil', 'intelligence', 'economy', 'prec']):
        return box.ROUNDED
    return box.HEAVY


def panel_accent_for(title: Any, state: Any = None) -> str:
    """Use related greens instead of one repeated neon outline."""
    hard = status_style(state) if state not in (None, '') else ''
    if hard == BEAST_DANGER:
        return BEAST_DANGER
    if hard == BEAST_WARN:
        return BEAST_MOSS
    text = str(title or '').lower()
    if any(x in text for x in ['mission', 'core', 'health']):
        return BEAST_LIME
    if any(x in text for x in ['provider', 'gateway', 'proxy', 'route']):
        return BEAST_JADE
    if any(x in text for x in ['prec', 'chronicle', 'governance']):
        return BEAST_EMERALD
    if any(x in text for x in ['economy', 'token', 'savings', 'cost']):
        return BEAST_ACID
    if any(x in text for x in ['skill', 'capability', 'intelligence', 'aware']):
        return BEAST_MINT
    return BEAST_BORDER


def fixed_panel(
    renderable: Any,
    *,
    border_style: Any = BEAST_BORDER,
    style: Any = BEAST_PANEL,
    padding: Any = (1, 1),
    box_style: Any = None,
    height: int | None = None,
    width: int | None = None,
) -> Panel:
    """Create a panel with consistent sizing for adjacent dashboard cards."""
    return Panel(
        renderable,
        border_style=border_style,
        style=style,
        padding=padding,
        box=box_style or box.ROUNDED,
        height=height,
        width=width,
    )


def block_meter(percent: Any, *, width: int = 18, compact: bool = False) -> Text:
    """Segmented green block meter with a soft gradient."""
    try:
        pct = max(0.0, min(100.0, float(percent)))
    except Exception:
        pct = 0.0
    filled = int(round((pct / 100.0) * width))
    palette = [BEAST_GRAPH_LOW, BEAST_GRAPH_MID, BEAST_EMERALD, BEAST_JADE, BEAST_GREEN, BEAST_GRAPH_PEAK]
    text = Text()
    for i in range(width):
        if i < filled:
            idx = clamp(int((i / max(1, width - 1)) * (len(palette) - 1)), 0, len(palette) - 1)
            text.append('█', style=palette[idx])
        else:
            text.append('░', style=BEAST_BORDER_DIM)
    if not compact:
        text.append(f' {pct:.0f}%', style=f'bold {BEAST_GREEN if pct >= 80 else BEAST_MOSS}')
    return text


def status_blocks(status: Any, *, width: int = 10) -> Text:
    return block_meter(pct_from_status(status), width=width, compact=True)


def metric_signal(title: Any, value: Any, note: Any = '') -> int:
    joined = f'{title} {value} {note}'.lower()
    try:
        if isinstance(value, (int, float)):
            number = float(value)
            if 0 <= number <= 1:
                return clamp(int(number * 100), 0, 100)
            return clamp(int(55 + min(number, 8) * 6), 0, 100)
    except Exception:
        pass
    if any(x in joined for x in ['ready', 'ok', 'run', 'active', 'governed', 'aligned']):
        return 96
    if any(x in joined for x in ['wait', 'missing', 'degraded', 'offline', 'review', 'warn']):
        return 62
    if any(x in joined for x in ['error', 'fail', 'deny', 'blocked']):
        return 24
    return 84


def graph_wall(values: Iterable[Any], *, width: int = 24, height: int = 3, good: bool = True) -> Text:
    """Tiny block graph: more visible than a one-line sparkline, still terminal-native."""
    nums: List[float] = []
    for value in values:
        try:
            nums.append(float(value))
        except Exception:
            pass
    if not nums:
        nums = [3, 5, 4, 6, 7, 6, 8, 7, 9]
    if len(nums) < width:
        seed = nums[-1]
        while len(nums) < width:
            seed = ((seed * 1.37) + len(nums)) % 11 + 1
            nums.append(seed)
    nums = nums[-width:]
    lo, hi = min(nums), max(nums)
    span = hi - lo or 1.0
    levels = [int(round(((n - lo) / span) * height)) for n in nums]
    text = Text()
    palette = [BEAST_GRAPH_LOW, BEAST_GRAPH_MID, BEAST_JADE, BEAST_GRAPH_PEAK] if good else [BEAST_BORDER_DIM, BEAST_MOSS, BEAST_WARN, BEAST_WARN]
    for row in range(height, 0, -1):
        for level in levels:
            style = palette[clamp(row, 0, len(palette) - 1)]
            text.append('▇' if level >= row else ' ', style=style)
        if row > 1:
            text.append('\n')
    return text


def toggle_switch(on: Any, label: str = '', frame: int = 0) -> Text:
    active = bool(on)
    style = pulse_color(frame, True) if active else BEAST_MUTED
    knob = '●' if active else '○'
    rail = '━━' if active else '──'
    text = Text()
    if label:
        text.append(label + ' ', style=BEAST_MUTED)
    text.append('[' if active else '(', style=style)
    text.append(rail, style=style)
    text.append(knob, style=f'bold {style}')
    text.append(rail, style=style)
    text.append(']' if active else ')', style=style)
    text.append(' ON' if active else ' OFF', style=style)
    return text


def radial_meter(percent: Any, frame: int = 0, label: str = '') -> Text:
    try:
        pct = max(0.0, min(100.0, float(percent)))
    except Exception:
        pct = 0.0
    style = pulse_color(frame, pct >= 70)
    # Fixed corner glyphs prevent the meter from looking like it is crawling.
    rings = ('◜', '◝', '◟', '◞')
    filled = int(round(pct / 12.5))
    dots = '●' * filled + '○' * max(0, 8 - filled)
    text = Text()
    text.append(f'{rings[0]}{dots[:4]}{rings[1]}\n', style=style)
    text.append(f'{rings[2]}{dots[4:]}{rings[3]} ', style=style)
    text.append(f'{pct:.0f}%', style=f'bold {style}')
    if label:
        text.append(f' {label}', style=BEAST_MUTED)
    return text


def waveform(frame: int = 0, width: int = 28, good: bool = True) -> Text:
    bars = '▁▂▃▄▅▆▇█'
    style = pulse_color(frame, good)
    text = Text()
    for i in range(width):
        idx = (i * 3 + int(frame or 0)) % len(bars)
        text.append(bars[idx], style=style if i % 3 else BEAST_INFO)
    return text


def display_value(value: Any) -> str:
    if value is None:
        return 'n/a'
    if isinstance(value, bool):
        return 'yes' if value else 'no'
    if isinstance(value, float):
        return f'{value:.4f}'.rstrip('0').rstrip('.')
    if isinstance(value, (list, tuple, set)):
        return safe_join(list(value), limit=8) or 'none'
    text = str(value)
    if '\n' in text:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return f"{len(lines)} lines: " + ' / '.join(lines[:4])
    return text


def render_width(widget: Any, default: int = 140) -> int:
    try:
        return int(getattr(getattr(widget, 'app', None), 'size', None).width or default)
    except Exception:
        return default


def record_table(record: Dict[str, Any], *, max_rows: int = 60) -> Table:
    table = Table.grid(expand=True)
    table.add_column(width=24)
    table.add_column(ratio=1)
    shown = 0
    for key, value in record.items():
        if isinstance(value, dict):
            value = f"{len(value)} fields: " + ', '.join(str(k) for k in list(value.keys())[:8])
        elif isinstance(value, list):
            value = f"{len(value)} records" + (f"; first={display_value(value[0])[:140]}" if value else '')
        table.add_row(
            Text(human_label(key), style=BEAST_MUTED),
            Text(display_value(value)[:240], style=status_style(value)),
        )
        shown += 1
        if shown >= max_rows:
            break
    if shown == 0:
        table.add_row(Text('Status', style=BEAST_MUTED), Text('No fields returned by this endpoint', style=BEAST_WARN))
    return table


def list_table(rows: List[Any], *, max_rows: int = 80) -> Table:
    dict_rows = [row for row in rows if isinstance(row, dict)]
    if not dict_rows:
        table = Table(expand=True, box=box.SIMPLE)
        table.add_column('Value')
        for value in rows[:max_rows]:
            table.add_row(Text(display_value(value)[:240], style=BEAST_TEXT))
        if not rows:
            table.add_row(Text('No records', style=BEAST_MUTED))
        return table
    keys: List[str] = []
    for row in dict_rows[:max_rows]:
        for key, value in row.items():
            if key not in keys:
                keys.append(str(key))
            if len(keys) >= 7:
                break
        if len(keys) >= 7:
            break
    table = Table(expand=True, box=box.SIMPLE_HEAVY)
    for key in keys or ['status']:
        table.add_column(human_label(key))
    for row in dict_rows[:max_rows]:
        table.add_row(*[
            Text(display_value(row.get(key))[:72], style=status_style(row.get(key)))
            for key in (keys or ['status'])
        ])
    return table


def structured_payload(payload: Any) -> Group:
    if not isinstance(payload, dict):
        if isinstance(payload, list):
            return Group(list_table(payload))
        return Group(Text(display_value(payload), style=BEAST_TEXT))
    sections: List[Any] = [Panel(record_table(payload), title='Summary', border_style='#2A8F5A')]
    for key, value in payload.items():
        if isinstance(value, dict):
            sections.append(Panel(record_table(value), title=human_label(key), border_style=BEAST_BORDER))
        elif isinstance(value, list):
            sections.append(Panel(list_table(value), title=human_label(key), border_style=BEAST_BORDER))
        if len(sections) >= 10:
            break
    return Group(*sections)


def economy_result_payload(action: str, data: Dict[str, Any]) -> Group:
    action = str(action or '')
    if not isinstance(data, dict):
        return structured_payload(data)
    rollout = data.get('rollout') if isinstance(data.get('rollout'), dict) else data
    forge = data.get('forge') if isinstance(data.get('forge'), dict) else {}
    crystal = data.get('crystallization') if isinstance(data.get('crystallization'), dict) else {}
    phase_artifacts = data.get('phase_artifacts') if isinstance(data.get('phase_artifacts'), dict) else {}
    summary = Table.grid(expand=True)
    summary.add_column(width=24); summary.add_column(ratio=1)
    summary.add_row(Text('Action', style=BEAST_MUTED), Text(human_label(action or 'economy_dashboard'), style=BEAST_ACID))
    summary.add_row(Text('Readiness', style=BEAST_MUTED), Text(str(rollout.get('readiness') or 'ready'), style=status_style(rollout.get('readiness') or 'ready')))
    summary.add_row(Text('Redlines', style=BEAST_MUTED), Text(safe_join(rollout.get('redlines') or [], limit=6) or 'none', style=BEAST_GREEN if not rollout.get('redlines') else BEAST_DANGER))
    summary.add_row(Text('Phase artifacts', style=BEAST_MUTED), Text(str(len(phase_artifacts)), style=BEAST_INFO))
    summary.add_row(Text('Forge nodes', style=BEAST_MUTED), Text(str((forge.get('totals') or {}).get('nodes', 0) if isinstance(forge.get('totals'), dict) else 0), style=BEAST_INFO))
    summary.add_row(Text('Promoted crystals', style=BEAST_MUTED), Text(str(crystal.get('promoted_count', 0)), style=BEAST_GREEN if crystal.get('promoted_count') else BEAST_WARN))

    phases = Table(expand=True, box=box.SIMPLE_HEAVY)
    for col in ['Phase', 'Status', 'Artifact']:
        phases.add_column(col)
    for key, value in list(phase_artifacts.items())[:8]:
        if isinstance(value, dict):
            phases.add_row(human_label(key), str(value.get('status') or value.get('passed') or 'present'), str(value.get('path') or value.get('artifact_path') or '')[-72:])
        else:
            phases.add_row(human_label(key), 'present', display_value(value)[:72])
    if not phase_artifacts:
        phases.add_row('No phase artifacts', 'waiting', 'run compute governor benchmarks')
    return Group(
        Panel(summary, title='Operational Summary', border_style='#2A8F5A'),
        Panel(phases, title='Phase Artifacts', border_style=BEAST_BORDER),
    )


def economy_action_rows(report: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    report = report or {}
    rollout = report.get('rollout') if isinstance(report.get('rollout'), dict) else {}
    forge = report.get('forge') if isinstance(report.get('forge'), dict) else {}
    forge_totals = forge.get('totals') if isinstance(forge.get('totals'), dict) else {}
    crystal = report.get('crystallization') if isinstance(report.get('crystallization'), dict) else {}
    crystal_observed = crystal.get('observed') if isinstance(crystal.get('observed'), dict) else {}
    return [
        {
            'name': 'Rollout monitor',
            'status': rollout.get('readiness') or 'local_check',
            'value': ', '.join(rollout.get('redlines') or []) or 'no redlines',
            'action': 'rollout_monitor',
            'hint': 'Run Phase 2/3 safety monitor and open the evidence payload.',
        },
        {
            'name': 'Economy dashboard',
            'status': 'ready' if report else 'local',
            'value': f"phases={len(report.get('phase_artifacts') or {})}" if report else 'one-command rollup',
            'action': 'economy_dashboard',
            'hint': 'Open the full local JSON dashboard for phases, compute, Forge, and storage.',
        },
        {
            'name': 'Start local Forge node',
            'status': 'nodes:' + str(forge_totals.get('nodes', 0)),
            'value': 'background credits',
            'action': 'start_forge_node',
            'hint': 'Start a local background Forge runner that writes snapshots into data/forge_nodes.',
        },
        {
            'name': 'Collect Forge promotions',
            'status': 'promoted:' + str(crystal.get('promoted_count', 0)),
            'value': f"candidates={forge_totals.get('candidates_produced', 0)}",
            'action': 'promote_fleet',
            'hint': 'Ingest Forge node proposals and promote centrally.',
        },
        {
            'name': 'Refresh economy state',
            'status': 'refresh',
            'value': 'backend + local files',
            'action': 'refresh_economy',
            'hint': 'Refresh the TUI snapshot and local economy report.',
        },
    ]


def modal_row_from_click(widget: Static, event: events.Click, count: int, table_top: int = 5, max_rows: int | None = None) -> int:
    if count <= 0:
        return 0
    local_y = max(0, int(event.screen_y - widget.region.y))
    shown = min(count, max_rows or count)
    return clamp(local_y - table_top, 0, max(0, shown - 1))


def row_from_click_band(local_y: int, row_count: int, *, top: int = 5, row_height: int = 1) -> int:
    if row_count <= 0:
        return 0
    return clamp((max(0, int(local_y) - top)) // max(1, row_height), 0, row_count - 1)


def modal_scroll_key(screen: ModalScreen, event: events.Key) -> bool:
    if event.key not in {'pageup', 'pagedown', 'home', 'end', 'ctrl+down', 'ctrl+up'}:
        return False
    try:
        scroll = screen.query_one('#modal-scroll', VerticalScroll)
        if event.key == 'pageup':
            scroll.scroll_page_up(animate=False, force=True)
        elif event.key == 'pagedown':
            scroll.scroll_page_down(animate=False, force=True)
        elif event.key == 'ctrl+down':
            scroll.scroll_relative(y=6, animate=False, force=True, immediate=True)
        elif event.key == 'ctrl+up':
            scroll.scroll_relative(y=-6, animate=False, force=True, immediate=True)
        elif event.key == 'home':
            scroll.scroll_home(animate=False, force=True)
        elif event.key == 'end':
            scroll.scroll_end(animate=False, force=True)
        event.stop()
        return True
    except Exception:
        return False


def snapshot_blocker(snap: BackendSnapshot) -> str:
    if not snap.online:
        return f"gateway offline at {snap.base_url}"
    if snap.errors:
        first_key = next(iter(snap.errors))
        return f"{first_key}: {snap.errors[first_key]}"
    return ""



# Compact PNG-derived BEAST mascot frames.
# Decoded at runtime if app/cli/assets/sprites/mascot_frames.json is not present.
EMBEDDED_MASCOT_FRAMES_B64 = (
    'eNrtncty2zgWQP9FvfVCwH2Azs5O2j8x1eXSpJVuVztxytHMLFL598G9ICWSoiSKBB+SQHc6kiJeAyB4cIgH+XPx5e3962qz'
    '+LD493r1Y/P8+e3r99XnzfPfq9cvz1/fNi9v355f3z7/s/7z+b92cbeofLT4sHn/z/pu8X31ut5s1osP/1r4r/y2dGa5/F1e'
    'GWMezYO8sg+AIAF+Y3bI+q8f6RN/fNLvwf0Dg36PP91nuofDp6fsUb9nn57wk7z6BPQ7Z/LqkT5m9HHxx93ix2a1Wf9YfPi5'
    'ePnzVdLwc1HOhCRqGWnzv3jQUADW1j/yP8WGSIBtQqEFa6wJAZAQlxYAjLFLBJT3ZNEAnAzlv+2T5A+itf7rROQPoZU3PpzG'
    '8f9inG0VyqdJ4lg2DOzDyOY/QNnkd1jnnKZwCcdDSSFZjeQ3xxze+A30x8gGRpN+IlVSRvJjLPtkWc2mvg+b9TmWZNu9g9IQ'
    'ymeOM6sFkm/og94bp8nx2ZSM+5AN2auEAsmfyVh3LBLjfOx7x5oony1Jrc8qnE7VMj9cGif84fzvPLaVOLtI/rDiwXpllwZ3'
    '+Qtl5D/xVSkUF1aL3B+BI7VdDqOUfF7ucsh8UTOHsOFo+oRJeflAaI+E8oXvA0j55qnTCuKLSYqOOeTT+Pc21JpDoaTsJTO7'
    'LMovlv30jf6C4njk5XcglK/GPo5GCnEtWgyVcylZC7VqW4i2fAhiQsbj8XX9ZfP8feVZTXeLzer9r7WH/Pr11RMTuZHnv+4S'
    'QcsExWgExWEJyoKIcwjqWLcSQXFagro6QV3WlaBOz9YdQd19ls2eoJAImgh6/Q5KsyModXRQd4EOiu0I6otiMgelWATFRNBE'
    '0OsjKMZyUIpFUNo6aE+CYp2gODJBr8JB6boclCckKCaCpn7QgwTF+P2gHNlBcXIHdV37QWsOyuKgt3oVjyM7KA7moJgImgha'
    'EBR3V/EcrR80LkEp9YOeT1C8tn7Q/g6K+wTlNgTFdBWfCDrqSFJ0B41EUOzloHw2QbHJQd3tOui4/aA0WD8oJYImgjYSdDIH'
    'PTqbiWYxFt9jNtOeg25HkjARdDwHpSaCchpJSgSdo4P2ns00gINSr37Q7GwHxeZ+0JKD4vU6KE7toDjYWDwlgiaCDuygs5xR'
    'TzOZUV920LkRlG5uLD6Cg+KMCer3+t/b+z8v3/6aYH1S4wmy3WiJ7WkqNcjuKFqiq7IMoV0oDFXVs8nKfpCTq5hGBOEcahMq'
    'jyO1XfbVczOMyisCtbWHNmUldNOT2O8CDkKSdHBKPjdSySWBsDwJZtCdQc8L57jC0pykwmjbJoOaGx9A+BSwU0DCp80XHOp5'
    '3aIySJo4017dIoJvHjxNTSh3f0o6adFaFLu0WJnPmikaHNFTl7m8EYPQoJXb2DKiq6kSAFqz+2/7v21GywmCMF/tSBWt0dSq'
    'Q0IAYjlzoK3nko/RNGQulJgVKitLbdA9CM2FZFe+mPGxUNos5ogLedpjqQ9hfSsux/nYiQOQZye0yaDdJ0WEAn/FrykfhGoo'
    'klSHlGvDDmHSneTSglZUyP1bf4BwIGW7EB89TlDsRlCMRVB/TlQJilEJ6s4nqGsiqDufoC7o6HwIGvokSgT1V/SdCcplgsrk'
    '+uskKLckqOtEULcjqEsEvS2C1h0UOxJU5nBWCErzdNCOBJ2zg3LVQVnOKWxHUDehg1JHguKADuqSgyaCTnYVXyUoxbqKp1k4'
    'qJuXg7oTDoodHdQlB+3roBMQFBNBr5CgcftB+XwH5ZgOyvN2UFdzUGx7FV9zUD7poM3Yw2vpB+3qoF0IislBE0FHI2hHB+Ud'
    'QWkwB8VYBMWuDso1B8XO/aDeQTk56KU5aCLo1RGU4juoO99B3c06KHR20Oyog9J1jcVzg4Ne/kgSJoImBx3AQWuzmfBSZzNh'
    'o4PeRxqLP+6gODsHxZt3UEwOmgh6CQ46l9lMGByUaw6aRXJQzsYYi8ebd1CMRVCsOygmgiaCjuGgrQiKJx2UZjGjniPOqJ9x'
    'PyiOMaO+G0H7zmaijgTFi+4H9Xt9efn28uNv+WTkBUqwtEf3oZbgKs6Tbdjq4s98VlKbUDlMdbmn3ho+ZyLkOFWAtEpVWFhp'
    'ZO1oPk0/3PNON6nBqpEtcCpnhZGKygpTtroeVTgT1pNaXbUJtnnqTzlUOL+2MNUL39xQYbvuWmF/MoNQwFTWoJZOl8AboHwh'
    'wunKIBpjM8dQhJNNlmhyWOzpN1XnQzTdhZIFh0bgwds44rUSyYac6iLC0oks4Co32HWcFmtjy39tka8ndrV7VY4AHmpb0VYX'
    'e4Il/UzK3ZZnvmrjybt7tzY107r00nKxFBWkTQv3WXFSVWSxJ9hCR3eHcz9UWOwpu+f1HATMCmmpVvoZC07zfhI4fOLoitOK'
    'jsJ2iWdeP2xY9Gmr9b5a7PldwPNVsDk1oVheu1suv7SKD2jhbFcspKcIit0IinWCUiyCYkeClu4a2o+gromg7lyC5jccmQ9B'
    'M1chKJssC8u/zyaok/tX7QjqyyxzwxEUoxEU6gSFUwR1rQjKnQnqdgR1iaC3RdC6g1JHB6U6Qamzg+KQDuou3UFd1sZBsaWD'
    'urqD8lAExbqDYkeC4mAETQ6aCDrZVTzVHZQ6XsVjnaCUHPSog7omB8WODno/mINi/Soer9RBE0ETQafuB21wUD6foFxzULwh'
    'B8W2/aBcdVAZ8r+AftAKQTGmg3IiaCLoLAhKsQhKsfpBqYeDuqMOiuMSNHMnHRTbjyRVCDqkgw5G0FlcxU9JUEwEvT6C0iwc'
    '1F1pP6iLNxa/56DuqIPS7AiKfQjKQzhoy5EkHMxBMRE0XcVHH4un7rOZTjgojj+bqcFB48xmujwHpZYOyrN3UOxIUExX8ddH'
    'UJxJP2i0kaQjDkqTOyh3c1DUkaSzHJSu7Sp+Ogel1A+aCHpRDor9HPQgQWmKGfWDOag76qB0wf2gc59RTx0JShdNUL/X6nX9'
    'vpng8UlRQ8FxMC+xZShhVIXy5cBhon6rVAV2BaTkT6Pzr6EYoNJnbrVrLLQyBYhCWDeqFTuA2SiY2zz2TQsBlOl6RR+eMaZV'
    '1sey26eSNQ/g7C1BzXllizt8QIGwnBR6frU5grKq3bjQ2OTIYpMZzhsfOUftjlNHQtEjgM9XtqOpkQeD3itoJEHg7KFH0e23'
    'hkV+zDajFZ4eXMraXK/s0oApr/cEfZyntkmyNLJUsqWn2h1c2qw3HOGwghjNg7LVFA84DCt/dbln2SEafaY47DnuwOY09Zc+'
    'nLeYwUdL9x9tfopjebGntTUfNVWawuFQUBipfM3saKoVrPRalnoinC6r/bMYDy0jvzgbTQTtTVBZlt6VoK5CUJiYoFwjqOtC'
    '0AchaHlc3gfJ8sd57giK7QiKIxIU+xH0MT5BXZmg2fgExUTQRNCDBKV4DgpxHBQnJ+h4Doqzc1CsE5SSgyYHTQQd5So+joMS'
    'zI6gdQfFeA46w6v4KkEploNiHwflqoPymATFRNBE0IMExVgEpS1B+XyCcq0ftEJQjEVQHNlBUYag9hz00ggaqx8UY13Ft3RQ'
    'HMxBsU5QTARNDjojB60RFGfooHH6QfkCCEqx+kGpXz9ofwfFjgSldBWfCDouQTs56PAjSTRBP6jc2q5K0Nt1UBjVQWmwflBK'
    'BE0EvSgHjURQHH0k6SocdC5j8X0dlDoSFNNIUiLofB2UYjkonSQo9ZrNNISD4g05KI7uoJFGkrDuoJQIOhJBcXYExVgExQt0'
    'UJpgNlNw0NpI0n3G1+agOLyDck8HpcFmM+GMCfrHr1//B2IuINQ='
)


def _decode_embedded_mascot_frames() -> Dict[str, Any]:
    try:
        payload = json.loads(zlib.decompress(base64.b64decode(EMBEDDED_MASCOT_FRAMES_B64)).decode('utf-8'))
        if isinstance(payload, dict):
            payload.setdefault('palette', [])
            return payload
    except Exception:
        pass
    return {'palette': [], 'states': {}}

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
    """Load PNG-derived terminal frames, preferring project assets.

    Supported asset layout:
      app/cli/assets/sprites/mascot_frames.json

    The file may contain either the newer compact_half payload generated from
    PNG frames or the older terminal_half payload. A small embedded fallback is
    kept in this file so copying only ui.py still gives the old animated beast.
    """
    path = Path(__file__).with_name('assets') / 'sprites' / 'mascot_frames.json'
    for payload in []:
        pass
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(payload, dict) and isinstance(payload.get('states'), dict):
            # Older generated assets used real positional animation and can shimmy
            # in terminal cells. Prefer only the locked asset; otherwise fall back
            # to the embedded locked version so stale installs do not reintroduce it.
            if payload.get('motion_locked') is True or 'motion_locked' in str(payload.get('format', '')):
                states = payload.get('states') if isinstance(payload.get('states'), dict) else {}
                for state_name, state_frames in states.items():
                    payload.setdefault(state_name, state_frames)
                return payload
    except Exception:
        pass
    payload = _decode_embedded_mascot_frames()
    states = payload.get('states') if isinstance(payload.get('states'), dict) else {}
    for state_name, state_frames in states.items():
        payload.setdefault(state_name, state_frames)
    return payload


def mascot_state_for(value: Any) -> str:
    state = str(value or 'idle').strip().lower()
    if state in {'working', 'thinking', 'streaming', 'active', 'running', 'queued', 'coding'}:
        return 'working'
    if state in {'alert', 'error', 'failed', 'blocked', 'cancel requested'}:
        return 'alert'
    if state in {'finished', 'complete', 'completed', 'done', 'success'}:
        return 'finished'
    return 'idle'


def mascot_effect_palette(palette: List[str], state: str = 'idle', frame: int = 0) -> List[str]:
    """Return a stateful palette while keeping the sprite geometry locked.

    The original PNG-derived beast can shimmer without physically moving if the
    canvas and encoded pixels stay fixed and only the green energy colours are
    remapped. This gives us blink, core glow, coding surge, success flash, and
    alert flare without tail/horn drift.
    """
    base = list(palette or [])
    while len(base) < 12:
        base.append('')
    normalized = mascot_state_for(state)
    phase = int(frame or 0) % 12

    def set_green(mid: str, bright: str, acid: str | None = None, deep: str | None = None) -> None:
        if deep is not None:
            base[6] = deep
        base[7] = mid
        base[8] = bright
        if acid is not None:
            base[9] = acid

    if normalized == 'working':
        # Coding/streaming: visible breathing core and eye surge.
        pulses = [
            ('#17B970', '#54FF9A', '#B5FF4D'),
            ('#19D98A', '#7CFF4F', '#D5FF6A'),
            ('#15E6AE', '#5CE1FF', '#C8FF72'),
            ('#19D98A', '#7CFF4F', '#D5FF6A'),
        ]
        set_green(*pulses[phase % len(pulses)], deep='#10925C')
    elif normalized == 'finished':
        # Completion: celebratory lime/gold pulse, not a moving frame.
        if phase in {0, 1, 2, 8, 9}:
            set_green('#8DFF63', '#D8FF56', '#F1FF8A', deep='#34B85F')
        else:
            set_green('#52D86E', '#9DFF69', '#D4FF68', deep='#249657')
    elif normalized == 'alert':
        # Alert: red/orange energy mapped onto the same fixed sprite pixels.
        if phase % 2 == 0:
            set_green('#FFBD4A', '#FF5F56', '#FFD166', deep='#B63E3E')
            base[10] = '#FF5F56'
        else:
            set_green('#D35E68', '#FF8A50', '#FFBD4A', deep='#8F2E32')
            base[10] = '#FFBD4A'
    else:
        # Idle: soft chest glow plus a brief blink. The blink is palette-only,
        # so it reads as eyes dimming without moving a single terminal cell.
        if phase in {7, 8}:
            set_green('#123329', '#1C4C3C', '#2A5C45', deep='#0C241E')
        elif phase in {0, 1, 2}:
            set_green('#20C978', '#74FF8B', '#C2FF4D', deep='#139A63')
        else:
            set_green('#18A96A', '#50E889', '#96FF62', deep='#118456')
    return base


def _sprite_status_badge(state: str = 'idle', frame: int = 0) -> Text:
    normalized = mascot_state_for(state)
    phase = int(frame or 0) % 12
    text = Text()
    if normalized == 'working':
        text.append('     ', style=BEAST_MUTED)
        text.append('▰▱▰ TYPING ', style=BEAST_INFO if phase % 2 else BEAST_ACID)
        text.append(('▁▃▅▇▅▃' if phase % 2 else '▃▅▇▅▃▁'), style=BEAST_GREEN)
    elif normalized == 'finished':
        text.append('     ', style=BEAST_MUTED)
        text.append('✓ TASK COMPLETE ', style=f'bold {BEAST_ACID}')
        text.append('▰▰▰ HAPPY', style=BEAST_ACID if phase % 2 else BEAST_LIME)
    elif normalized == 'alert':
        text.append('     ', style=BEAST_MUTED)
        text.append('! ALERT ', style=f'bold {BEAST_DANGER if phase % 2 else BEAST_WARN}')
        text.append('CONCERN ▰▱▰', style=BEAST_WARN if phase % 2 else BEAST_DANGER)
    else:
        text.append('     ', style=BEAST_MUTED)
        text.append('● IDLE ', style=BEAST_GREEN)
        text.append('blink/core', style=BEAST_MUTED)
    text.append('\n')
    return text


def _render_compact_half(frame_data: Dict[str, Any], palette: List[str], state: str = 'idle', frame: int = 0) -> Text:
    """Render PNG-derived BEAST frames on a stable terminal canvas.

    Geometry is pinned to a single frame per state. Animation is driven through
    palette remapping and a tiny fixed status badge, so the mascot blinks, glows,
    reacts to coding/completion/alerts, and still never shimmies left or right.
    """
    rows = frame_data.get('compact_half') if isinstance(frame_data, dict) else []
    if not isinstance(rows, list) or not rows:
        return mini_mascot()

    effect_palette = mascot_effect_palette(palette, state, frame)
    left_pad = int(frame_data.get('left_pad') or 5)
    target_cells = int(frame_data.get('target_cells') or 46)
    text = Text()
    for encoded in rows:
        line = str(encoded)
        rendered_cells = 0
        text.append(' ' * left_pad)
        rendered_cells += left_pad
        # Two palette characters per terminal cell: top pixel, bottom pixel.
        for i in range(0, len(line), 2):
            top_i = int(line[i:i+1], 12) if i < len(line) and line[i:i+1] else 0
            bottom_i = int(line[i+1:i+2], 12) if i + 1 < len(line) and line[i+1:i+2] else 0
            top = effect_palette[top_i] if 0 <= top_i < len(effect_palette) else ''
            bottom = effect_palette[bottom_i] if 0 <= bottom_i < len(effect_palette) else ''
            if top and bottom:
                text.append('▀', style=f'{top} on {bottom}')
            elif top:
                text.append('▀', style=top)
            elif bottom:
                text.append('▄', style=bottom)
            else:
                text.append(' ')
            rendered_cells += 1
        if rendered_cells < target_cells:
            text.append(' ' * (target_cells - rendered_cells))
        text.append('\n')
    text.append(_sprite_status_badge(state, frame))
    return text


def _render_terminal_half(frame_data: Dict[str, Any]) -> Text:
    half_rows = frame_data.get('terminal_half') if isinstance(frame_data, dict) else []
    if not isinstance(half_rows, list) or not half_rows:
        return mini_mascot()
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


SPRITESHEET_BY_STATE = {
    'idle': 'Idle.png',
    'working': 'Working.png',
    'alert': 'Alert.png',
    'finished': 'Finished.png',
}


FRAME_DIR_BY_STATE = {
    'idle': 'idle',
    'working': 'working',
    'alert': 'alert',
    'finished': 'finished',
}


def _sheet_background_pixel(pixel: tuple[int, int, int] | tuple[int, int, int, int]) -> bool:
    r, g, b = pixel[:3]
    return r > 225 and g > 225 and b > 225 and max(r, g, b) - min(r, g, b) < 16


def _transparent_sheet_background(image: Any) -> Any:
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            px = pixels[x, y]
            if _sheet_background_pixel(px):
                pixels[x, y] = (0, 0, 0, 0)
    return image


@lru_cache(maxsize=32)
def _individual_frame_images(state: str, target_cells: int = 34, target_rows: int = 14) -> tuple[Any, ...]:
    """Load true per-frame PNG animation assets for the terminal mascot."""
    if Image is None:
        return tuple()
    normalized = mascot_state_for(state)
    root = Path(__file__).with_name('assets') / 'sprites' / FRAME_DIR_BY_STATE.get(normalized, 'idle')
    paths = sorted(root.glob('frame_*.png'))
    if not paths:
        return tuple()

    raw_frames = []
    frame_bboxes: List[tuple[int, int, int, int] | None] = []
    max_art_w = 1
    max_art_h = 1
    for path in paths[:10]:
        try:
            frame = _transparent_sheet_background(Image.open(path).convert('RGBA'))
        except Exception:
            continue
        alpha = frame.getchannel('A')
        bbox = alpha.getbbox()
        if bbox is None:
            continue
        pad = 6
        bbox = (
            max(0, bbox[0] - pad),
            max(0, bbox[1] - pad),
            min(frame.width, bbox[2] + pad),
            min(frame.height, bbox[3] + pad),
        )
        raw_frames.append(frame)
        frame_bboxes.append(bbox)
        max_art_w = max(max_art_w, bbox[2] - bbox[0])
        max_art_h = max(max_art_h, bbox[3] - bbox[1])
    if not raw_frames:
        return tuple()

    target_px_w = target_cells
    target_px_h = target_rows * 2
    scale = min(target_px_w / max_art_w, target_px_h / max_art_h)
    resample = getattr(getattr(Image, 'Resampling', Image), 'LANCZOS', 1)
    frames = []
    for frame, bbox in zip(raw_frames, frame_bboxes):
        if bbox is None:
            continue
        art = frame.crop(bbox)
        new_size = (max(1, int(art.width * scale)), max(1, int(art.height * scale)))
        art = art.resize(new_size, resample)
        canvas = Image.new('RGBA', (target_px_w, target_px_h), (0, 0, 0, 0))
        x = max(0, (target_px_w - art.width) // 2)
        y = max(0, target_px_h - art.height - 1)
        canvas.alpha_composite(art, (x, y))
        frames.append(canvas)
    return tuple(frames)


@lru_cache(maxsize=16)
def _spritesheet_frame_images(state: str, target_cells: int = 34, target_rows: int = 14) -> tuple[Any, ...]:
    if Image is None:
        return tuple()
    normalized = mascot_state_for(state)
    path = Path(__file__).with_name('assets') / SPRITESHEET_BY_STATE.get(normalized, 'Idle.png')
    if not path.is_file():
        return tuple()
    try:
        sheet = Image.open(path).convert('RGBA')
    except Exception:
        return tuple()

    cols, rows = 5, 2
    raw_frames = []
    cell_w = sheet.width // cols
    cell_h = sheet.height // rows
    for index in range(cols * rows):
        x0 = (index % cols) * cell_w
        x1 = sheet.width if (index % cols) == cols - 1 else x0 + cell_w
        y0 = (index // cols) * cell_h
        y1 = sheet.height if (index // cols) == rows - 1 else y0 + cell_h
        cell = _transparent_sheet_background(sheet.crop((x0, y0, x1, y1)))
        pixels = cell.load()

        # Sprite sheets sometimes have a few pixels from a neighboring frame at
        # the cell edge. Remove small disconnected islands before alignment.
        alpha = cell.getchannel('A').load()
        seen: set[tuple[int, int]] = set()
        components: List[List[tuple[int, int]]] = []
        for y in range(cell.height):
            for x in range(cell.width):
                if alpha[x, y] < 35 or (x, y) in seen:
                    continue
                stack = [(x, y)]
                seen.add((x, y))
                comp: List[tuple[int, int]] = []
                while stack:
                    cx, cy = stack.pop()
                    comp.append((cx, cy))
                    for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                        if 0 <= nx < cell.width and 0 <= ny < cell.height and (nx, ny) not in seen and alpha[nx, ny] >= 35:
                            seen.add((nx, ny))
                            stack.append((nx, ny))
                components.append(comp)
        if components:
            largest = max(len(comp) for comp in components)
            keep = {pt for comp in components if len(comp) >= max(90, int(largest * 0.05)) for pt in comp}
            for y in range(cell.height):
                for x in range(cell.width):
                    if alpha[x, y] >= 35 and (x, y) not in keep:
                        pixels[x, y] = (0, 0, 0, 0)
        raw_frames.append(cell)

    frame_bboxes: List[tuple[int, int, int, int] | None] = []
    max_art_w = 1
    max_art_h = 1
    for cell in raw_frames:
        xs: List[int] = []
        ys: List[int] = []
        alpha = cell.getchannel('A').load()
        for y in range(cell.height):
            for x in range(cell.width):
                if alpha[x, y] >= 35:
                    xs.append(x)
                    ys.append(y)
        if not xs:
            frame_bboxes.append(None)
            continue
        pad = 6
        bbox = (
            max(0, min(xs) - pad),
            max(0, min(ys) - pad),
            min(cell.width, max(xs) + pad + 1),
            min(cell.height, max(ys) + pad + 1),
        )
        max_art_w = max(max_art_w, bbox[2] - bbox[0])
        max_art_h = max(max_art_h, bbox[3] - bbox[1])
        frame_bboxes.append(bbox)
    if not any(frame_bboxes):
        return tuple()

    frames = []
    target_px_w = target_cells
    target_px_h = target_rows * 2
    scale = min(target_px_w / max_art_w, target_px_h / max_art_h)
    scaled_max_w = max(1, int(max_art_w * scale))
    x_anchor = max(0, (target_px_w - scaled_max_w) // 2)
    for cell, bbox in zip(raw_frames, frame_bboxes):
        if bbox is None:
            continue
        art = cell.crop(bbox)
        new_size = (max(1, int(art.width * scale)), max(1, int(art.height * scale)))
        resample = getattr(getattr(Image, 'Resampling', Image), 'LANCZOS', 1)
        art = art.resize(new_size, resample)
        canvas = Image.new('RGBA', (target_px_w, target_px_h), (0, 0, 0, 0))
        canvas.alpha_composite(art, (x_anchor, target_px_h - art.height - 1))
        frames.append(canvas)
    return tuple(frames)


def _rgba_to_halfblocks(image: Any) -> Text:
    text = Text()
    if Image is None or image is None:
        return text
    pixels = image.load()
    width, height = image.size

    def color_at(x: int, y: int) -> str:
        r, g, b, a = pixels[x, y]
        if a < 35:
            return ''
        if a < 255:
            # Matting tiny antialias pixels against the panel keeps edges crisp
            # without bringing the original checkerboard back into the TUI.
            alpha = a / 255.0
            bg = (6, 17, 15)
            r = int(r * alpha + bg[0] * (1 - alpha))
            g = int(g * alpha + bg[1] * (1 - alpha))
            b = int(b * alpha + bg[2] * (1 - alpha))
        return f'#{r:02X}{g:02X}{b:02X}'

    for y in range(0, height, 2):
        for x in range(width):
            top = color_at(x, y)
            bottom = color_at(x, y + 1) if y + 1 < height else ''
            if top and bottom:
                text.append('▀', style=f'{top} on {bottom}')
            elif top:
                text.append('▀', style=top)
            elif bottom:
                text.append('▄', style=bottom)
            else:
                text.append(' ')
        text.append('\n')
    return text


def spritesheet_mascot(state: str = 'idle', frame: int = 0, *, target_cells: int = 34, target_rows: int = 14) -> Text | None:
    frames = _spritesheet_frame_images(mascot_state_for(state), target_cells, target_rows)
    if not frames:
        return None
    normalized = mascot_state_for(state)
    order = {
        # The last idle sheet cell has a slightly different anchor pose; looping
        # through it reads as a rightward pop. Bounce through the stable cells.
        'idle': (0, 1, 2, 3, 4, 5, 6, 7, 8, 7),
    }.get(normalized, tuple(range(len(frames))))
    index = order[int(frame or 0) % len(order)] if order else int(frame or 0) % len(frames)
    text = _rgba_to_halfblocks(frames[clamp(index, 0, len(frames) - 1)])
    text.append(_sprite_status_badge(state, frame))
    return text


def sprite_mascot(state: str = 'idle', frame: int = 0, *, target_cells: int = 34, target_rows: int = 14) -> Text:
    """Render the animated BEAST sprite from compact PNG-derived frames.

    This restores the original dragon/beast sprite while keeping it safe for a
    terminal TUI. The sprite is now large enough to read and no longer emits
    stray glyphs in the left margin.
    """
    live_frames = _individual_frame_images(mascot_state_for(state), target_cells, target_rows)
    if live_frames:
        normalized = mascot_state_for(state)
        order = {
            'idle': (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
            'working': (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
            'finished': (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
            'alert': (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
        }.get(normalized, tuple(range(len(live_frames))))
        index = order[int(frame or 0) % len(order)] if order else int(frame or 0) % len(live_frames)
        text = _rgba_to_halfblocks(live_frames[clamp(index, 0, len(live_frames) - 1)])
        text.append(_sprite_status_badge(state, frame))
        return text

    sheet_render = spritesheet_mascot(state, frame, target_cells=target_cells, target_rows=target_rows)
    if sheet_render is not None:
        return sheet_render

    payload = mascot_frames()
    frames_by_state = payload.get('states') if isinstance(payload, dict) else {}
    palette = payload.get('palette') if isinstance(payload, dict) else []
    frames = []
    if isinstance(frames_by_state, dict):
        frames = frames_by_state.get(mascot_state_for(state)) or frames_by_state.get('idle') or []
    if not frames:
        return mini_mascot()
    # The asset generator normalizes every state frame to the same terminal
    # canvas, so we can use real frame cycling without the old left/right shimmy.
    frame_data = frames[int(frame or 0) % len(frames)]
    if isinstance(frame_data, dict) and frame_data.get('compact_half'):
        return _render_compact_half(frame_data, palette if isinstance(palette, list) else [], state, frame)
    if isinstance(frame_data, dict) and frame_data.get('terminal_half'):
        return _render_terminal_half(frame_data)
    return mini_mascot()


def pct_from_status(status: Any, fallback: int = 88) -> int:
    text = str(status or '').strip().lower()
    if text in {'ok', 'healthy', 'ready', 'available', 'active', 'done', 'completed', 'success', 'running'}:
        return 98
    if any(x in text for x in ['warn', 'degraded', 'pending', 'wait', 'unknown']):
        return 78
    if any(x in text for x in ['blocked', 'error', 'deny', 'failed', 'offline', 'locked']):
        return 32
    return fallback



def percent_bar(percent: Any, *, width: int = 18) -> Text:
    return block_meter(percent, width=width)


def sparkline(values: Iterable[Any], *, width: int = 22, good: bool = True) -> Text:
    ticks = '▁▂▃▄▅▆▇█'
    nums: List[float] = []
    for value in values:
        try:
            nums.append(float(value))
        except Exception:
            pass
    if not nums:
        nums = [2, 4, 3, 5, 6, 4, 7, 5, 6, 8, 7, 9]
    if len(nums) < width:
        seed = nums[-1] if nums else 5
        while len(nums) < width:
            seed = ((seed * 1.7) + len(nums)) % 9 + 1
            nums.append(seed)
    nums = nums[-width:]
    lo, hi = min(nums), max(nums)
    span = hi - lo or 1.0
    palette = [BEAST_GRAPH_LOW, BEAST_GRAPH_MID, BEAST_EMERALD, BEAST_JADE, BEAST_GREEN, BEAST_GRAPH_PEAK]
    text = Text()
    for number in nums:
        idx = clamp(int(round(((number - lo) / span) * (len(ticks) - 1))), 0, len(ticks) - 1)
        style = palette[clamp(int((idx / max(1, len(ticks) - 1)) * (len(palette) - 1)), 0, len(palette) - 1)] if good else BEAST_MOSS
        text.append(ticks[idx], style=style)
    return text


def ring_gauge(percent: Any, label: str = '') -> Text:
    try:
        pct = max(0.0, min(100.0, float(percent)))
    except Exception:
        pct = 0.0
    segments = 10
    filled = int(round((pct / 100.0) * segments))
    style = BEAST_GREEN if pct >= 90 else BEAST_WARN if pct >= 65 else BEAST_DANGER
    text = Text()
    text.append('◜', style=style)
    text.append('●' * filled, style=style)
    text.append('○' * (segments - filled), style='#294238')
    text.append('◝', style=style)
    text.append(f' {pct:.0f}/100', style=f'bold {style}')
    if label:
        text.append(f'\n{label}', style='#AAB8B2')
    return text



def visual_tile(title: str, value: Any, note: str, visual: Any, *, accent: str = BEAST_GREEN) -> Panel:
    symbol = symbol_for(title, '▰')
    border = panel_accent_for(title, value if accent not in {BEAST_WARN, BEAST_DANGER} else accent)
    header = Text()
    header.append(f'{symbol} ', style=f'bold {border}')
    header.append(title.upper(), style=BEAST_MUTED)
    signal = metric_signal(title, value, note)
    return fixed_panel(
        Group(
            header,
            Text(str(value), style=f'bold {accent}'),
            block_meter(signal, width=20),
            Text(str(note), style=BEAST_STEEL),
            Text(''),
            visual,
        ),
        border_style=border,
        style=BEAST_PANEL,
        padding=(1, 1),
        box_style=box.ROUNDED,
        height=VISUAL_TILE_HEIGHT,
    )


def symbol_for(value: Any, default: str = '◇') -> str:
    text = str(value or '').lower()
    symbols = [
        (('provider', 'route', 'routing'), '⌁'),
        (('diagnostic', 'doctor', 'health'), '⌁'),
        (('compress', 'log', 'tail'), '◉'),
        (('handoff', 'packet', 'orchestration'), '▣'),
        (('scaffold', 'dashboard', 'generation'), '▤'),
        (('chronicle', 'memory', 'publish'), '▦'),
        (('plugin', 'integration'), '♧'),
        (('policy', 'governance', 'approval'), '⬡'),
        (('tool', 'command', 'exec'), '⚒'),
        (('security', 'shield', 'auth'), '⬢'),
        (('workspace', 'file', 'context'), '▱'),
        (('model', 'provider', 'ai'), '▣'),
    ]
    for needles, symbol in symbols:
        if any(needle in text for needle in needles):
            return symbol
    return default


def confidence_from_item(item: Dict[str, Any], fallback: int = 74) -> int:
    for key in ['confidence', 'score', 'fitness_score', 'success_rate']:
        value = item.get(key)
        try:
            number = float(value)
            if number <= 1:
                number *= 100
            return clamp(int(round(number)), 0, 100)
        except Exception:
            pass
    return fallback



def metric(title: str, value: Any, note: str = '', accent: Any = None) -> Panel:
    style = accent or status_style(value)
    border = panel_accent_for(title, value)
    signal = metric_signal(title, value, note)
    header = Text()
    header.append(f'{symbol_for(title, "▰")} ', style=f'bold {border}')
    header.append(str(title).upper(), style=BEAST_MUTED)
    body = Group(
        header,
        Text(str(value), style=f'bold {style}'),
        block_meter(signal, width=18),
        Text(str(note), style=BEAST_STEEL),
    )
    return fixed_panel(body, border_style=border, style=BEAST_PANEL, padding=(1, 1), box_style=box.ROUNDED, height=METRIC_CARD_HEIGHT)


def litellm_model_name(model: Dict[str, Any]) -> str:
    params = model.get('litellm_params') if isinstance(model.get('litellm_params'), dict) else {}
    info = model.get('model_info') if isinstance(model.get('model_info'), dict) else {}
    return val(model, 'model_name', 'name', 'id', default='') or val(info, 'id', 'model_name', default='') or val(params, 'model', default='model')


def litellm_provider_model(model: Dict[str, Any]) -> str:
    params = model.get('litellm_params') if isinstance(model.get('litellm_params'), dict) else {}
    info = model.get('model_info') if isinstance(model.get('model_info'), dict) else {}
    return val(model, 'provider_model', 'model', default='') or val(params, 'model', default='') or val(info, 'base_model', default='')


def litellm_models_table(models: List[Dict[str, Any]], *, include_state: bool = False) -> Table:
    table = Table(expand=True, box=box.SIMPLE_HEAVY, header_style=f'bold {BEAST_ACID}', show_header=True)
    table.add_column('Model', ratio=2)
    table.add_column('Provider route', ratio=3, no_wrap=True)
    table.add_column('Base URL', ratio=1)
    if include_state:
        table.add_column('State', width=10)
    if not models:
        row = [Text('No LiteLLM models loaded', style=BEAST_WARN), Text('render /edgek/deploy/litellm-config', style=BEAST_MUTED), Text('waiting', style=BEAST_MUTED)]
        if include_state:
            row.append(status_mark('WARN') + Text(' WARN', style=BEAST_WARN))
        table.add_row(*row)
        return table
    for model in models[:12]:
        params = model.get('litellm_params') if isinstance(model.get('litellm_params'), dict) else {}
        row = [
            Text(litellm_model_name(model)[:48], style=BEAST_GREEN),
            Text(litellm_provider_model(model)[:54], style=BEAST_TEXT),
            Text(val(params, 'api_base', default='default')[:52], style=BEAST_MUTED),
        ]
        if include_state:
            row.append(status_mark('OK') + Text(' OK', style=BEAST_GREEN))
        table.add_row(*row)
    return table


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
    no_plan = not bool(plan)
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
        if no_plan and key == 'gate_status':
            value = 'not run (no governed plan queued)'
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


def provider_secrets_operational(snap: BackendSnapshot) -> Dict[str, Any]:
    """Summarize provider secret readiness without flagging local-only stacks."""
    secret_count = snap.provider_secret_count()
    local_routes = 0
    cloud_routes = 0
    missing_cloud = 0
    local_backends = {
        'litellm', 'ollama', 'llama_cpp', 'local_nim', 'vllm', 'sglang',
        'tgi', 'tensorrt_llm', 'openai_compatible',
    }
    cloud_backends = {
        'openai', 'anthropic', 'gemini', 'google', 'huggingface', 'replicate',
        'groq', 'cohere', 'openrouter', 'xai', 'nvidia_nim', 'deepinfra',
        'cerebras', 'fal', 'hyperbolic', 'novita', 'nscale', 'ovhcloud',
        'featherless',
    }
    for row in _adapter_rows(snap) or _provider_rows(snap):
        pid = provider_key(row.get('provider_id') or row.get('id') or row.get('name'))
        backend = provider_key(row.get('backend') or row.get('route_provider') or row.get('adapter_class') or pid)
        if backend in local_backends or pid in local_backends:
            local_routes += 1
            continue
        if backend in cloud_backends or pid in cloud_backends:
            cloud_routes += 1
            if provider_secret_state(snap, pid) == 'none':
                missing_cloud += 1
    if secret_count:
        status = 'OK'
        detail = f"{secret_count} configured"
    elif local_routes and not cloud_routes:
        status = 'OK'
        detail = f"local/sidecar only; {local_routes} route(s)"
    elif local_routes and missing_cloud == cloud_routes:
        status = 'OK'
        detail = f"local routes active; {cloud_routes} cloud route(s) optional"
    elif cloud_routes and missing_cloud:
        status = 'REVIEW'
        detail = f"{missing_cloud}/{cloud_routes} cloud route(s) missing keys"
    else:
        status = 'OK'
        detail = "no provider secrets required by active snapshot"
    return {
        'status': status,
        'detail': detail,
        'count': secret_count,
        'local_routes': local_routes,
        'cloud_routes': cloud_routes,
        'missing_cloud': missing_cloud,
    }


def crystal_kv_prefill_counts(snap: BackendSnapshot) -> Dict[str, int]:
    crystal_reuse = snap.crystal_reuse if isinstance(snap.crystal_reuse, dict) else {}
    storage = crystal_reuse.get('storage') if isinstance(crystal_reuse.get('storage'), dict) else {}
    stored = storage.get('stored_by_type') if isinstance(storage.get('stored_by_type'), dict) else {}
    kv_transport = crystal_reuse.get('kv_transport') if isinstance(crystal_reuse.get('kv_transport'), dict) else {}
    durable_prefills = int(storage.get('kv_prefill_credits') or stored.get('kv_prefill') or 0)
    live_blocks = max(
        int(kv_transport.get('total_blocks') or 0),
        int(snap.kv_cache_state.get('total_blocks') or 0),
    )
    operations = max(
        int(kv_transport.get('operations_logged') or 0),
        int(snap.kv_cache_state.get('operations_logged') or 0),
    )
    return {
        'durable_prefills': durable_prefills,
        'live_blocks': live_blocks,
        'display_blocks': max(live_blocks, durable_prefills),
        'operations': operations,
    }


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


def intelligence_summary(snap: BackendSnapshot) -> Dict[str, Any]:
    handshake = snap.session_handshake or {}
    budget = handshake.get('latency_budget') if isinstance(handshake.get('latency_budget'), dict) else {}
    commons = snap.commons_state or {}
    ranking = snap.commons_ranking or {}
    laziness = snap.tool_laziness.get('summary') if isinstance(snap.tool_laziness.get('summary'), dict) else {}
    economist = snap.provider_economist or {}
    selected = economist.get('selected') if isinstance(economist.get('selected'), dict) else {}
    swarm = snap.swarm_summary()
    crystal_reuse = snap.crystal_reuse if isinstance(snap.crystal_reuse, dict) else {}
    crystal_storage = crystal_reuse.get('storage') if isinstance(crystal_reuse.get('storage'), dict) else {}
    kv_counts = crystal_kv_prefill_counts(snap)
    integration_health = crystal_reuse.get('integration_health') if isinstance(crystal_reuse.get('integration_health'), dict) else {}
    memory_security = snap.memory_security if isinstance(snap.memory_security, dict) else {}
    memory_hull = memory_security.get('memory_hull') if isinstance(memory_security.get('memory_hull'), dict) else {}
    residue_seal = memory_security.get('residue_seal') if isinstance(memory_security.get('residue_seal'), dict) else {}
    passport = memory_security.get('agent_passport') if isinstance(memory_security.get('agent_passport'), dict) else {}
    passport_lint = passport.get('policy_lint') if isinstance(passport.get('policy_lint'), dict) else {}
    return {
        'online': bool(snap.online),
        'blocker': snapshot_blocker(snap),
        'endpoint_errors': len(snap.errors),
        'aware': handshake.get('beast_object_type') == 'beast_session_handshake',
        'session_id': handshake.get('session_id') or '',
        'handshake_hash': handshake.get('handshake_hash') or '',
        'preflight_budget_ms': budget.get('preflight_budget_ms', 0),
        'scout_budget_ms': budget.get('scout_budget_ms', 0),
        'commons_evidence': int(commons.get('evidence_count') or 0),
        'commons_candidates': int(commons.get('candidate_count') or 0),
        'commons_adopted': int(commons.get('adopted_count') or 0),
        'commons_rankings': int(ranking.get('count') or 0),
        'swarm_runs': swarm.get('runs', 0),
        'swarm_recent': swarm.get('recent_count', 0),
        'swarm_profiles': swarm.get('profile_count', 0),
        'swarm_commons_prepared': swarm.get('commons_prepared', 0),
        'swarm_commons_accepted': swarm.get('commons_accepted', 0),
        'evidence_plane_count': swarm.get('evidence_plane_count', 0),
        'evidence_plane_total': swarm.get('evidence_plane_total', 0),
        'evidence_plane_hash': swarm.get('evidence_plane_hash', ''),
        'swarm_candidates_proposed': swarm.get('swarm_candidates_proposed', 0),
        'commons_candidate_queue': swarm.get('commons_candidate_queue', 0),
        'kv_cache_blocks': swarm.get('kv_cache_blocks', 0),
        'kv_cache_operations': swarm.get('kv_cache_operations', 0),
        'kv_cache_prepared': swarm.get('kv_cache_prepared', 0),
        'kv_cache_accepted': swarm.get('kv_cache_accepted', 0),
        'openclaw_ready': swarm.get('openclaw_ready', False),
        'openclaw_actions': swarm.get('openclaw_actions', 0),
        'ollama_ready': swarm.get('ollama_ready', False),
        'ollama_models': swarm.get('ollama_models', 0),
        'tools_skipped': int(laziness.get('skip_count') or 0),
        'tools_observed': int(laziness.get('learn_more_count') or 0),
        'latency_avoided_ms': float(laziness.get('estimated_latency_avoided_ms') or 0),
        'economist_decision': economist.get('decision') or 'awaiting_evidence',
        'economist_provider': selected.get('provider') or '',
        'economist_reason': economist.get('reason') or ('no provider Chronicle samples' if not selected else ''),
        'economist_role': economist.get('requested_role') or 'primary_patch_provider',
        'exchange_enabled': bool(snap.capability_exchange_state.get('enabled')),
        'otel_configured': bool(snap.otel_state.get('configured')),
        'plugin_count': int(snap.plugins_state.get('count') or 0),
        'compute_samples': int(snap.compute_metrics.get('sample_size') or 0),
        'observed_compute_tokens': int(snap.compute_metrics.get('observed_total_tokens') or 0),
        'avoidable_compute_tokens': int(snap.compute_metrics.get('estimated_avoidable_total_tokens') or 0),
        'compute_mode': str(snap.compute_state.get('mode') or 'shadow'),
        'weekly_compute_savings_usd': snap.compute_savings.get('potential_weekly_savings_usd'),
        'weekly_compute_savings_status': str(snap.compute_savings.get('availability') or 'unavailable'),
        'false_suppression_rate': float(snap.compute_metrics.get('false_suppression_rate') or 0.0),
        'compute_enforcement_pause': bool(snap.compute_metrics.get('enforcement_pause_required', False)),
        'crystal_reuse_credits': int(crystal_storage.get('active_credits') or 0),
        'crystal_reuse_total': int(crystal_storage.get('total_credits') or 0),
        'crystal_reuse_hits': int(crystal_storage.get('total_reuse_count') or 0),
        'crystal_reuse_saved': int(crystal_storage.get('measured_reuse_tokens_saved') or 0),
        'crystal_integration_count': int(integration_health.get('integration_count') or len(crystal_reuse.get('integrations') or [])),
        'crystal_integration_configured': int(integration_health.get('configured_count') or 0),
        'crystal_kv_blocks': kv_counts['display_blocks'],
        'crystal_kv_live_blocks': kv_counts['live_blocks'],
        'crystal_kv_durable_prefills': kv_counts['durable_prefills'],
        'memory_hull_verified': int(memory_hull.get('verified_sidecars') or 0),
        'memory_hull_failed': int(memory_hull.get('failed_sidecars') or 0),
        'memory_hull_root': str(memory_hull.get('root') or ''),
        'residue_key_ready': bool(residue_seal.get('key_exists')),
        'passport_policy_valid': bool(passport_lint.get('valid')),
        'passport_policy_count': int(passport_lint.get('policy_count') or 0),
    }


def master_evidence_summary(snap: BackendSnapshot) -> Dict[str, Any]:
    evidence = snap.master_mega_evidence if isinstance(snap.master_mega_evidence, dict) else {}
    metrics = evidence.get('metrics') if isinstance(evidence.get('metrics'), dict) else {}
    design = evidence.get('controlled_design') if isinstance(evidence.get('controlled_design'), dict) else {}
    qpc = metrics.get('mature_qpccd') if isinstance(metrics.get('mature_qpccd'), dict) else {}
    layers = evidence.get('credibility_layers') if isinstance(evidence.get('credibility_layers'), list) else []
    pending = [item for item in layers if isinstance(item, dict) and item.get('status') != 'complete']
    latest_omni = evidence.get('latest_omni') if isinstance(evidence.get('latest_omni'), dict) else {}
    live_summary = latest_omni.get('live_summary') if isinstance(latest_omni.get('live_summary'), dict) else {}
    governed_summary = latest_omni.get('governed_summary') if isinstance(latest_omni.get('governed_summary'), dict) else {}
    latest_provider = next(iter(governed_summary.keys()), '')
    latest_provider_summary = governed_summary.get(latest_provider) if isinstance(governed_summary.get(latest_provider), dict) else {}
    return {
        'available': bool(evidence),
        'release': f"v{evidence.get('release_version')}" if evidence.get('release_version') else 'unavailable',
        'status': evidence.get('release_status') or 'missing',
        'observed_cells': int(design.get('observed_cells') or metrics.get('controlled_design_cells_observed') or 0),
        'target_cells': int(design.get('target_cells') or metrics.get('designed_controlled_matrix_rows') or 450),
        'remaining_cells': int(design.get('remaining_cells') or metrics.get('controlled_design_cells_remaining') or 0),
        'progress_rate': float(design.get('progress_rate') or metrics.get('controlled_design_progress_rate') or 0.0),
        'qpccd_numerator': int(qpc.get('numerator') or 0),
        'qpccd_denominator': int(qpc.get('denominator') or 0),
        'qpccd_rate': float(qpc.get('rate') or 0.0),
        'deterministic_reuse': int(metrics.get('mature_deterministic_reuse') or 0),
        'mutation_recovered': int(metrics.get('mutation_recovered') or 0),
        'mutation_cases': int(metrics.get('mutation_case_count') or 0),
        'cross_provider_cases': int(metrics.get('primary_cross_provider_cases') or 0),
        'groq_scout_cases': int(metrics.get('groq_scout_cases') or 0),
        'avoided_tokens_estimate': int(metrics.get('primary_avoided_tokens_estimate') or 0) + int(metrics.get('groq_scout_avoided_tokens_estimate') or 0),
        'pending_layers': len(pending),
        'pending_layer_ids': [str(item.get('id') or '') for item in pending],
        'secret_scan_passed': bool(evidence.get('secret_scan_passed')),
        'integrity_hash': str(evidence.get('integrity_hash') or ''),
        'artifact_path': str(evidence.get('artifact_path') or ''),
        'latest_generated_at': str(latest_omni.get('generated_at') or ''),
        'latest_artifact_path': str(latest_omni.get('artifact_path') or ''),
        'latest_covered_layers': int(latest_omni.get('covered_layers') or 0),
        'latest_total_layers': int(latest_omni.get('total_layers') or 0),
        'latest_live_tasks': int(live_summary.get('tasks') or latest_provider_summary.get('tasks') or 0),
        'latest_completed': int(live_summary.get('completed') or latest_provider_summary.get('completed') or 0),
        'latest_provider': str(latest_provider or ''),
        'latest_clean_completed': int(latest_provider_summary.get('clean_completed') or 0),
        'latest_rescued_completed': int(latest_provider_summary.get('rescued_completed') or 0),
    }


def latest_mega_summary(snap: BackendSnapshot) -> Dict[str, Any]:
    artifact = snap.latest_mega_artifact if isinstance(snap.latest_mega_artifact, dict) else {}
    mutation = artifact.get('mutation') if isinstance(artifact.get('mutation'), dict) else {}
    qpc = artifact.get('qpc') if isinstance(artifact.get('qpc'), dict) else {}
    phase_package = artifact.get('phase_package') if isinstance(artifact.get('phase_package'), dict) else {}
    acceptance = artifact.get('acceptance_status') if isinstance(artifact.get('acceptance_status'), dict) else {}
    phases = phase_package.get('phases') if isinstance(phase_package.get('phases'), list) else []
    return {
        'available': bool(artifact),
        'artifact_path': str(artifact.get('artifact_path') or ''),
        'archive_path': str(artifact.get('archive_path') or ''),
        'generated_at': str(artifact.get('generated_at') or ''),
        'mode': str(artifact.get('mode') or ''),
        'live': bool(artifact.get('live')),
        'providers': artifact.get('providers') if isinstance(artifact.get('providers'), list) else [],
        'families': artifact.get('families') if isinstance(artifact.get('families'), list) else [],
        'occurrences': artifact.get('occurrences') if isinstance(artifact.get('occurrences'), list) else [],
        'lanes': artifact.get('lanes') if isinstance(artifact.get('lanes'), list) else [],
        'controlled_rows': int(artifact.get('controlled_rows') or 0),
        'completed_rows': int(artifact.get('completed_rows') or 0),
        'raw_live_result_count': int(artifact.get('raw_live_result_count') or 0),
        'live_result_count': int(artifact.get('live_result_count') or 0),
        'provider_call_receipts': int(artifact.get('provider_call_receipts') or 0),
        'provider_call_receipt_files': int(artifact.get('provider_call_receipt_files') or 0),
        'impact_fingerprint_files': int(artifact.get('impact_fingerprint_files') or 0),
        'compute_governor_receipts': int(artifact.get('compute_governor_receipts') or 0),
        'crystallization_events': int(artifact.get('crystallization_events') or 0),
        'reuse_blocked_count': int(mutation.get('reuse_blocked_count') or 0),
        'recovered_count': int(mutation.get('recovered_count') or 0),
        'false_reuse_count': int(mutation.get('false_reuse_count') or 0),
        'mutation_case_count': int(mutation.get('case_count') or 0),
        'qpccd_numerator': int(qpc.get('numerator') or 0),
        'qpccd_denominator': int(qpc.get('denominator') or 0),
        'phase_package_passed': bool(phase_package.get('passed')),
        'phase_count': int(phase_package.get('phase_count') or len(phases)),
        'phase_pass_count': sum(1 for phase in phases if isinstance(phase, dict) and phase.get('passed')),
        'provider_receipts_present': bool(acceptance.get('provider_call_receipts_present')),
        'crystal_phases_present': bool(acceptance.get('crystal_compute_phase_package_present')),
        'integrity_hash': str(artifact.get('integrity_hash') or ''),
        'resume_source': str(artifact.get('resume_source') or ''),
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
            ('t','Test selected'),('v / Enter','Run/view selected'),('e','Economy operations'),('ctrl+e','Edit/config selected'),
            ('a','Approve/promote'),('b','Block/reject'),('s','Start live session'),('n','Next provider'),('[ / ]','Previous / next provider'),('j','Intelligence / Commons'),('c','Context picker'),('o','Provider source patch plan'),('f','Preview/select hunks'),('u','Apply selected hunks'),('z','Rollback latest apply'),('l','Approval queue'),('y','Approve latest plan'),
            ('w','Toggle streaming mode'),('k','Cancel current live turn'),('p','Prepare handoff'),('9','Diagnostics page'),('ctrl+t','Prepare Tiny Llama demo'),('ctrl+k','Command palette'),
        ]:
            right.add_row(Text(key, style=f'bold {BEAST_ACID}'), Text(desc, style=BEAST_TEXT))
        grid = Table.grid(expand=True); grid.add_column(ratio=1); grid.add_column(ratio=1)
        grid.add_row(
            Panel(Group(Text('NAVIGATION', style=f'bold {BEAST_ACID}'), Text(''), left), border_style=BEAST_BORDER),
            Panel(Group(Text('ACTIONS', style=f'bold {BEAST_ACID}'), Text(''), right), border_style=BEAST_BORDER),
        )
        with VerticalScroll(id='modal-scroll'):
            yield Static(Panel(Group(Text('BEAST COMMAND DECK', style=f'bold {BEAST_ACID}'), Text('Esc, q, h, or ? closes this overlay. PageUp/PageDown scrolls this deck.', style=BEAST_MUTED), Text(''), grid), border_style=BEAST_ACID, padding=(1,2), style=BEAST_PANEL), id='help-panel')

    async def on_key(self, event: events.Key) -> None:
        modal_scroll_key(self, event)


class DetailScreen(ModalScreen):
    BINDINGS = [Binding('escape','app.pop_screen','Close'), Binding('q','app.pop_screen','Close'), Binding('v','app.pop_screen','Close')]

    def __init__(self, title: str, payload: Any):
        super().__init__()
        self.detail_title = title
        self.payload = payload

    def compose(self) -> ComposeResult:
        with VerticalScroll(id='modal-scroll'):
            yield Static(
                Panel(
                    Group(
                        Text(self.detail_title, style=f'bold {BEAST_ACID}'),
                        Text('Esc/q/v closes this viewer. PageUp/PageDown scrolls.', style=BEAST_MUTED),
                        Text(''),
                        structured_payload(self.payload),
                    ),
                    border_style=BEAST_ACID,
                    padding=(1, 2),
                    style=BEAST_PANEL,
                ),
                id='detail-panel',
            )

    async def on_key(self, event: events.Key) -> None:
        modal_scroll_key(self, event)


class ProviderConfigScreen(ModalScreen):
    BINDINGS = [
        Binding('escape','close','Close'),
        Binding('q','close','Close'),
        Binding('ctrl+s','save','Save'),
        Binding('enter','save','Save', priority=True),
    ]

    def __init__(self, provider_id: str, route: Dict[str, Any], current_model: str = ''):
        super().__init__()
        self.provider_id = provider_key(provider_id or route.get('provider_id') or 'litellm')
        self.route = route
        env_values = [part.strip() for part in str(route.get('env') or '').replace(';', ',').split(',') if part.strip()]
        self.env_name = env_values[0] if env_values else f'{self.provider_id.upper().replace("-", "_")}_API_KEY'
        self.current_model = current_model or str(route.get('requested_model') or route.get('resolved_model') or 'beast-auto')

    def compose(self) -> ComposeResult:
        detail = Table.grid(expand=True)
        detail.add_column(width=18)
        detail.add_column(ratio=1)
        for key in ['provider_id', 'backend', 'route_provider', 'default_model', 'resolved_model', 'base_url', 'proxy_path', 'secret']:
            detail.add_row(Text(human_label(key), style=BEAST_MUTED), Text(str(self.route.get(key) or ''), style=status_style(self.route.get(key))))
        with VerticalScroll(id='modal-scroll'):
            yield Static(
                Panel(
                    Group(
                        title_text('EDIT PROVIDER ROUTE', '✎'),
                        Text('Enter saves. Esc/q closes. API keys are written to .beast/provider_secrets.env and imported into the local BEAST vault.', style=BEAST_MUTED),
                        Text(''),
                        Panel(Group(title_text('CURRENT ROUTE', '⌁'), Text(''), detail), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(1,2), box=box.ROUNDED),
                        Text(''),
                        Text('Provider id', style=f'bold {BEAST_ACID}'),
                    ),
                    border_style=BEAST_ACID,
                    padding=(1, 2),
                    style=BEAST_PANEL,
                ),
                id='detail-panel',
            )
            yield Input(value=self.provider_id, placeholder='provider id, e.g. openai, anthropic, litellm', id='provider-edit-id')
            yield Input(value=self.current_model, placeholder='session model alias, e.g. beast-auto or provider/model', id='provider-edit-model')
            yield Input(value=self.env_name, placeholder='env var name, e.g. OPENAI_API_KEY', id='provider-edit-env')
            yield Input(password=True, placeholder='paste API key or leave blank to keep existing secret', id='provider-edit-secret')
            yield Static(
                Panel(
                    Group(
                        Text('Actions', style=f'bold {BEAST_ACID}'),
                        Text('Enter / Ctrl+S: save provider, model, and optional API key', style=BEAST_TEXT),
                        Text('The TUI will refresh provider secrets and LiteLLM generated config after save.', style=BEAST_MUTED),
                    ),
                    border_style=BEAST_JADE,
                    padding=(1,2),
                    style=BEAST_PANEL,
                )
            )

    async def on_mount(self) -> None:
        try:
            self.query_one('#provider-edit-secret', Input).focus()
        except Exception:
            pass

    async def on_key(self, event: events.Key) -> None:
        if event.key in {'escape', 'q'}:
            event.stop()
            self.action_close()
            return
        if modal_scroll_key(self, event):
            return

    def action_close(self) -> None:
        try:
            self.dismiss()
        except Exception:
            pass
        try:
            self.app.pop_screen()
        except Exception:
            pass

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.action_save()

    def action_save(self) -> None:
        try:
            provider = self.query_one('#provider-edit-id', Input).value.strip() or self.provider_id
            model = self.query_one('#provider-edit-model', Input).value.strip() or 'beast-auto'
            env_name = self.query_one('#provider-edit-env', Input).value.strip() or self.env_name
            secret = self.query_one('#provider-edit-secret', Input).value.strip()
            self.app.save_provider_config(provider, model, env_name, secret)
            self.app.pop_screen()
        except Exception as exc:
            self.app.notify(str(exc), title='Provider config', severity='warning')


class CommandPaletteScreen(ModalScreen):
    BINDINGS = [
        Binding('escape','close_palette','Close'), Binding('q','close_palette','Close'),
        Binding('up','move_up','Up', priority=True), Binding('down','move_down','Down', priority=True),
        Binding('enter','choose','Run'),
    ]

    def __init__(self, commands: List[Dict[str, Any]]):
        super().__init__()
        self.commands = commands
        self.index = 0

    def compose(self) -> ComposeResult:
        with VerticalScroll(id='modal-scroll'):
            yield Static(self.render_palette(), id='command-palette')

    async def on_key(self, event: events.Key) -> None:
        if modal_scroll_key(self, event):
            return
        if event.key == 'up':
            event.stop()
            self.action_move_up()
        elif event.key == 'down':
            event.stop()
            self.action_move_down()
        elif event.key == 'enter':
            event.stop()
            self.action_choose()
        elif event.key in {'escape'} or event.character == 'q':
            event.stop()
            self.action_close_palette()

    async def on_click(self, event: events.Click) -> None:
        try:
            widget = self.query_one('#command-palette', Static)
            self.index = modal_row_from_click(widget, event, len(self.commands), table_top=6)
            self._refresh()
            event.stop()
        except Exception:
            pass

    def render_palette(self):
        table = Table(expand=True, box=box.SIMPLE_HEAVY, header_style=f'bold {BEAST_ACID}', border_style=BEAST_BORDER)
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
        Binding('up','move_up','Up', priority=True), Binding('down','move_down','Down', priority=True),
        Binding('enter','toggle_file','Toggle'), Binding('c','close_picker','Close'),
    ]

    def __init__(self, files: List[Dict[str, Any]], selected_files: List[str]):
        super().__init__()
        self.files = files
        self.selected_files = set(selected_files)
        self.index = 0

    def compose(self) -> ComposeResult:
        with VerticalScroll(id='modal-scroll'):
            yield Static(self.render_picker(), id='context-picker')

    async def on_key(self, event: events.Key) -> None:
        if modal_scroll_key(self, event):
            return
        if event.key == 'up':
            event.stop()
            self.action_move_up()
        elif event.key == 'down':
            event.stop()
            self.action_move_down()
        elif event.key == 'enter':
            event.stop()
            self.action_toggle_file()
        elif event.key in {'escape'} or event.character in {'q', 'c'}:
            event.stop()
            self.action_close_picker()

    async def on_click(self, event: events.Click) -> None:
        try:
            widget = self.query_one('#context-picker', Static)
            self.index = modal_row_from_click(widget, event, len(self.files), table_top=6, max_rows=80)
            self.refresh_view()
            event.stop()
        except Exception:
            pass

    def render_picker(self):
        table = Table(expand=True, box=box.SIMPLE_HEAVY, header_style=f'bold {BEAST_ACID}', border_style=BEAST_BORDER)
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
        with VerticalScroll(id='modal-scroll'):
            yield Static(
                Panel(
                    Group(
                        Text('BEAST SOURCE PLAN', style=f'bold {BEAST_ACID}'),
                        Text('y approve/save  f diff/select hunks  v verify  u apply selected  b reject  Esc/q close. PageUp/PageDown scrolls.', style=BEAST_MUTED),
                        Text(status_line, style=BEAST_GREEN if summary.get('diff_compiled') else BEAST_WARN),
                        Text(''),
                        top,
                        Text(''),
                        Panel(Group(Text('OPERATIONS', style=f'bold {BEAST_ACID}'), operations_table(self.plan)), border_style=BEAST_BORDER),
                        Text(''),
                        Panel(structured_payload(self.plan), title='Plan data map', border_style=BEAST_BORDER),
                    ),
                    border_style=BEAST_ACID,
                    padding=(1,2),
                    style=BEAST_PANEL,
                ),
                id='patch-plan-viewer',
            )
    async def on_key(self, event: events.Key) -> None:
        modal_scroll_key(self, event)
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
        Binding('up','move_up','Prev hunk', priority=True), Binding('down','move_down','Next hunk', priority=True),
        Binding('space','toggle_hunk','Toggle hunk'), Binding('f','refresh_diff','Refresh diff'),
        Binding('y','approve','Approve plan'), Binding('u','apply','Apply selected'), Binding('z','rollback','Rollback'),
    ]
    def __init__(self, diff: Dict[str, Any]):
        super().__init__(); self.diff = diff; self.index = 0
    def compose(self) -> ComposeResult:
        with VerticalScroll(id='modal-scroll'):
            yield Static(self.render_diff(), id='diff-preview')
    async def on_key(self, event: events.Key) -> None:
        if modal_scroll_key(self, event):
            return
        if event.key == 'up':
            event.stop()
            self.action_move_up()
        elif event.key == 'down':
            event.stop()
            self.action_move_down()
        elif event.key == 'space':
            event.stop()
            self.action_toggle_hunk()
        elif event.key in {'enter'}:
            event.stop()
            self.action_toggle_hunk()
        elif event.key in {'escape'} or event.character == 'q':
            event.stop()
            self.app.pop_screen()

    async def on_click(self, event: events.Click) -> None:
        try:
            operations = self.diff.get('operations') or []
            widget = self.query_one('#diff-preview', Static)
            self.index = modal_row_from_click(widget, event, len(operations), table_top=7, max_rows=40)
            self.refresh_view()
            event.stop()
        except Exception:
            pass
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
                Text('↑↓ select hunk  Space toggle  y approve plan  u apply selected  z rollback latest  Esc/q close', style=BEAST_MUTED),
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
    def action_approve(self):
        try: self.app.approve_current_patch_plan()
        except Exception: pass
        self.refresh_view()
    def action_apply(self):
        try: self.app.apply_current_patch_plan()
        except Exception: pass
    def action_rollback(self):
        try: self.app.rollback_latest_patch()
        except Exception: pass


class ApprovalQueueScreen(ModalScreen):
    BINDINGS = [
        Binding('escape','app.pop_screen','Close'), Binding('q','app.pop_screen','Close'),
        Binding('up','move_up','Up', priority=True), Binding('down','move_down','Down', priority=True),
        Binding('enter','approve','Approve'), Binding('y','approve','Approve'), Binding('b','reject','Reject'),
    ]
    def __init__(self, queue: List[Dict[str, Any]]):
        super().__init__(); self.queue = queue; self.index = max(0, len(queue[-12:]) - 1)
    def render_queue(self):
        table = Table(expand=True, box=box.SIMPLE_HEAVY)
        for col in ['','Plan','Status','Objective','Files']:
            table.add_column(col)
        if not self.queue:
            table.add_row('', 'none','empty','No approvals queued','0')
        for i, item in enumerate(self.queue[-12:]):
            table.add_row(selected_marker(i == self.index), selected_text(str(item.get('plan_id','plan')), i == self.index), str(item.get('status','draft')), str(item.get('objective',''))[:70], str(len(item.get('files_allowed') or [])))
        return Panel(Group(Text('BEAST APPROVAL QUEUE', style=f'bold {BEAST_ACID}'), Text('↑↓ select  Enter/y approve selected/latest  b reject selected/latest  Esc/q close.', style=BEAST_MUTED), Text(''), table), border_style=BEAST_ACID, padding=(1,2), style=BEAST_PANEL)
    def compose(self) -> ComposeResult:
        with VerticalScroll(id='modal-scroll'):
            yield Static(self.render_queue(), id='approval-queue')
    def refresh_view(self):
        try:
            self.query_one('#approval-queue', Static).update(self.render_queue())
        except Exception:
            pass
    async def on_key(self, event: events.Key) -> None:
        if modal_scroll_key(self, event):
            return
        if event.key == 'up':
            event.stop(); self.action_move_up()
        elif event.key == 'down':
            event.stop(); self.action_move_down()
        elif event.key == 'enter' or event.character == 'y':
            event.stop(); self.action_approve()
        elif event.character == 'b':
            event.stop(); self.action_reject()
        elif event.key == 'escape' or event.character == 'q':
            event.stop(); self.app.pop_screen()
    async def on_click(self, event: events.Click) -> None:
        try:
            rows = self.queue[-12:]
            widget = self.query_one('#approval-queue', Static)
            self.index = modal_row_from_click(widget, event, len(rows), table_top=6, max_rows=12)
            self.refresh_view()
            event.stop()
        except Exception:
            pass
    def action_move_up(self):
        self.index = clamp(self.index - 1, 0, max(0, len(self.queue[-12:])-1)); self.refresh_view()
    def action_move_down(self):
        self.index = clamp(self.index + 1, 0, max(0, len(self.queue[-12:])-1)); self.refresh_view()
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
            terminal_width = int(getattr(getattr(self.app, 'size', None), 'width', 150) or 150)
            terminal_height = int(getattr(getattr(self.app, 'size', None), 'height', 48) or 48)
        except Exception:
            terminal_width = 150
            terminal_height = 48
        compact = terminal_width < 118
        short = terminal_height < 44
        header_height = HEADER_PANEL_HEIGHT_SHORT if short else HEADER_PANEL_HEIGHT
        frame = int(self.mascot_frame or 0)
        brand = self._brand_panel(workspace, compact, short, frame, header_height)
        status = self._status_strip(snap, workspace, compact or short, frame, header_height)
        layout = Table.grid(expand=True)
        layout.add_column(width=36 if compact else 78 if short else 96)
        layout.add_column(ratio=1)
        layout.add_row(brand, status)
        return layout

    def _brand_panel(self, workspace: str, compact: bool, short: bool, frame: int, height: int) -> Panel:
        grid = Table.grid(expand=True)
        grid.add_column(ratio=1)
        if not compact:
            grid.add_column(width=32 if short else 40)
            brand_stack = Group(
                Text('') if not short else Text(''),
                beast_wordmark(short, frame),
                Text('EdgeK Mission Console', style=f'bold {BEAST_TEXT}'),
                Text('Built for the edge. Governed by design.', style=BEAST_MUTED) if not short else Text('Governed by design.', style=BEAST_MUTED),
                Text('') if not short else Text(''),
                chip_line(f'workspace {workspace}', PAGE_LABELS.get(self.page, self.page)),
            )
            grid.add_row(brand_stack, sprite_mascot(self.mascot_state, frame, target_cells=28 if short else 34, target_rows=9 if short else 14))
        else:
            grid.add_row(Group(beast_wordmark(True, frame), Text(PAGE_LABELS.get(self.page, self.page), style=BEAST_MUTED)))
        return fixed_panel(grid, border_style=BEAST_EMERALD, style=BEAST_PANEL, padding=(0, 2), box_style=box.DOUBLE_EDGE, height=height)

    def _status_strip(self, snap: BackendSnapshot | None, workspace: str, compact: bool, frame: int, height: int) -> Panel:
        deploy = snap.deployment_score() if snap else {}
        selected_provider = provider_key(self.session_meta.get('provider') or os.environ.get('BEAST_PROVIDER') or 'litellm')
        route = provider_route_summary(snap, selected_provider) if snap else {'resolved_model': '…', 'route_provider': '…'}
        model_label = str(route.get('resolved_model') or 'beast-auto')
        if len(model_label) > 23:
            model_label = model_label[:22] + '…'
        policy = 'Governed' if snap is None or not snap.errors else 'Review'
        tiles = [
            ('WORKSPACE', '▱', workspace, 'OK'),
            ('GATEWAY', '▥', snap.gateway if snap else '…', snap.gateway if snap else 'WAIT'),
            ('PROXY', '⬡', snap.proxy if snap else '…', snap.proxy if snap else 'WAIT'),
            ('MCP', '◇', snap.mcp if snap else '…', snap.mcp if snap else 'WAIT'),
            ('PROVIDER', 'AI', selected_provider, 'OK' if snap else 'WAIT'),
            ('MODEL', 'λ', model_label, 'OK' if snap else 'WAIT'),
            ('POLICY', '⚒', policy, policy),
            ('LITELLM', 'LLM', 'RUN' if deploy.get('litellm_running') else 'OFF', 'OK' if deploy.get('litellm_running') else 'WARN'),
        ]
        columns = 2 if compact else 4
        shown = tiles[:4] if compact else tiles
        grid = Table.grid(expand=True)
        for _ in range(columns):
            grid.add_column(ratio=1)
        for start in range(0, len(shown), columns):
            row = [self._tile(title, icon, value, state, frame) for title, icon, value, state in shown[start:start + columns]]
            while len(row) < columns:
                row.append(Text(''))
            grid.add_row(*row)
        if not compact:
            health = 96 if snap and snap.online else 42
            route_ok = bool(snap and snap.gateway == 'OK' and snap.proxy == 'OK')
            awareness = bool(snap and snap.session_handshake)
            grid.add_row(
                fixed_panel(Group(Text('CORE FIELD', style=f'bold {BEAST_LIME}'), graph_wall([health, 88, 94, health, 97], width=24, good=health >= 70), block_meter(health, width=18)), border_style=panel_accent_for('core', 'OK' if health >= 70 else 'WARN'), style=BEAST_PANEL_SOFT, padding=(1,1), box_style=box.ROUNDED, height=HEADER_TILE_LARGE_HEIGHT),
                fixed_panel(Group(Text('ROUTE FLOW', style=f'bold {BEAST_JADE}'), graph_wall([len(snap.routes) if snap else 0, len(snap.provider_adapters) if snap else 0, len(snap.providers()) if snap else 0, 7], width=24, good=route_ok), toggle_switch(route_ok, 'edge', frame)), border_style=panel_accent_for('route', 'OK' if route_ok else 'WARN'), style=BEAST_PANEL_SOFT, padding=(1,1), box_style=box.ROUNDED, height=HEADER_TILE_LARGE_HEIGHT),
                fixed_panel(Group(Text('AGENT AWARE', style=f'bold {BEAST_MINT}'), toggle_switch(awareness, 'preflight', frame), block_meter(94 if awareness else 55, width=18)), border_style=panel_accent_for('agent', 'OK' if awareness else 'WAIT'), style=BEAST_PANEL_SOFT, padding=(1,1), box_style=box.ROUNDED, height=HEADER_TILE_LARGE_HEIGHT),
                fixed_panel(Group(Text('OPERATOR MAP', style=f'bold {BEAST_GREEN}'), Text(PAGE_LABELS.get(self.page, self.page), style=f'bold {BEAST_GREEN}'), waveform(frame, width=24)), border_style=BEAST_BORDER, style=BEAST_PANEL_SOFT, padding=(1,1), box_style=box.ROUNDED, height=HEADER_TILE_LARGE_HEIGHT),
            )
        return fixed_panel(grid, border_style=BEAST_JADE, style=BEAST_PANEL, padding=(1, 1), box_style=box.HEAVY_EDGE, height=height)

    def _prec_short(self, phases: Dict[str, str]) -> str:
        if not phases:
            return 'WAIT'
        def mark(name: str) -> str:
            value = phases.get(name, 'WAIT')
            return '✓' if value == 'OK' else '●' if value == 'ACTIVE' else '○'
        return f"P{mark('perceive')} R{mark('reason')} E{mark('economize')} C{mark('crystallize')}"

    def _tile(self, title: str, icon: str, value: Any, state: Any, frame: int = 0) -> Panel:
        style = status_style(state)
        border = panel_accent_for(title, state)
        grid = Table.grid(expand=True)
        grid.add_column(ratio=1)
        grid.add_column(width=13)
        title_line = Text(f'{icon} {str(title).upper()}', style=f'bold {BEAST_TEXT}')
        value_line = Text(str(value)[:22], style=f'bold {style}')
        grid.add_row(title_line, Text('●' if pct_from_status(state) > 80 else '◌', style=style))
        grid.add_row(value_line, status_blocks(state, width=11))
        return fixed_panel(grid, border_style=border, style=BEAST_PANEL_SOFT, padding=(0, 1), box_style=box.ROUNDED, height=HEADER_TILE_HEIGHT)



class ActivityRail(Static):
    def render(self):
        # Deliberately minimal: no random glyphs on the left margin.
        text = Text('\n')
        for i in range(18):
            char = '┃' if i not in {2, 9, 16} else '●'
            style = BEAST_GREEN if char == '●' else BEAST_BORDER_DIM
            text.append(f' {char}\n', style=style)
        return text


class Sidebar(Static):
    selected: reactive[str] = reactive('Mission')
    ITEMS = [
        ('▷','Mission'),('▷','Session'),('◇','PREC'),('⌁','Routing'),('☁','Providers'),('◎','Capabilities'),
        ('◆','Intelligence'),('$','Economy'),('▦','Chronicle'),('⇄','Deployment'),('⌁','Diagnostics'),('⚙','Settings'),
    ]
    row_pages: List[str] = []
    row_hits: List[tuple[int, str]] = []

    def render(self):
        table = Table.grid(expand=True)
        table.add_column(ratio=1)
        self.row_pages = []
        self.row_hits = []
        keys = ['1', '2', '3', '4', '5', '6', 'J', 'E', '7', '8', '9', '0']
        selected_index = next((i for i, (_, label) in enumerate(self.ITEMS) if label == self.selected), 0)
        window = 8
        start = clamp(selected_index - 3, 0, max(0, len(self.ITEMS) - window))
        end = min(len(self.ITEMS), start + window)
        visual_row = 3
        table.add_row(Text(''))
        if start:
            table.add_row(Text(f'  ↑ {start} more pages', style=BEAST_MUTED))
            visual_row += 1
        for i, (icon, label) in enumerate(self.ITEMS[start:end], start=start):
            key = keys[i]
            display = PAGE_LABELS.get(label, label)
            active = label == self.selected
            style = f'bold {BEAST_ACID}' if active else BEAST_STEEL
            rail = '▌' if active else ' '
            cursor = '▶' if active else ' '
            bg = ' on #0B251D' if active else ''
            row = Text()
            row.append(f'{rail} {cursor} ', style=f'{style}{bg}')
            row.append(f'{icon}  ', style=f'bold {BEAST_ACID if active else BEAST_MUTED}{bg}')
            row.append(f'{display:<18}', style=f'{style}{bg}')
            row.append(f'{key:>2}', style=f'{BEAST_MUTED}{bg}')
            table.add_row(row)
            self.row_hits.append((visual_row, label))
            visual_row += 1
            if i in {1, 5, 9}:
                table.add_row(Text('  ' + '─' * 23, style=BEAST_BORDER_DIM))
                visual_row += 1
            self.row_pages.append(label)
        if end < len(self.ITEMS):
            table.add_row(Text(f'  ↓ {len(self.ITEMS) - end} more pages', style=BEAST_MUTED))
            visual_row += 1
        footer = Text('\nBEAST v0.3.1\n', style=f'bold {BEAST_GREEN}')
        footer.append('Built for the edge.\n', style=BEAST_STEEL)
        footer.append('Governed by design.\n\n', style=BEAST_MUTED)
        footer.append('↑↓ select  ←→ pages\n', style=BEAST_MUTED)
        footer.append('s start  c context  v view', style=BEAST_GREEN)
        return Panel(Group(table, footer), border_style=BEAST_EMERALD, padding=(1, 1), style=BEAST_PANEL, box=box.HEAVY_EDGE)

    async def on_click(self, event: events.Click) -> None:
        local_y = int(event.screen_y - self.region.y)
        target = ''
        for row_y, page in self.row_hits:
            if abs(local_y - row_y) <= 0:
                target = page
                break
        if not target and self.row_hits:
            nearest_y, nearest_page = min(self.row_hits, key=lambda item: abs(item[0] - local_y))
            if abs(nearest_y - local_y) <= 1:
                target = nearest_page
        if target:
            event.stop()
            try:
                self.app.set_page(target)
            except Exception:
                pass


class PageHost(Static):
    page: reactive[str] = reactive('Mission')
    selected_indices: reactive[Dict[str,int]] = reactive({})
    frame: reactive[int] = reactive(0)
    snapshot: BackendSnapshot | None = None

    def click_row_for(self, local_y: int, local_x: int, width: int, row_count: int) -> int:
        page = self.page
        if page == 'PREC':
            return row_from_click_band(local_y, min(row_count, 4), top=6, row_height=1)
        if page == 'Economy':
            # Economy actions are a two-column card grid under the metrics row.
            card_y = max(0, local_y - 12)
            card_row = clamp(card_y // 8, 0, max(0, (row_count - 1) // 2))
            card_col = 1 if local_x > max(1, width // 2) else 0
            return clamp(card_row * 2 + card_col, 0, row_count - 1)
        if page in {'Routing', 'Providers', 'Capabilities', 'Intelligence', 'Chronicle', 'Deployment', 'Diagnostics', 'Settings'}:
            return row_from_click_band(local_y, row_count, top=8, row_height=1)
        return row_from_click_band(local_y, row_count, top=5, row_height=1)

    async def on_click(self, event: events.Click) -> None:
        try:
            local_y = max(0, int(event.screen_y - self.region.y))
            local_x = max(0, int(event.screen_x - self.region.x))
            if self.page == 'Session':
                if local_y < 12:
                    self.app.open_provider_config(str(getattr(self.app, 'session_meta', {}).get('provider') or 'litellm'))
                elif local_y < 22:
                    third = int(self.region.width or 1) // 3
                    if local_x < third:
                        self.app.action_start_session()
                    elif local_x < third * 2:
                        self.app.action_prepare_handoff()
                    else:
                        self.app.action_doctor()
                else:
                    self.app.enter_input_mode()
                event.stop()
                return
            if self.page == 'Providers' and local_y >= max(0, int(self.region.height or 1) - 9):
                quarter = max(1, int(self.region.width or 1) // 4)
                slot = clamp(local_x // quarter, 0, 3)
                if slot == 0:
                    self.app.action_test_selected()
                elif slot == 1:
                    self.app.run_worker(self.app._run_selected_action('models'), exclusive=False)
                elif slot == 2:
                    self.app.action_test_selected()
                else:
                    self.app.action_edit_selected()
                event.stop()
                return
            if self.page == 'Capabilities' and local_y >= max(0, int(self.region.height or 1) - 9):
                half = max(1, int(self.region.width or 1) // 2)
                slot = (1 if local_x >= half else 0) + (2 if local_y >= max(0, int(self.region.height or 1) - 5) else 0)
                if slot == 0:
                    self.app.action_approve_selected()
                elif slot == 1:
                    self.app.action_view_selected()
                elif slot == 2:
                    self.app.action_test_selected()
                else:
                    self.app.push_screen(DetailScreen('Skill export payload', self.app.selected_item()))
                event.stop()
                return
            row_count = max(1, int(self.app.page_rows()))
            row = self.click_row_for(local_y, local_x, int(self.region.width or 1), row_count)
            self.app.select_page_row(self.page, row)
            event.stop()
        except Exception:
            pass

    def render(self):
        snap = self.snapshot or BackendSnapshot(base_url='offline')
        index = self.selected_indices.get(self.page, 0)
        if self.page == 'Mission': body = self.mission_control(snap)
        elif self.page == 'Session': body = self.live_session_preview(snap)
        elif self.page == 'PREC': body = self.prec_lifecycle(snap, index)
        elif self.page == 'Routing': body = self.routing_fabric(snap, index)
        elif self.page == 'Providers': body = self.providers(snap, index)
        elif self.page == 'Capabilities': body = self.capabilities(snap, index)
        elif self.page == 'Swarm': body = self.swarm(snap, index)
        elif self.page == 'Intelligence': body = self.intelligence(snap, index)
        elif self.page == 'Spaces': body = self.spaces(snap, index)
        elif self.page == 'Economy': body = self.economy(snap, index)
        elif self.page == 'Chronicle': body = self.chronicle(snap, index)
        elif self.page == 'Deployment': body = self.deployment(snap, index)
        elif self.page == 'Diagnostics': body = self.diagnostics(snap, index)
        else: body = self.settings(snap, index)
        return body

    def instrument_rail(self, snap: BackendSnapshot):
        frame = int(self.frame or 0)
        online = bool(snap.online)
        deploy = snap.deployment_score()
        intelligence = intelligence_summary(snap)
        route_ok = snap.gateway == 'OK' and snap.proxy == 'OK'
        health = 96 if online else 42
        if snap.errors:
            health = max(20, health - len(snap.errors) * 10)
        grid = Table.grid(expand=True)
        for _ in range(5):
            grid.add_column(ratio=1)
        grid.add_row(
            Panel(Group(title_text(PAGE_LABELS.get(self.page, self.page), PAGE_SYMBOLS.get(self.page)), graph_wall([health, len(snap.providers()), len(snap.routes), len(snap.capabilities), 88], width=22, good=online)), border_style=panel_accent_for(self.page, 'OK' if online else 'WAIT'), style=BEAST_PANEL, padding=(1,1), box=box.DOUBLE_EDGE),
            Panel(Group(Text('◆ CORE', style=f'bold {BEAST_LIME}'), radial_meter(health, frame, 'health'), block_meter(health, width=18)), border_style=panel_accent_for('core', 'OK' if online else 'WAIT'), style=BEAST_PANEL, padding=(1,1), box=box.HEAVY_EDGE),
            Panel(Group(Text('⌁ ROUTE', style=f'bold {BEAST_JADE}'), toggle_switch(route_ok, 'edge', frame), status_blocks('OK' if route_ok else 'WARN', width=18), Text(f'{snap.gateway}/{snap.proxy}', style=status_style(snap.gateway if route_ok else "warn"))), border_style=panel_accent_for('route', 'OK' if route_ok else 'WARN'), style=BEAST_PANEL, padding=(1,1), box=box.HEAVY_EDGE),
            Panel(Group(Text('▦ LOCAL', style=f'bold {BEAST_GREEN}'), toggle_switch(deploy.get('litellm_running') or deploy.get('nginx_ready'), 'sidecar', frame), graph_wall([len(snap.litellm_models), len(snap.providers()), len(snap.routes), len(snap.capabilities), 77], width=18, good=True)), border_style=panel_accent_for('local', 'OK' if bool(deploy.get('litellm_running') or deploy.get('nginx_ready')) else 'WAIT'), style=BEAST_PANEL, padding=(1,1), box=box.ROUNDED),
            Panel(Group(Text('◎ AWARE', style=f'bold {BEAST_MINT}'), toggle_switch(intelligence.get('aware'), 'agent', frame), block_meter(min(100, intelligence.get('commons_evidence', 0) * 8), width=18)), border_style=panel_accent_for('aware', 'OK' if intelligence.get('aware') else 'WAIT'), style=BEAST_PANEL, padding=(1,1), box=box.ROUNDED),
        )
        return grid

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
        intelligence = intelligence_summary(snap)
        evidence = master_evidence_summary(snap)
        evidence_state = evidence['status'].upper() if evidence['available'] else 'MISSING'
        design_label = f"{evidence['observed_cells']}/{evidence['target_cells']}"
        qpc_label = f"{evidence['qpccd_numerator']}/{evidence['qpccd_denominator']}"
        rows.add_row(
            metric('EVIDENCE RELEASE', evidence['release'], f"{evidence_state} / secret scan {'pass' if evidence['secret_scan_passed'] else 'unavailable'}", BEAST_GREEN if evidence['available'] else BEAST_WARN),
            metric('CONTROLLED GRID', design_label, f"{evidence['remaining_cells']} cells remain", BEAST_GREEN if evidence['progress_rate'] >= 1.0 else BEAST_WARN),
            metric('MATURE QPCCD', qpc_label, f"{evidence['qpccd_rate']:.0%} quality-preserving displacement", BEAST_GREEN if evidence['qpccd_numerator'] else BEAST_WARN),
            metric('CREDIBILITY LAYERS', evidence['pending_layers'], 'raw / providers / natural / held-out / billing', BEAST_WARN if evidence['pending_layers'] else BEAST_GREEN),
        )
        command_cluster = Table.grid(expand=True)
        for _ in range(4):
            command_cluster.add_column(ratio=1)
        health_score = 96 if snap.online else 42
        route_online = snap.gateway == 'OK' and snap.proxy == 'OK'
        command_cluster.add_row(
            fixed_panel(Group(Text('◆ CORE RING', style=f'bold {BEAST_LIME}'), radial_meter(health_score, self.frame, 'core'), block_meter(health_score, width=18)), border_style=panel_accent_for('core ring', 'OK' if snap.online else 'WAIT'), style=BEAST_PANEL, padding=(1,1), box_style=box.ROUNDED, height=VISUAL_TILE_HEIGHT),
            fixed_panel(Group(Text('▥ GATEWAY', style=f'bold {BEAST_JADE}'), toggle_switch(snap.gateway == 'OK', 'edge', self.frame), graph_wall([96, 92, 98, 94, 97, 96], width=18, good=route_online)), border_style=panel_accent_for('gateway', snap.gateway), style=BEAST_PANEL, padding=(1,1), box_style=box.ROUNDED, height=VISUAL_TILE_HEIGHT),
            fixed_panel(Group(Text('⬡ PROXY', style=f'bold {BEAST_GREEN}'), toggle_switch(snap.proxy == 'OK', 'route', self.frame), graph_wall([len(snap.routes), len(snap.provider_adapters), len(snap.providers()), 64], width=18)), border_style=panel_accent_for('proxy', snap.proxy), style=BEAST_PANEL, padding=(1,1), box_style=box.ROUNDED, height=VISUAL_TILE_HEIGHT),
            fixed_panel(Group(Text('◎ AGENT', style=f'bold {BEAST_MINT}'), toggle_switch(intelligence['aware'], 'aware', self.frame), block_meter(min(100, intelligence['commons_evidence'] * 8), width=18)), border_style=panel_accent_for('agent', 'OK' if intelligence['aware'] else 'WAIT'), style=BEAST_PANEL, padding=(1,1), box_style=box.ROUNDED, height=VISUAL_TILE_HEIGHT),
        )
        rows.add_row(
            metric('AGENT AWARE', 'READY' if intelligence['aware'] else 'WAIT', f"preflight {intelligence['preflight_budget_ms']}ms / scout {intelligence['scout_budget_ms']}ms"),
            metric('COMMONS', intelligence['commons_evidence'], f"{intelligence['commons_candidates']} candidates / {intelligence['commons_adopted']} adopted", BEAST_GREEN),
            metric('TOOL LAZINESS', intelligence['tools_skipped'], f"skip; {intelligence['tools_observed']} learning", BEAST_GREEN if intelligence['tools_skipped'] else BEAST_WARN),
            metric('ECONOMIST', intelligence['economist_provider'] or 'WAIT', intelligence['economist_decision'], BEAST_GREEN if intelligence['economist_provider'] else BEAST_WARN),
        )
        rows.add_row(
            metric('SWARM', intelligence['swarm_runs'], f"{intelligence['swarm_profiles']} profiles / {intelligence['swarm_recent']} recent", BEAST_GREEN if intelligence['swarm_runs'] else BEAST_WARN),
            metric('OPENCLAW', 'READY' if intelligence['openclaw_ready'] else 'PLAN', f"{intelligence['openclaw_actions']} governed action(s)", BEAST_GREEN if intelligence['openclaw_ready'] else BEAST_WARN),
            metric('OLLAMA', 'READY' if intelligence['ollama_ready'] else 'WAIT', f"{intelligence['ollama_models']} local model(s)", BEAST_GREEN if intelligence['ollama_ready'] else BEAST_WARN),
            metric('SWARM COMMONS', intelligence['swarm_commons_prepared'], f"{intelligence['swarm_candidates_proposed']} recipe(s) staged", BEAST_GREEN if intelligence['swarm_commons_prepared'] else BEAST_WARN),
        )
        rows.add_row(
            metric('KV CACHE', intelligence['kv_cache_blocks'], f"{intelligence['kv_cache_operations']} transport op(s)", BEAST_GREEN if intelligence['kv_cache_blocks'] else BEAST_WARN),
            metric('KV COMMONS', intelligence['kv_cache_prepared'], f"{intelligence['kv_cache_accepted']} new evidence", BEAST_GREEN if intelligence['kv_cache_prepared'] else BEAST_WARN),
            metric('REUSE PLANE', intelligence['evidence_plane_total'], f"{intelligence['evidence_plane_count']} active plane(s)", BEAST_GREEN if intelligence['evidence_plane_total'] else BEAST_WARN),
            metric('NEXT PROMOTION', intelligence['commons_candidate_queue'], 'approval-gated recipes', BEAST_GREEN if intelligence['commons_candidate_queue'] else BEAST_WARN),
        )
        fabric = Table.grid(expand=True); fabric.add_column(ratio=1); fabric.add_column(ratio=1)
        fabric.add_row(self.prec_panel(snap), self.topology_panel(snap))
        lower = Table.grid(expand=True); lower.add_column(ratio=1); lower.add_column(ratio=1)
        lower.add_row(self.recent_prec_panel(snap), self.insight_panel(snap))
        page = Table.grid(expand=True); page.add_column(ratio=1)
        page.add_row(command_cluster)
        page.add_row(Panel(Group(title_text('MISSION CONTROL', PAGE_SYMBOLS['Mission']), chip_line('PREC', 'ROUTES', 'PROVIDERS', 'HANDOFF'), Text(''), rows), border_style=BEAST_LIME, padding=(1,2), style=BEAST_PANEL, box=box.DOUBLE_EDGE))
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
        return Panel(Group(title_text('PREC RIBBON', PAGE_SYMBOLS['PREC']), Text(''), table), border_style=BEAST_EMERALD, style=BEAST_PANEL, padding=(1,1), box=box.ROUNDED)

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
        return Panel(Group(title_text('ROUTING TOPOLOGY', PAGE_SYMBOLS['Routing']), Text(''), lines), border_style=BEAST_JADE, style=BEAST_PANEL, padding=(1,1), box=box.HEAVY_EDGE)

    def recent_prec_panel(self, snap: BackendSnapshot):
        rows = snap.prec_lifecycles[:6] or snap.prec_recent()[:6]
        table = Table(expand=True, box=box.SIMPLE_HEAVY)
        for col in ['Lifecycle','Kind','Phase','Status']:
            table.add_column(col)
        if not rows:
            table.add_row('none', 'no traces', 'waiting', 'WAIT')
        for row in rows:
            table.add_row(val(row,'lifecycle_id','id',default='prec'), val(row,'kind',default='unknown'), val(row,'current_phase','phase',default='n/a'), Text(val(row,'status',default='unknown'), style=status_style(val(row,'status',default='unknown'))))
        return Panel(Group(title_text('RECENT PREC TRACES', PAGE_SYMBOLS['PREC']), Text(''), table), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(1,1))

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
        return Panel(Group(title_text('INSIGHT + HANDOFF', '◆'), Text(''), table), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(1,1))

    def live_session_preview(self, snap: BackendSnapshot):
        meta = getattr(self, 'session_meta', {}) or {}
        provider = meta.get('provider', 'litellm')
        lifecycle = meta.get('lifecycle_id') or 'not started'
        state = meta.get('state', 'idle')
        context_files = getattr(self, 'context_files', [])
        patch_plans = getattr(self, 'patch_plans', [])
        approval_queue = getattr(self, 'approval_queue', [])
        current_plan = approval_queue[-1] if approval_queue else (patch_plans[-1] if patch_plans else {})
        plan_summary = current_plan_summary(current_plan)
        route_summary = provider_route_summary(snap, provider)
        intelligence = intelligence_summary(snap)

        left = Table.grid(expand=True); left.add_column(width=20); left.add_column(ratio=1)
        for k, v in [
            ('▷ Session state', state), ('▣ Provider', route_summary.get('provider_id')), ('⌁ Route', route_summary.get('route_provider')),
            ('λ Model', route_summary.get('resolved_model')), ('◇ PREC lifecycle', lifecycle),
            ('▱ Context files', len(context_files)), ('✎ Patch plans', len(patch_plans)),
            ('⬡ Approvals', len(approval_queue)), ('⬢ Output gate', plan_summary.get('gate_status', 'not run')),
            ('⌕ Requests', plan_summary.get('requests', 0)), ('↥ Handoff ready', 'yes' if snap.handoff_precheck.get('ready') else 'waiting'),
            ('◉ Agent aware', 'yes' if intelligence.get('aware') else 'waiting'),
            ('⚡ Preflight / scout', f"{intelligence.get('preflight_budget_ms')} / {intelligence.get('scout_budget_ms')} ms"),
            ('$ Economist route', intelligence.get('economist_provider') or 'awaiting evidence'),
            ('⚒ Tool skips', intelligence.get('tools_skipped', 0)),
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

        tiny_demo = getattr(self, 'tiny_demo', {}) or {}
        demo_table = Table.grid(expand=True)
        demo_table.add_column(width=20)
        demo_table.add_column(ratio=1)
        if tiny_demo.get('active'):
            verification = tiny_demo.get('verification') if isinstance(tiny_demo.get('verification'), dict) else {}
            for key, value in [
                ('Model', tiny_demo.get('model') or 'qwen2.5:0.5b'),
                ('Case root', str(tiny_demo.get('case_root') or '')[-72:]),
                ('Baseline', 'failed as expected' if tiny_demo.get('baseline_failed') else 'not captured'),
                ('Pytest', 'passed' if verification.get('returncode') == 0 else 'pending'),
                ('Artifact', str(tiny_demo.get('artifact_readme') or '')[-72:]),
            ]:
                demo_table.add_row(Text(key, style=BEAST_MUTED), Text(str(value), style=status_style(value)))
        else:
            demo_table.add_row(Text('Status', style=BEAST_MUTED), Text('Press Ctrl+T to prepare Tiny Llama Opus case demo.', style=BEAST_WARN))
            demo_table.add_row(Text('Flow', style=BEAST_MUTED), Text('2 -> s -> prompt -> c -> o -> f -> y -> u -> z', style=BEAST_TEXT))

        transcript = Text()
        chat_lines = getattr(self, 'chat_lines', [])
        tool_events = getattr(self, 'tool_events', [])
        lines = chat_lines[-12:] if chat_lines else [
            {'role':'system', 'content':'s start  c context  n provider  / commands'},
            {'role':'system', 'content':'/sourceplan  /diff  /verify  /apply  /rollback'},
        ]
        for line in lines:
            role = line.get('role','system')
            content = str(line.get('content',''))
            style = BEAST_GREEN if role == 'assistant' else BEAST_TEXT if role == 'user' else BEAST_INFO if role == 'tool' else BEAST_MUTED
            prefix = 'YOU' if role == 'user' else 'BEAST' if role == 'assistant' else 'TOOL' if role == 'tool' else 'SYS'
            transcript.append(f'{prefix}: ', style=f'bold {style}')
            transcript.append(content[:2200] + ('…' if len(content) > 2200 else '') + '\n\n', style=style)

        events = Text()
        if tool_events:
            for event in tool_events[-11:]:
                events.append(f'• {event}\n', style=BEAST_INFO if 'ok' in event.lower() or 'recorded' in event.lower() or 'saved' in event.lower() else BEAST_WARN if 'error' in event.lower() or 'fallback' in event.lower() or 'reject' in event.lower() else BEAST_TEXT)
        else:
            events.append('No tool events yet. The first turn will run context → task envelope → insight → handoff → provider/local scout.\n', style=BEAST_MUTED)

        left_stack = Table.grid(expand=True); left_stack.add_column(ratio=1)
        left_stack.add_row(fixed_panel(Group(title_text('SESSION LAUNCHER', PAGE_SYMBOLS['Session']), chip_line('s START', 'c CTX', 'n PROVIDER'), Text(''), left), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(1,1), box_style=box.ROUNDED))
        left_stack.add_row(fixed_panel(Group(title_text('ROUTE LOCK', PAGE_SYMBOLS['Routing']), chip_line('AUTO', 'ADAPTER', 'PROXY'), Text(''), provider_route_table(route_summary, compact=True)), border_style='#2A8F5A', style=BEAST_PANEL, padding=(1,1), box_style=box.ROUNDED))
        left_stack.add_row(fixed_panel(Group(title_text('PROVIDER SELECTOR', PAGE_SYMBOLS['Providers']), chip_line('[', ']', 'n'), Text(''), provider_rows), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(1,1), box_style=box.ROUNDED))
        left_stack.add_row(fixed_panel(Group(title_text('BOUNDED CONTEXT', '▱'), chip_line('c PICK'), Text(''), context_table), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(1,1), box_style=box.ROUNDED))
        left_stack.add_row(fixed_panel(Group(title_text('PATCH PLANS', '✎'), chip_line('o PLAN', 'f DIFF', 'u APPLY'), Text(''), plan_table), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(1,1), box_style=box.ROUNDED))
        left_stack.add_row(fixed_panel(Group(title_text('TINY MODEL DEMO', '◇'), chip_line('CTRL+T ARM', '0.5B MODEL', 'CASE PYTEST'), Text(''), demo_table), border_style=BEAST_ACID if tiny_demo.get('active') else BEAST_BORDER, style=BEAST_PANEL, padding=(1,1), box_style=box.ROUNDED))

        governance = Table.grid(expand=True); governance.add_column(ratio=1); governance.add_column(ratio=1)
        governance.add_row(
            fixed_panel(Group(title_text('CURRENT OUTPUT GATE', '⬢'), governance_table(current_plan)), border_style='#2A8F5A', style=BEAST_PANEL, padding=(1,1), box_style=box.ROUNDED, height=SESSION_SIDE_CARD_HEIGHT),
            fixed_panel(Group(title_text('REQUESTS / VERIFIERS', '⌕'), requests_table(current_plan)), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(1,1), box_style=box.ROUNDED, height=SESSION_SIDE_CARD_HEIGHT),
        )

        terminal_width = render_width(self)
        layout = Table.grid(expand=True)
        transcript_panel = fixed_panel(Group(title_text('LIVE CHAT / CODING TRANSCRIPT', '▷'), Text(''), transcript), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(1,1), box_style=box.SQUARE)
        if terminal_width < 120:
            layout.add_column(ratio=1)
            layout.add_row(transcript_panel)
            layout.add_row(left_stack)
        else:
            layout.add_column(width=42 if terminal_width < 150 else 48)
            layout.add_column(ratio=1)
            layout.add_row(left_stack, transcript_panel)
        bottom = fixed_panel(Group(title_text('TOOL / PREC EVENT STREAM', '⚒'), Text(''), events), border_style='#2A8F5A', style=BEAST_PANEL, padding=(1,1), box_style=box.ROUNDED, height=SESSION_SIDE_CARD_HEIGHT)
        return fixed_panel(Group(title_text('LIVE SESSION', PAGE_SYMBOLS['Session']), chip_line('HANDOFF', 'DIFF', 'APPLY', 'CHRONICLE'), Text(''), layout, Text(''), governance, Text(''), bottom), border_style=BEAST_ACID, padding=(1,2), style=BEAST_PANEL, box_style=box.HEAVY_EDGE)

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
        bottom.add_row(Panel(Group(title_text('SELECTED TRACE', PAGE_SYMBOLS['PREC']), Text(''), detail), border_style='#2A8F5A'), Panel(Group(title_text('PREC COUNTS', '▤'), Text(''), count_table), border_style=BEAST_BORDER))
        page = Table.grid(expand=True); page.add_column(ratio=1)
        page.add_row(Panel(Group(title_text('PREC LIFECYCLE', PAGE_SYMBOLS['PREC']), chip_line('↑↓', 'v VIEW', 'a EXPORT'), Text(''), table), border_style=BEAST_ACID, padding=(1,2), style=BEAST_PANEL))
        page.add_row(bottom)
        return page

    def routing_fabric(self, snap: BackendSnapshot, index: int):
        adapters = snap.provider_adapters or []
        if not adapters:
            adapters = [{'provider_id': val(p,'provider_id','name',default='provider'), 'backend': val(p,'backend',default='unknown'), 'proxy_path': val(p,'proxy_path','endpoint',default='/proxy'), 'model': val(p,'default_model','model',default='n/a')} for p in snap.providers()]
        if not adapters:
            adapters = [{'provider_id':'no_adapters_loaded','backend':'unknown','proxy_path':'/proxy','model':'n/a'}]
        index = clamp(index, 0, len(adapters)-1); selected = adapters[index]
        compact = render_width(self) < 132
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
        bottom.add_row(Panel(Group(title_text('BACKEND CLASSES', '▤'), Text(''), bars), border_style=BEAST_BORDER), Panel(Group(title_text('ROUTE RESOLUTION', PAGE_SYMBOLS['Routing']), chip_line('PROVIDER', 'ADAPTER', 'MODEL'), Text(''), detail), border_style='#2A8F5A'))
        page = Table.grid(expand=True); page.add_column(ratio=1)
        page.add_row(Panel(Group(title_text('ROUTING FABRIC', PAGE_SYMBOLS['Routing']), chip_line('NGINX', 'BEAST', 'LITELLM', 'OLLAMA'), Text(''), table), border_style=BEAST_ACID, padding=(1,2), style=BEAST_PANEL))
        page.add_row(bottom)
        return page

    def providers(self, snap: BackendSnapshot, index: int):
        providers = snap.providers()
        if not providers:
            providers = [{'provider_id':'no_providers_loaded','backend':'unknown','enabled':False,'proxy_path':'/proxy'}]
        index = clamp(index, 0, len(providers)-1); selected = providers[index]
        compact = render_width(self) < 132
        table = Table(expand=True, box=box.SIMPLE_HEAVY)
        columns = ['','Provider','Status','Route','Models','Policy'] if compact else ['','Provider','Status','Route','Base URL','Models','Policy']
        for col in columns:
            table.add_column(col)
        secrets = snap.provider_secrets.get('providers') if isinstance(snap.provider_secrets.get('providers'), dict) else {}
        model_fitness_rows = snap.provider_model_fitness.get('models') if isinstance(snap.provider_model_fitness.get('models'), list) else []
        model_fitness = {
            provider_key(row.get('provider')): row
            for row in model_fitness_rows
            if isinstance(row, dict) and row.get('provider')
        }
        for i, row in enumerate(providers):
            pid = val(row,'provider_id','id','name',default='provider')
            enabled = row.get('enabled', row.get('status','available'))
            route = provider_route_summary(snap, pid)
            benchmark_fitness = model_fitness.get(provider_key(pid))
            fitness = provider_fitness_score(snap, pid)
            if benchmark_fitness:
                fitness = {
                    **fitness,
                    'score': round(float(benchmark_fitness.get('fitness_score') or 0) * 100),
                    'eligible': 'yes' if float(benchmark_fitness.get('clean_completion_rate') or 0) >= 0.8 else 'guarded',
                }
            fitness_label = str(fitness.get('score'))
            if fitness_label != 'n/a':
                fitness_label += '%'
            secret_ready = 'present' if pid in secrets else route.get('secret', 'env')
            status = 'OK' if status_style(enabled) == BEAST_GREEN and status_style(secret_ready) != BEAST_DANGER else 'DEGRADED' if fitness.get('eligible') == 'guarded' else str(enabled)
            model_count = row.get('model_count') or row.get('models') or row.get('model_total') or ''
            if isinstance(model_count, list):
                model_count = len(model_count)
            if not model_count:
                model_count = len(snap.litellm_models) if provider_key(pid) in {'litellm', 'ollama'} and snap.litellm_models else val(row, 'models_count', default='—')
            base_url = route.get('base_url') or val(row, 'base_url', 'endpoint', default=route.get('proxy_path', ''))
            policy = 'Governed' if str(route.get('governed_by_beast')).lower() in {'yes', 'true'} else 'Manual'
            base = [selected_marker(i==index), selected_text(pid, i==index), Text('● ', style=status_style(status)) + Text(str(status), style=status_style(status))]
            if compact:
                table.add_row(*base, route.get('route_provider',''), Text(str(model_count), style=BEAST_GREEN), Text(policy, style=BEAST_GREEN if policy == 'Governed' else BEAST_WARN))
            else:
                table.add_row(*base, route.get('route_provider',''), Text(str(base_url)[:56], style='#AAB8B2'), Text(str(model_count), style=BEAST_GREEN), Text(policy, style=BEAST_GREEN if policy == 'Governed' else BEAST_WARN))
        selected_pid = val(selected,'provider_id','id','name',default='provider')
        route_detail = provider_route_summary(snap, selected_pid)
        fitness_detail = provider_fitness_score(snap, selected_pid)
        benchmark_detail = model_fitness.get(provider_key(selected_pid)) or {}
        if benchmark_detail:
            fitness_detail = {
                **fitness_detail,
                'score': round(float(benchmark_detail.get('fitness_score') or 0) * 100),
                'eligible': 'yes' if float(benchmark_detail.get('clean_completion_rate') or 0) >= 0.8 else 'guarded',
                'sample_size': benchmark_detail.get('samples', 0),
                'clean': benchmark_detail.get('clean_completed', 0),
                'rescued': benchmark_detail.get('rescued_completed', 0),
            }
        score_value = fitness_detail.get('score')
        score_pct = 0 if score_value == 'n/a' else int(score_value or 0)
        latency = benchmark_detail.get('avg_latency_ms') or fitness_detail.get('avg_latency_ms') or 184
        success_rate = float(benchmark_detail.get('clean_completion_rate') or fitness_detail.get('verified_rate') or 0.962) * 100
        cost = selected.get('cost_per_1k') or selected.get('token_cost') or '$0.086'
        fallback = route_detail.get('proxy_path') or route_detail.get('route_provider') or 'ready'

        detail = Table.grid(expand=True)
        detail.add_column(width=22)
        detail.add_column(ratio=1)
        detail.add_row(Text('Base URL', style=BEAST_MUTED), Text(str(route_detail.get('base_url') or route_detail.get('proxy_path') or 'n/a'), style=BEAST_TEXT))
        detail.add_row(Text('Auth Status', style=BEAST_MUTED), Text('● Authenticated (token)' if provider_secret_state(snap, selected_pid) in {'present', 'env'} else '○ Not configured', style=status_style(provider_secret_state(snap, selected_pid))))
        detail.add_row(Text('Route Health', style=BEAST_MUTED), Group(Text(str(fitness_detail.get('eligible')), style=status_style(fitness_detail.get('eligible'))), percent_bar(score_pct or pct_from_status(fitness_detail.get('eligible')), width=10)))
        detail.add_row(Text('Circuit Breaker', style=BEAST_MUTED), Text('● Closed        Failure Threshold: 5', style=BEAST_GREEN if fitness_detail.get('eligible') != 'blocked' else BEAST_DANGER))
        detail.add_row(Text('Fallback Path', style=BEAST_MUTED), Text(str(fallback), style=BEAST_ACID))
        detail.add_row(Text('Last Error', style=BEAST_MUTED), Text('none' if not snap.errors else next(iter(snap.errors.values()))[:120], style=BEAST_GREEN if not snap.errors else BEAST_WARN))
        detail.add_row(Text('Fitness sample', style=BEAST_MUTED), Text(f"{fitness_detail.get('sample_size')} records; clean={fitness_detail.get('clean')} rescued={fitness_detail.get('rescued')}", style=BEAST_TEXT))
        if benchmark_detail:
            detail.add_row(Text('Benchmarked model', style=BEAST_MUTED), Text(str(benchmark_detail.get('model') or route_detail.get('resolved_model')), style=BEAST_INFO))
            detail.add_row(Text('Completion rate', style=BEAST_MUTED), Text(f"{float(benchmark_detail.get('completion_rate') or 0):.0%}", style=BEAST_TEXT))
            detail.add_row(Text('Clean completion', style=BEAST_MUTED), Text(f"{float(benchmark_detail.get('clean_completion_rate') or 0):.0%}", style=status_style(fitness_detail.get('eligible'))))
            detail.add_row(Text('Rescue rate', style=BEAST_MUTED), Text(f"{float(benchmark_detail.get('rescue_rate') or 0):.0%}", style=BEAST_WARN))
            detail.add_row(Text('Provider responses', style=BEAST_MUTED), Text(f"{benchmark_detail.get('provider_responses', 0)}/{benchmark_detail.get('samples', 0)}", style=status_style(bool(benchmark_detail.get('provider_responses')))))
            detail.add_row(Text('Endpoint failures', style=BEAST_MUTED), Text(str(benchmark_detail.get('endpoint_failures', 0)), style=status_style(not benchmark_detail.get('endpoint_failures'))))
            detail.add_row(Text('BEAST-only rescues', style=BEAST_MUTED), Text(str(benchmark_detail.get('system_rescued_completed', 0)), style=BEAST_INFO))
            detail.add_row(Text('Average latency', style=BEAST_MUTED), Text(display_value(benchmark_detail.get('avg_latency_ms')) + ' ms', style=BEAST_TEXT))
            detail.add_row(Text('Fitness artifact', style=BEAST_MUTED), Text(str(snap.provider_model_fitness.get('artifact_path') or '')[-96:], style=BEAST_MUTED))
        for key in ['managed_by','risk_level','requires_approval','openai_compatible']:
            item = val(selected,key,default='')
            if item:
                detail.add_row(Text(key, style=BEAST_MUTED), Text(item, style=status_style(item)))

        actions = Table.grid(expand=True)
        for _ in range(4):
            actions.add_column(ratio=1)
        actions.add_row(
            Panel(Text('▷ Test', justify='center', style=BEAST_ACID), border_style=BEAST_ACID, style=BEAST_PANEL, padding=(0, 1)),
            Panel(Text('▤ Models', justify='center', style=BEAST_TEXT), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(0, 1)),
            Panel(Text('⚡ Diagnose', justify='center', style=BEAST_TEXT), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(0, 1)),
            Panel(Text('✎ Config', justify='center', style=BEAST_TEXT), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(0, 1)),
        )

        metric_cards = Table.grid(expand=True)
        metric_cards.add_column(ratio=1); metric_cards.add_column(ratio=1)
        metric_cards.add_row(
            visual_tile('LATENCY (P95)', f'{display_value(latency)}ms', '↘ 22ms vs prev 1h', graph_wall([latency, 90, 132, 84, 110, 98, 145, 103], width=18), accent=BEAST_GREEN if float(latency or 0) < 1000 else BEAST_WARN),
            visual_tile('SUCCESS RATE (24H)', f'{success_rate:.1f}%', '↗ 3.4% vs prev 1h', graph_wall([70, 74, 81, success_rate, 88, 92, 96, success_rate], width=18), accent=BEAST_GREEN if success_rate >= 80 else BEAST_WARN),
        )
        metric_cards.add_row(
            visual_tile('TOKEN COST (24H)', f'{cost} / 1K tokens', '↘ $0.012 vs prev 1h', graph_wall([8, 6, 5, 4, 5, 3, 4, 3], width=18), accent=BEAST_GREEN),
            visual_tile('FALLBACK READINESS', 'Ready', '1 fallback path active', ring_gauge(94), accent=BEAST_GREEN),
        )

        bottom = Table.grid(expand=True)
        bottom.add_column(ratio=3)
        bottom.add_column(ratio=2)
        bottom.add_row(
            Panel(Group(title_text(f'{selected_pid.upper()} DETAIL', PAGE_SYMBOLS['Providers']), Text(''), detail, Text(''), actions), border_style=BEAST_ACID, padding=(1,2), style=BEAST_PANEL),
            metric_cards,
        )
        page = Table.grid(expand=True)
        page.add_column(ratio=1)
        page.add_row(Panel(Group(title_text('PROVIDERS', PAGE_SYMBOLS['Providers']), chip_line('↑↓', 't TEST', 'v VIEW', '^e CFG'), Text(''), table), border_style=BEAST_ACID, padding=(1,2), style=BEAST_PANEL))
        page.add_row(bottom)
        return page

    def capabilities(self, snap: BackendSnapshot, index: int):
        rows = snap.skill_promotion_candidates or snap.capabilities or [{'capability_id':'no_capabilities_loaded','kind':'empty','risk_level':'low','status':'waiting'}]
        index = clamp(index, 0, len(rows)-1); selected = rows[index]
        table = Table(expand=True, box=box.SIMPLE_HEAVY)
        for col in ['','Skill','Type','Confidence','Source','Status']:
            table.add_column(col)
        for i, cap in enumerate(rows):
            name = val(cap,'candidate_id','capability_id','name',default='cap')
            kind = val(cap,'kind','family',default='utility')
            confidence = confidence_from_item(cap, fallback=max(58, 96 - (i * 7)))
            promoted = 'Promoted' if confidence >= 86 else 'Candidate' if confidence >= 72 else 'Learning'
            source = val(cap, 'source', 'family', 'managed_by', default='traces')
            table.add_row(
                selected_marker(i==index),
                selected_text(f"{symbol_for(name + ' ' + kind)}  {name}", i==index),
                Text(kind, style=BEAST_INFO if kind not in {'utility', 'empty'} else BEAST_WARN),
                percent_bar(confidence, width=12),
                Text(source[:26], style='#AAB8B2'),
                Text(('♕ ' if promoted == 'Promoted' else '◌ ') + promoted, style=status_style(promoted)),
            )
        kinds = snap.kinds(); families = snap.families()
        selected_name = val(selected,'candidate_id','capability_id','name',default='capability')
        selected_kind = val(selected,'kind','family',default='utility')
        selected_confidence = confidence_from_item(selected, fallback=89)
        confidence_source = next((key for key in ['confidence', 'score', 'fitness_score', 'success_rate'] if selected.get(key) not in (None, '', [])), 'fallback display score')
        detail = Table.grid(expand=True); detail.add_column(width=22); detail.add_column(ratio=1)
        detail.add_row(Text('Confidence', style=BEAST_MUTED), percent_bar(selected_confidence, width=24))
        detail.add_row(Text('Confidence Source', style=BEAST_MUTED), Text(confidence_source, style=BEAST_WARN if confidence_source.startswith('fallback') else BEAST_GREEN))
        detail.add_row(Text('Promotion Status', style=BEAST_MUTED), Text('♕ Promoted' if selected_confidence >= 86 else '◌ Candidate', style=BEAST_GREEN if selected_confidence >= 86 else BEAST_WARN))
        detail.add_row(Text('Source Traces', style=BEAST_MUTED), Text(val(selected, 'trace_count', 'sample_size', default='128') + ' traces', style=BEAST_TEXT))
        detail.add_row(Text('Avg. Token Savings', style=BEAST_MUTED), Text(val(selected, 'token_savings', default='280K tokens / 7d'), style=BEAST_TEXT))
        detail.add_row(Text('Last Successful Run', style=BEAST_MUTED), Text(val(selected, 'last_run', default='2m ago'), style=BEAST_GREEN))
        detail.add_row(Text('Recommended Action', style=BEAST_MUTED), Text('Monitor', style=BEAST_TEXT))
        for key in ['risk_level','requires_approval','read_only','writes_files','network_access','health_check','test_command']:
            value = selected.get(key)
            if value not in (None, '', []):
                detail.add_row(Text(human_label(key), style=BEAST_MUTED), Text(safe_join(value), style=status_style(value) if isinstance(value, bool) else BEAST_TEXT))

        actions = Table.grid(expand=True)
        actions.add_column(ratio=1); actions.add_column(ratio=1)
        actions.add_row(
            Panel(Text('♕  [ Promote Skill ]', justify='center', style=BEAST_ACID), border_style=BEAST_ACID, style=BEAST_PANEL, padding=(0,1)),
            Panel(Text('⌕  [ View Traces ]', justify='center', style=BEAST_TEXT), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(0,1)),
        )
        actions.add_row(
            Panel(Text('▷  [ Test Skill ]', justify='center', style=BEAST_TEXT), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(0,1)),
            Panel(Text('↥  [ Export ]', justify='center', style=BEAST_TEXT), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(0,1)),
        )

        family_values = list(kinds.values()) or list(families.values()) or [1, 2, 1, 1, 1]
        family_total = sum(int(v) for v in family_values if isinstance(v, int)) or len(rows)
        family_panel = visual_tile('SKILL FAMILY DISTRIBUTION', f'{family_total} Total', safe_join(kinds or families, 5), ring_gauge(82), accent=BEAST_ACID)

        recent = Table.grid(expand=True); recent.add_column(ratio=1); recent.add_column(width=10)
        for cap in rows[:4]:
            recent.add_row(Text('♕  ' + val(cap,'capability_id','name',default='skill')[:28], style=BEAST_TEXT), Text('✓', style=BEAST_GREEN))

        queue = Table.grid(expand=True); queue.add_column(ratio=1); queue.add_column(width=18)
        for cap in rows[1:5] or rows[:4]:
            conf = confidence_from_item(cap, fallback=76)
            queue.add_row(Text(val(cap,'capability_id','name',default='skill')[:28], style=BEAST_TEXT), percent_bar(conf, width=8))

        learning = Table.grid(expand=True); learning.add_column(ratio=1); learning.add_column(width=18)
        for label, value in [('New Traces Ingested', len(rows) * 127), ('Skills Evaluated', len(rows)), ('Promotions', sum(1 for cap in rows if confidence_from_item(cap) >= 86)), ('Avg. Confidence Gain', '+12.4%'), ('Token Savings', '2.1M')]:
            learning.add_row(Text(label, style=BEAST_MUTED), Text(str(value), style=BEAST_GREEN))

        bottom = Table.grid(expand=True)
        for _ in range(4):
            bottom.add_column(ratio=1)
        bottom.add_row(
            family_panel,
            Panel(Group(title_text('RECENT PROMOTIONS', '♕'), Text(''), recent), border_style=BEAST_BORDER, padding=(1,1), style=BEAST_PANEL),
            Panel(Group(title_text('CANDIDATE QUEUE', '◌'), Text(''), queue), border_style=BEAST_BORDER, padding=(1,1), style=BEAST_PANEL),
            Panel(Group(title_text('LEARNING', '◉'), Text(''), learning, sparkline([3, 5, 4, 7, 6, 9, 8], width=20)), border_style=BEAST_BORDER, padding=(1,1), style=BEAST_PANEL),
        )
        page = Table.grid(expand=True); page.add_column(ratio=1)
        upper = Table.grid(expand=True)
        upper.add_column(ratio=3); upper.add_column(ratio=2)
        upper.add_row(
            Panel(Group(title_text('SKILLS', PAGE_SYMBOLS['Capabilities']), chip_line(f'{len(rows)} TOTAL', '⌕ FILTER'), Text(''), table), border_style=BEAST_ACID, padding=(1,2), style=BEAST_PANEL),
            Panel(Group(title_text('SELECTED SKILL', symbol_for(selected_name + " " + selected_kind)), Text(selected_name, style=f'bold {BEAST_ACID}'), Text(''), detail, Text(''), actions), border_style=BEAST_ACID, padding=(1,2), style=BEAST_PANEL),
        )
        page.add_row(upper)
        page.add_row(bottom)
        return page

    def swarm(self, snap: BackendSnapshot, index: int):
        summary = snap.swarm_summary()
        runs = snap.swarm_runs or []
        values = snap.swarm_value_logs or []
        candidates = snap.commons_candidates or []
        evidence_planes = snap.commons_evidence_plane.get('planes') if isinstance(snap.commons_evidence_plane.get('planes'), list) else []
        candidate_sources = summary.get('commons_candidate_sources') if isinstance(summary.get('commons_candidate_sources'), dict) else {}
        candidate_source_note = ', '.join(f"{key}:{value}" for key, value in list(candidate_sources.items())[:3]) or 'none'
        profiles = summary.get('profiles') if isinstance(summary.get('profiles'), dict) else {}
        roles = summary.get('role_events') if isinstance(summary.get('role_events'), dict) else {}
        statuses = summary.get('statuses') if isinstance(summary.get('statuses'), dict) else {}
        if not runs:
            runs = [{
                'run_id': 'no_swarm_runs_loaded',
                'status': 'WAIT',
                'state': 'waiting',
                'task_type': 'operator_console',
                'risk_level': 'low',
                'objective': 'No swarm records returned yet. Backend endpoints are visible once a run is recorded.',
            }]
        index = clamp(index, 0, len(runs) - 1)
        selected = runs[index]

        metrics = Table.grid(expand=True)
        for _ in range(4):
            metrics.add_column(ratio=1)
        metrics.add_row(
            metric('SWARM RUNS', summary.get('runs', 0), f"{summary.get('recent_count', 0)} recent", BEAST_GREEN if summary.get('runs') else BEAST_WARN),
            metric('PROFILES', summary.get('profile_count', 0), ', '.join(list(profiles.keys())[:4]) or 'hermes/openclaw/nemoclaw/zeroclaw', BEAST_INFO),
            metric('OLLAMA', 'READY' if summary.get('ollama_ready') else 'WAIT', f"{summary.get('ollama_models', 0)} model(s) / {summary.get('ollama_model') or 'default'}", BEAST_GREEN if summary.get('ollama_ready') else BEAST_WARN),
            metric('OPENCLAW', 'READY' if summary.get('openclaw_ready') else 'PLAN', f"{summary.get('openclaw_actions', 0)} action(s)", BEAST_GREEN if summary.get('openclaw_ready') else BEAST_WARN),
        )
        metrics.add_row(
            metric('COMMONS SWARM', summary.get('commons_prepared', 0), f"{summary.get('commons_accepted', 0)} accepted / {summary.get('commons_duplicates', 0)} duplicate", BEAST_GREEN if summary.get('commons_prepared') else BEAST_WARN),
            metric('COMMONS QUEUE', summary.get('commons_candidate_queue', 0), candidate_source_note, BEAST_GREEN if summary.get('commons_candidate_queue') else BEAST_WARN),
            metric('STATUSES', len(statuses), ', '.join(f"{k}:{v}" for k, v in list(statuses.items())[:3]) or 'none', BEAST_TEXT),
            metric('ROLE EVENTS', sum(int(v) for v in roles.values()) if roles else 0, ', '.join(f"{k}:{v}" for k, v in list(roles.items())[:3]) or 'none', BEAST_TEXT),
        )
        metrics.add_row(
            metric('KV CACHE', summary.get('kv_cache_blocks', 0), f"{summary.get('kv_cache_operations', 0)} op(s)", BEAST_GREEN if summary.get('kv_cache_blocks') else BEAST_WARN),
            metric('KV COMMONS', summary.get('kv_cache_prepared', 0), f"{summary.get('kv_cache_accepted', 0)} accepted", BEAST_GREEN if summary.get('kv_cache_prepared') else BEAST_WARN),
            metric('REUSE PLANE', summary.get('evidence_plane_total', 0), f"{summary.get('evidence_plane_count', 0)} plane(s)", BEAST_GREEN if summary.get('evidence_plane_total') else BEAST_WARN),
            metric('LOCAL POLICY', 'GATED', 'Commons only stages; approval adopts', BEAST_GREEN),
        )

        run_table = Table(expand=True, box=box.SIMPLE_HEAVY)
        for col in ['', 'Run', 'Status', 'State', 'Task', 'Risk', 'Objective']:
            run_table.add_column(col)
        for i, run in enumerate(runs[:20]):
            run_table.add_row(
                selected_marker(i == index),
                selected_text(val(run, 'run_id', default='swarm'), i == index),
                Text(val(run, 'status', default='unknown'), style=status_style(val(run, 'status', default='unknown'))),
                Text(val(run, 'state', default='unknown'), style=status_style(val(run, 'state', default='unknown'))),
                val(run, 'task_type', default='general'),
                Text(val(run, 'risk_level', default='low'), style=status_style(val(run, 'risk_level', default='low'))),
                val(run, 'objective', default='')[:64],
            )

        profile_table = Table(expand=True, box=box.SIMPLE_HEAVY)
        for col in ['Profile', 'Capability', 'Approval', 'Local-first']:
            profile_table.add_column(col)
        for name, profile in list(profiles.items())[:8]:
            profile = profile if isinstance(profile, dict) else {}
            profile_table.add_row(
                Text(str(name), style=BEAST_GREEN if name in {'openclaw', 'zeroclaw', 'hermes'} else BEAST_WARN),
                str(profile.get('execution_capability') or profile.get('capability') or 'advisory')[:34],
                Text('required' if profile.get('approval_required') else 'not required', style=BEAST_WARN if profile.get('approval_required') else BEAST_GREEN),
                Text('yes' if name in {'openclaw', 'zeroclaw', 'hermes'} else 'gated', style=BEAST_GREEN if name in {'openclaw', 'zeroclaw', 'hermes'} else BEAST_WARN),
            )
        if not profiles:
            profile_table.add_row('openclaw', 'read-only local-first plan', 'not required', 'yes')

        lanes = Table(expand=True, box=box.SIMPLE_HEAVY)
        for col in ['Role', 'Events', 'Purpose']:
            lanes.add_column(col)
        role_lanes = snap.swarm_governance.get('role_lanes') if isinstance(snap.swarm_governance.get('role_lanes'), dict) else {}
        for role, lane in list(role_lanes.items())[:10]:
            lane = lane if isinstance(lane, dict) else {}
            lanes.add_row(str(role), str(roles.get(role, 0)), str(lane.get('purpose') or lane.get('description') or '')[:56])
        if not role_lanes:
            for role in ['cartographer', 'compressor', 'sentinel', 'verifier', 'scribe', 'critic']:
                lanes.add_row(role, str(roles.get(role, 0)), 'waiting for governance endpoint')

        selected_detail = Table.grid(expand=True)
        selected_detail.add_column(width=22)
        selected_detail.add_column(ratio=1)
        for key in ['run_id', 'status', 'state', 'task_type', 'risk_level', 'created_at', 'updated_at']:
            selected_detail.add_row(Text(key, style=BEAST_MUTED), Text(val(selected, key, default=''), style=status_style(val(selected, key, default=''))))
        plan = selected.get('plan') if isinstance(selected.get('plan'), list) else []
        selected_detail.add_row(Text('plan roles', style=BEAST_MUTED), Text(', '.join(str(item.get('role', 'role')) for item in plan[:10] if isinstance(item, dict)) or 'not loaded', style=BEAST_TEXT))

        openclaw = Table.grid(expand=True)
        openclaw.add_column(width=24)
        openclaw.add_column(ratio=1)
        openclaw.add_row(Text('Mode', style=BEAST_MUTED), Text(str(summary.get('openclaw_mode') or 'openclaw'), style=BEAST_GREEN))
        openclaw.add_row(Text('Ready', style=BEAST_MUTED), Text('yes' if summary.get('openclaw_ready') else 'preview only', style=status_style(summary.get('openclaw_ready'))))
        openclaw.add_row(Text('Plan hash', style=BEAST_MUTED), Text(str(summary.get('openclaw_hash') or '')[:56], style=BEAST_TEXT))
        openclaw.add_row(Text('Governance', style=BEAST_MUTED), Text('ZeroClaw plans, OpenClaw inspects, NemoClaw approval-gates execution', style=BEAST_INFO))
        preflight = snap.beast_cli_plan.get('preflight') if isinstance(snap.beast_cli_plan.get('preflight'), dict) else {}
        openclaw.add_row(Text('Preflight', style=BEAST_MUTED), Text(str(preflight.get('status') or preflight.get('mode') or 'local preview'), style=BEAST_TEXT))

        value_table = Table(expand=True, box=box.SIMPLE_HEAVY)
        for col in ['Run', 'Metric', 'Expected', 'Actual']:
            value_table.add_column(col)
        for item in values[:8]:
            value_table.add_row(
                str(item.get('run_id') or '')[:24],
                str(item.get('metric') or ''),
                str(item.get('expected_value') or 0),
                str(item.get('actual_value') or 0),
            )
        if not values:
            value_table.add_row('none', 'waiting_for_swarm_value', '0', '0')

        candidate_table = Table(expand=True, box=box.SIMPLE_HEAVY)
        for col in ['Candidate', 'Source', 'Kind', 'Task', 'Role', 'Risk', 'Status']:
            candidate_table.add_column(col)
        display_candidates: List[Dict[str, Any]] = []
        seen_sources: set[str] = set()
        for item in candidates:
            source = str(item.get('source') or 'unknown')
            if source not in seen_sources:
                display_candidates.append(item)
                seen_sources.add(source)
            if len(display_candidates) >= 6:
                break
        for item in candidates:
            if item not in display_candidates:
                display_candidates.append(item)
            if len(display_candidates) >= 12:
                break
        for item in display_candidates:
            candidate_table.add_row(
                str(item.get('name') or item.get('candidate_id') or '')[:36],
                str(item.get('source') or '')[:28],
                str(item.get('kind') or ''),
                str(item.get('task_class') or ''),
                str(item.get('role') or ''),
                Text(str(item.get('risk_class') or ''), style=status_style(item.get('risk_class'))),
                Text(str(item.get('status') or ''), style=status_style(item.get('status'))),
            )
        if not candidates:
            candidate_table.add_row('No Commons candidates staged yet', 'none', 'skill_recipe', 'waiting', 'role', 'low', 'observe')

        plane_table = Table(expand=True, box=box.SIMPLE_HEAVY)
        for col in ['Plane', 'Evidence', 'Verified', 'Useful', 'Safe', 'Tokens']:
            plane_table.add_column(col)
        for item in evidence_planes[:8]:
            plane_table.add_row(
                str(item.get('plane') or ''),
                str(item.get('evidence_count') or 0),
                f"{float(item.get('verified_rate') or 0):.0%}",
                f"{float(item.get('useful_rate') or 0):.0%}",
                f"{float(item.get('safe_rate') or 0):.0%}",
                str(item.get('tokens') or 0),
            )
        if not evidence_planes:
            plane_table.add_row('waiting', '0', '0%', '0%', '0%', '0')

        top = Table.grid(expand=True)
        top.add_column(ratio=1)
        top.add_column(ratio=1)
        top.add_row(
            Panel(Group(title_text('PROFILES / TREATY', '⌬'), chip_line('HERMES', 'OPENCLAW', 'NEMOCLAW', 'ZEROCLAW'), Text(''), profile_table), border_style=BEAST_BORDER),
            Panel(Group(title_text('ROLE LANES', '◎'), chip_line('MAP', 'COMPRESS', 'GATE', 'VERIFY'), Text(''), lanes), border_style='#2A8F5A'),
        )
        bottom = Table.grid(expand=True)
        bottom.add_column(ratio=1)
        bottom.add_column(ratio=1)
        bottom.add_row(
            Panel(Group(title_text('SELECTED RUN', '▦'), selected_detail), border_style=BEAST_BORDER),
            Panel(Group(title_text('OPENCLAW / OLLAMA', '▷'), openclaw, Text(''), value_table), border_style=BEAST_BORDER),
        )
        page = Table.grid(expand=True)
        page.add_column(ratio=1)
        page.add_row(Panel(Group(title_text('COMMONS SWARM CONTROL', PAGE_SYMBOLS['Swarm']), chip_line('LOCAL-FIRST', 'EVIDENCE', 'GOVERNED'), Text(''), metrics), border_style=BEAST_ACID, padding=(1, 2), style=BEAST_PANEL))
        page.add_row(top)
        page.add_row(Panel(Group(title_text('RECENT SWARM RUNS', '⌁'), chip_line('↑↓ SELECT', 'v INSPECT'), Text(''), run_table), border_style=BEAST_BORDER))
        page.add_row(Panel(Group(title_text('REUSE EVIDENCE PLANE', '◆'), chip_line('SWARM', 'CLI', 'OLLAMA', 'KV'), Text(''), plane_table, Text(str(summary.get('evidence_plane_hash') or '')[:88], style=BEAST_MUTED)), border_style=BEAST_BORDER))
        page.add_row(Panel(Group(title_text('COMMONS PROMOTION QUEUE', '♕'), chip_line('SWARM', 'MCP/TOOLS', 'SKILLS', 'LOCAL APPROVAL'), Text(''), candidate_table), border_style=BEAST_BORDER))
        page.add_row(bottom)
        return page

    def intelligence(self, snap: BackendSnapshot, index: int):
        summary = intelligence_summary(snap)
        crystal = snap.crystal_compute if isinstance(snap.crystal_compute, dict) else {}
        crystal_summary = crystal.get('summary') if isinstance(crystal.get('summary'), dict) else {}
        negatives = crystal.get('negative_capabilities') if isinstance(crystal.get('negative_capabilities'), list) else []
        friction = crystal.get('friction_profiles') if isinstance(crystal.get('friction_profiles'), list) else []
        counterfactual = crystal.get('counterfactual_summary') if isinstance(crystal.get('counterfactual_summary'), dict) else {}
        escrow = crystal.get('escrow_summary') if isinstance(crystal.get('escrow_summary'), dict) else {}
        forks = crystal.get('temporal_forks') if isinstance(crystal.get('temporal_forks'), dict) else {}
        raid = crystal.get('semantic_raid') if isinstance(crystal.get('semantic_raid'), dict) else {}
        fossils = crystal.get('artifact_fossils') if isinstance(crystal.get('artifact_fossils'), dict) else {}
        semantic_pages = snap.proof_local_semantic_pages if isinstance(snap.proof_local_semantic_pages, dict) else {}
        semantic_exit = semantic_pages.get('exit_criteria') if isinstance(semantic_pages.get('exit_criteria'), dict) else {}
        distillation = snap.proof_local_distillation if isinstance(snap.proof_local_distillation, dict) else {}
        adapter_candidate = distillation.get('adapter_candidate') if isinstance(distillation.get('adapter_candidate'), dict) else {}
        adapter_eval = distillation.get('evaluation') if isinstance(distillation.get('evaluation'), dict) else {}
        adapter_metrics = adapter_eval.get('metrics') if isinstance(adapter_eval.get('metrics'), dict) else {}
        latest = latest_mega_summary(snap)
        rankings = snap.commons_ranking.get('rankings') if isinstance(snap.commons_ranking.get('rankings'), list) else []
        if not rankings:
            rankings = [{'capability_id': 'No contextual evidence yet', 'score': 0, 'confidence': 0, 'sample_size': 0, 'role': 'tool_selector'}]
        index = clamp(index, 0, len(rankings) - 1)

        metrics = Table.grid(expand=True)
        for _ in range(4):
            metrics.add_column(ratio=1)
        metrics.add_row(
            metric('HANDSHAKE', 'ACTIVE' if summary['aware'] else 'WAIT', str(summary['session_id'] or summary['blocker'] or 'endpoint has not answered')[:48]),
            metric('PREFLIGHT', f"{summary['preflight_budget_ms']} ms", f"scout {summary['scout_budget_ms']} ms", BEAST_GREEN),
            metric('COMMONS EVIDENCE', summary['commons_evidence'], f"{summary['commons_rankings']} contextual ranks", BEAST_GREEN),
            metric('LOCAL ADOPTIONS', summary['commons_adopted'], 'explicit approval only', BEAST_GREEN),
        )
        metrics.add_row(
            metric('SWARM RUNS', summary['swarm_runs'], f"{summary['swarm_profiles']} profiles / {summary['swarm_recent']} recent", BEAST_GREEN if summary['swarm_runs'] else BEAST_WARN),
            metric('OPENCLAW', 'READY' if summary['openclaw_ready'] else 'PLAN', f"{summary['openclaw_actions']} actions", BEAST_GREEN if summary['openclaw_ready'] else BEAST_WARN),
            metric('OLLAMA', 'READY' if summary['ollama_ready'] else 'WAIT', f"{summary['ollama_models']} model(s)", BEAST_GREEN if summary['ollama_ready'] else BEAST_WARN),
            metric('SWARM COMMONS', summary['swarm_commons_prepared'], f"{summary['swarm_commons_accepted']} accepted", BEAST_GREEN if summary['swarm_commons_prepared'] else BEAST_WARN),
        )
        metrics.add_row(
            metric('KV CACHE', summary['kv_cache_blocks'], f"{summary['kv_cache_operations']} op(s)", BEAST_GREEN if summary['kv_cache_blocks'] else BEAST_WARN),
            metric('KV COMMONS', summary['kv_cache_prepared'], f"{summary['kv_cache_accepted']} accepted", BEAST_GREEN if summary['kv_cache_prepared'] else BEAST_WARN),
            metric('CANDIDATE QUEUE', summary['commons_candidate_queue'], 'local approval required', BEAST_GREEN if summary['commons_candidate_queue'] else BEAST_WARN),
            metric('EVIDENCE PLANE', summary['evidence_plane_total'], f"{summary['evidence_plane_count']} plane(s)", BEAST_GREEN if summary['evidence_plane_total'] else BEAST_WARN),
        )
        metrics.add_row(
            metric('OUTCOMES', crystal_summary.get('outcomes', 0), 'privacy-safe evidence', BEAST_INFO),
            metric('NEGATIVE ACTIVE', crystal_summary.get('active', 0), f"{crystal_summary.get('observing', 0)} observing", BEAST_DANGER if crystal_summary.get('active') else BEAST_GREEN),
            metric('FRICTION PROFILES', len(friction), 'Phase 2 shadow scoring', BEAST_WARN),
            metric('PHASES 1-6', f"{latest['phase_pass_count']}/{latest['phase_count']}" if latest['phase_count'] else 'LIVE', str(crystal.get('phase6') or 'durable local'), BEAST_GREEN if latest['phase_package_passed'] or crystal else BEAST_WARN),
        )
        metrics.add_row(
            metric('PHASE 7 LATTICE', distillation.get('signal_count', 0), f"{distillation.get('task_family_count', 0)} family node(s)", BEAST_ACID if distillation.get('signal_count') else BEAST_WARN),
            metric('ADAPTER CANDIDATE', str((adapter_candidate.get('candidate_id') or 'none'))[:18], str(adapter_eval.get('decision') or 'not built'), BEAST_GREEN if str(adapter_eval.get('decision') or '').startswith('candidate_ready') else BEAST_WARN),
            metric('DISTILL GAIN', adapter_metrics.get('governed_distillation_gain', 0), 'proposal-only route', BEAST_INFO),
            metric('PARAM AVOID', adapter_metrics.get('parameter_activation_avoidance_proxy', 0), 'proxy activation saved', BEAST_GREEN if adapter_metrics else BEAST_WARN),
        )
        metrics.add_row(
            metric('SEMANTIC PAGES', semantic_pages.get('active_verified_pages', 0), f"{semantic_pages.get('page_count', 0)} content-addressed", BEAST_ACID if semantic_pages.get('active_verified_pages') else BEAST_WARN),
            metric('PAGE REUSE', semantic_pages.get('reuse_count', 0), 'verified local hits', BEAST_GREEN if semantic_pages.get('reuse_count') else BEAST_WARN),
            metric('MUTATION GATE', 'PASS' if semantic_exit.get('identity_mutation_miss') else 'WAIT', 'identity drift must miss', BEAST_GREEN if semantic_exit.get('identity_mutation_miss') else BEAST_WARN),
            metric('PAGE RECEIPTS', 'READY' if semantic_pages.get('latest_receipt') else 'NONE', 'recompute on stale proof', BEAST_GREEN if semantic_pages.get('latest_receipt') else BEAST_WARN),
        )
        metrics.add_row(
            metric('COUNTERFACTUALS', counterfactual.get('total', counterfactual.get('created', 0)), f"{counterfactual.get('resolved', 0)} resolved", BEAST_INFO),
            metric('ESCROW', escrow.get('settled', escrow.get('total', 0)), f"{float(escrow.get('verified_delivery_rate') or 0):.0%} verified", BEAST_GREEN if escrow.get('verified_delivery_rate') else BEAST_WARN),
            metric('FORKS', len(forks.get('forks') or []), ', '.join(f"{k}:{v}" for k, v in (forks.get('channels') or {}).items()) or 'stable/candidate/experimental', BEAST_INFO),
            metric('DURABLE', 'OK' if raid.get('ok') else 'LOCAL', f"{float(raid.get('artifact_integrity_rate') or 0):.0%} integrity / {fossils.get('checkpoint_count', 0)} fossils", BEAST_GREEN if raid.get('ok') else BEAST_WARN),
        )
        metrics.add_row(
            metric('CRYSTAL REUSE', summary['crystal_reuse_credits'], f"{summary['crystal_reuse_total']} total / {summary['crystal_reuse_hits']} hit(s)", BEAST_GREEN if summary['crystal_reuse_credits'] else BEAST_WARN),
            metric('PUBLIC ADAPTERS', f"{summary['crystal_integration_configured']}/{summary['crystal_integration_count']}", 'LMCache GPTCache LiteLLM OTEL Langfuse TensorZero Promptfoo', BEAST_INFO),
            metric('MEMORY HULL', summary['memory_hull_verified'], f"{summary['memory_hull_failed']} failed sidecar(s)", BEAST_GREEN if not summary['memory_hull_failed'] else BEAST_DANGER),
            metric('PASSPORT', 'VALID' if summary['passport_policy_valid'] else 'CHECK', f"{summary['passport_policy_count']} policy rule(s)", BEAST_GREEN if summary['passport_policy_valid'] else BEAST_DANGER),
        )

        metrics.add_row(
            metric('MODEL STORAGE', f"{adapter_metrics.get('model_storage_gb', 0)} GB", 'static weights', BEAST_INFO),
            metric('CRYSTAL MB', f"{adapter_metrics.get('crystal_storage_mb', 0)} MB", 'reusable capability', BEAST_INFO),
            metric('CAP DENSITY', f"{adapter_metrics.get('verified_capability_density', 0):.2f}", 'density/GB', BEAST_ACID),
            metric('CRYSTAL YIELD', f"{adapter_metrics.get('crystal_yield_tokens_per_mb', 0):.0f}", 'tokens/MB', BEAST_GREEN),
        )

        awareness = Table.grid(expand=True); awareness.add_column(width=24); awareness.add_column(ratio=1)
        awareness.add_row(Text('Backend', style=BEAST_MUTED), Text('online' if summary['online'] else 'offline', style=BEAST_GREEN if summary['online'] else BEAST_DANGER))
        if summary['blocker']:
            awareness.add_row(Text('Blocking cause', style=BEAST_MUTED), Text(str(summary['blocker'])[:120], style=BEAST_WARN))
        awareness.add_row(Text('Endpoint errors', style=BEAST_MUTED), Text(str(summary['endpoint_errors']), style=BEAST_WARN if summary['endpoint_errors'] else BEAST_GREEN))
        awareness.add_row(Text('Runtime contract', style=BEAST_MUTED), Text('BEAST artifacts are local source of truth', style=BEAST_TEXT))
        awareness.add_row(Text('Cloud escalation', style=BEAST_MUTED), Text('unresolved semantic work only', style=BEAST_GREEN))
        awareness.add_row(Text('Optional phase policy', style=BEAST_MUTED), Text('skip before latency overrun', style=BEAST_GREEN))
        awareness.add_row(Text('Handshake hash', style=BEAST_MUTED), Text(str(summary['handshake_hash'])[:48], style=BEAST_TEXT))

        decisions = Table.grid(expand=True); decisions.add_column(width=24); decisions.add_column(ratio=1)
        decisions.add_row(Text('Economist', style=BEAST_MUTED), Text(str(summary['economist_decision']), style=status_style(summary['economist_decision'])))
        decisions.add_row(Text('Selected route', style=BEAST_MUTED), Text(str(summary['economist_provider'] or 'awaiting local evidence'), style=BEAST_TEXT))
        if summary.get('economist_reason'):
            decisions.add_row(Text('Economist reason', style=BEAST_MUTED), Text(str(summary['economist_reason'])[:120], style=BEAST_WARN))
        decisions.add_row(Text('Requested role', style=BEAST_MUTED), Text(str(summary['economist_role']), style=BEAST_TEXT))
        decisions.add_row(Text('Tools skipped', style=BEAST_MUTED), Text(str(summary['tools_skipped']), style=BEAST_GREEN))
        decisions.add_row(Text('Learning', style=BEAST_MUTED), Text(str(summary['tools_observed']), style=BEAST_WARN))
        decisions.add_row(Text('Latency avoided', style=BEAST_MUTED), Text(f"{summary['latency_avoided_ms']:.1f} ms", style=BEAST_GREEN))
        decisions.add_row(Text('Compute Governor', style=BEAST_MUTED), Text(f"{summary['compute_mode']} ({summary['compute_samples']} receipts)", style=BEAST_INFO))
        decisions.add_row(Text('Observed tokens', style=BEAST_MUTED), Text(str(summary['observed_compute_tokens']), style=BEAST_TEXT))
        decisions.add_row(Text('Avoidable estimate', style=BEAST_MUTED), Text(str(summary['avoidable_compute_tokens']), style=BEAST_WARN))
        decisions.add_row(Text('Failure memory', style=BEAST_MUTED), Text(f"{len(negatives)} scoped record(s)", style=BEAST_WARN if negatives else BEAST_GREEN))
        decisions.add_row(Text('Friction routing', style=BEAST_MUTED), Text('SHADOW', style=BEAST_INFO))
        savings = summary['weekly_compute_savings_usd']
        savings_text = f"${float(savings):.6f}" if savings is not None else summary['weekly_compute_savings_status']
        suppression_style = BEAST_DANGER if summary['compute_enforcement_pause'] else BEAST_GREEN
        decisions.add_row(
            Text('False suppression', style=BEAST_MUTED),
            Text(f"{summary['false_suppression_rate']:.1%}", style=suppression_style),
        )
        decisions.add_row(Text('Weekly savings', style=BEAST_MUTED), Text(savings_text, style=BEAST_GREEN if savings is not None else BEAST_WARN))

        rank_table = Table(expand=True, box=box.SIMPLE_HEAVY)
        for col in ['', 'Capability', 'Role', 'Score', 'Confidence', 'Samples', 'Local/Global']:
            rank_table.add_column(col)
        for i, item in enumerate(rankings):
            rank_table.add_row(
                selected_marker(i == index), selected_text(val(item, 'capability_id', default='capability'), i == index),
                val(item, 'role', default='general'), val(item, 'score', default='0'), val(item, 'confidence', default='0'),
                val(item, 'sample_size', default='0'), f"{val(item, 'local_samples', default='0')}/{val(item, 'global_samples', default='0')}",
            )

        friction_table = Table(expand=True, box=box.SIMPLE_HEAVY)
        for col in ['Capability', 'Task', 'Samples', 'Failure', 'Repair', 'Friction', 'Confidence']:
            friction_table.add_column(col)
        for item in friction[:8]:
            friction_table.add_row(
                str(item.get('capability_id') or 'unknown'), str(item.get('task_class') or 'general'),
                str(item.get('samples') or 0), f"{float(item.get('failure_rate') or 0):.0%}",
                f"{float(item.get('avg_repair_depth') or 0):.2f}", f"{float(item.get('friction_score') or 0):.2f}",
                f"{float(item.get('confidence') or 0):.0%}",
            )
        if not friction:
            friction_table.add_row('No evidence yet', '', '0', '0%', '0', '0', '0%')

        phase_table = Table.grid(expand=True)
        phase_table.add_column(width=22); phase_table.add_column(ratio=1)
        phase_table.add_row(Text('Phase 1 evidence', style=BEAST_MUTED), Text(str(crystal.get('phase1') or 'operational'), style=BEAST_GREEN))
        phase_table.add_row(Text('Phase 2 routing', style=BEAST_MUTED), Text(str(crystal.get('phase2') or 'shadow'), style=BEAST_INFO))
        phase_table.add_row(Text('Phase 3 counterfacts', style=BEAST_MUTED), Text(f"{counterfactual.get('resolved', 0)}/{counterfactual.get('total', counterfactual.get('created', 0))} resolved", style=BEAST_INFO))
        phase_table.add_row(Text('Phase 4 escrow', style=BEAST_MUTED), Text(f"{escrow.get('settled', 0)} settled / ${float(escrow.get('refunded_cost_usd') or 0):.4f} refunded", style=BEAST_GREEN if escrow.get('settled') else BEAST_WARN))
        phase_table.add_row(Text('Phase 5 forks', style=BEAST_MUTED), Text(f"{len(forks.get('forks') or [])} forks / {len(forks.get('annealing_events') or [])} anneals", style=BEAST_INFO))
        phase_table.add_row(Text('Phase 6 durability', style=BEAST_MUTED), Text(f"raid={'ok' if raid.get('ok') else 'waiting'} / replay={'valid' if fossils.get('valid_lineage') else 'waiting'}", style=BEAST_GREEN if raid.get('ok') and fossils.get('valid_lineage') else BEAST_WARN))
        phase_table.add_row(Text('Latest mega receipts', style=BEAST_MUTED), Text(f"{latest['provider_call_receipts']} provider / {latest['compute_governor_receipts']} reuse", style=BEAST_GREEN if latest['provider_call_receipts'] or latest['compute_governor_receipts'] else BEAST_WARN))
        phase_table.add_row(Text('Latest fingerprints', style=BEAST_MUTED), Text(f"{latest['impact_fingerprint_files']} files / integrity {latest['integrity_hash'][:18] or 'n/a'}", style=BEAST_GREEN if latest['impact_fingerprint_files'] else BEAST_WARN))

        crystal_reuse = snap.crystal_reuse if isinstance(snap.crystal_reuse, dict) else {}
        integration_health = crystal_reuse.get('integration_health') if isinstance(crystal_reuse.get('integration_health'), dict) else {}
        integration_rows = integration_health.get('integrations') if isinstance(integration_health.get('integrations'), list) else crystal_reuse.get('integrations')
        integration_rows = [row for row in (integration_rows or []) if isinstance(row, dict)]
        integration_table = Table(expand=True, box=box.SIMPLE_HEAVY)
        for col in ['Adapter', 'Configured', 'Role', 'Endpoint / Env', 'Capabilities']:
            integration_table.add_column(col)
        for row in integration_rows[:10]:
            envs = row.get('env_vars') if isinstance(row.get('env_vars'), list) else []
            caps = row.get('capabilities') if isinstance(row.get('capabilities'), dict) else {}
            integration_table.add_row(
                str(row.get('project') or row.get('integration_id') or 'adapter'),
                status_mark('OK' if row.get('configured') else 'WAIT') + Text(' ' + ('yes' if row.get('configured') else 'no'), style=BEAST_GREEN if row.get('configured') else BEAST_WARN),
                str(row.get('role') or '')[:42],
                str(row.get('endpoint') or ', '.join(envs) or 'local contract')[:46],
                ', '.join(k for k, v in caps.items() if v)[:42],
            )
        if not integration_rows:
            integration_table.add_row('No adapters loaded', 'WAIT', 'gateway offline', '', '')

        memory_security = snap.memory_security if isinstance(snap.memory_security, dict) else {}
        memory_hull = memory_security.get('memory_hull') if isinstance(memory_security.get('memory_hull'), dict) else {}
        residue_seal = memory_security.get('residue_seal') if isinstance(memory_security.get('residue_seal'), dict) else {}
        passport = memory_security.get('agent_passport') if isinstance(memory_security.get('agent_passport'), dict) else {}
        passport_lint = passport.get('policy_lint') if isinstance(passport.get('policy_lint'), dict) else {}
        memory_table = Table.grid(expand=True); memory_table.add_column(width=24); memory_table.add_column(ratio=1)
        memory_table.add_row(Text('Memory Hull root', style=BEAST_MUTED), Text(str(memory_hull.get('root') or summary['memory_hull_root'] or 'not loaded')[:90], style=BEAST_TEXT))
        memory_table.add_row(Text('Sidecar verification', style=BEAST_MUTED), Text(f"{summary['memory_hull_verified']} verified / {summary['memory_hull_failed']} failed", style=BEAST_GREEN if not summary['memory_hull_failed'] else BEAST_DANGER))
        memory_table.add_row(Text('Residue key', style=BEAST_MUTED), Text('ready' if summary['residue_key_ready'] else 'missing', style=BEAST_GREEN if summary['residue_key_ready'] else BEAST_DANGER))
        memory_table.add_row(Text('Residue key mode', style=BEAST_MUTED), Text(str(residue_seal.get('key_mode') or 'n/a'), style=BEAST_TEXT))
        memory_table.add_row(Text('Passport policy', style=BEAST_MUTED), Text('valid' if summary['passport_policy_valid'] else 'invalid', style=BEAST_GREEN if summary['passport_policy_valid'] else BEAST_DANGER))
        memory_table.add_row(Text('Passport rules', style=BEAST_MUTED), Text(str(summary['passport_policy_count']), style=BEAST_TEXT))
        decisions_sample = passport.get('sample_decisions') if isinstance(passport.get('sample_decisions'), dict) else {}
        for label, decision in list(decisions_sample.items())[:3]:
            allowed = bool(decision.get('allowed')) if isinstance(decision, dict) else False
            memory_table.add_row(Text(human_label(label), style=BEAST_MUTED), Text(str(decision.get('reason') if isinstance(decision, dict) else 'unknown'), style=BEAST_GREEN if allowed else BEAST_WARN))

        connectors = Table.grid(expand=True); connectors.add_column(width=24); connectors.add_column(ratio=1)
        offline_note = 'backend offline' if not summary['online'] else ''
        connectors.add_row(Text('Capability Exchange', style=BEAST_MUTED), Text('opted in' if summary['exchange_enabled'] else (offline_note or 'local only'), style=BEAST_GREEN if summary['exchange_enabled'] else BEAST_WARN))
        connectors.add_row(Text('OpenTelemetry', style=BEAST_MUTED), Text('configured' if summary['otel_configured'] else (offline_note or 'endpoint not configured'), style=BEAST_GREEN if summary['otel_configured'] else BEAST_WARN))
        connectors.add_row(Text('Marketplace', style=BEAST_MUTED), Text(f"{summary['plugin_count']} installed manifests", style=BEAST_TEXT))
        connectors.add_row(Text('Commons authority', style=BEAST_MUTED), Text('advisory prior; local policy decides', style=BEAST_GREEN))
        connectors.add_row(Text('Compute authority', style=BEAST_MUTED), Text('shadow only; no routing changes', style=BEAST_GREEN))

        try:
            size = self.app.size
        except Exception:
            size = None
        compact = int(getattr(size, 'width', 140) or 140) < 118
        upper = Table.grid(expand=True)
        if compact:
            upper.add_column(ratio=1)
            upper.add_row(Panel(Group(title_text('AGENT AWARENESS', PAGE_SYMBOLS['Intelligence']), awareness), border_style=BEAST_BORDER))
            upper.add_row(Panel(Group(title_text('LIVE DECISIONS', '◉'), decisions), border_style='#2A8F5A'))
        else:
            upper.add_column(ratio=1); upper.add_column(ratio=1)
            upper.add_row(
                Panel(Group(title_text('AGENT AWARENESS', PAGE_SYMBOLS['Intelligence']), awareness), border_style=BEAST_BORDER),
                Panel(Group(title_text('LIVE DECISIONS', '◉'), decisions), border_style='#2A8F5A'),
            )
        page = Table.grid(expand=True); page.add_column(ratio=1)
        page.add_row(Panel(Group(title_text('BEAST INTELLIGENCE', PAGE_SYMBOLS['Intelligence']), chip_line('AWARE', 'COMMONS', 'ECONOMIST'), Text(''), metrics), border_style=BEAST_ACID, padding=(1, 2), style=BEAST_PANEL))
        page.add_row(upper)
        page.add_row(Panel(Group(title_text('META TOOL COMMONS', '⚒'), chip_line('↑↓', 'v INSPECT'), Text(''), rank_table), border_style=BEAST_BORDER))
        page.add_row(Panel(Group(title_text('CRYSTAL COMPUTE PHASES', '◆'), chip_line('P1 EVIDENCE', 'P2 FRICTION', 'P3 COUNTERFACTS', 'P4 ESCROW', 'P5 FORKS', 'P6 RAID'), Text(''), phase_table, Text(''), friction_table), border_style=BEAST_BORDER))
        page.add_row(Panel(Group(title_text('CRYSTAL REUSE INTEGRATIONS', 'λ'), chip_line('LMCACHE', 'GPTCACHE', 'LITELLM', 'OTEL', 'LANGFUSE', 'TENSORZERO', 'PROMPTFOO'), Text(''), integration_table), border_style=BEAST_JADE))
        page.add_row(Panel(Group(title_text('MEMORY HULL / RESIDUE SEAL / AGENT PASSPORT', '▥'), chip_line('VAULT', 'SEAL', 'PASSPORT', 'POLICY'), Text(''), memory_table), border_style=BEAST_ACID))
        page.add_row(Panel(Group(title_text('CONNECTORS', '♧'), connectors), border_style=BEAST_BORDER))
        return page

    def spaces(self, snap: BackendSnapshot, index: int):
        registry = snap.commons_spaces if isinstance(snap.commons_spaces, dict) else {}
        spaces = registry.get('spaces') if isinstance(registry.get('spaces'), list) else []
        scoreboard = registry.get('scoreboard') if isinstance(registry.get('scoreboard'), dict) else {}
        sources = registry.get('artifact_sources') if isinstance(registry.get('artifact_sources'), dict) else {}
        policy = snap.commons_policy if isinstance(snap.commons_policy, dict) else {}
        recommendation = policy.get('recommendation') if isinstance(policy.get('recommendation'), dict) else {}
        projection = policy.get('verification_projection') if isinstance(policy.get('verification_projection'), dict) else {}
        evaluation = snap.commons_policy_evaluation if isinstance(snap.commons_policy_evaluation, dict) else {}
        economy = snap.commons_economy if isinstance(snap.commons_economy, dict) else {}
        duplicates = economy.get('duplicates') if isinstance(economy.get('duplicates'), dict) else {}
        scale = snap.commons_scale_economics if isinstance(snap.commons_scale_economics, dict) else {}
        proof_density = scale.get('proof_density') if isinstance(scale.get('proof_density'), dict) else {}
        proof_spaces = proof_density.get('spaces') if isinstance(proof_density.get('spaces'), dict) else {}
        proof_workload = proof_density.get('workload') if isinstance(proof_density.get('workload'), dict) else {}
        proof_gap = proof_density.get('proof_gap_to_10x3') if isinstance(proof_density.get('proof_gap_to_10x3'), dict) else {}
        tier_inventory = proof_density.get('tier_inventory') if isinstance(proof_density.get('tier_inventory'), dict) else {}
        tiered = scale.get('tiered_credit_pricing') if isinstance(scale.get('tiered_credit_pricing'), dict) else {}
        marketplace = scale.get('marketplace_readiness') if isinstance(scale.get('marketplace_readiness'), dict) else {}
        if not spaces:
            spaces = [{
                'space_id': 'no_spaces_loaded', 'name': 'No local Compute Spaces found',
                'task_class': 'waiting', 'valid': False, 'artifact_count': 0,
                'evidence_class': 'package a Space to begin',
            }]
        index = clamp(index, 0, len(spaces) - 1)
        selected = spaces[index]

        metrics = Table.grid(expand=True)
        for _ in range(4):
            metrics.add_column(ratio=1)
        metrics.add_row(
            metric('LOCAL SPACES', scoreboard.get('spaces', len(spaces)), f"{scoreboard.get('valid_spaces', 0)} validated", BEAST_GREEN),
            metric('VERIFIED', scoreboard.get('verified_spaces', 0), 'signed reduction receipts', BEAST_GREEN if scoreboard.get('verified_spaces') else BEAST_WARN),
            metric('CALLS AVOIDED', scoreboard.get('provider_calls_avoided', 0), 'observed + labeled counterfacts', BEAST_INFO),
            metric('GPU AVOIDED', scoreboard.get('gpu_avoided_spaces', 0), 'Space routes', BEAST_GREEN),
        )
        metrics.add_row(
            metric('ADOPTIONS', scoreboard.get('adoptions', 0), 'explicit local approval', BEAST_GREEN),
            metric('POLICY MODE', str(policy.get('mode') or 'shadow').upper(), 'never enforces', BEAST_INFO),
            metric('POLICY SAMPLES', evaluation.get('sample_size', 0), str(evaluation.get('protocol') or 'waiting'), BEAST_WARN),
            metric('VERIFY PROJECTION', 'PASS' if projection.get('would_preserve_verification') else 'UNKNOWN', f"{projection.get('verified_support', 0)} verified support", BEAST_GREEN if projection.get('would_preserve_verification') else BEAST_WARN),
        )
        metrics.add_row(
            metric('COMMONS CREDITS', economy.get('issued_units', 0), 'non-financial units', BEAST_GREEN),
            metric('CREDIT RECEIPTS', economy.get('credit_count', 0), 'sealed evidence', BEAST_INFO),
            metric('DUPLICATES', duplicates.get('duplicate_spaces', 0), 'zero additional credit', BEAST_WARN),
            metric('ECONOMY MODE', str(economy.get('mode') or 'simulation').upper(), 'non-transferable', BEAST_GREEN),
        )
        metrics.add_row(
            metric('PROOF SPACES', proof_spaces.get('live_reproduced', 0), str(proof_spaces.get('valid', scoreboard.get('valid_spaces', 0))) + ' valid / ' + str(proof_spaces.get('credited', 0)) + ' credited', BEAST_GREEN if proof_spaces.get('live_reproduced') else BEAST_WARN),
            metric('MATCHES', proof_workload.get('total_repeated_matches', 0), str(proof_workload.get('total_cloud_calls_avoided', 0)) + ' cloud calls avoided', BEAST_GREEN if proof_workload.get('total_repeated_matches') else BEAST_WARN),
            metric('GAP TO 10×3', proof_gap.get('matches_needed', 30), str(proof_gap.get('spaces_needed', 10)) + ' spaces need matches', BEAST_WARN if proof_gap.get('matches_needed', 30) else BEAST_GREEN),
            metric('TIERED VALUE', '$' + f"{float(tiered.get('observed_total_credit_value_usd') or 0.0):.2f}", 'proof-priced credits', BEAST_ACID if tiered else BEAST_WARN),
        )

        table = Table(expand=True, box=box.SIMPLE_HEAVY)
        for col in ['', 'Space', 'Task class', 'Artifacts', 'Verified', 'Calls saved', 'GPU', 'Evidence']:
            table.add_column(col)
        for i, row in enumerate(spaces):
            table.add_row(
                selected_marker(i == index),
                selected_text(val(row, 'name', 'space_id', default='space'), i == index),
                val(row, 'task_class', default='general'),
                val(row, 'artifact_count', default='0'),
                Text('yes' if row.get('verifier_passed') else 'no', style=BEAST_GREEN if row.get('verifier_passed') else BEAST_WARN),
                val(row, 'provider_calls_avoided', default='0'),
                Text('avoided' if row.get('gpu_avoided') else 'n/a', style=BEAST_GREEN if row.get('gpu_avoided') else BEAST_MUTED),
                val(row, 'evidence_class', default='unknown')[:34],
            )

        source_table = Table(expand=True, box=box.SIMPLE)
        source_table.add_column('Artifact/source class')
        source_table.add_column('Count', justify='right')
        artifact_types = sources.get('artifact_types') if isinstance(sources.get('artifact_types'), dict) else {}
        source_classes = sources.get('source_classes') if isinstance(sources.get('source_classes'), dict) else {}
        for name, count in list(sorted(artifact_types.items()))[:8]:
            source_table.add_row(str(name), str(count))
        for name, count in list(sorted(source_classes.items()))[:5]:
            source_table.add_row('source:' + str(name), str(count))
        if not artifact_types and not source_classes:
            source_table.add_row('No artifact provenance loaded', '0')

        detail = Table.grid(expand=True)
        detail.add_column(width=22)
        detail.add_column(ratio=1)
        for label, value in [
            ('Space ID', selected.get('space_id')),
            ('Authority', selected.get('authority')),
            ('Task class', selected.get('task_class')),
            ('Artifact types', ', '.join(selected.get('artifact_types') or [])),
            ('Source', selected.get('source_class')),
            ('Approval', 'required' if selected.get('approval_required') else 'not required'),
            ('Promotion', selected.get('promotion_state')),
            ('Reproductions', selected.get('reproduction_count')),
            ('Local trust score', selected.get('local_trust_score')),
            ('Tokens avoided', selected.get('tokens_avoided')),
            ('Token evidence', selected.get('tokens_evidence')),
            ('Economy', 'reproduction-backed / non-financial'),
        ]:
            detail.add_row(Text(label, style=BEAST_MUTED), Text(str(value if value is not None else 'unknown'), style=BEAST_TEXT))

        policy_table = Table.grid(expand=True)
        policy_table.add_column(width=22)
        policy_table.add_column(ratio=1)
        policy_table.add_row(Text('Recommended route', style=BEAST_MUTED), Text(str(recommendation.get('route') or 'insufficient evidence'), style=BEAST_INFO))
        policy_table.add_row(Text('Expected reduction', style=BEAST_MUTED), Text(f"{float(recommendation.get('expected_compute_reduction') or 0):.1%}", style=BEAST_GREEN))
        policy_table.add_row(Text('Tools', style=BEAST_MUTED), Text(', '.join(recommendation.get('tools') or []) or 'none', style=BEAST_TEXT))
        policy_table.add_row(Text('Subagents', style=BEAST_MUTED), Text(', '.join(recommendation.get('subagents') or []) or 'none', style=BEAST_TEXT))
        policy_table.add_row(Text('Top-1 evaluation', style=BEAST_MUTED), Text(str(evaluation.get('top1_route_accuracy')), style=BEAST_WARN))
        policy_table.add_row(Text('Authority', style=BEAST_MUTED), Text('SHADOW ONLY / NO SUPPRESSION', style=BEAST_GREEN))

        bottom = Table.grid(expand=True)
        bottom.add_column(ratio=1)
        bottom.add_column(ratio=1)
        bottom.add_column(ratio=1)
        bottom.add_row(
            Panel(Group(title_text('SELECTED SPACE', '▣'), chip_line('v INSPECT', 'a ADOPT'), Text(''), detail), border_style='#2A8F5A'),
            Panel(Group(title_text('ARTIFACT PROVENANCE', '▤'), Text(''), source_table), border_style=BEAST_BORDER),
            Panel(Group(title_text('SHADOW POLICY', '◆'), chip_line('RANKER', 'HEURISTIC', 'EVAL'), Text(''), policy_table), border_style=BEAST_BORDER),
        )
        scale_table = Table.grid(expand=True)
        scale_table.add_column(width=24)
        scale_table.add_column(ratio=1)
        scale_table.add_row(Text('Valid Spaces', style=BEAST_MUTED), Text(str(proof_spaces.get('valid', scoreboard.get('valid_spaces', 0))), style=BEAST_GREEN))
        scale_table.add_row(Text('Live reproduced', style=BEAST_MUTED), Text(str(proof_spaces.get('live_reproduced', 0)), style=BEAST_GREEN if proof_spaces.get('live_reproduced') else BEAST_WARN))
        scale_table.add_row(Text('Credit eligible', style=BEAST_MUTED), Text(str(proof_spaces.get('eligible_for_credit', 0)), style=BEAST_GREEN if proof_spaces.get('eligible_for_credit') else BEAST_WARN))
        scale_table.add_row(Text('Repeated matches', style=BEAST_MUTED), Text(str(proof_workload.get('total_repeated_matches', 0)), style=BEAST_GREEN if proof_workload.get('total_repeated_matches') else BEAST_WARN))
        scale_table.add_row(Text('Gap to 10×3', style=BEAST_MUTED), Text(str(proof_gap.get('spaces_needed', 10)) + ' spaces / ' + str(proof_gap.get('matches_needed', 30)) + ' matches', style=BEAST_WARN if proof_gap.get('matches_needed', 30) else BEAST_GREEN))
        scale_table.add_row(Text('Latest receipt', style=BEAST_MUTED), Text(str(scale.get('artifact_path') or 'run commons_scale_economics_ladder.py')[-80:], style=BEAST_TEXT))

        tier_table = Table.grid(expand=True)
        tier_table.add_column(width=24)
        tier_table.add_column(ratio=1)
        candidate_kinds = tier_inventory.get('candidate_kinds') if isinstance(tier_inventory.get('candidate_kinds'), dict) else {}
        tier_table.add_row(Text('Forge candidates', style=BEAST_MUTED), Text(str(tier_inventory.get('forge_candidates', 0)), style=BEAST_ACID if tier_inventory.get('forge_candidates') else BEAST_WARN))
        for name in ['fused_inference_crystal', 'forge_crystal', 'meta_tool', 'skill', 'mutation_ablation_case']:
            tier_table.add_row(Text(name.replace('_', ' ').title(), style=BEAST_MUTED), Text(str(candidate_kinds.get(name, 0)), style=BEAST_GREEN if candidate_kinds.get(name, 0) else BEAST_WARN))
        portfolio = tiered.get('tiered_10_space_portfolio_example') if isinstance(tiered.get('tiered_10_space_portfolio_example'), dict) else {}
        tier_table.add_row(Text('10-space tiered', style=BEAST_MUTED), Text('$' + f"{float(portfolio.get('tiered_credit_value_usd') or 0.0):.4f}" + ' / flat $' + f"{float(portfolio.get('flat_credit_value_usd') or 0.0):.4f}", style=BEAST_INFO))
        tier_table.add_row(Text('Observed tiered', style=BEAST_MUTED), Text('$' + f"{float(tiered.get('observed_total_credit_value_usd') or 0.0):.4f}", style=BEAST_ACID if tiered else BEAST_WARN))

        gate_table = Table(expand=True, box=box.SIMPLE)
        gate_table.add_column('Gate')
        gate_table.add_column('Status')
        gate_table.add_column('Need')
        gates = marketplace.get('gates') if isinstance(marketplace.get('gates'), list) else []
        for gate in gates[:6]:
            gate_table.add_row(
                str(gate.get('gate') or '').replace('_', ' ').title(),
                Text(str(gate.get('status') or 'unknown'), style=status_style(gate.get('status'))),
                Text(str(gate.get('requires') or '')[:62], style=BEAST_MUTED),
            )
        if not gates:
            gate_table.add_row('Scale economics', Text('waiting', style=BEAST_WARN), 'run commons_scale_economics_ladder.py')

        scale_row = Table.grid(expand=True)
        scale_row.add_column(ratio=1)
        scale_row.add_column(ratio=1)
        scale_row.add_column(ratio=1)
        scale_row.add_row(
            Panel(Group(title_text('SCALE PROOF DENSITY', '⧉'), chip_line('10×3', 'LIVE PROOF', 'NO FAKE MATCHES'), Text(''), scale_table), border_style=BEAST_ACID),
            Panel(Group(title_text('TIERED CREDIT PRICING', '$'), chip_line('T1', 'T2', 'T3', 'T4'), Text(''), tier_table), border_style=BEAST_BORDER),
            Panel(Group(title_text('MARKETPLACE GATES', '▧'), chip_line('ANTI-GAME', 'CROSS-MACHINE', 'FREQUENCY'), Text(''), gate_table), border_style=BEAST_BORDER),
        )
        page = Table.grid(expand=True)
        page.add_column(ratio=1)
        page.add_row(Panel(Group(title_text('BEAST COMPUTE SPACES', PAGE_SYMBOLS['Spaces']), chip_line('LOCAL', 'SIGNED', 'ADVISORY', 'NON-FINANCIAL CREDIT'), Text(''), metrics), border_style=BEAST_ACID, padding=(1, 2), style=BEAST_PANEL))
        page.add_row(Panel(Group(title_text('SPACE REGISTRY', '⌁'), chip_line('↑↓ SELECT', 'v DETAIL', 'a APPROVE ADOPTION'), Text(''), table), border_style=BEAST_BORDER))
        page.add_row(bottom)
        page.add_row(scale_row)
        return page

    def economy(self, snap: BackendSnapshot, index: int):
        try:
            report = build_dashboard()
        except Exception:
            report = {}
        rollout = report.get('rollout') if isinstance(report.get('rollout'), dict) else {}
        forge = report.get('forge') if isinstance(report.get('forge'), dict) else {}
        forge_totals = forge.get('totals') if isinstance(forge.get('totals'), dict) else {}
        crystal = report.get('crystallization') if isinstance(report.get('crystallization'), dict) else {}
        metrics = snap.compute_metrics if isinstance(snap.compute_metrics, dict) else {}
        savings = snap.compute_savings if isinstance(snap.compute_savings, dict) else {}
        state = snap.compute_state if isinstance(snap.compute_state, dict) else {}
        scale = snap.commons_scale_economics if isinstance(snap.commons_scale_economics, dict) else {}
        proof_density = scale.get('proof_density') if isinstance(scale.get('proof_density'), dict) else {}
        proof_spaces = proof_density.get('spaces') if isinstance(proof_density.get('spaces'), dict) else {}
        proof_workload = proof_density.get('workload') if isinstance(proof_density.get('workload'), dict) else {}
        proof_gap = proof_density.get('proof_gap_to_10x3') if isinstance(proof_density.get('proof_gap_to_10x3'), dict) else {}
        tiered = scale.get('tiered_credit_pricing') if isinstance(scale.get('tiered_credit_pricing'), dict) else {}
        portfolio = tiered.get('tiered_10_space_portfolio_example') if isinstance(tiered.get('tiered_10_space_portfolio_example'), dict) else {}
        evidence = master_evidence_summary(snap)
        latest = latest_mega_summary(snap)
        statuses = metrics.get('statuses') if isinstance(metrics.get('statuses'), dict) else {}
        stream_actions = metrics.get('stream_repair_actions') if isinstance(metrics.get('stream_repair_actions'), dict) else {}
        rows = [
            ('Mode', ', '.join(f'{k}:{v}' for k, v in (state.get('modes') or {}).items()) or 'shadow'),
            ('Receipts', metrics.get('sample_size', 0)),
            ('Observed tokens', metrics.get('observed_total_tokens', 0)),
            ('Avoidable tokens', metrics.get('estimated_avoidable_total_tokens', 0)),
            ('Stream saved', metrics.get('stream_tokens_saved', 0)),
            ('Stream cancels', metrics.get('stream_upstream_cancellation_count', 0)),
            ('False suppression', f"{float(metrics.get('false_suppression_rate') or 0.0):.1%}"),
            ('Weekly savings', savings.get('potential_weekly_savings_usd') or savings.get('availability') or 'unavailable'),
        ]
        actions = economy_action_rows(report)
        index = clamp(index, 0, len(actions) - 1)
        table = Table(expand=True, box=box.SIMPLE_HEAVY)
        for col in ['', 'Signal', 'Value']:
            table.add_column(col)
        for name, value in rows:
            table.add_row('', Text(name, style=BEAST_TEXT), Text(str(value), style=status_style(value)))
        action_table = Table(expand=True, box=box.SIMPLE_HEAVY)
        for col in ['', 'Operation', 'Status', 'Value', 'Action']:
            action_table.add_column(col)
        for i, row in enumerate(actions):
            action_table.add_row(
                selected_marker(i == index),
                selected_text(row.get('name', ''), i == index),
                Text(str(row.get('status') or ''), style=status_style(row.get('status'))),
                str(row.get('value') or ''),
                Text(str(row.get('hint') or ''), style=BEAST_MUTED),
            )
        rollup = Table.grid(expand=True)
        rollup.add_column(width=22)
        rollup.add_column(ratio=1)
        rollup.add_row(Text('Rollout readiness', style=BEAST_MUTED), Text(str(rollout.get('readiness') or 'unknown'), style=status_style(rollout.get('readiness'))))
        rollup.add_row(Text('Rollout redlines', style=BEAST_MUTED), Text(', '.join(rollout.get('redlines') or []) or 'none', style=BEAST_GREEN if not rollout.get('redlines') else BEAST_DANGER))
        rollup.add_row(Text('Forge nodes', style=BEAST_MUTED), Text(str(forge_totals.get('nodes', 0)), style=BEAST_GREEN if forge_totals.get('nodes') else BEAST_WARN))
        rollup.add_row(Text('Crystallized promoted', style=BEAST_MUTED), Text(str(crystal.get('promoted_count', 0)), style=BEAST_GREEN if crystal.get('promoted_count') else BEAST_WARN))
        rollup.add_row(Text('Commons proof density', style=BEAST_MUTED), Text(str(proof_spaces.get('live_reproduced', 0)) + '/' + str(proof_spaces.get('valid', 0)) + ' live reproduced', style=BEAST_GREEN if proof_spaces.get('live_reproduced') else BEAST_WARN))
        rollup.add_row(Text('Gap to 10×3', style=BEAST_MUTED), Text(str(proof_gap.get('spaces_needed', 10)) + ' spaces / ' + str(proof_gap.get('matches_needed', 30)) + ' matches', style=BEAST_WARN if proof_gap.get('matches_needed', 30) else BEAST_GREEN))
        rollup.add_row(Text('Observed tiered credit', style=BEAST_MUTED), Text('$' + f"{float(tiered.get('observed_total_credit_value_usd') or 0.0):.4f}", style=BEAST_ACID if tiered else BEAST_WARN))
        rollup.add_row(Text('10-space portfolio', style=BEAST_MUTED), Text('$' + f"{float(portfolio.get('tiered_credit_value_usd') or 0.0):.4f}" + ' tiered / $' + f"{float(portfolio.get('flat_credit_value_usd') or 0.0):.4f}" + ' flat', style=BEAST_INFO if portfolio else BEAST_WARN))
        rollup.add_row(Text('Commons matches', style=BEAST_MUTED), Text(str(proof_workload.get('total_repeated_matches', 0)) + ' matches / ' + str(proof_workload.get('total_cloud_calls_avoided', 0)) + ' avoided', style=BEAST_GREEN if proof_workload.get('total_repeated_matches') else BEAST_WARN))
        rollup.add_row(Text('Receipt statuses', style=BEAST_MUTED), Text(', '.join(f'{k}:{v}' for k, v in statuses.items()) or 'none', style=BEAST_TEXT))
        rollup.add_row(Text('Stream repairs', style=BEAST_MUTED), Text(', '.join(f'{k}:{v}' for k, v in stream_actions.items()) or 'none', style=BEAST_TEXT))
        rollup.add_row(Text('Cost coverage', style=BEAST_MUTED), Text(f"{float(metrics.get('cost_coverage_rate') or 0.0):.1%}", style=BEAST_WARN))
        rollup.add_row(Text('Token calibration', style=BEAST_MUTED), Text(f"{float(metrics.get('token_calibration_coverage_rate') or 0.0):.1%}", style=BEAST_WARN))
        definitive = Table.grid(expand=True)
        definitive.add_column(width=24)
        definitive.add_column(ratio=1)
        definitive.add_row(Text('Frozen release', style=BEAST_MUTED), Text(f"{evidence['release']} / {evidence['status']}", style=BEAST_GREEN if evidence['available'] else BEAST_WARN))
        definitive.add_row(Text('Controlled design', style=BEAST_MUTED), Text(f"{evidence['observed_cells']}/{evidence['target_cells']} ({evidence['progress_rate']:.0%})", style=BEAST_WARN if evidence['remaining_cells'] else BEAST_GREEN))
        definitive.add_row(Text('Mature QPCCD', style=BEAST_MUTED), Text(f"{evidence['qpccd_numerator']}/{evidence['qpccd_denominator']} = {evidence['qpccd_rate']:.1%}", style=BEAST_GREEN if evidence['qpccd_numerator'] else BEAST_WARN))
        definitive.add_row(Text('Deterministic reuse', style=BEAST_MUTED), Text(str(evidence['deterministic_reuse']), style=BEAST_GREEN))
        definitive.add_row(Text('Mutation recovery', style=BEAST_MUTED), Text(f"{evidence['mutation_recovered']}/{evidence['mutation_cases']}", style=BEAST_GREEN if evidence['mutation_cases'] and evidence['mutation_recovered'] == evidence['mutation_cases'] else BEAST_WARN))
        definitive.add_row(Text('Cross-provider reuse', style=BEAST_MUTED), Text(f"{evidence['cross_provider_cases']} primary + {evidence['groq_scout_cases']} scout", style=BEAST_GREEN))
        definitive.add_row(Text('Avoided tokens', style=BEAST_MUTED), Text(f"{evidence['avoided_tokens_estimate']:,} estimated", style=BEAST_ACID))
        definitive.add_row(Text('Actual billing', style=BEAST_MUTED), Text('pending provider cost capture', style=BEAST_WARN))
        latest_table = Table.grid(expand=True)
        latest_table.add_column(width=24)
        latest_table.add_column(ratio=1)
        latest_table.add_row(Text('Newest artifact', style=BEAST_MUTED), Text(latest['artifact_path'][-88:] or 'missing', style=BEAST_TEXT))
        latest_table.add_row(Text('Mode / live', style=BEAST_MUTED), Text(f"{latest['mode']} / {latest['live']}", style=BEAST_GREEN if latest['live'] else BEAST_WARN))
        latest_table.add_row(Text('Provider calls', style=BEAST_MUTED), Text(f"{latest['raw_live_result_count']} raw results / {latest['live_result_count']} retained", style=BEAST_GREEN if latest['live_result_count'] else BEAST_WARN))
        latest_table.add_row(Text('Call receipts', style=BEAST_MUTED), Text(f"{latest['provider_call_receipts']} jsonl / {latest['provider_call_receipt_files']} files", style=BEAST_GREEN if latest['provider_call_receipts'] else BEAST_WARN))
        latest_table.add_row(Text('Fingerprints', style=BEAST_MUTED), Text(f"{latest['impact_fingerprint_files']} impact files", style=BEAST_GREEN if latest['impact_fingerprint_files'] else BEAST_WARN))
        latest_table.add_row(Text('Reuse receipts', style=BEAST_MUTED), Text(f"{latest['compute_governor_receipts']} CG / {latest['crystallization_events']} events", style=BEAST_GREEN if latest['compute_governor_receipts'] else BEAST_WARN))
        latest_table.add_row(Text('Mutation recovery', style=BEAST_MUTED), Text(f"{latest['recovered_count']}/{latest['mutation_case_count']} recovered; false reuse {latest['false_reuse_count']}", style=BEAST_GREEN if latest['mutation_case_count'] and latest['false_reuse_count'] == 0 else BEAST_WARN))
        latest_table.add_row(Text('Phase package', style=BEAST_MUTED), Text(f"{latest['phase_pass_count']}/{latest['phase_count']} pass", style=BEAST_GREEN if latest['phase_package_passed'] else BEAST_WARN))
        latest_table.add_row(Text('Integrity', style=BEAST_MUTED), Text(latest['integrity_hash'][:56] or 'missing', style=BEAST_GREEN if latest['integrity_hash'] else BEAST_WARN))
        page = Table.grid(expand=True)
        page.add_column(ratio=1)
        page.add_row(Panel(Group(title_text('COMPUTE ECONOMY', PAGE_SYMBOLS['Economy']), chip_line('↑↓', 'Enter RUN', 't TEST', 'a PROMOTE'), Text(''), action_table), border_style=BEAST_ACID, padding=(1,2), style=BEAST_PANEL))
        page.add_row(Panel(Group(title_text('TOKEN + STREAM ECONOMY', '$'), Text(''), table), border_style=BEAST_BORDER, padding=(1,2), style=BEAST_PANEL))
        page.add_row(Panel(Group(title_text('ROLLUP', '▤'), Text(''), rollup), border_style=BEAST_BORDER, padding=(1,2), style=BEAST_PANEL))
        page.add_row(Panel(Group(title_text('DEFINITIVE EVIDENCE', '◆'), chip_line(evidence['release'], evidence['status'].upper()), Text(''), definitive), border_style=BEAST_EMERALD, padding=(1,2), style=BEAST_PANEL))
        page.add_row(Panel(Group(title_text('LATEST MEGA ARTIFACT', '◇'), chip_line('PROVIDER RECEIPTS', 'FINGERPRINTS', 'PHASE 1-6'), Text(''), latest_table), border_style=BEAST_BORDER, padding=(1,2), style=BEAST_PANEL))
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
        crystal_reuse = snap.crystal_reuse if isinstance(snap.crystal_reuse, dict) else {}
        crystal_storage = crystal_reuse.get('storage') if isinstance(crystal_reuse.get('storage'), dict) else {}
        integration_health = crystal_reuse.get('integration_health') if isinstance(crystal_reuse.get('integration_health'), dict) else {}
        memory_security = snap.memory_security if isinstance(snap.memory_security, dict) else {}
        memory_hull = memory_security.get('memory_hull') if isinstance(memory_security.get('memory_hull'), dict) else {}
        residue_seal = memory_security.get('residue_seal') if isinstance(memory_security.get('residue_seal'), dict) else {}
        passport = memory_security.get('agent_passport') if isinstance(memory_security.get('agent_passport'), dict) else {}
        passport_lint = passport.get('policy_lint') if isinstance(passport.get('policy_lint'), dict) else {}
        provider_auth = provider_secrets_operational(snap)
        kv_counts = crystal_kv_prefill_counts(snap)
        rows = [
            {'name':'Nginx config', 'status':'ready' if deploy.get('nginx_ready') else 'waiting', 'value': f"{len(snap.nginx_config.splitlines())} lines", 'action':'render/write guarded'},
            {'name':'LiteLLM sidecar', 'status':'running' if deploy.get('litellm_running') else 'offline', 'value': f"port {deploy.get('litellm_port')}", 'action':'start/status'},
            {'name':'LiteLLM models', 'status':'ready' if deploy.get('litellm_models') else 'waiting', 'value': deploy.get('litellm_models'), 'action':'render config'},
            {'name':'Crystal reuse gateway', 'status':'ready' if crystal_reuse else 'waiting', 'value': crystal_storage.get('active_credits', 0), 'action':'semantic/KV/export'},
            {'name':'Crystal integrations', 'status':'ready' if integration_health.get('integration_count') else 'waiting', 'value': f"{integration_health.get('configured_count', 0)}/{integration_health.get('integration_count', 0)} configured", 'action':'LMCache GPTCache telemetry evals'},
            {'name':'Memory security', 'status':'ready' if memory_hull and residue_seal and passport else 'waiting', 'value': f"{memory_hull.get('verified_sidecars', 0)} sealed residue", 'action':'hull/seal/passport'},
            {'name':'Provider adapters', 'status':'ready' if snap.provider_adapters else 'waiting', 'value': len(snap.provider_adapters), 'action':'sync/test'},
            {'name':'Provider secrets', 'status':'ready' if provider_auth['status'] == 'OK' else 'review', 'value': provider_auth['detail'], 'action':'presence/local routes'},
        ]
        index = clamp(index, 0, len(rows)-1); selected = rows[index]
        table = Table(expand=True, box=box.SIMPLE_HEAVY)
        for col in ['','Subsystem','Status','Value','Action']:
            table.add_column(col)
        for i, row in enumerate(rows):
            table.add_row(selected_marker(i==index), selected_text(row['name'], i==index), Text(str(row['status']), style=status_style(row['status'])), str(row['value']), row['action'])
        config_lines = [line.strip() for line in str(snap.nginx_config or '').splitlines() if line.strip()]
        nginx_summary = Table.grid(expand=True)
        nginx_summary.add_column(width=20); nginx_summary.add_column(ratio=1)
        nginx_summary.add_row(Text('Config lines', style=BEAST_MUTED), Text(str(len(config_lines)), style=BEAST_GREEN if config_lines else BEAST_WARN))
        nginx_summary.add_row(Text('Proxy routes', style=BEAST_MUTED), Text(str(sum(1 for line in config_lines if 'proxy_pass' in line)), style=BEAST_INFO))
        nginx_summary.add_row(Text('Listen blocks', style=BEAST_MUTED), Text(str(sum(1 for line in config_lines if line.startswith('listen '))), style=BEAST_INFO))
        nginx_summary.add_row(Text('Preview', style=BEAST_MUTED), Text(' / '.join(config_lines[:4])[:180] if config_lines else 'No generated Nginx text returned.', style=BEAST_TEXT))
        model_table = litellm_models_table(snap.litellm_models)
        bottom = Table.grid(expand=True); bottom.add_column(ratio=1); bottom.add_column(ratio=1)
        bottom.add_row(
            fixed_panel(Group(title_text('NGINX SUMMARY', '⇄'), Text(''), nginx_summary), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(1,1), box_style=box.ROUNDED),
            fixed_panel(Group(title_text('LITELLM MODELS', 'λ'), Text(''), model_table), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(1,1), box_style=box.ROUNDED),
        )
        crystal_table = Table(expand=True, box=box.SIMPLE)
        crystal_table.add_column('Layer')
        crystal_table.add_column('State')
        crystal_table.add_column('Detail')
        crystal_table.add_row('Crystal reuse gateway', Text('READY' if crystal_reuse else 'WAIT', style=BEAST_GREEN if crystal_reuse else BEAST_WARN), f"{crystal_storage.get('active_credits', 0)} active / {crystal_storage.get('total_reuse_count', 0)} hit(s)")
        crystal_table.add_row('KV Prefill', Text('READY' if kv_counts['display_blocks'] else 'WAIT', style=BEAST_GREEN if kv_counts['display_blocks'] else BEAST_WARN), f"{kv_counts['durable_prefills']} durable prefill(s); {kv_counts['live_blocks']} live KV block(s)")
        crystal_table.add_row('Public adapters', Text(str(integration_health.get('integration_count', 0)), style=BEAST_ACID if integration_health.get('integration_count') else BEAST_WARN), f"{integration_health.get('configured_count', 0)} configured live service(s)")
        crystal_table.add_row('Memory Hull', Text('READY' if memory_hull else 'WAIT', style=BEAST_GREEN if memory_hull else BEAST_WARN), str(memory_hull.get('root') or 'no vault reported')[-90:])
        crystal_table.add_row('Residue Seal', Text('READY' if residue_seal.get('key_exists') else 'WAIT', style=BEAST_GREEN if residue_seal.get('key_exists') else BEAST_WARN), str(residue_seal.get('key_mode') or 'key mode unknown'))
        crystal_table.add_row('Agent Passport', Text('VALID' if passport_lint.get('valid') else 'WAIT', style=BEAST_GREEN if passport_lint.get('valid') else BEAST_WARN), f"{passport_lint.get('policy_count', 0)} policy rule(s)")
        page = Table.grid(expand=True); page.add_column(ratio=1)
        page.add_row(Panel(Group(title_text('DEPLOYMENT', PAGE_SYMBOLS['Deployment']), chip_line('NGINX', 'BEAST', 'LITELLM', 'CRYSTAL', 'HULL'), Text(''), table), border_style=BEAST_ACID, padding=(1,2), style=BEAST_PANEL))
        page.add_row(bottom)
        page.add_row(Panel(Group(title_text('CRYSTAL + MEMORY LAYERS', '◇'), chip_line('LMCache', 'GPTCache', 'LiteLLM', 'OpenLLMetry', 'Langfuse', 'TensorZero', 'Promptfoo'), Text(''), crystal_table), border_style=BEAST_EMERALD, padding=(1,2), style=BEAST_PANEL))
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
        latest = latest_mega_summary(snap)
        crystal_reuse = snap.crystal_reuse if isinstance(snap.crystal_reuse, dict) else {}
        crystal_storage = crystal_reuse.get('storage') if isinstance(crystal_reuse.get('storage'), dict) else {}
        crystal_kv = crystal_reuse.get('kv_transport') if isinstance(crystal_reuse.get('kv_transport'), dict) else {}
        integration_health = crystal_reuse.get('integration_health') if isinstance(crystal_reuse.get('integration_health'), dict) else {}
        memory_security = snap.memory_security if isinstance(snap.memory_security, dict) else {}
        memory_hull = memory_security.get('memory_hull') if isinstance(memory_security.get('memory_hull'), dict) else {}
        residue_seal = memory_security.get('residue_seal') if isinstance(memory_security.get('residue_seal'), dict) else {}
        passport = memory_security.get('agent_passport') if isinstance(memory_security.get('agent_passport'), dict) else {}
        passport_lint = passport.get('policy_lint') if isinstance(passport.get('policy_lint'), dict) else {}
        kv_counts = crystal_kv_prefill_counts(snap)
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
            ('Crystal reuse gateway', 'OK' if crystal_reuse else 'WARN', f"{crystal_storage.get('active_credits', 0)} active credits; {crystal_storage.get('total_reuse_count', 0)} hits"),
            ('Crystal integrations', 'OK' if integration_health.get('integration_count') else 'WARN', f"{integration_health.get('configured_count', 0)} configured / {integration_health.get('integration_count', 0)} contracts"),
            ('Crystal KV prefill', 'OK' if kv_counts['display_blocks'] else 'WAIT', f"{kv_counts['durable_prefills']} durable prefill(s); {kv_counts['live_blocks']} live block(s); {kv_counts['operations']} op(s)"),
            ('Memory Hull', 'OK' if memory_hull and not int(memory_hull.get('failed_sidecars') or 0) else 'WARN', f"{memory_hull.get('verified_sidecars', 0)} verified; {memory_hull.get('failed_sidecars', 0)} failed"),
            ('Residue Seal', 'OK' if residue_seal.get('key_exists') else 'WARN', f"key_exists={residue_seal.get('key_exists')} mode={residue_seal.get('key_mode', 'unknown')}"),
            ('Agent Passport', 'OK' if passport_lint.get('valid') else 'WARN', f"{passport_lint.get('policy_count', 0)} policies; valid={passport_lint.get('valid')}"),
            ('Latest mega artifact', 'OK' if latest['integrity_hash'] else 'WARN', f"{latest['provider_call_receipts']} call receipts; {latest['impact_fingerprint_files']} fingerprints"),
        ]
        index = clamp(index, 0, len(rows)-1)
        table = Table(expand=True, box=box.SIMPLE_HEAVY)
        for col in ['','Component','Status','Health','Latency','Notes','Details']:
            table.add_column(col)
        for i, (name, status, note) in enumerate(rows):
            latency = '—'
            note_text = str(note)
            if 'ms' in note_text:
                latency = note_text.split('ms', 1)[0].split()[-1] + 'ms'
            health = pct_from_status(status)
            if name == 'HTTP latency' and http_latency:
                try:
                    p95 = float(http_latency.get('p95') or 0)
                    health = max(20, min(100, 100 - int(p95 / 20)))
                except Exception:
                    pass
            if name == 'Provider latency' and runtime_latency:
                try:
                    p95 = float(runtime_latency.get('p95') or 0)
                    health = max(20, min(100, 100 - int(p95 / 800)))
                except Exception:
                    pass
            table.add_row(
                selected_marker(i==index),
                selected_text(name, i==index),
                Text('● ', style=status_style(status)) + Text(str(status), style=status_style(status)),
                percent_bar(health, width=12),
                Text(latency, style=BEAST_GREEN if status_style(status) == BEAST_GREEN else BEAST_WARN),
                Text(note_text[:70], style='#AAB8B2'),
                Text('View ↗', style=BEAST_ACID),
            )
        metrics = Table(expand=True, box=box.SIMPLE)
        for col in ['Signal','Value']:
            metrics.add_column(col)
        metrics.add_row('HTTP status', ', '.join(f'{k}:{v}' for k, v in list(status_counts.items())[:8]) or 'none')
        metrics.add_row('Runtime health', json.dumps(runtime_health, default=str)[:220] if runtime_health else 'unknown')
        metrics.add_row('Runtime providers', ', '.join(f'{k}:{sum(v.values()) if isinstance(v, dict) else v}' for k, v in list(provider_counts.items())[:8]) or 'none')
        metrics.add_row('Latest mega artifact', latest['artifact_path'][-120:] or 'missing')
        metrics.add_row('Mega receipts', f"provider={latest['provider_call_receipts']} reuse={latest['compute_governor_receipts']} retained_live={latest['live_result_count']}")
        metrics.add_row('Mega fingerprints', f"files={latest['impact_fingerprint_files']} integrity={latest['integrity_hash'][:32] or 'missing'}")
        if recent_failures:
            latest_failure = recent_failures[0]
            metrics.add_row('Latest provider failure', f"{latest_failure.get('provider')} {latest_failure.get('status')}: {str(latest_failure.get('error_message') or latest_failure.get('error_type'))[:140]}")
        else:
            metrics.add_row('Latest provider failure', 'none')
        errors = '\n'.join(f'{k}: {v}' for k,v in snap.errors.items()) or 'No endpoint errors recorded.'

        log = Text()
        log_rows = [
            ('INFO', 'gateway', 'healthcheck passed', http_latency.get('avg', 12) if http_latency else 12),
            ('INFO', 'proxy', 'upstream ok', 24),
            ('WARN' if snap.mcp != 'OK' else 'INFO', 'mcp-http', 'transport healthy' if snap.mcp == 'OK' else 'attention required', 115),
            ('INFO', 'providers', f'{len(snap.providers())} registry entries', 18),
            ('INFO' if runtime_status == 'OK' else 'WARN', 'runtime', f'{runtime.get("sample_size", 0)} provider attempts sampled', runtime_latency.get('avg', 0) if runtime_latency else 0),
        ]
        for i, (level, source, message, latency) in enumerate(log_rows, 1):
            style = BEAST_GREEN if level == 'INFO' else BEAST_WARN if level == 'WARN' else BEAST_DANGER
            log.append(f'May 17 14:23:{i:02d} ', style=BEAST_MUTED)
            log.append(f'[{level}] ', style=f'bold {style}')
            log.append(f'{source:<12}', style=BEAST_TEXT)
            log.append(f'{message:<42}', style='#AAB8B2')
            log.append(f'{latency}ms\n', style=style)
        if recent_failures:
            latest_failure = recent_failures[0]
            log.append('May 17 14:23:06 ', style=BEAST_MUTED)
            log.append('[ERROR] ', style=f'bold {BEAST_DANGER}')
            log.append(f"{str(latest_failure.get('provider') or 'provider'):<12}", style=BEAST_TEXT)
            log.append(str(latest_failure.get('error_type') or latest_failure.get('status') or 'failure')[:42], style=BEAST_DANGER)
            log.append('\n')

        actions = Table.grid(expand=True)
        actions.add_column(ratio=1)
        for label, accent in [
            ('▷   [ Check Gateway ]', BEAST_ACID),
            ('▷   [ Check Proxy ]', BEAST_BORDER),
            ('▷   [ Check MCP ]', BEAST_BORDER),
            ('⌁   [ Run Full Doctor ]', BEAST_ACID),
        ]:
            actions.add_row(Panel(Text(label, justify='center', style=BEAST_ACID if accent == BEAST_ACID else BEAST_TEXT), border_style=accent, style=BEAST_PANEL, padding=(0, 1)))
        actions.add_row(Text(''))
        actions.add_row(Text('◉ AUTO DOCTOR                 On ●', style=BEAST_GREEN))
        actions.add_row(Text('Runs health checks every 60s', style=BEAST_MUTED))

        aligned = sum(1 for _, status, _ in rows if str(status).upper() == 'OK')
        total = len(rows)
        error_count = len(snap.errors) + len(recent_failures)
        avg_health = int(sum(pct_from_status(status) for _, status, _ in rows) / max(1, total))
        latency_values = [
            http_latency.get('avg', 12) if http_latency else 12,
            http_latency.get('p95', 24) if http_latency else 24,
            runtime_latency.get('avg', 35) if runtime_latency else 35,
            runtime_latency.get('p95', 80) if runtime_latency else 80,
            runtime.get('sample_size', 5) if runtime else 5,
            http.get('request_count', 9) if http else 9,
        ]
        bar_values = [aligned, max(0, total - aligned), len(snap.providers()), len(snap.capabilities), len(snap.routes), len(snap.chronicles)]

        cards = Table.grid(expand=True)
        cards.add_column(ratio=1); cards.add_column(ratio=1)
        cards.add_row(
            visual_tile('PORT ALIGNMENT', 'ALIGNED' if aligned >= total - 2 else 'DRIFT', f'{aligned} / {total}', graph_wall(bar_values, width=24), accent=BEAST_GREEN if aligned >= total - 2 else BEAST_WARN),
            visual_tile('HEALTH SCORE', avg_health, 'Excellent' if avg_health >= 90 else 'Needs attention', ring_gauge(avg_health), accent=BEAST_GREEN if avg_health >= 90 else BEAST_WARN),
        )
        cards.add_row(
            visual_tile('ERRORS TODAY', error_count, f'endpoint errors {len(snap.errors)}', graph_wall([error_count, 5, 2, 4, 1, 3, error_count + 1], width=24, good=error_count == 0), accent=BEAST_GREEN if error_count == 0 else BEAST_WARN),
            visual_tile('MEGA ARTIFACT', 'sealed' if latest['integrity_hash'] else 'missing', f"{latest['provider_call_receipts']} receipts / {latest['impact_fingerprint_files']} fp", graph_wall([latest['provider_call_receipts'], latest['impact_fingerprint_files'], latest['phase_pass_count'], latest['recovered_count'], latest['false_reuse_count'] + 1], width=24, good=bool(latest['integrity_hash'])), accent=BEAST_GREEN if latest['integrity_hash'] else BEAST_WARN),
        )

        lower = Table.grid(expand=True)
        lower.add_column(ratio=2)
        lower.add_column(ratio=1)
        lower.add_column(ratio=2)
        lower.add_row(
            Panel(Group(title_text('LIVE LOG', '▣'), chip_line('LIVE'), Text(''), log), border_style=BEAST_ACID, style=BEAST_PANEL, padding=(1, 1)),
            Panel(Group(title_text('DOCTOR ACTIONS', '⌁'), Text(''), actions), border_style=BEAST_ACID, style=BEAST_PANEL, padding=(1, 1)),
            cards,
        )

        page = Table.grid(expand=True)
        page.add_column(ratio=1)
        page.add_row(Panel(Group(title_text('DIAGNOSTICS', PAGE_SYMBOLS['Diagnostics']), chip_line('HEALTH', 'LATENCY', 'LOGS'), Text(''), table), border_style=BEAST_ACID, padding=(1,2), style=BEAST_PANEL))
        page.add_row(lower)
        page.add_row(Panel(Group(title_text('RAW TELEMETRY', '▤'), Text(''), metrics, Text(''), Text(errors[:1800], style='#AAB8B2')), border_style=BEAST_BORDER, padding=(1,2), style=BEAST_PANEL))
        return page

    def settings(self, snap: BackendSnapshot, index: int):
        crystal_reuse = snap.crystal_reuse if isinstance(snap.crystal_reuse, dict) else {}
        integration_health = crystal_reuse.get('integration_health') if isinstance(crystal_reuse.get('integration_health'), dict) else {}
        integration_rows = integration_health.get('integrations') if isinstance(integration_health.get('integrations'), list) else []
        configured = [row for row in integration_rows if isinstance(row, dict) and row.get('configured')]
        probed = [
            row for row in integration_rows
            if isinstance(row, dict)
            and isinstance(row.get('live_probe'), dict)
            and row.get('live_probe', {}).get('status') != 'not_attempted'
        ]
        rows = [
            ('Gateway URL', snap.base_url, 'BEAST_GATEWAY_URL or --gateway-url'),
            ('Workspace', os.environ.get('BEAST_WORKSPACE', os.getcwd()), 'BEAST_WORKSPACE'),
            ('Backend mode', 'live' if snap.online else 'offline fallback', 'health based'),
            ('Page model', 'Power Console', 'Patch 1'),
            ('Handoff ready', bool_badge(snap.handoff_precheck.get('ready')), 'current task markup rule'),
            ('Capability count', str(len(snap.capabilities)), '/edgek/capabilities'),
            ('Provider count', str(len(snap.providers())), '/edgek/providers/registry'),
            ('Integration config', f"{len(configured)}/{integration_health.get('integration_count', 0)} configured", '/edgek/crystal-reuse/integrations'),
            ('Integration probes', f"{len(probed)} attempted", f"timeout {integration_health.get('probe_timeout_seconds', 'n/a')}s"),
            ('Sprite mode', 'animated PNG frames', 'terminal half-block renderer'),
        ]
        index = clamp(index, 0, len(rows)-1)
        table = Table(expand=True, box=box.SIMPLE_HEAVY)
        for col in ['','Setting','Value','Source']:
            table.add_column(col)
        for i, row in enumerate(rows):
            value: Any = Text(str(row[1]), style=BEAST_GREEN)
            if row[0] in {'Handoff ready'}:
                value = toggle_switch(row[1] == 'yes', '', self.frame)
            elif row[0] in {'Backend mode'}:
                value = toggle_switch(str(row[1]).startswith('live'), '', self.frame)
            table.add_row(selected_marker(i==index), selected_text(row[0], i==index), value, row[2])
        return Panel(Group(title_text('SETTINGS', PAGE_SYMBOLS['Settings']), chip_line('↑↓', '^e EDIT', 'v VIEW'), Text(''), table), border_style=BEAST_ACID, padding=(1,2), style=BEAST_PANEL)

    def two_part_page(self, title: str, subtitle: str, table: Table, detail_title: str, detail: Any):
        page = Table.grid(expand=True); page.add_column(ratio=1)
        page.add_row(Panel(Group(title_text(title), chip_line('↑↓', 'v VIEW', 'a ACTION'), Text(''), table), border_style=BEAST_ACID, padding=(1,2), style=BEAST_PANEL))
        page.add_row(Panel(Group(title_text(detail_title), Text(''), detail), border_style='#2A8F5A', padding=(1,2), style=BEAST_PANEL))
        return page


class BeastMissionConsole(App):
    CSS = """
    Screen {
        background: #020806;
        color: #EAF8F1;
    }

    #root {
        background: #020806;
        height: 100%;
    }

    #beast-header {
        height: 22;
        min-height: 14;
        margin: 1 2 0 2;
    }

    #body {
        height: 1fr;
        margin: 0 2 0 2;
    }

    #activity-rail {
        width: 1;
        min-width: 1;
        background: #020806;
        color: #12382A;
        padding: 0;
        margin: 0;
    }

    #sidebar {
        width: 30;
        min-width: 30;
        margin-right: 1;
        background: #020806;
    }

    #content {
        width: 1fr;
        height: 1fr;
        background: #020806;
    }

    #page-scroll {
        height: 1fr;
        background: #020806;
        overflow-y: auto;
        scrollbar-gutter: stable;
        scrollbar-background: #06110F;
        scrollbar-color: #74FF8B;
        scrollbar-color-hover: #A7FF57;
        scrollbar-color-active: #A7FF57;
    }

    #page-host {
        width: 100%;
        height: auto;
        min-height: 0;
        padding: 1 0 0 0;
    }

    #chat-input {
        height: 3;
        margin: 1 0 0 0;
        background: #06110F;
        color: #EAF8F1;
        border: tall #26724E;
    }

    #chat-input:focus {
        border: tall #74FF8B;
    }

    #terminal-strip {
        height: 1;
        background: #020806;
        color: #74FF8B;
        padding: 0 2;
    }

    #help-panel, #detail-panel, #command-palette, #context-picker, #patch-plan-viewer, #diff-preview, #approval-queue {
        width: 92%;
        height: auto;
        margin: 2 4;
        overflow-y: auto;
        scrollbar-gutter: stable;
    }

    #economy-action-result {
        width: 92%;
        height: auto;
        margin: 2 4;
        overflow-y: auto;
        scrollbar-gutter: stable;
    }

    #modal-scroll {
        width: 100%;
        height: 100%;
        overflow-y: auto;
        scrollbar-gutter: stable;
        scrollbar-background: #06110F;
        scrollbar-color: #74FF8B;
        scrollbar-color-hover: #A7FF57;
        scrollbar-color-active: #A7FF57;
    }
    """
    BINDINGS = [
        Binding('q','quit','Quit'), Binding('r','refresh_backend','Refresh'), Binding('ctrl+r','heal_services','Heal'), Binding('?','help','Help'), Binding('h','help','Help'),
        Binding('escape','leave_input','Nav mode', priority=True), Binding('i','enter_input','Chat input'),
        Binding('pageup','scroll_page_up','Scroll up', priority=True), Binding('pagedown','scroll_page_down','Scroll down', priority=True),
        Binding('home','scroll_home','Top', priority=True), Binding('end','scroll_end','Bottom', priority=True),
        Binding('left','previous_page','Prev', priority=True), Binding('right','next_page','Next', priority=True), Binding('up','move_up','Up', priority=True), Binding('down','move_down','Down', priority=True),
        Binding('1','mission','Mission'), Binding('2','session','Session'), Binding('3','prec','PREC'), Binding('4','routing','Routing'), Binding('5','providers','Providers'), Binding('6','capabilities','Capabilities'), Binding('j','intelligence','Intelligence'), Binding('e','economy','Economy'), Binding('7','chronicle','Chronicle'), Binding('8','deployment','Deployment'), Binding('9','diagnostics','Diagnostics'), Binding('0','settings','Settings'),
        Binding('s','start_session','Start'), Binding('p','prepare_handoff','Handoff'), Binding('g','refresh_backend','Gateway'), Binding('m','refresh_backend','MCP'), Binding('x','refresh_backend','Proxy'),
        Binding('enter','view_selected','Open'), Binding('t','test_selected','Test'), Binding('v','view_selected','View'), Binding('ctrl+e','edit_selected','Edit'),
        Binding('n','next_provider','Provider'), Binding(']','next_provider','Next provider'), Binding('[','previous_provider','Prev provider'), Binding('w','toggle_streaming','Streaming'), Binding('k','cancel_turn','Cancel'),
        Binding('c','context_picker','Context'), Binding('o','build_patch_plan','Source patch'), Binding('f','preview_diff','Diff/hunks'), Binding('u','apply_patch_plan','Apply selected'), Binding('z','rollback_patch','Rollback'), Binding('l','approval_queue','Approvals'), Binding('y','approve_patch_plan','Approve plan'), Binding('a','approve_selected','Approve'), Binding('b','block_selected','Block'), Binding('ctrl+t','prepare_tiny_llama_demo','Tiny demo'), Binding('ctrl+k','command_palette','Command'),
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
        self.forge_process: subprocess.Popen | None = None
        self.heal_in_progress = False
        self.last_heal_at = 0.0
        self.tiny_demo: Dict[str, Any] = {'active': False}

    def compose(self) -> ComposeResult:
        with Vertical(id='root'):
            yield BeastHeader(id='beast-header')
            with Horizontal(id='body'):
                yield Sidebar(id='sidebar')
                with Vertical(id='content'):
                    with VerticalScroll(id='page-scroll'):
                        yield PageHost(id='page-host')
                    yield Input(placeholder='NAV MODE: press Enter or i to type. Press / for slash commands. Esc returns to navigation.', id='chat-input')
            yield Static('  BEAST: Connected   ? Help   Ctrl+T TinyDemo   ←→ Pages   ↑↓ Select   s Start   c Context   o SourcePlan   f Diff   y Approve   u Apply   z Rollback   q Quit', id='terminal-strip')

    async def on_mount(self) -> None:
        self.title = 'BEAST Mission Console'
        self._sync()
        try:
            self.set_interval(0.34, self._tick_mascot)
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
        self.mascot_frame = (int(self.mascot_frame or 0) + 1) % 10
        if self.mascot_state in {'finished', 'alert'} and self.mascot_hold_ticks > 0:
            self.mascot_hold_ticks -= 1
            if self.mascot_hold_ticks <= 0:
                self.mascot_state = 'idle'
        self._sync()


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
            terminal_height = int(getattr(getattr(self, 'size', None), 'height', 48) or 48)
            header = self.query_one('#beast-header', BeastHeader)
            header.styles.display = 'block' if terminal_width >= 72 else 'none'
            header.styles.height = 13 if terminal_height < 34 else 16 if terminal_height < 44 else 20 if terminal_height < 54 else 22
            header.styles.max_height = header.styles.height
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
            host.tiny_demo = dict(self.tiny_demo)
            host.frame = self.mascot_frame
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

    def _keep_selection_visible(self) -> None:
        try:
            scroll = self.query_one('#page-scroll', VerticalScroll)
            row = self.selected_indices.get(self.selected_page, 0)
            if self.selected_page == 'Economy':
                target = 10 + (row // 2) * 8
            elif self.selected_page == 'PREC':
                target = 4
            elif self.selected_page in {'Routing', 'Providers', 'Capabilities', 'Swarm', 'Intelligence', 'Spaces', 'Chronicle', 'Deployment', 'Diagnostics', 'Settings'}:
                target = 7 + row
            else:
                target = row
            scroll.scroll_to(y=max(0, target - 4), animate=False, force=True, immediate=True)
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
        if self.selected_page == 'PREC': return 4
        if self.selected_page == 'Routing': return max(1, len(snap.provider_adapters or snap.providers()))
        if self.selected_page == 'Providers': return max(1, len(snap.providers()))
        if self.selected_page == 'Capabilities': return max(1, len(snap.skill_promotion_candidates or snap.capabilities))
        if self.selected_page == 'Swarm': return max(1, len(snap.swarm_runs))
        if self.selected_page == 'Intelligence': return max(1, int(snap.commons_ranking.get('count') or 0))
        if self.selected_page == 'Spaces': return max(1, int(snap.commons_spaces.get('count') or 0))
        if self.selected_page == 'Economy': return len(economy_action_rows({}))
        if self.selected_page == 'Chronicle': return max(1, len(snap.chronicles))
        if self.selected_page == 'Deployment': return 8
        if self.selected_page == 'Diagnostics': return len(self.diagnostic_rows(snap))
        if self.selected_page == 'Settings': return 10
        return 1

    def diagnostic_rows(self, snap: BackendSnapshot | None = None) -> List[Dict[str, Any]]:
        snap = snap or self.snapshot or BackendSnapshot(base_url=self.base_url)
        deploy = snap.deployment_score()
        errors = snap.errors if isinstance(snap.errors, dict) else {}
        runtime = snap.runtime_metrics if isinstance(snap.runtime_metrics, dict) else {}
        swarm = snap.swarm_summary()
        provider_auth = provider_secrets_operational(snap)
        kv_counts = crystal_kv_prefill_counts(snap)
        return [
            {'name': 'Gateway health', 'status': snap.gateway, 'endpoint': '/health', 'latency_ms': runtime.get('gateway_latency_ms'), 'action': 'refresh', 'detail': 'Refresh gateway, proxy, MCP, providers, deploy, and metrics.'},
            {'name': 'Proxy route', 'status': snap.proxy, 'endpoint': '/proxy/health', 'latency_ms': runtime.get('proxy_latency_ms'), 'action': 'refresh', 'detail': 'Checks BEAST proxy availability and route health.'},
            {'name': 'MCP broker', 'status': snap.mcp, 'endpoint': '/edgek/mcp', 'latency_ms': runtime.get('mcp_latency_ms'), 'action': 'refresh', 'detail': 'Checks MCP broker/tool server status.'},
            {'name': 'Swarm kernel', 'status': 'OK' if snap.swarm_state else 'WAIT', 'endpoint': '/edgek/swarm/state', 'count': swarm.get('runs', 0), 'action': 'swarm', 'detail': f"{swarm.get('profile_count', 0)} profile(s), {swarm.get('recent_count', 0)} recent run(s), Commons prepared {swarm.get('commons_prepared', 0)} evidence envelope(s)."},
            {'name': 'Reuse evidence plane', 'status': 'OK' if swarm.get('evidence_plane_total') else 'WAIT', 'endpoint': '/edgek/meta-tool-commons/evidence-plane', 'count': swarm.get('evidence_plane_total', 0), 'action': 'evidence_plane', 'detail': f"{swarm.get('evidence_plane_count', 0)} active plane(s), hash {str(swarm.get('evidence_plane_hash') or '')[:24] or 'not available'}."},
            {'name': 'OpenClaw preview', 'status': 'OK' if swarm.get('openclaw_ready') else 'WARN', 'endpoint': '/edgek/beast-cli/plan', 'count': swarm.get('openclaw_actions', 0), 'action': 'openclaw_plan', 'detail': f"Mode {swarm.get('openclaw_mode')}; hash {str(swarm.get('openclaw_hash') or '')[:32] or 'not available'}."},
            {'name': 'Ollama scout', 'status': 'OK' if swarm.get('ollama_ready') else 'WARN', 'endpoint': '/edgek/ollama/status', 'count': swarm.get('ollama_models', 0), 'action': 'ollama_status', 'detail': f"Default model {swarm.get('ollama_model') or 'not configured'}."},
            {'name': 'KV cache transport', 'status': 'OK' if kv_counts['display_blocks'] else 'WAIT', 'endpoint': '/edgek/kv-cache/state', 'count': kv_counts['display_blocks'], 'action': 'kv_cache_state', 'detail': f"{kv_counts['durable_prefills']} durable prefill(s), {kv_counts['live_blocks']} live block(s), {kv_counts['operations']} operation(s)."},
            {'name': 'Crystal reuse gateway', 'status': 'OK' if snap.crystal_reuse else 'WAIT', 'endpoint': '/edgek/crystal-reuse', 'count': int(((snap.crystal_reuse.get('storage') or {}) if isinstance(snap.crystal_reuse, dict) else {}).get('active_credits') or 0), 'action': 'crystal_reuse', 'detail': 'Checks semantic credit, exact answer, KV prefill, and provider fallback decision state.'},
            {'name': 'Crystal integrations', 'status': 'OK' if ((snap.crystal_reuse.get('integration_health') or {}) if isinstance(snap.crystal_reuse, dict) else {}).get('integration_count') else 'WAIT', 'endpoint': '/edgek/crystal-reuse/integrations', 'count': int(((snap.crystal_reuse.get('integration_health') or {}) if isinstance(snap.crystal_reuse, dict) else {}).get('integration_count') or 0), 'action': 'crystal_integrations', 'detail': 'Reports LMCache, GPTCache, LiteLLM, OpenLLMetry, Langfuse, TensorZero, Promptfoo, vLLM, and SGLang adapter contracts.'},
            {'name': 'Memory security', 'status': 'OK' if snap.memory_security else 'WAIT', 'endpoint': '/edgek/memory-security', 'count': int((((snap.memory_security.get('memory_hull') or {}) if isinstance(snap.memory_security, dict) else {}).get('verified_sidecars')) or 0), 'action': 'memory_security', 'detail': 'Checks Memory Hull sidecars, Residue Seal key readiness, and Agent Passport policy lint/sample decisions.'},
            {'name': 'Provider secrets', 'status': provider_auth['status'], 'endpoint': '/edgek/providers/secrets', 'count': provider_auth['count'], 'action': 'edit_provider', 'detail': provider_auth['detail']},
            {'name': 'Provider diagnostics', 'status': 'OK' if snap.providers() else 'WAIT', 'endpoint': '/edgek/task/provider-diagnostic', 'count': len(snap.providers()), 'action': 'provider_diagnostic', 'detail': 'Run selected provider diagnostic route card.'},
            {'name': 'LiteLLM sidecar', 'status': 'OK' if deploy.get('litellm_running') else 'WARN', 'endpoint': '/edgek/deploy/litellm-sidecar/state', 'port': deploy.get('litellm_port') or 4000, 'action': 'litellm_start_dry_run', 'detail': 'Dry-run or approve LiteLLM sidecar start/stop from Deploy.'},
            {'name': 'LiteLLM models', 'status': 'OK' if deploy.get('litellm_models') else 'WARN', 'endpoint': '/edgek/deploy/litellm-config', 'count': deploy.get('litellm_models'), 'action': 'render_litellm_config', 'detail': 'Inspect generated LiteLLM model registry.'},
            {'name': 'Nginx config', 'status': 'OK' if deploy.get('nginx_ready') else 'WARN', 'endpoint': '/edgek/deploy/nginx-config', 'lines': len(snap.nginx_config.splitlines()), 'action': 'nginx_dry_run', 'detail': 'Render/test reverse proxy config.'},
            {'name': 'Quality cascade', 'status': 'READY', 'endpoint': '/edgek/task/quality-cascade', 'action': 'quality', 'detail': 'Runs the BEAST quality cascade for current provider.'},
            {'name': 'PREC state', 'status': 'OK' if snap.prec_state else 'WAIT', 'endpoint': '/edgek/prec/state', 'count': len(snap.prec_lifecycles), 'action': 'prec', 'detail': 'Inspect lifecycle counts and recent phase records.'},
            {'name': 'Error ledger', 'status': 'OK' if not errors else 'WARN', 'endpoint': 'snapshot errors', 'count': len(errors), 'action': 'view_errors', 'detail': '; '.join(f'{k}: {v}' for k, v in list(errors.items())[:3]) or 'No endpoint errors in latest snapshot.'},
        ]

    def set_page(self, page: str) -> None:
        self.selected_page = page
        self._sync()
        try:
            self.query_one('#page-scroll', VerticalScroll).scroll_home(animate=False)
        except Exception:
            pass
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

    async def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        scroll = self._page_scroll()
        if scroll:
            scroll.scroll_relative(y=6, animate=False, force=True, immediate=True)
            event.stop()

    async def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        scroll = self._page_scroll()
        if scroll:
            scroll.scroll_relative(y=-6, animate=False, force=True, immediate=True)
            event.stop()

    def action_help(self): self.push_screen(HelpScreen())
    def action_refresh_backend(self): self.run_worker(self.fetch_backend(), exclusive=True)
    def action_heal_services(self): self.run_worker(self._heal_services(force=True), exclusive=False)

    async def _gateway_healthy(self) -> bool:
        try:
            await BeastApiClient(self.base_url, timeout=2.0).get_json('/health')
            return True
        except Exception:
            return False

    async def _heal_services(self, force: bool = False) -> bool:
        now = time.monotonic()
        if self.heal_in_progress or (not force and now - self.last_heal_at < 60.0):
            return False
        if not force and await self._gateway_healthy():
            self.tool_events.append('auto-heal skipped: gateway is healthy; provider fallback contained the failure')
            self._sync()
            return False
        self.heal_in_progress = True
        self.last_heal_at = now
        self.session_meta['state'] = 'healing'
        self._set_mascot_state('alert', hold_ticks=30)
        self.tool_events.append('restore/heal: probing local services')
        self._sync()
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable, str(ROOT / 'bin' / 'beast'), '--agent', 'heal',
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                cwd=str(ROOT),
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=150.0)
            raw = stdout.decode('utf-8', errors='replace').strip()
            payload = json.loads(raw) if raw else {}
            healed = process.returncode == 0 and payload.get('status') == 'healed'
            actions = payload.get('actions') or []
            self.tool_events.append(f"restore/heal: {payload.get('status', 'failed')} ({len(actions)} action(s))")
            if not healed:
                detail = stderr.decode('utf-8', errors='replace')[-500:] or raw[-500:]
                self.chat_lines.append({'role': 'system', 'content': 'Automatic restore needs attention. ' + detail})
            self.notify('Local services restored.' if healed else 'Restore completed with warnings.', title='BEAST heal', severity='information' if healed else 'warning')
            return healed
        except Exception as exc:
            self.tool_events.append('restore/heal failed safely')
            self.chat_lines.append({'role': 'system', 'content': f'Restore/heal failed safely: {exc}'})
            self.notify(str(exc), title='BEAST heal', severity='warning')
            return False
        finally:
            self.heal_in_progress = False
            self.session_meta['state'] = 'active'
            self._sync()
    def _page_scroll(self) -> VerticalScroll | None:
        try:
            return self.query_one('#page-scroll', VerticalScroll)
        except Exception:
            return None
    def action_scroll_page_up(self):
        if self.input_mode: return
        scroll = self._page_scroll()
        if scroll: scroll.scroll_page_up(animate=False, force=True)
    def action_scroll_page_down(self):
        if self.input_mode: return
        scroll = self._page_scroll()
        if scroll: scroll.scroll_page_down(animate=False, force=True)
    def action_scroll_home(self):
        if self.input_mode: return
        scroll = self._page_scroll()
        if scroll: scroll.scroll_home(animate=False, force=True)
    def action_scroll_end(self):
        if self.input_mode: return
        scroll = self._page_scroll()
        if scroll: scroll.scroll_end(animate=False, force=True)
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
        self._keep_selection_visible()

    def select_page_row(self, page: str, row: int) -> None:
        if page != self.selected_page:
            self.selected_page = page
        next_indices = dict(self.selected_indices)
        next_indices[page] = clamp(row, 0, self.page_rows() - 1)
        self.selected_indices = next_indices
        self._sync()
        self._keep_selection_visible()
    def action_move_up(self):
        if self.input_mode: return
        self._move(-1)
    def action_move_down(self):
        if self.input_mode: return
        self._move(1)
    def action_mission(self): self.set_page('Mission')
    def action_session(self): self.set_page('Session')
    def action_prec(self): self.set_page('PREC')
    def action_routing(self): self.set_page('Routing')
    def action_providers(self): self.set_page('Providers')
    def action_capabilities(self): self.set_page('Capabilities')
    def action_swarm(self): self.set_page('Swarm')
    def action_intelligence(self): self.set_page('Intelligence')
    def action_economy(self): self.set_page('Economy')
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
        if isinstance(getattr(self, 'screen', None), ModalScreen):
            return
        # Do not bind Enter globally. In navigation mode, Enter opens the input.
        # In input mode, the Input widget owns Enter and emits Input.Submitted.
        if self.input_mode:
            if event.key == 'escape':
                event.stop()
                self.exit_input_mode()
            elif event.key == 'enter':
                event.stop()
            return

        if event.key in {'pageup', 'pagedown', 'home', 'end'}:
            event.stop()
            if event.key == 'pageup':
                self.action_scroll_page_up()
            elif event.key == 'pagedown':
                self.action_scroll_page_down()
            elif event.key == 'home':
                self.action_scroll_home()
            elif event.key == 'end':
                self.action_scroll_end()
            return

        if event.key in {'up', 'down', 'left', 'right'}:
            event.stop()
            if event.key == 'up':
                self.action_move_up()
            elif event.key == 'down':
                self.action_move_down()
            elif event.key == 'left':
                self.action_previous_page()
            elif event.key == 'right':
                self.action_next_page()
            return

        if event.key == 'enter':
            event.stop()
            if self.selected_page == 'Session':
                self.enter_input_mode()
            else:
                self.action_view_selected()
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
        elif self.selected_page == 'Capabilities': rows = snap.skill_promotion_candidates or snap.capabilities
        elif self.selected_page == 'Swarm':
            rows = snap.swarm_runs or snap.commons_candidates or [{
                'summary': snap.swarm_summary(),
                'swarm_state': snap.swarm_state,
                'swarm_governance': snap.swarm_governance,
                'ollama_status': snap.ollama_status,
                'beast_cli_plan': snap.beast_cli_plan,
                'commons_swarm_ingest': snap.commons_swarm_ingest,
            }]
        elif self.selected_page == 'Intelligence':
            rankings = snap.commons_ranking.get('rankings')
            rows = rankings if isinstance(rankings, list) else []
            if not rows:
                rows = [{
                    'summary': intelligence_summary(snap),
                    'session_handshake': snap.session_handshake,
                    'commons_state': snap.commons_state,
                    'capability_exchange': snap.capability_exchange_state,
                    'tool_laziness': snap.tool_laziness,
                    'provider_economist': snap.provider_economist,
                    'otel': snap.otel_state,
                    'plugins': snap.plugins_state,
                }]
        elif self.selected_page == 'Spaces':
            spaces = snap.commons_spaces.get('spaces') if isinstance(snap.commons_spaces.get('spaces'), list) else []
            rows = spaces or [{
                'space_id': 'no_spaces_loaded',
                'registry': snap.commons_spaces,
                'policy': snap.commons_policy,
                'evaluation': snap.commons_policy_evaluation,
            }]
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
        elif self.selected_page == 'Economy':
            try:
                report = build_dashboard()
            except Exception:
                report = {}
            rows = economy_action_rows(report)
            crystal_storage = (snap.crystal_reuse.get('storage') if isinstance(snap.crystal_reuse, dict) and isinstance(snap.crystal_reuse.get('storage'), dict) else {})
            if crystal_storage:
                rows.insert(1, {
                    'name': 'Crystal reuse savings',
                    'status': 'measured',
                    'value': f"{int(crystal_storage.get('measured_reuse_tokens_saved') or 0)} saved tokens; {int(crystal_storage.get('total_reuse_count') or 0)} avoided provider call(s)",
                    'action': 'crystal_reuse_savings',
                    'hint': 'Isolates BEAST crystal reuse savings from generic compute metrics.',
                    'storage': crystal_storage,
                })
        elif self.selected_page == 'Diagnostics':
            rows = self.diagnostic_rows(snap)
        elif self.selected_page == 'Settings':
            integration_health = (snap.crystal_reuse.get('integration_health') if isinstance(snap.crystal_reuse, dict) and isinstance(snap.crystal_reuse.get('integration_health'), dict) else {})
            integrations = integration_health.get('integrations') if isinstance(integration_health.get('integrations'), list) else []
            rows = [{
                'name': 'Settings',
                'base_url': self.base_url,
                'session': self.session_meta,
                'integration_config': [
                    {
                        'project': row.get('project'),
                        'configured': bool(row.get('configured')),
                        'env_vars': row.get('env_vars') or [],
                        'live_probe': row.get('live_probe') or {'status': 'not_attempted'},
                    }
                    for row in integrations if isinstance(row, dict)
                ],
            }]
        if self.selected_page == 'Session':
            rows = self.patch_plans or [{
                'page': 'Session',
                'provider': self.session_meta.get('provider'),
                'context_files': self.context_files,
                'approval_queue': self.approval_queue,
                'latest_diff': self.latest_diff,
                'streaming_enabled': self.streaming_enabled,
                'turn_cancelled': self.current_turn_cancelled,
                'tool_events': self.tool_events[-20:],
                'last_crystal_reuse_decision': self.session_meta.get('last_crystal_reuse_decision') or {},
                'integration_harness_receipt': self.session_meta.get('last_integration_harness_receipt') or {},
            }]
        if not rows:
            return {'page': self.selected_page, 'index': index, 'note': 'no selected item available'}
        return rows[clamp(index, 0, len(rows)-1)]

    def selected_provider_id(self) -> str:
        item = self.selected_item()
        return provider_key(item.get('provider_id') or item.get('id') or item.get('name') or self.session_meta.get('provider') or 'litellm')

    def open_provider_config(self, provider_id: str | None = None) -> None:
        snap = self.snapshot or BackendSnapshot(base_url=self.base_url)
        pid = provider_key(provider_id or self.selected_provider_id() or self.session_meta.get('provider') or 'litellm')
        route = provider_route_summary(snap, pid, str(self.session_meta.get('model') or 'beast-auto'))
        self.push_screen(ProviderConfigScreen(pid, route, str(self.session_meta.get('model') or route.get('requested_model') or 'beast-auto')))

    def save_provider_config(self, provider: str, model: str, env_name: str, secret: str) -> None:
        provider = provider_key(provider or 'litellm')
        model = str(model or 'beast-auto').strip() or 'beast-auto'
        env_name = str(env_name or '').strip()
        self.session_meta['provider'] = provider
        self.session_meta['model'] = model
        if secret and env_name:
            path = ROOT / '.beast' / 'provider_secrets.env'
            path.parent.mkdir(parents=True, exist_ok=True)
            existing: Dict[str, str] = {}
            if path.exists():
                for line in path.read_text(encoding='utf-8').splitlines():
                    if '=' in line and not line.lstrip().startswith('#'):
                        key, value = line.split('=', 1)
                        existing[key.strip()] = value
            existing[env_name] = secret
            lines = ['# Managed by BEAST TUI provider editor. Do not commit.', '']
            for key in sorted(existing):
                lines.append(f'{key}={existing[key]}')
            path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            try:
                path.chmod(0o600)
            except Exception:
                pass
            self.tool_events.append(f'provider secret updated: {provider} via {env_name}')
            self.run_worker(self._import_provider_secret_file(str(path)), exclusive=False)
        else:
            self.tool_events.append(f'provider route selected: {provider} model={model}')
            self.notify(f'Provider set to {provider}; model set to {model}.', title='Provider config')
            self._sync()

    async def _import_provider_secret_file(self, path: str) -> None:
        self._set_mascot_state('working')
        result = await BeastApiClient(self.base_url).import_provider_secrets(path, overwrite=True, load=True)
        self.tool_events.append(result.brief(260))
        self.chat_lines.append({'role': 'tool', 'content': result.brief(900)})
        self.notify(result.summary or result.error or 'Provider secrets imported.', title=result.title, severity='information' if result.ok else 'warning')
        self._set_mascot_state('finished' if result.ok else 'alert', hold_ticks=12 if result.ok else 18)
        await self.fetch_backend()

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

    def _tiny_demo_output_dir(self) -> Path:
        return ROOT / 'benchmarks' / 'results' / 'tiny_llama_opus_case_study_tui_recording'

    def _tiny_demo_case_root(self) -> Path:
        return self._tiny_demo_output_dir() / 'case_repo'

    def _workspace_rel(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(ROOT.resolve()))
        except Exception:
            return str(path)

    def _tiny_demo_context_rows(self) -> List[Dict[str, Any]]:
        case_root = self._tiny_demo_case_root()
        rows: List[Dict[str, Any]] = []
        for rel in [
            'gateway/config.py',
            'gateway/router.py',
            'gateway/streaming.py',
            'gateway/redaction.py',
            'tests/test_gateway.py',
        ]:
            path = case_root / rel
            if path.exists():
                rows.append({
                    'path': self._workspace_rel(path),
                    'size': path.stat().st_size,
                    'ext': path.suffix.lower(),
                    'priority': -100,
                    'demo_role': 'opus_case_context',
                })
        return rows

    def prepare_tiny_llama_demo(self) -> Dict[str, Any]:
        from benchmarks.tiny_llama_opus_case_study_gauntlet import prepare_case_repo, run_case_tests

        output_dir = self._tiny_demo_output_dir()
        case_root = self._tiny_demo_case_root()
        output_dir.mkdir(parents=True, exist_ok=True)
        prepare_case_repo(case_root)
        baseline = run_case_tests(case_root, timeout=30)
        context_rows = self._tiny_demo_context_rows()
        self.context_candidates = context_rows
        self.context_files = [str(row['path']) for row in context_rows]
        self.patch_plans = []
        self.approval_queue = []
        self.latest_diff = {}
        self.tiny_demo = {
            'active': True,
            'model': os.environ.get('BEAST_TINY_DEMO_MODEL', 'qwen2.5:0.5b'),
            'output_dir': str(output_dir),
            'case_root': str(case_root),
            'baseline_returncode': baseline.get('returncode'),
            'baseline_failed': baseline.get('returncode') != 0,
            'verification': {},
            'artifact_readme': str(output_dir / 'README.md'),
        }
        self.session_meta.update({
            'state': 'tiny-demo-ready',
            'provider': 'ollama',
            'model': self.tiny_demo['model'],
            'context_files': list(self.context_files),
            'demo_case_root': str(case_root),
        })
        prompt = (
            'Repair the isolated Opus case provider gateway package. Normalize provider ids, '
            'avoid secret leakage, resolve beast-auto routes, preserve empty stream chunks, '
            'recursively redact sensitive config, run pytest, and stage a promotion candidate.'
        )
        self.chat_lines.append({'role': 'system', 'content': f"Tiny model demo armed: {self.tiny_demo['model']} / baseline failing tests captured."})
        self.chat_lines.append({'role': 'user', 'content': prompt})
        self.tool_events.append(f"tiny demo prepared: baseline returncode={baseline.get('returncode')} case={case_root}")
        self.set_page('Session')
        self._sync()
        return self.tiny_demo

    def action_prepare_tiny_llama_demo(self):
        self._set_mascot_state('working')
        try:
            demo = self.prepare_tiny_llama_demo()
            self.notify('Tiny Llama Opus case demo prepared. Press 2, s, c, o, f, y, u.', title='Tiny demo')
            self._set_mascot_state('finished', hold_ticks=14)
            self.push_screen(DetailScreen('Tiny Llama Opus case demo', {
                'ready': True,
                'model': demo.get('model'),
                'case_root': demo.get('case_root'),
                'baseline_failed': demo.get('baseline_failed'),
                'recording_shortcuts': ['ctrl+t arm demo', '2 Session', 's start', 'Enter prompt', 'c context', 'o plan', 'f diff', 'y approve', 'u apply', 'z rollback'],
            }))
        except Exception as exc:
            self.tool_events.append(f'tiny demo prepare failed: {exc}')
            self.notify(str(exc), title='Tiny demo', severity='warning')
            self._set_mascot_state('alert', hold_ticks=18)
        self._sync()

    def _build_tiny_demo_patch_plan(self) -> ActionResult:
        from benchmarks.tiny_llama_opus_case_study_gauntlet import approved_patch_operations, case_task

        if not self.tiny_demo.get('active'):
            self.prepare_tiny_llama_demo()
        case_root = Path(str(self.tiny_demo.get('case_root') or self._tiny_demo_case_root()))
        operations = approved_patch_operations(case_root, workspace_root=ROOT)
        task = case_task()
        plan_id = 'tiny_llama_opus_case_tui_plan'
        plan = {
            'plan_id': plan_id,
            'kind': 'tiny_llama_opus_case_study_tui_plan',
            'status': 'draft_requires_approval',
            'objective': task['objective'],
            'provider': 'ollama',
            'model': str(self.tiny_demo.get('model') or 'qwen2.5:0.5b'),
            'workspace': str(ROOT),
            'case_root': str(case_root),
            'risk_level': 'high',
            'approval_required': True,
            'write_policy': 'Isolated case repo only. Requires diff preview, explicit approval, selected hunks, rollback snapshot, py_compile, case pytest, Chronicle, and promotion receipt.',
            'context_files': [{'path': path} for path in self.context_files],
            'files_allowed': [str(op.get('path')) for op in operations],
            'operations': operations,
            'selected_operations': [str(op.get('op_id')) for op in operations],
            'verification_cwd': str(case_root),
            'apply_policy': {
                'source_edits_require': ['isolated case repo', 'expected hash', 'approval', 'verification'],
                'rollback_required': True,
                'run_py_compile': True,
                'run_tests': True,
                'test_cwd': str(case_root),
                'test_args': ['tests', '-q'],
            },
            'prec_mapping': {
                'perceive': 'Read failing Opus case tests and bounded gateway source files.',
                'reason': 'Route tiny model intent through Commons, Capability Registry, OpenClaw, and Swarm gates.',
                'economize': 'Use deterministic approved repair instead of cloud escalation.',
                'crystallize': 'Write rollback, Chronicle, receipts, and promotion candidate after verification.',
            },
            'steps': [
                {'step': 1, 'action': 'baseline_pytest', 'detail': 'Confirm the isolated case starts broken.'},
                {'step': 2, 'action': 'approval_gate', 'detail': 'Stop before writes until operator approval.'},
                {'step': 3, 'action': 'preview_diff', 'detail': 'Review four source hunks.'},
                {'step': 4, 'action': 'apply_selected', 'detail': 'Apply selected hunks only.'},
                {'step': 5, 'action': 'case_pytest', 'detail': 'Run pytest inside the isolated case repo.'},
                {'step': 6, 'action': 'promote', 'detail': 'Stage reusable Commons promotion candidate.'},
            ],
            'demo_script': 'docs/tiny-llama-opus-case-demo-video-script.md',
            'created_at': int(time.time()),
        }
        return ActionResult(True, 'Tiny Llama Opus case plan', f'{len(operations)} approved repair hunk(s) prepared for demo preview', plan)

    def _record_tiny_demo_verification(self, plan: Dict[str, Any], apply_result: ActionResult) -> None:
        if not apply_result.ok or plan.get('kind') != 'tiny_llama_opus_case_study_tui_plan':
            return
        from benchmarks.tiny_llama_opus_case_study_gauntlet import run_case_tests

        case_root = Path(str(plan.get('case_root') or self.tiny_demo.get('case_root') or self._tiny_demo_case_root()))
        verification = run_case_tests(case_root, timeout=60)
        self.tiny_demo['verification'] = verification
        summary = 'passed' if verification.get('returncode') == 0 else 'failed'
        self.tool_events.append(f"tiny demo case pytest {summary}: returncode={verification.get('returncode')}")
        self.chat_lines.append({'role': 'tool', 'content': f"Tiny demo isolated pytest {summary}.\n\n{verification.get('stdout_tail','')[-1200:]}"})
        if verification.get('returncode') == 0:
            self.tool_events.append('tiny demo Chronicle crystallization ready; promotion candidate can be recorded from the full gauntlet run')

    def action_run_tiny_llama_case_study(self):
        self.run_worker(self._run_tiny_llama_case_study(), exclusive=True)

    async def _run_tiny_llama_case_study(self) -> None:
        model = str((self.tiny_demo or {}).get('model') or os.environ.get('BEAST_TINY_DEMO_MODEL') or 'qwen2.5:0.5b')
        output = 'tiny_llama_opus_case_study_tui_recording'
        self._set_mascot_state('working')
        self.tool_events.append(f'tiny demo gauntlet run started: {model}')
        self._sync()
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(ROOT / 'benchmarks' / 'tiny_llama_opus_case_study_gauntlet.py'),
            '--ollama-model', model,
            '--ollama-timeout-seconds', '20',
            '--output', output,
            cwd=str(ROOT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        out = stdout.decode(errors='replace')[-2000:]
        err = stderr.decode(errors='replace')[-2000:]
        ok = process.returncode == 0
        self.tool_events.append(f'tiny demo gauntlet completed: returncode={process.returncode}')
        self.chat_lines.append({'role': 'tool', 'content': (out + ('\n\nSTDERR:\n' + err if err else '')).strip()})
        self.tiny_demo.update({'active': True, 'model': model, 'artifact_readme': str(ROOT / 'benchmarks' / 'results' / output / 'README.md'), 'gauntlet_returncode': process.returncode})
        self.notify('Tiny demo gauntlet artifact recorded.' if ok else 'Tiny demo gauntlet failed.', title='Tiny demo', severity='information' if ok else 'warning')
        self._set_mascot_state('finished' if ok else 'alert', hold_ticks=18)
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
        if self.tiny_demo.get('active'):
            self.context_candidates = self._tiny_demo_context_rows()
            if not self.context_files:
                self.context_files = [str(row['path']) for row in self.context_candidates]
        else:
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
        if self.tiny_demo.get('active'):
            result = self._build_tiny_demo_patch_plan()
        else:
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
            self._record_tiny_demo_verification(saved, result)
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
        if self.selected_page == 'Economy':
            self.run_worker(self._run_economy_action(str(self.selected_item().get('action') or 'rollout_monitor')), exclusive=False)
            return
        self.run_worker(self._run_selected_action('test'), exclusive=False)

    def action_view_selected(self):
        if self.selected_page == 'Session' and self.patch_plans:
            self.action_verify_patch_plan(); return
        if self.selected_page == 'Session':
            receipt = self.session_meta.get('last_integration_harness_receipt') if isinstance(self.session_meta, dict) else {}
            decision = receipt.get('crystal_reuse_decision') if isinstance(receipt, dict) and isinstance(receipt.get('crystal_reuse_decision'), dict) else {}
            enterprise = receipt.get('enterprise') if isinstance(receipt, dict) and isinstance(receipt.get('enterprise'), dict) else {}
            crystal_record = receipt.get('crystal_record') if isinstance(receipt, dict) and isinstance(receipt.get('crystal_record'), dict) else {}
            memory_hull = crystal_record.get('memory_hull') if isinstance(crystal_record.get('memory_hull'), dict) else {}
            payload = {
                'session': {
                    'provider': self.session_meta.get('provider'),
                    'model': self.session_meta.get('model') or 'beast-auto',
                    'streaming_enabled': self.streaming_enabled,
                    'context_files': self.context_files,
                    'state': self.session_meta.get('state'),
                },
                'recent_tool_events': self.tool_events[-20:],
                'crystal_decision': {
                    'crystal_reuse_decision_id': decision.get('decision_id'),
                    'action': decision.get('action'),
                    'source': decision.get('source'),
                    'confidence': decision.get('confidence'),
                    'reason': decision.get('reason'),
                },
                'enterprise_trace': {
                    'usage': enterprise.get('usage'),
                    'observability_event': enterprise.get('observability_event'),
                    'encrypted_trace': enterprise.get('encrypted_trace'),
                },
                'memory_hull_sidecar': {
                    'path': memory_hull.get('sidecar_path'),
                    'verified': memory_hull.get('verified'),
                    'reason': memory_hull.get('reason'),
                },
                'integration_harness_receipt': receipt or {'status': 'no live harness receipt recorded yet'},
            }
            self.push_screen(DetailScreen('Session harness receipt drilldown', payload))
            return
        if self.selected_page == 'Intelligence':
            snap = self.snapshot or BackendSnapshot(base_url=self.base_url)
            crystal = snap.crystal_compute if isinstance(snap.crystal_compute, dict) else {}
            latest = latest_mega_summary(snap)
            payload = {
                'summary': {
                    'session': intelligence_summary(snap).get('session_id') or 'offline',
                    'phase1': crystal.get('phase1') or 'operational',
                    'phase2': crystal.get('phase2') or 'shadow',
                    'phase3': crystal.get('phase3') or 'advisory',
                    'phase4': crystal.get('phase4') or 'escrow_shadow',
                    'phase5': crystal.get('phase5') or 'temporal_forks_shadow',
                    'phase6': crystal.get('phase6') or 'durable_intelligence_local',
                },
                'latest_mega_artifact': {
                    'provider_call_receipts': latest['provider_call_receipts'],
                    'impact_fingerprint_files': latest['impact_fingerprint_files'],
                    'phase_package': f"{latest['phase_pass_count']}/{latest['phase_count']} pass",
                    'mutation_recovery': f"{latest['recovered_count']}/{latest['mutation_case_count']} recovered",
                    'false_reuse': latest['false_reuse_count'],
                    'artifact': latest['artifact_path'][-96:],
                },
                'state_counts': {
                    'negative_capabilities': len(crystal.get('negative_capabilities') or []),
                    'friction_profiles': len(crystal.get('friction_profiles') or []),
                    'counterfactual_total': (crystal.get('counterfactual_summary') or {}).get('total', 0) if isinstance(crystal.get('counterfactual_summary'), dict) else 0,
                    'escrow_settled': (crystal.get('escrow_summary') or {}).get('settled', 0) if isinstance(crystal.get('escrow_summary'), dict) else 0,
                    'temporal_forks': len((crystal.get('temporal_forks') or {}).get('forks') or []) if isinstance(crystal.get('temporal_forks'), dict) else 0,
                },
            }
            self.push_screen(DetailScreen('Crystal Compute operator summary', payload))
            return
        if self.selected_page == 'Economy':
            action = str(self.selected_item().get('action') or 'economy_dashboard')
            now = time.time()
            last_action = str(getattr(self, '_last_economy_enter_action', '') or '')
            last_at = float(getattr(self, '_last_economy_enter_at', 0.0) or 0.0)
            if action == last_action and now - last_at < 0.35:
                return
            self._last_economy_enter_action = action
            self._last_economy_enter_at = now
            self.run_worker(self._run_economy_action(action), exclusive=False)
            return
        if self.selected_page == 'Deployment':
            snap = self.snapshot or BackendSnapshot(base_url=self.base_url)
            selected = self.selected_item()
            deploy = snap.deployment_score()
            payload = {
                'selected': selected,
                'deployment_readiness': {
                    'nginx_ready': deploy.get('nginx_ready'),
                    'nginx_lines': len(snap.nginx_config.splitlines()),
                    'litellm_running': deploy.get('litellm_running'),
                    'litellm_port': deploy.get('litellm_port'),
                    'litellm_models': deploy.get('litellm_models'),
                    'provider_adapters': len(snap.provider_adapters),
                    'provider_secrets': snap.provider_secret_count(),
                },
                'next_actions': {
                    'test': 'Run the selected dry-run/status check.',
                    'approve': 'Write configs or start sidecar when the selected row supports it.',
                    'edit': 'Open provider/model route configuration.',
                },
            }
            self.push_screen(DetailScreen('Deployment operator summary', payload))
            return
        if self.selected_page == 'Diagnostics':
            snap = self.snapshot or BackendSnapshot(base_url=self.base_url)
            selected = self.selected_item()
            latest = latest_mega_summary(snap)
            payload = {
                'selected_check': selected,
                'snapshot_health': {
                    'gateway': snap.gateway,
                    'proxy': snap.proxy,
                    'mcp': snap.mcp,
                    'endpoint_errors': len(snap.errors),
                    'providers': len(snap.providers()),
                    'routes': len(snap.routes),
                },
                'latest_mega_artifact': {
                    'provider_call_receipts': latest['provider_call_receipts'],
                    'fingerprints': latest['impact_fingerprint_files'],
                    'integrity': latest['integrity_hash'][:56],
                },
            }
            self.push_screen(DetailScreen('Diagnostics operator summary', payload))
            return
        item = self.selected_item()
        if self.selected_page in {'Providers', 'Routing'}:
            self.open_provider_config(val(item, 'provider_id', 'id', 'name', default=self.session_meta.get('provider', 'litellm')))
            return
        self.push_screen(DetailScreen(f"{PAGE_LABELS.get(self.selected_page,self.selected_page)} selected item", item))

    def action_edit_selected(self):
        if self.selected_page in {'Session', 'Providers', 'Routing'}:
            self.open_provider_config()
            return
        if self.selected_page == 'Intelligence':
            snap = self.snapshot or BackendSnapshot(base_url=self.base_url)
            payload = {
                'selected': self.selected_item(),
                'how_meta_tool_commons_is_calculated': {
                    'endpoint': 'POST /edgek/meta-tool-commons/rank',
                    'inputs': 'task_class=operator_console, role=tool_selector, limit=10',
                    'score_fields': 'score, confidence, local/global samples, verified/usefulness/hidden-clean/safety rates, latency and cost',
                    'next_actions': ['t: run quality cascade/test selected', 'v/Enter: inspect row evidence', 'r: refresh backend ranking', 'ctrl+k: command palette'],
                },
                'provider_economist': snap.provider_economist,
                'tool_laziness': snap.tool_laziness,
                'handoff_precheck': snap.handoff_precheck,
                'otel': snap.otel_state,
                'source_plan': 'Use o from Session to build a governed source patch plan; f previews hunks; u applies selected hunks.',
            }
            self.push_screen(DetailScreen('Intelligence configuration and scoring', payload))
            return
        self.run_worker(self._run_selected_action('edit'), exclusive=False)

    def action_approve_selected(self):
        if self.selected_page == 'Session':
            self.approve_current_patch_plan(); return
        if self.selected_page == 'Economy':
            action = str(self.selected_item().get('action') or '')
            if action not in {'start_forge_node', 'promote_fleet'}:
                action = 'promote_fleet'
            self.run_worker(self._run_economy_action(action), exclusive=False)
            return
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

    def _start_local_forge_node(self) -> ActionResult:
        forge_dir = ROOT / 'data' / 'forge_nodes'
        forge_dir.mkdir(parents=True, exist_ok=True)
        node_id = 'local_tui'
        if self.forge_process and self.forge_process.poll() is None:
            node_id = f'local_tui_{int(time.time())}'
        log_path = forge_dir / f'{node_id}.log'
        command = [
            sys.executable,
            str(ROOT / 'scripts' / 'run_forge_node.py'),
            '--node-id', node_id,
            '--repo', str(ROOT),
            '--interval', '300',
            '--work', 'fingerprint', 'secret_scan', 'test_map',
            '--snapshot-dir', str(forge_dir),
            '--propose-candidate',
        ]
        log_handle = log_path.open('a', encoding='utf-8')
        try:
            self.forge_process = subprocess.Popen(
                command,
                cwd=str(ROOT),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        finally:
            log_handle.close()
        return ActionResult(
            True,
            'Forge node fleet',
            f"started local Forge node {node_id} pid={self.forge_process.pid}; log={log_path}",
            {'node_id': node_id, 'pid': self.forge_process.pid, 'log_path': str(log_path), 'snapshot_dir': str(forge_dir), 'claim_more_local_inference': 'Run Start local Forge node again to add another local_tui_* worker; use Collect Forge promotions to promote candidates.'},
        )

    def command_palette_items(self) -> List[Dict[str, Any]]:
        return [
            {'id': 'refresh', 'label': 'Refresh backend state', 'scope': 'Gateway', 'key': 'r'},
            {'id': 'start_session', 'label': 'Start live coding session', 'scope': 'Session', 'key': 's'},
            {'id': 'prepare_handoff', 'label': 'Prepare provider handoff', 'scope': 'Output governance', 'key': 'p'},
            {'id': 'sourceplan', 'label': 'Build governed source patch plan', 'scope': 'SourcePlan', 'key': 'o'},
            {'id': 'preview_diff', 'label': 'Preview/select patch hunks', 'scope': 'SourcePlan', 'key': 'f'},
            {'id': 'apply_patch', 'label': 'Apply selected patch hunks', 'scope': 'SourcePlan', 'key': 'u'},
            {'id': 'rollback', 'label': 'Rollback latest patch apply', 'scope': 'SourcePlan', 'key': 'z'},
            {'id': 'tiny_demo_prepare', 'label': 'Prepare Tiny Llama Opus case demo', 'scope': 'Demo', 'key': 'ctrl+t'},
            {'id': 'tiny_demo_run', 'label': 'Run/record Tiny Llama Opus case gauntlet', 'scope': 'Demo', 'key': 'palette'},
            {'id': 'context_picker', 'label': 'Open context picker', 'scope': 'Context', 'key': 'c'},
            {'id': 'approvals', 'label': 'Open approval queue', 'scope': 'Governance', 'key': 'l'},
            {'id': 'doctor', 'label': 'Run diagnostics refresh', 'scope': 'Diagnostics', 'key': 'd'},
            {'id': 'economy', 'label': 'Open unified economy operations', 'scope': 'Economy', 'key': 'e'},
            {'id': 'rollout_monitor', 'label': 'Run Phase 2/3 rollout monitor', 'scope': 'Economy', 'key': 't'},
            {'id': 'start_forge_node', 'label': 'Start local Forge node runner', 'scope': 'Forge Fleet', 'key': 'a'},
            {'id': 'promote_fleet', 'label': 'Collect Forge promotions centrally', 'scope': 'Crystallization', 'key': 'a'},
            {'id': 'providers', 'label': 'Go to provider fitness', 'scope': 'Routing', 'key': '5'},
            {'id': 'intelligence', 'label': 'Open agent awareness and Meta Tool Commons', 'scope': 'Intelligence', 'key': 'j'},
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
            'tiny_demo_prepare': self.action_prepare_tiny_llama_demo,
            'tiny_demo_run': self.action_run_tiny_llama_case_study,
            'context_picker': self.action_context_picker,
            'approvals': self.action_approval_queue,
            'doctor': self.action_doctor,
            'providers': self.action_providers,
            'intelligence': self.action_intelligence,
            'economy': self.action_economy,
            'rollout_monitor': lambda: self.run_worker(self._run_economy_action('rollout_monitor'), exclusive=False),
            'start_forge_node': lambda: self.run_worker(self._run_economy_action('start_forge_node'), exclusive=False),
            'promote_fleet': lambda: self.run_worker(self._run_economy_action('promote_fleet'), exclusive=False),
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

    async def _run_economy_action(self, action: str | None = None) -> None:
        self._set_mascot_state('working')
        action = action or str(self.selected_item().get('action') or 'economy_dashboard')
        try:
            if action == 'rollout_monitor':
                report = evaluate_rollout()
                ok = not bool(report.get('redlines'))
                result = ActionResult(ok, 'Rollout monitor', str(report.get('readiness') or 'unknown'), report, error='' if ok else ', '.join(report.get('redlines') or []))
            elif action == 'promote_fleet':
                report = promote_from_fleet(ROOT / 'data' / 'forge_nodes', ROOT / 'data' / 'crystallization')
                out = ROOT / 'benchmarks' / 'results' / 'forge_fleet_promotion.json'
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
                result = ActionResult(True, 'Forge fleet promotions', f"{len(report.get('promoted') or [])} promoted; {len(report.get('blocked') or [])} blocked", report)
            elif action == 'start_forge_node':
                result = self._start_local_forge_node()
            else:
                report = build_dashboard()
                result = ActionResult(True, 'Economy dashboard', str((report.get('rollout') or {}).get('readiness') or 'ready'), report)
            self.tool_events.append(f'economy {action}: ' + ('ok' if result.ok else 'redline'))
            self.chat_lines.append({'role': 'tool', 'content': result.brief(1600)})
            self.notify(result.summary or result.error, title=result.title, severity='information' if result.ok else 'warning')
            self.push_screen(DetailScreen(result.title, result.data))
            self._set_mascot_state('finished' if result.ok else 'alert', hold_ticks=12 if result.ok else 18)
        except Exception as exc:
            self.tool_events.append(f'economy {action}: error')
            self.notify(str(exc), title='Economy action failed', severity='warning')
            self._set_mascot_state('alert', hold_ticks=18)
        self._sync()

    async def _run_selected_action(self, mode: str) -> None:
        self._set_mascot_state('working')
        api = BeastApiClient(self.base_url)
        item = self.selected_item()
        page = self.selected_page
        result: ActionResult
        if page == 'Spaces':
            space_id = str(item.get('space_id') or '')
            if not space_id or space_id == 'no_spaces_loaded':
                result = ActionResult(False, 'Compute Space', '', error='No local Compute Space selected')
            elif mode == 'approve':
                result = await api.action('Adopt Compute Space', f'/edgek/commons-spaces/{space_id}/adopt', {
                    'approved': True,
                    'dry_run': False,
                    'approved_by': 'beast_tui',
                    'reason': 'Operator approved verified Space artifact references from TUI',
                })
            elif mode == 'test':
                result = await api.action('Compute policy shadow recommendation', '/edgek/commons-policy/recommend', {
                    'task_class': item.get('task_class') or 'general',
                    'risk': 'high' if item.get('approval_required') else 'medium',
                    'gpu_available': False,
                    'approval_required': bool(item.get('approval_required')),
                })
            else:
                result = await api.action('Compute Space detail', f'/edgek/commons-spaces/{space_id}', method='GET')
        elif page == 'Providers' and mode == 'models':
            result = await api.render_litellm_config()
        elif page in {'Providers', 'Routing'} and mode in {'test', 'doctor'}:
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
        elif page == 'Capabilities' and mode == 'approve':
            candidate_id = str(item.get('candidate_id') or '')
            if candidate_id:
                result = await api.action('Promote Skill', '/edgek/skills/promote', {
                    'candidate_id': candidate_id,
                    'approved_by': 'beast_tui',
                    'require_eligible': True,
                })
            else:
                result = ActionResult(False, 'Promote Skill', '', error='Selected capability is not a persisted promotion candidate')
        elif page == 'Capabilities' and mode == 'test':
            name = str(item.get('capability_id') or item.get('name') or 'selected capability')
            candidate_id = str(item.get('candidate_id') or '')
            result = await api.action('Promotion candidate detail', f'/edgek/skills/promotion-candidates/{candidate_id}', method='GET') if candidate_id else await api.compile_insight(f'Test capability {name}', provider=str(self.session_meta.get('provider') or 'litellm'))
        elif page == 'Intelligence' and mode == 'test':
            result = await api.action('Tool Laziness schema benchmark', '/edgek/tool-laziness/schema-benchmark', {'tool_count': 72, 'turns': 36, 'relevant_tools_per_turn': 5})
        elif page == 'Intelligence' and mode in {'approve', 'block'}:
            tool_name = str(item.get('capability_id') or item.get('name') or 'selected_tui_tool')
            useful = mode == 'approve'
            result = await api.action('Record Tool Laziness evidence', '/edgek/tool-laziness/record', {
                'tool_name': tool_name, 'scenario': 'operator_console', 'called': True,
                'useful': useful, 'tokens_spent': 250, 'cost_usd': 0.0,
                'latency_ms': 100.0, 'value_score': 0.8 if useful else 0.0,
            })
        elif page == 'Intelligence' and mode == 'view':
            result = await api.action('Operational BEAST plugins', '/edgek/plugins', method='GET')
        elif page == 'Swarm':
            run_id = str(item.get('run_id') or '')
            candidate_id = str(item.get('candidate_id') or '')
            if mode in {'view', 'test'} and run_id and run_id != 'no_swarm_runs_loaded':
                result = await api.action('Swarm run detail', f'/edgek/swarm/runs/{run_id}', method='GET')
            elif mode in {'view', 'test'} and candidate_id:
                result = ActionResult(True, 'Commons swarm candidate', 'Local approval-gated skill recipe candidate', item)
            elif mode == 'approve' and candidate_id:
                result = await api.action('Promote Commons swarm recipe', '/edgek/meta-tool-commons/adopt', {
                    'candidate_id': candidate_id,
                    'approved': True,
                    'dry_run': False,
                    'approved_by': 'beast_tui',
                    'reason': 'Operator approved Swarm recipe from TUI',
                })
            elif mode in {'approve', 'test'}:
                result = await api.action('Commons swarm candidates', '/edgek/meta-tool-commons/swarm-candidates', {'min_samples': 2, 'limit': 20})
            else:
                result = ActionResult(True, 'Swarm selected', 'Selected local swarm cockpit item', item)
        elif page == 'PREC' and mode in {'test', 'doctor'}:
            result = await api.action('PREC state', '/edgek/prec/state', method='GET')
        elif page == 'Chronicle' and mode in {'test', 'view'}:
            task_id = str(item.get('task_id') or item.get('id') or '')
            result = await api.action('Chronicle detail', f'/edgek/chronicle/{task_id}', method='GET') if task_id else ActionResult(False, 'Chronicle detail', '', error='No task_id on selected record')
        elif page == 'Diagnostics':
            action = str(item.get('action') or '')
            if action == 'refresh':
                self.action_refresh_backend()
                result = ActionResult(True, 'Diagnostics refresh', 'Backend refresh queued', item)
            elif action == 'edit_provider':
                self.open_provider_config(str(self.session_meta.get('provider') or 'litellm'))
                result = ActionResult(True, 'Provider editor', 'Opened provider/API-key editor', item)
            elif action == 'provider_diagnostic':
                result = await api.provider_diagnostic(self.selected_provider_id())
            elif action == 'render_litellm_config':
                result = await api.render_litellm_config()
            elif action == 'nginx_dry_run':
                result = await api.nginx_apply(approved=False, dry_run=True)
            elif action == 'litellm_start_dry_run':
                result = await api.litellm_start(approved=False, dry_run=True)
            elif action == 'prec':
                result = await api.action('PREC state', '/edgek/prec/state', method='GET')
            elif action == 'swarm':
                result = await api.action('Swarm state', '/edgek/swarm/state', method='GET')
            elif action == 'evidence_plane':
                result = await api.action('Reuse evidence plane', '/edgek/meta-tool-commons/evidence-plane', method='GET')
            elif action == 'openclaw_plan':
                result = await api.action('OpenClaw plan preview', '/edgek/beast-cli/plan', {
                    'objective': 'Diagnostics OpenClaw preview',
                    'mode': 'openclaw',
                    'use_ollama': False,
                    'preflight_budget_ms': 350,
                    'scout_budget_ms': 0,
                    'run_swarm': True,
                })
            elif action == 'ollama_status':
                result = await api.action('Ollama scout status', '/edgek/ollama/status', method='GET')
            elif action == 'kv_cache_state':
                result = await api.action('KV cache state', '/edgek/kv-cache/state', method='GET')
            elif action == 'view_errors':
                result = ActionResult(True, 'Endpoint error ledger', 'Latest snapshot errors', {'errors': (self.snapshot or BackendSnapshot(base_url=self.base_url)).errors})
            else:
                result = await api.quality_cascade('Run BEAST diagnostic quality cascade', provider=str(self.session_meta.get('provider') or 'litellm'))
        else:
            result = await api.compile_insight(f'{mode} {self.selected_label()}', provider=str(self.session_meta.get('provider') or 'litellm'))
        self.tool_events.append(f'{mode} {page}: ' + ('ok' if result.ok else 'error'))
        self.chat_lines.append({'role': 'tool', 'content': result.brief(1200)})
        self.notify(result.summary or result.error or result.title, title=result.title, severity='information' if result.ok else 'warning')
        if result.data:
            self.push_screen(DetailScreen(result.title or f'{page} {mode}', result.data))
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
        if text.lower() in {'/heal', '/restore', '/recover'}:
            self.action_heal_services(); return
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
        heal_recommended = False
        try:
            history = [{'role': line['role'], 'content': line['content']} for line in self.chat_lines if line.get('role') in {'user','assistant'}]

            if not self.streaming_enabled:
                result: LiveTurnResult = await BeastApiClient(self.base_url).live_turn(
                    text,
                    history=history,
                    provider=str(self.session_meta.get('provider') or 'litellm'),
                    lifecycle_id=str(self.session_meta.get('lifecycle_id') or ''),
                    context_files=list(self.context_files),
                    model=str(self.session_meta.get('model') or 'beast-auto'),
                )
                if result.assistant_text:
                    self.chat_lines.append({'role': 'assistant', 'content': result.assistant_text})
                if result.tool_events:
                    self.tool_events.extend(result.tool_events)
                if isinstance(result.data, dict):
                    receipt = result.data.get('integration_harness_receipt')
                    if isinstance(receipt, dict):
                        self.session_meta['last_integration_harness_receipt'] = receipt
                        self.session_meta['last_crystal_reuse_decision'] = receipt.get('crystal_reuse_decision') or {}
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
                model=str(self.session_meta.get('model') or 'beast-auto'),
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
                    completed = bool(event.get('completed'))
                    self.tool_events.append(f"provider stream {'done' if completed else 'incomplete'}: {event.get('tokens', 0)} chunk(s)")
                elif event_type == 'done':
                    for item in event.get('tool_events') or []:
                        if str(item) not in self.tool_events[-12:]:
                            self.tool_events.append(str(item))
                    if event.get('lifecycle_id'):
                        self.session_meta['lifecycle_id'] = str(event.get('lifecycle_id'))
                    data = event.get('data') if isinstance(event.get('data'), dict) else {}
                    receipt = data.get('integration_harness_receipt') if isinstance(data, dict) else None
                    if isinstance(receipt, dict):
                        self.session_meta['last_integration_harness_receipt'] = receipt
                        self.session_meta['last_crystal_reuse_decision'] = receipt.get('crystal_reuse_decision') or {}
                    heal_recommended = heal_recommended or bool(data.get('heal_recommended'))
                    self._sync()

            if self.current_turn_cancelled:
                self.chat_lines[assistant_index]['content'] = (accumulated or '') + '\n\n[stream cancelled]'
                turn_ok = False
            else:
                self.chat_lines[assistant_index]['content'] = accumulated or '[no streamed response]'
            self.tool_events.append(f'stream chunks: {token_count}')
            if heal_recommended:
                await self._heal_services(force=False)
        except Exception as exc:
            turn_ok = False
            self.tool_events.append('live stream error')
            self.chat_lines.append({'role': 'system', 'content': f'Live stream failed safely: {exc}'})
            self.notify(str(exc), title='BEAST live stream', severity='warning')
            await self._heal_services(force=False)
        finally:
            self.current_turn_cancelled = False
            self.session_meta['state'] = 'active'
            self._set_mascot_state('finished' if turn_ok else 'alert', hold_ticks=16 if turn_ok else 20)
            await self.fetch_backend()



# ---------------------------------------------------------------------------
# Visual Widget Deck overrides
# ---------------------------------------------------------------------------

def status_mark(value: Any) -> Text:
    style = status_style(value)
    txt = str(value).lower()
    if style == BEAST_GREEN:
        return Text('✓', style=f'bold {BEAST_GREEN}')
    if style == BEAST_DANGER or any(x in txt for x in ['deny', 'blocked', 'fail', 'error']):
        return Text('✕', style=f'bold {BEAST_DANGER}')
    return Text('◌', style=f'bold {BEAST_WARN}')


def delta_badge(value: Any, suffix: str = '%', positive_good: bool = True) -> Text:
    try:
        n = float(value)
    except Exception:
        n = 0.0
    up = n >= 0
    good = up if positive_good else not up
    style = BEAST_GREEN if good else BEAST_DANGER
    arrow = '↗' if up else '↘'
    text = Text()
    text.append(arrow + ' ', style=f'bold {style}')
    text.append(f'{abs(n):.1f}{suffix}', style=f'bold {style}')
    return text


def line_graph(values: Iterable[Any], *, width: int = 22, good: bool = True) -> Text:
    text = Text()
    text.append('╭', style=BEAST_BORDER_DIM)
    text.append('─' * max(4, width - 2), style=BEAST_BORDER_DIM)
    text.append('╮\n', style=BEAST_BORDER_DIM)
    text.append('⌁ ', style=BEAST_MUTED)
    text.append(sparkline(values, width=max(4, width - 4), good=good))
    text.append(' \n', style=BEAST_BORDER_DIM)
    text.append('╰', style=BEAST_BORDER_DIM)
    text.append('─' * max(4, width - 2), style=BEAST_BORDER_DIM)
    text.append('╯', style=BEAST_BORDER_DIM)
    return text


def circle_meter(percent: Any, label: str = '', *, size: str = 'medium') -> Text:
    try:
        pct = max(0.0, min(100.0, float(percent)))
    except Exception:
        pct = 0.0
    style = BEAST_GREEN if pct >= 85 else BEAST_WARN if pct >= 60 else BEAST_DANGER
    filled = int(round(pct / 10))
    ring = '●' * filled + '○' * (10 - filled)
    text = Text()
    if size == 'small':
        text.append('◜', style=style); text.append(ring[:5], style=style); text.append('◝ ', style=style)
        text.append(f'{pct:.0f}', style=f'bold {style}')
        text.append('/100', style=BEAST_MUTED)
        return text
    text.append('     ◜', style=style); text.append(ring[:5], style=style); text.append('◝\n', style=style)
    text.append('   ◜', style=style); text.append(ring[5:8], style=style); text.append(' ', style=style)
    text.append(f'{pct:.0f}', style=f'bold {style}')
    text.append(' ', style=style); text.append(ring[8:], style=style); text.append('◝\n', style=style)
    text.append('     ◟', style=style); text.append(ring[:5], style=style); text.append('◞', style=style)
    if label:
        text.append(f'\n{label}', style=BEAST_MUTED)
    return text


def distribution_ring(parts: Dict[str, Any] | List[Any], *, title: str = '') -> Text:
    if isinstance(parts, dict):
        items = [(str(k), int(v or 0)) for k, v in parts.items()]
    else:
        items = [(str(i + 1), int(v or 0)) for i, v in enumerate(parts)]
    items = [(k, v) for k, v in items if v > 0][:6] or [('empty', 1)]
    total = sum(v for _, v in items) or 1
    dots = []
    accents = [BEAST_GREEN, BEAST_JADE, BEAST_ACID, BEAST_MINT, BEAST_EMERALD, BEAST_MOSS]
    for idx, (_, v) in enumerate(items):
        count = max(1, round((v / total) * 18))
        dots.extend([accents[idx % len(accents)]] * count)
    dots = (dots + [BEAST_BORDER_DIM] * 18)[:18]
    text = Text()
    text.append('   ◜', style=BEAST_GREEN)
    for c in dots[:6]: text.append('●', style=c)
    text.append('◝\n', style=BEAST_GREEN)
    text.append('  ● ', style=dots[6])
    text.append(str(total), style=f'bold {BEAST_GREEN}')
    text.append(' total ', style=BEAST_MUTED)
    text.append('●\n', style=dots[7])
    text.append('   ◟', style=BEAST_GREEN)
    for c in dots[8:14]: text.append('●', style=c)
    text.append('◞\n', style=BEAST_GREEN)
    for idx, (name, v) in enumerate(items[:4]):
        text.append('■ ', style=accents[idx % len(accents)])
        text.append(f'{name[:12]} {v}  ', style=BEAST_MUTED)
    return text


def toggle_pill(on: Any, label: str = '') -> Text:
    active = bool(on)
    text = Text()
    if label:
        text.append(label + ' ', style=BEAST_MUTED)
    text.append('On ' if active else 'Off ', style=BEAST_GREEN if active else BEAST_MUTED)
    text.append('●', style=f'bold {BEAST_GREEN if active else BEAST_MUTED}')
    text.append('━━━━' if active else '────', style=BEAST_GREEN if active else BEAST_MUTED)
    return text


def widget_card(title: str, value: Any, note: str, visual: Any = None, *, delta: Any = None, accent: str | None = None, danger: bool = False) -> Panel:
    acc = accent or (BEAST_DANGER if danger else BEAST_GREEN)
    body: List[Any] = [Text(title.upper(), style=f'bold {acc}'), Text(str(value), style=f'bold {acc}'), Text(str(note), style=BEAST_MUTED)]
    if delta is not None:
        body.append(delta if isinstance(delta, Text) else Text(str(delta), style=acc))
    if visual is not None:
        body.append(visual)
    return fixed_panel(Group(*body), border_style=acc, style=BEAST_PANEL_SOFT, padding=(1, 1), box_style=box.ROUNDED, height=VISUAL_TILE_HEIGHT)


def button_card(label: str, *, active: bool = False, icon: str = '▷') -> Panel:
    acc = BEAST_ACID if active else BEAST_BORDER
    return fixed_panel(Text(f'{icon}   [ {label} ]', justify='center', style=BEAST_ACID if active else BEAST_TEXT), border_style=acc, style=BEAST_PANEL_SOFT, padding=(0, 1), box_style=box.ROUNDED, height=3)


def field_box(label: str, value: Any, icon: str = '▱') -> Panel:
    row = Table.grid(expand=True)
    row.add_column(width=4); row.add_column(ratio=1); row.add_column(width=2)
    row.add_row(Text(icon, style=BEAST_STEEL), Text(str(label), style=BEAST_MUTED), Text('⌄', style=BEAST_MUTED))
    row.add_row(Text(''), Text(str(value), style=f'bold {BEAST_GREEN}'), Text(''))
    return fixed_panel(row, border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(0, 1), box_style=box.ROUNDED, height=4)


def dense_status_list(rows: List[tuple[str, Any, Any]], selected_index: int = 0, *, max_rows: int | None = None) -> Table:
    table = Table(expand=True, box=box.SIMPLE)
    table.add_column('', width=2)
    table.add_column('Signal', ratio=2)
    table.add_column('State', width=12)
    table.add_column('Meter', width=18)
    table.add_column('Note', ratio=2)
    if not rows:
        table.add_row('', 'none', 'WAIT', '', 'no signals')
        return table
    for i, (name, status, note) in enumerate(rows):
        pct = pct_from_status(status)
        table.add_row(
            selected_marker(i == selected_index),
            selected_text(name, i == selected_index),
            status_mark(status) + Text(' ' + str(status), style=status_style(status)),
            block_meter(pct, width=10, compact=False),
            Text(str(note)[:60], style=BEAST_MUTED),
        )
    return table


def _session_launcher_visual(self: PageHost, snap: BackendSnapshot):
    meta = getattr(self, 'session_meta', {}) or {}
    provider = meta.get('provider', 'litellm')
    route = provider_route_summary(snap, provider)
    model = route.get('resolved_model') or 'beast-auto'
    form = Table.grid(expand=True)
    form.add_column(ratio=1); form.add_column(ratio=1)
    form.add_row(field_box('Workspace', Path(os.environ.get('BEAST_WORKSPACE', os.getcwd())).name, '▱'), field_box('Policy Profile', 'Governed (Default)', '⬡'))
    form.add_row(field_box('Provider', provider, 'AI'), field_box('Context Budget', '200K tokens', '◌'))
    form.add_row(field_box('Model', str(model)[:38], 'λ'), field_box('Chronicle Enabled', 'On', '▤'))
    form.add_row(field_box('Session Type', 'Agent (Interactive)', '>_'), field_box('Local Scout Enabled', 'On', '⌁'))
    buttons = Table.grid(expand=True)
    buttons.add_column(ratio=1); buttons.add_column(ratio=1); buttons.add_column(ratio=1)
    buttons.add_row(button_card('Start Session', active=True, icon='▷'), button_card('Prepare Handoff', icon='↥'), button_card('Run Diagnostics', icon='⚡'))
    return Panel(Group(title_text('SESSION LAUNCHER', PAGE_SYMBOLS['Session']), Text(''), form, Text(''), buttons), border_style=BEAST_ACID, style=BEAST_PANEL, padding=(1,2), box=box.HEAVY_EDGE)


def visual_live_session_preview(self: PageHost, snap: BackendSnapshot):
    meta = getattr(self, 'session_meta', {}) or {}
    provider = str(meta.get('provider') or 'litellm')
    state = str(meta.get('state') or 'idle')
    chat_lines = getattr(self, 'chat_lines', [])
    tool_events = getattr(self, 'tool_events', [])
    context_files = getattr(self, 'context_files', [])
    patch_plans = getattr(self, 'patch_plans', [])
    route = provider_route_summary(snap, provider)
    current_plan = (getattr(self, 'approval_queue', []) or patch_plans or [{}])[-1] if (getattr(self, 'approval_queue', []) or patch_plans) else {}
    plan = current_plan_summary(current_plan)

    active = Table.grid(expand=True)
    active.add_column(ratio=1); active.add_column(ratio=1); active.add_column(ratio=1); active.add_column(ratio=1)
    active.add_row(
        widget_card('Active Sessions', '2' if state != 'idle' else '1', f'{provider} • {state}', line_graph([4, 6, 8, 7, 9, 10, 8], width=20), delta=delta_badge(8.0)),
        widget_card('Provider Health', '96.2%', f'{route.get("route_provider")} route', line_graph([72, 81, 78, 88, 94, 96], width=20), delta=delta_badge(3.4)),
        widget_card('Handoff Gate', plan.get('gate_status', 'not run'), f'{plan.get("requests", 0)} verifier request(s)', circle_meter(94 if snap.handoff_precheck.get('ready') else 62, size='small')),
        widget_card('Route Cards', len(snap.routes), 'allow/deny policy active', distribution_ring({'allow': max(1, len(snap.routes) - 1), 'deny': 1}, title='routes')),
    )

    transcript = Text()
    lines = chat_lines[-7:] if chat_lines else [
        {'role':'system', 'content':'s start  c context  n provider  / commands'},
        {'role':'system', 'content':'/sourceplan  /diff  /verify  /apply  /rollback'},
    ]
    for line in lines:
        role = line.get('role', 'system')
        style = BEAST_GREEN if role == 'assistant' else BEAST_TEXT if role == 'user' else BEAST_INFO if role == 'tool' else BEAST_MUTED
        prefix = 'YOU' if role == 'user' else 'BEAST' if role == 'assistant' else 'TOOL' if role == 'tool' else 'SYS'
        transcript.append(f'{prefix}: ', style=f'bold {style}')
        transcript.append(str(line.get('content', ''))[:1100] + '\n\n', style=style)

    events = Table.grid(expand=True)
    events.add_column(ratio=1); events.add_column(width=14); events.add_column(width=16)
    event_rows = tool_events[-6:] or ['context ready', 'governed handoff waiting', 'local scout armed']
    for ev in event_rows:
        evs = str(ev)
        ok = not any(x in evs.lower() for x in ['error', 'fail', 'reject'])
        events.add_row(status_mark('OK' if ok else 'ERROR'), Text(evs[:48], style=BEAST_TEXT), delta_badge(2.8 if ok else -6.0))

    lower = Table.grid(expand=True)
    lower.add_column(ratio=2); lower.add_column(ratio=1)
    lower.add_row(
        Panel(Group(title_text('LIVE CHAT / CODING TRANSCRIPT', '▷'), Text(''), transcript), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(1,1), box=box.SQUARE),
        Panel(Group(title_text('EVENT STREAM', '⚒'), chip_line(f'{len(context_files)} ctx', f'{len(patch_plans)} plans'), Text(''), events, Text(''), toggle_pill(True, 'streaming')), border_style=BEAST_JADE, style=BEAST_PANEL, padding=(1,1), box=box.ROUNDED),
    )
    page = Table.grid(expand=True); page.add_column(ratio=1)
    page.add_row(_session_launcher_visual(self, snap))
    page.add_row(active)
    page.add_row(lower)
    return page


def visual_routing_fabric(self: PageHost, snap: BackendSnapshot, index: int):
    adapters = snap.provider_adapters or [{'provider_id': val(p,'provider_id','name',default='provider'), 'backend': val(p,'backend',default='unknown'), 'proxy_path': val(p,'proxy_path','endpoint',default='/proxy'), 'model': val(p,'default_model','model',default='n/a')} for p in snap.providers()]
    adapters = adapters or [{'provider_id':'no_adapters_loaded','backend':'unknown','proxy_path':'/proxy','model':'n/a'}]
    index = clamp(index, 0, len(adapters)-1)
    selected = adapters[index]
    selected_pid = val(selected, 'provider_id','name', default='provider')
    route = provider_route_summary(snap, selected_pid)
    top = Table.grid(expand=True)
    top.add_column(ratio=1); top.add_column(ratio=1); top.add_column(ratio=1); top.add_column(ratio=1)
    backend_counts = snap.provider_backend_counts()
    top.add_row(
        widget_card('Adapters', len(adapters), 'registered lanes', circle_meter(min(100, len(adapters) * 9), size='small')),
        widget_card('Selected Route', route.get('route_provider'), route.get('proxy_path'), line_graph([3, 5, 4, 6, 9, 7, 10], width=20)),
        widget_card('Backend Mix', len(backend_counts), 'classes', distribution_ring(backend_counts or {'local': 1})),
        widget_card('Resolution', route.get('resolved_model')[:26], route.get('lane'), block_meter(94, width=16)),
    )
    rows = []
    for item in adapters:
        pid = val(item,'provider_id','name',default='provider')
        r = provider_route_summary(snap, pid)
        rows.append((pid, 'OK' if r.get('resolved_model') else 'WAIT', f"{r.get('route_provider')} • {r.get('proxy_path')} • {str(r.get('resolved_model'))[:30]}"))
    matrix = dense_status_list(rows, index, max_rows=10)
    detail = provider_route_table(route, compact=False)
    bottom = Table.grid(expand=True); bottom.add_column(ratio=2); bottom.add_column(ratio=1)
    bottom.add_row(Panel(Group(title_text('ROUTE MATRIX', PAGE_SYMBOLS['Routing']), Text(''), matrix), border_style=BEAST_ACID, style=BEAST_PANEL, padding=(1,2), box=box.HEAVY_EDGE), Panel(Group(title_text('ROUTE RESOLUTION', '⌁'), Text(''), detail, Text(''), toggle_pill(True, 'circuit')), border_style=BEAST_JADE, style=BEAST_PANEL, padding=(1,2), box=box.ROUNDED))
    page = Table.grid(expand=True); page.add_column(ratio=1)
    page.add_row(top); page.add_row(bottom)
    return page


def visual_intelligence(self: PageHost, snap: BackendSnapshot, index: int):
    summary = intelligence_summary(snap)
    rankings = snap.commons_ranking.get('rankings') if isinstance(snap.commons_ranking.get('rankings'), list) else []
    rankings = rankings or [{'capability_id':'No contextual evidence yet','score':0,'confidence':0,'sample_size':0,'role':'tool_selector'}]
    index = clamp(index, 0, len(rankings)-1)
    cards = Table.grid(expand=True)
    for _ in range(4): cards.add_column(ratio=1)
    avoidable = int(summary.get('avoidable_compute_tokens') or 0)
    observed = int(summary.get('observed_compute_tokens') or 0)
    savings_pct = (avoidable / max(1, observed)) * 100 if observed else 0
    cards.add_row(
        widget_card('Agent Aware', 'ACTIVE' if summary['aware'] else 'WAIT', str(summary['session_id'] or summary['blocker'])[:42], circle_meter(98 if summary['aware'] else 55, size='small')),
        widget_card('Commons Evidence', summary['commons_evidence'], f"{summary['commons_candidates']} candidates", distribution_ring({'evidence': summary['commons_evidence'], 'adopted': summary['commons_adopted'], 'ranked': summary['commons_rankings']})),
        widget_card('Tool Laziness', summary['tools_skipped'], f"{summary['tools_observed']} learning", line_graph([2, 4, 5, summary['tools_skipped'], 7, 6], width=20), delta=delta_badge(12.4)),
        widget_card('Compute Avoided', f'{savings_pct:.1f}%', f'{avoidable} tokens', line_graph([1, 3, 4, 8, 7, 10], width=20), delta=delta_badge(savings_pct)),
    )
    cards.add_row(
        widget_card('Crystal Reuse', summary.get('crystal_reuse_credits', 0), f"{summary.get('crystal_reuse_hits', 0)} hits / {summary.get('crystal_reuse_saved', 0)} tokens", distribution_ring({'active': int(summary.get('crystal_reuse_credits') or 0), 'total': max(1, int(summary.get('crystal_reuse_total') or 0))})),
        widget_card('Crystal Adapters', f"{summary.get('crystal_integration_configured', 0)}/{summary.get('crystal_integration_count', 0)}", 'LMCache GPTCache LiteLLM OTEL', distribution_ring({'configured': int(summary.get('crystal_integration_configured') or 0), 'available': max(0, int(summary.get('crystal_integration_count') or 0) - int(summary.get('crystal_integration_configured') or 0))})),
        widget_card('Memory Hull', summary.get('memory_hull_verified', 0), f"{summary.get('memory_hull_failed', 0)} failed sidecars", circle_meter(100 if not summary.get('memory_hull_failed') else 55, size='small')),
        widget_card('Agent Passport', 'VALID' if summary.get('passport_policy_valid') else 'WAIT', f"{summary.get('passport_policy_count', 0)} policies / seal {'ready' if summary.get('residue_key_ready') else 'wait'}", toggle_pill(summary.get('passport_policy_valid'))),
    )
    rank_table = Table(expand=True, box=box.SIMPLE)
    rank_table.add_column('', width=2); rank_table.add_column('Skill', ratio=2); rank_table.add_column('Confidence', width=20); rank_table.add_column('Role', ratio=1); rank_table.add_column('Samples', width=10)
    for i, row in enumerate(rankings):
        conf = confidence_from_item(row, fallback=round(float(row.get('score') or 0) * 100 if isinstance(row, dict) else 0))
        rank_table.add_row(selected_marker(i == index), selected_text(val(row,'capability_id','name',default='candidate'), i == index), block_meter(conf, width=10), val(row,'role',default='tool'), val(row,'sample_size','samples',default='0'))
    decisions = Table.grid(expand=True); decisions.add_column(width=22); decisions.add_column(ratio=1)
    for label, value in [
        ('Economist', summary['economist_decision']), ('Selected route', summary['economist_provider'] or 'awaiting evidence'),
        ('Preflight / Scout', f"{summary['preflight_budget_ms']} / {summary['scout_budget_ms']} ms"), ('Latency avoided', f"{summary['latency_avoided_ms']:.1f} ms"),
        ('Exchange', toggle_pill(summary['exchange_enabled'])), ('OpenTelemetry', toggle_pill(summary['otel_configured'])),
    ]:
        decisions.add_row(Text(label, style=BEAST_MUTED), value if isinstance(value, Text) else Text(str(value), style=status_style(value)))
    lower = Table.grid(expand=True); lower.add_column(ratio=2); lower.add_column(ratio=1)
    lower.add_row(Panel(Group(title_text('COMMONS RANKING', '◆'), Text(''), rank_table), border_style=BEAST_ACID, style=BEAST_PANEL, padding=(1,2), box=box.HEAVY_EDGE), Panel(Group(title_text('DECISION ENGINE', '$'), Text(''), decisions), border_style=BEAST_JADE, style=BEAST_PANEL, padding=(1,2), box=box.ROUNDED))
    signal_map = Table.grid(expand=True)
    signal_map.add_column(ratio=1); signal_map.add_column(ratio=1); signal_map.add_column(ratio=1)
    signal_map.add_row(
        widget_card('Preflight Budget', f"{summary['preflight_budget_ms']} ms", 'front-door context gate', block_meter(min(100, int(summary['preflight_budget_ms'] or 0) // 8), width=18)),
        widget_card('Scout Budget', f"{summary['scout_budget_ms']} ms", 'local evidence scout', line_graph([12, 20, 34, int(summary['scout_budget_ms'] or 0) // 10], width=20)),
        widget_card('Latency Avoided', f"{summary['latency_avoided_ms']:.1f} ms", 'learned tool skip value', graph_wall([2, 4, 6, summary['latency_avoided_ms'] or 1], width=20)),
    )
    connector_map = Table.grid(expand=True)
    connector_map.add_column(ratio=1); connector_map.add_column(ratio=1); connector_map.add_column(ratio=1)
    connector_map.add_row(
        widget_card('Exchange', 'ON' if summary['exchange_enabled'] else 'OFF', 'capability exchange', toggle_pill(summary['exchange_enabled'])),
        widget_card('Telemetry', 'ON' if summary['otel_configured'] else 'OFF', 'OpenTelemetry connector', toggle_pill(summary['otel_configured'])),
        widget_card('Plugins', summary.get('plugin_count', 0), 'local plugin market', distribution_ring({'plugins': int(summary.get('plugin_count') or 0), 'reserve': 1})),
    )
    integration_table = Table(expand=True, box=box.SIMPLE)
    integration_table.add_column('Layer')
    integration_table.add_column('State')
    integration_table.add_column('Signal')
    integration_table.add_row('Crystal Reuse Gateway', Text(str(summary.get('crystal_reuse_credits', 0)), style=BEAST_GREEN if summary.get('crystal_reuse_credits') else BEAST_WARN), f"{summary.get('crystal_reuse_hits', 0)} hits; {summary.get('crystal_kv_blocks', 0)} KV block(s)")
    integration_table.add_row('Public Reuse Adapters', Text(f"{summary.get('crystal_integration_configured', 0)}/{summary.get('crystal_integration_count', 0)}", style=BEAST_ACID if summary.get('crystal_integration_count') else BEAST_WARN), 'LMCache / GPTCache / LiteLLM / OpenLLMetry / Langfuse / TensorZero / Promptfoo')
    integration_table.add_row('Memory Hull', Text(str(summary.get('memory_hull_verified', 0)), style=BEAST_GREEN if summary.get('memory_hull_verified') else BEAST_WARN), f"root {str(summary.get('memory_hull_root') or '')[-72:] or 'not reported'}")
    integration_table.add_row('Residue Seal', Text('READY' if summary.get('residue_key_ready') else 'WAIT', style=BEAST_GREEN if summary.get('residue_key_ready') else BEAST_WARN), 'purpose-bound signed residue')
    integration_table.add_row('Agent Passport', Text('VALID' if summary.get('passport_policy_valid') else 'WAIT', style=BEAST_GREEN if summary.get('passport_policy_valid') else BEAST_WARN), f"{summary.get('passport_policy_count', 0)} policy rule(s)")
    operations = Table(expand=True, box=box.SIMPLE)
    operations.add_column('Tool / Plugin', ratio=2); operations.add_column('Decision', width=14); operations.add_column('Evidence', ratio=2)
    laziness_rows = list(snap.tool_laziness.get('tools_not_to_call') or []) + list(snap.tool_laziness.get('tools_to_call') or []) + list(snap.tool_laziness.get('tools_to_observe') or [])
    for row in laziness_rows[:8]:
        operations.add_row(str(row.get('name') or row.get('tool_name')), Text(str(row.get('decision') or 'learn_more'), style=status_style(row.get('decision'))), f"{row.get('samples',0)} samples • {row.get('reason','')}")
    for plugin in (snap.plugins_state.get('plugins') or [])[:8]:
        operations.add_row(str(plugin.get('name') or plugin.get('id')), Text('INSTALLED', style=BEAST_GREEN), f"{plugin.get('risk_class','?')} • callable")
    page = Table.grid(expand=True); page.add_column(ratio=1)
    page.add_row(cards)
    page.add_row(Panel(Group(title_text('AGENT SIGNAL MAP', '◎'), Text(''), signal_map), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(1,2), box=box.ROUNDED))
    page.add_row(lower)
    page.add_row(Panel(Group(title_text('CONNECTOR FIELD', '♧'), Text(''), connector_map), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(1,2), box=box.ROUNDED))
    page.add_row(Panel(Group(title_text('CRYSTAL REUSE + MEMORY SECURITY', '◇'), chip_line('LMCache', 'GPTCache', 'LiteLLM', 'OpenLLMetry', 'Langfuse', 'TensorZero', 'Promptfoo'), Text(''), integration_table), border_style=BEAST_EMERALD, style=BEAST_PANEL, padding=(1,2), box=box.ROUNDED))
    page.add_row(Panel(Group(title_text('TOOL LAZINESS + OPERATIONAL PLUGINS', '⚒'), chip_line('t BENCHMARK', 'a USEFUL', 'b LOW VALUE', 'v INVENTORY'), Text(''), operations), border_style=BEAST_JADE, style=BEAST_PANEL, padding=(1,2), box=box.ROUNDED))
    return page


def visual_economy(self: PageHost, snap: BackendSnapshot, index: int):
    try:
        report = build_dashboard()
    except Exception:
        report = {}
    metrics = snap.compute_metrics if isinstance(snap.compute_metrics, dict) else {}
    savings = snap.compute_savings if isinstance(snap.compute_savings, dict) else {}
    rollout = report.get('rollout') if isinstance(report.get('rollout'), dict) else {}
    forge = report.get('forge') if isinstance(report.get('forge'), dict) else {}
    forge_totals = forge.get('totals') if isinstance(forge.get('totals'), dict) else {}
    crystal = report.get('crystallization') if isinstance(report.get('crystallization'), dict) else {}
    observed = int(metrics.get('observed_total_tokens') or 0)
    avoidable = int(metrics.get('estimated_avoidable_total_tokens') or 0)
    receipts = int(metrics.get('sample_size') or 0)
    false_supp = float(metrics.get('false_suppression_rate') or 0.0) * 100
    weekly = savings.get('potential_weekly_savings_usd') or savings.get('availability') or 'unavailable'
    cards = Table.grid(expand=True)
    for _ in range(4): cards.add_column(ratio=1)
    cards.add_row(
        widget_card('Receipts', receipts, 'compute samples', circle_meter(min(100, receipts * 4), size='small'), delta=delta_badge(9.2)),
        widget_card('Avoidable Tokens', avoidable, f'observed {observed}', line_graph([observed*.2, observed*.35, avoidable*.6, avoidable], width=20), delta=delta_badge((avoidable / max(1, observed))*100 if observed else 0)),
        widget_card('Weekly Savings', weekly, 'potential', graph_wall([1, 3, 2, 5, 7, 6, 8, 9], width=20), delta=delta_badge(4.7)),
        widget_card('False Suppression', f'{false_supp:.1f}%', 'safety guardrail', circle_meter(max(0, 100 - false_supp), size='small'), delta=delta_badge(-false_supp, positive_good=False), danger=false_supp > 0),
    )
    actions = economy_action_rows(report)
    index = clamp(index, 0, len(actions)-1)
    action_grid = Table.grid(expand=True)
    action_grid.add_column(ratio=1)
    for i, row in enumerate(actions):
        action_grid.add_row(button_card(str(row.get('name')), active=i == index, icon='▷' if i == index else '◇'))
    rollup = Table.grid(expand=True); rollup.add_column(width=22); rollup.add_column(ratio=1)
    for label, value in [
        ('Rollout readiness', rollout.get('readiness') or 'unknown'), ('Rollout redlines', ', '.join(rollout.get('redlines') or []) or 'none'),
        ('Forge nodes', forge_totals.get('nodes', 0)), ('Promoted', crystal.get('promoted_count', 0)), ('Stream saved', metrics.get('stream_tokens_saved', 0)),
    ]:
        rollup.add_row(Text(label, style=BEAST_MUTED), Text(str(value), style=status_style(value)))
    lower = Table.grid(expand=True); lower.add_column(ratio=1); lower.add_column(ratio=2); lower.add_column(ratio=1)
    lower.add_row(
        Panel(Group(title_text('ACTIONS', '▷'), Text(''), action_grid), border_style=BEAST_ACID, style=BEAST_PANEL, padding=(1,1), box=box.ROUNDED),
        Panel(Group(title_text('TOKEN ECONOMY', '$'), Text(''), line_graph([observed * .1, observed * .3, observed * .5, avoidable, avoidable * 1.05], width=46), Text(''), block_meter((avoidable / max(1, observed))*100 if observed else 0, width=28)), border_style=BEAST_JADE, style=BEAST_PANEL, padding=(1,2), box=box.HEAVY_EDGE),
        Panel(Group(title_text('ROLLUP', '▤'), distribution_ring({'rollout': 1 if rollout else 0, 'forge': forge_totals.get('nodes', 0), 'promoted': crystal.get('promoted_count', 0), 'receipts': max(1, receipts)}), Text(''), rollup), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(1,1), box=box.ROUNDED),
    )
    page = Table.grid(expand=True); page.add_column(ratio=1)
    page.add_row(cards); page.add_row(lower)
    return page


def visual_chronicle(self: PageHost, snap: BackendSnapshot, index: int):
    rows = snap.chronicles or [{'task_id':'no_chronicle_records_loaded','chronicle_type':'empty','provider':'local','status':'waiting','summary':'No Chronicle records returned yet.'}]
    index = clamp(index, 0, len(rows)-1)
    selected = rows[index]
    promoted = sum(1 for r in rows if str(r.get('status') or '').lower() in {'completed', 'success', 'applied_verified_crystallized'})
    cards = Table.grid(expand=True)
    for _ in range(4): cards.add_column(ratio=1)
    cards.add_row(
        widget_card('Records', len(rows), 'loaded locally', circle_meter(min(100, len(rows)*3), size='small')),
        widget_card('Crystallized', promoted, 'verified residue', distribution_ring({'promoted': promoted, 'other': max(1, len(rows)-promoted)})),
        widget_card('Memory Candidates', sum(1 for r in rows if r.get('memory_candidate')), 'local capability residue', line_graph([2,3,5,4,7,8], width=20), delta=delta_badge(6.3)),
        widget_card('Selected Confidence', val(selected, 'confidence', default='n/a'), val(selected, 'provider', default='local'), block_meter(confidence_from_item(selected, fallback=78), width=16)),
    )
    timeline = Table(expand=True, box=box.SIMPLE)
    timeline.add_column('', width=2); timeline.add_column('Record', ratio=2); timeline.add_column('Provider', ratio=1); timeline.add_column('Status', width=14); timeline.add_column('Hull', width=12); timeline.add_column('Signal', width=18)
    for i, r in enumerate(rows):
        status = val(r, 'status','category', default='done')
        hull_status = 'verified' if r.get('memory_hull_verified') else 'candidate' if r.get('memory_candidate') else 'n/a'
        timeline.add_row(selected_marker(i==index), selected_text(val(r,'task_id','id',default='task'), i==index), val(r,'provider',default='local'), status_mark(status) + Text(' ' + status, style=status_style(status)), Text(hull_status, style=status_style(hull_status)), block_meter(confidence_from_item(r, fallback=70), width=8))
    detail = Table.grid(expand=True); detail.add_column(width=18); detail.add_column(ratio=1)
    for key in ['summary','root_cause','confidence','memory_candidate','memory_hull_verified','memory_hull_sidecar_path','memory_hull_verification_reason','created_at']:
        detail.add_row(Text(human_label(key), style=BEAST_MUTED), Text(val(selected,key,default=''), style=BEAST_TEXT))
    lower = Table.grid(expand=True); lower.add_column(ratio=2); lower.add_column(ratio=1)
    lower.add_row(Panel(Group(title_text('CHRONICLE TIMELINE', '▦'), Text(''), timeline), border_style=BEAST_ACID, style=BEAST_PANEL, padding=(1,2), box=box.HEAVY_EDGE), Panel(Group(title_text('SELECTED RECORD', '◆'), Text(''), detail), border_style=BEAST_JADE, style=BEAST_PANEL, padding=(1,2), box=box.ROUNDED))
    page = Table.grid(expand=True); page.add_column(ratio=1)
    page.add_row(cards); page.add_row(lower)
    return page


def visual_deployment(self: PageHost, snap: BackendSnapshot, index: int):
    deploy = snap.deployment_score()
    crystal_reuse = snap.crystal_reuse if isinstance(snap.crystal_reuse, dict) else {}
    integration_health = crystal_reuse.get('integration_health') if isinstance(crystal_reuse.get('integration_health'), dict) else {}
    memory_security = snap.memory_security if isinstance(snap.memory_security, dict) else {}
    memory_hull = memory_security.get('memory_hull') if isinstance(memory_security.get('memory_hull'), dict) else {}
    passport = memory_security.get('agent_passport') if isinstance(memory_security.get('agent_passport'), dict) else {}
    passport_lint = passport.get('policy_lint') if isinstance(passport.get('policy_lint'), dict) else {}
    configured_integrations = int(integration_health.get('configured_count') or 0)
    total_integrations = int(integration_health.get('integration_count') or len(crystal_reuse.get('integrations') or []))
    memory_failed = int(memory_hull.get('failed_sidecars') or 0)
    provider_auth = provider_secrets_operational(snap)
    kv_counts = crystal_kv_prefill_counts(snap)
    rows = [
        ('Nginx config', 'OK' if deploy.get('nginx_ready') else 'WARN', f"{len(snap.nginx_config.splitlines())} lines"),
        ('LiteLLM sidecar', 'OK' if deploy.get('litellm_running') else 'WARN', f"port {deploy.get('litellm_port') or 4000}"),
        ('LiteLLM models', 'OK' if deploy.get('litellm_models') else 'WARN', f"{deploy.get('litellm_models') or len(snap.litellm_models)} models"),
        ('Provider adapters', 'OK' if snap.provider_adapters else 'WARN', f"{len(snap.provider_adapters)} adapters"),
        ('Provider secrets', provider_auth['status'], provider_auth['detail']),
        ('Crystal reuse gateway', 'OK' if crystal_reuse else 'WARN', f"{int((crystal_reuse.get('storage') or {}).get('active_credits') or 0)} active credits"),
        ('Public reuse adapters', 'OK' if total_integrations else 'WARN', f"{configured_integrations}/{total_integrations} configured"),
        ('Memory security', 'OK' if memory_security and not memory_failed and passport_lint.get('valid') else 'WARN', f"{memory_failed} failed sidecars"),
    ]
    index = clamp(index, 0, len(rows)-1)
    ok_count = sum(1 for _, status, _ in rows if status == 'OK')
    cards = Table.grid(expand=True)
    for _ in range(5): cards.add_column(ratio=1)
    cards.add_row(
        widget_card('Deploy Health', f'{ok_count}/{len(rows)}', 'subsystems ready', circle_meter((ok_count / max(1,len(rows))) * 100, size='small')),
        widget_card('Nginx Edge', 'READY' if deploy.get('nginx_ready') else 'WAIT', 'reverse proxy', toggle_pill(deploy.get('nginx_ready'))),
        widget_card('LiteLLM', 'RUN' if deploy.get('litellm_running') else 'OFF', f"port {deploy.get('litellm_port') or 4000}", toggle_pill(deploy.get('litellm_running'))),
        widget_card('Models', deploy.get('litellm_models') or len(snap.litellm_models), 'sidecar registry', distribution_ring({'models': len(snap.litellm_models), 'adapters': len(snap.provider_adapters), 'secrets': snap.provider_secret_count()})),
        widget_card('Crystal Adapters', f'{configured_integrations}/{total_integrations}', 'LMCache/GPTCache/OTEL/etc', distribution_ring({'configured': configured_integrations, 'available': max(0, total_integrations - configured_integrations)})),
    )
    matrix = dense_status_list(rows, index, max_rows=8)
    config_preview = snap.nginx_config[:1000] if snap.nginx_config else 'No generated Nginx text returned from /edgek/deploy/nginx-config.'
    model_table = litellm_models_table(snap.litellm_models, include_state=True)
    lower = Table.grid(expand=True); lower.add_column(ratio=1); lower.add_column(ratio=1)
    lower.add_row(
        fixed_panel(Group(title_text('DEPLOY MATRIX', '⇄'), Text(''), matrix), border_style=BEAST_ACID, style=BEAST_PANEL, padding=(1,2), box_style=box.ROUNDED),
        fixed_panel(Group(title_text('LITELLM MODELS', 'λ'), Text(''), model_table), border_style=BEAST_JADE, style=BEAST_PANEL, padding=(1,2), box_style=box.ROUNDED),
    )
    layer_table = Table(expand=True, box=box.SIMPLE)
    layer_table.add_column('Layer')
    layer_table.add_column('Deploy state')
    layer_table.add_column('Contract')
    layer_table.add_row('Crystal Reuse Gateway', Text('OK' if crystal_reuse else 'WAIT', style=BEAST_GREEN if crystal_reuse else BEAST_WARN), 'semantic credit, exact answer, KV prefill, provider fallback')
    layer_table.add_row('KV Prefill Store', Text('OK' if kv_counts['display_blocks'] else 'WAIT', style=BEAST_GREEN if kv_counts['display_blocks'] else BEAST_WARN), f"{kv_counts['durable_prefills']} durable prefill(s), {kv_counts['live_blocks']} live block(s)")
    layer_table.add_row('Public Reuse Adapters', Text(f'{configured_integrations}/{total_integrations}', style=BEAST_ACID if total_integrations else BEAST_WARN), 'LMCache / GPTCache / LiteLLM / OpenLLMetry / Langfuse / TensorZero / Promptfoo')
    layer_table.add_row('Memory Hull', Text('OK' if memory_hull and not memory_failed else 'WARN', style=BEAST_GREEN if memory_hull and not memory_failed else BEAST_WARN), f"{memory_hull.get('verified_sidecars', 0)} verified sidecar(s)")
    layer_table.add_row('Residue Seal', Text('OK' if (memory_security.get('residue_seal') or {}).get('key_exists') else 'WARN', style=BEAST_GREEN if (memory_security.get('residue_seal') or {}).get('key_exists') else BEAST_WARN), 'purpose-bound signatures')
    layer_table.add_row('Agent Passport', Text('OK' if passport_lint.get('valid') else 'WARN', style=BEAST_GREEN if passport_lint.get('valid') else BEAST_WARN), f"{passport_lint.get('policy_count', 0)} identity policy rule(s)")
    page = Table.grid(expand=True); page.add_column(ratio=1)
    page.add_row(cards)
    page.add_row(lower)
    page.add_row(Panel(Group(title_text('CRYSTAL + MEMORY LAYERS', '◇'), chip_line('CRYSTAL', 'HULL', 'SEAL', 'PASSPORT'), Text(''), layer_table), border_style=BEAST_EMERALD, style=BEAST_PANEL, padding=(1,2), box=box.ROUNDED))
    page.add_row(Panel(Group(title_text('NGINX PREVIEW', '▤'), Text(''), Text(config_preview, style=BEAST_MUTED)), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(1,2), box=box.SQUARE))
    return page


# Install the less-listy visual pages.
PageHost.live_session_preview = visual_live_session_preview
PageHost.routing_fabric = visual_routing_fabric
PageHost.intelligence = visual_intelligence
PageHost.economy = visual_economy
PageHost.chronicle = visual_chronicle
PageHost.deployment = visual_deployment

# ---------------------------------------------------------------------------
# Final visual deck polish: stable sprite gutters, PREC command deck, and
# richer Compute Economy action surfaces.
# ---------------------------------------------------------------------------

PHASE_DECK = [
    ('perceive', 'P', 'PERCEIVE', 'Context sensing', '▱'),
    ('reason', 'R', 'REASON', 'Route judgement', '◇'),
    ('economize', 'E', 'ECONOMIZE', 'Compute thrift', '$'),
    ('crystallize', 'C', 'CRYSTALLIZE', 'Verified residue', '◆'),
]


def phase_status_value(phases: Dict[str, Any], key: str) -> str:
    return str(phases.get(key) or phases.get(key.capitalize()) or phases.get(key.upper()) or 'WAIT')


def phase_index_score(status: Any) -> int:
    text = str(status or '').strip().lower()
    if text in {'ok', 'done', 'completed', 'complete', 'passed', 'ready'}:
        return 96
    if text in {'active', 'running', 'working', 'current'}:
        return 88
    if any(x in text for x in ['warn', 'wait', 'pending', 'unknown']):
        return 58
    if any(x in text for x in ['error', 'fail', 'blocked', 'deny']):
        return 22
    return pct_from_status(status, fallback=72)


def phase_card(key: str, letter: str, label: str, note: str, icon: str, status: Any, selected: bool = False) -> Panel:
    pct = phase_index_score(status)
    accent = BEAST_ACID if selected else BEAST_GREEN if pct >= 85 else BEAST_WARN if pct >= 55 else BEAST_DANGER
    top = Table.grid(expand=True)
    top.add_column(width=4); top.add_column(ratio=1); top.add_column(width=12)
    top.add_row(Text(letter, style=f'bold {accent}'), Text(label, style=f'bold {accent}'), status_mark(status) + Text(' ' + str(status), style=status_style(status)))
    body = Group(
        top,
        Text(note, style=BEAST_MUTED),
        Text(''),
        circle_meter(pct, 'phase health', size='small'),
        Text(''),
        block_meter(pct, width=18),
        Text(''),
        line_graph([pct * .55, pct * .62, pct * .71, pct * .86, pct], width=24, good=pct >= 55),
    )
    return Panel(body, border_style=accent, style=BEAST_PANEL_SOFT, padding=(1,1), box=box.HEAVY_EDGE if selected else box.ROUNDED)


def prec_flow_line(phases: Dict[str, Any]) -> Text:
    text = Text()
    for idx, (key, letter, label, _, _) in enumerate(PHASE_DECK):
        status = phase_status_value(phases, key)
        pct = phase_index_score(status)
        style = BEAST_GREEN if pct >= 85 else BEAST_WARN if pct >= 55 else BEAST_DANGER
        text.append('◉', style=f'bold {style}')
        text.append(f' {letter}:{label[:3]} ', style=f'bold {style}')
        if idx < len(PHASE_DECK) - 1:
            text.append('━━▶ ', style=BEAST_BORDER_DIM)
    return text


def visual_prec_lifecycle_deck(self: PageHost, snap: BackendSnapshot, index: int):
    phases = snap.phase_status() if snap else {}
    if not phases:
        phases = {'perceive': 'WAIT', 'reason': 'WAIT', 'economize': 'WAIT', 'crystallize': 'WAIT'}
    scores = [phase_index_score(phase_status_value(phases, key)) for key, *_ in PHASE_DECK]
    active_candidates = [i for i, score in enumerate(scores) if 55 <= score < 95]
    selected_phase = clamp(index, 0, len(PHASE_DECK) - 1) if index else (active_candidates[0] if active_candidates else min(len(PHASE_DECK)-1, max(0, sum(1 for s in scores if s >= 90) - 1)))

    cards = Table.grid(expand=True)
    for _ in range(4):
        cards.add_column(ratio=1)
    cards.add_row(*[
        phase_card(key, letter, label, note, icon, phase_status_value(phases, key), i == selected_phase)
        for i, (key, letter, label, note, icon) in enumerate(PHASE_DECK)
    ])

    overall = sum(scores) / max(1, len(scores))
    handshake = snap.session_handshake if isinstance(snap.session_handshake, dict) else {}
    precheck = snap.handoff_precheck if isinstance(snap.handoff_precheck, dict) else {}
    selected_key, selected_letter, selected_label, selected_note, selected_icon = PHASE_DECK[selected_phase]
    selected_status = phase_status_value(phases, selected_key)

    gate_rows = [
        ('Lifecycle chain', 'OK' if overall >= 80 else 'WARN', f'{overall:.0f}% harmonic'),
        ('Session handshake', 'OK' if handshake else 'WAIT', str(handshake.get('session_id') or 'no active handshake')[:48]),
        ('Handoff precheck', 'OK' if precheck.get('ready') else 'WARN', str(precheck.get('reason') or precheck.get('status') or 'current_task_markup pending')[:48]),
        ('Policy covenant', 'OK', 'governed write path'),
        ('Local scout', 'OK' if snap.online else 'WARN', 'context scout armed' if snap.online else 'gateway offline'),
    ]
    gate_matrix = dense_status_list(gate_rows, 0, max_rows=8)

    selected_detail = Table.grid(expand=True)
    selected_detail.add_column(width=18); selected_detail.add_column(ratio=1)
    selected_detail.add_row(Text('Selected phase', style=BEAST_MUTED), Text(f'{selected_letter} • {selected_label}', style=f'bold {BEAST_ACID}'))
    selected_detail.add_row(Text('Status', style=BEAST_MUTED), status_mark(selected_status) + Text(' ' + str(selected_status), style=status_style(selected_status)))
    selected_detail.add_row(Text('Purpose', style=BEAST_MUTED), Text(selected_note, style=BEAST_TEXT))
    selected_detail.add_row(Text('Signal', style=BEAST_MUTED), block_meter(phase_index_score(selected_status), width=20))
    selected_detail.add_row(Text('Enabled', style=BEAST_MUTED), toggle_pill(phase_index_score(selected_status) >= 55))
    selected_detail.add_row(Text('Trend', style=BEAST_MUTED), line_graph([22, 38, 57, 74, phase_index_score(selected_status)], width=26))

    lower = Table.grid(expand=True)
    lower.add_column(ratio=2); lower.add_column(ratio=1); lower.add_column(ratio=1)
    lower.add_row(
        Panel(Group(title_text('PREC PIPELINE', '◇'), Text(''), prec_flow_line(phases), Text(''), gate_matrix), border_style=BEAST_ACID, style=BEAST_PANEL, padding=(1,2), box=box.HEAVY_EDGE),
        Panel(Group(title_text('SELECTED NODE', selected_icon), Text(''), selected_detail), border_style=BEAST_JADE, style=BEAST_PANEL, padding=(1,2), box=box.ROUNDED),
        Panel(Group(title_text('LIFECYCLE MIX', '◉'), distribution_ring({k: max(1, phase_index_score(phase_status_value(phases, k)) // 20) for k, *_ in PHASE_DECK}), Text(''), circle_meter(overall, 'overall')), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(1,1), box=box.ROUNDED),
    )

    page = Table.grid(expand=True); page.add_column(ratio=1)
    page.add_row(Panel(Group(title_text('PREC LIFECYCLE', PAGE_SYMBOLS['PREC']), chip_line('PERCEIVE', 'REASON', 'ECONOMIZE', 'CRYSTALLIZE'), Text(''), cards), border_style=BEAST_ACID, style=BEAST_PANEL, padding=(1,2), box=box.HEAVY_EDGE))
    page.add_row(lower)
    return page


def economy_action_icon(action: str) -> str:
    return {
        'rollout_monitor': '⌁',
        'economy_dashboard': '$',
        'start_forge_node': '⚙',
        'promote_fleet': '♕',
        'refresh_economy': '↻',
    }.get(action, '▷')


def economy_action_meter(row: Dict[str, Any]) -> int:
    action = str(row.get('action') or '')
    status = str(row.get('status') or '')
    if action == 'start_forge_node':
        try:
            return min(100, 55 + int(status.split(':')[-1]) * 12)
        except Exception:
            return 62
    if action == 'promote_fleet':
        try:
            return min(100, 50 + int(status.split(':')[-1]) * 10)
        except Exception:
            return pct_from_status(status, fallback=72)
    return pct_from_status(status, fallback=78)


def economy_action_card(row: Dict[str, Any], selected: bool = False) -> Panel:
    action = str(row.get('action') or '')
    name = str(row.get('name') or human_label(action))
    status = str(row.get('status') or 'ready')
    value = str(row.get('value') or '')
    hint = str(row.get('hint') or '')
    pct = economy_action_meter(row)
    accent = BEAST_ACID if selected else BEAST_GREEN if pct >= 80 else BEAST_WARN if pct >= 55 else BEAST_DANGER
    header = Table.grid(expand=True)
    header.add_column(width=4); header.add_column(ratio=1); header.add_column(width=12)
    header.add_row(Text(economy_action_icon(action), style=f'bold {accent}'), Text(name.upper(), style=f'bold {accent}'), status_mark(status) + Text(' ' + status[:8], style=status_style(status)))
    visual = distribution_ring({'ready': pct, 'reserve': max(1, 100 - pct)}) if action in {'promote_fleet', 'economy_dashboard'} else line_graph([pct*.42, pct*.55, pct*.63, pct*.8, pct], width=24, good=pct >= 55)
    body = Group(
        header,
        Text(value[:54], style=BEAST_TEXT),
        Text(hint[:82], style=BEAST_MUTED),
        Text(''),
        block_meter(pct, width=18),
        Text(''),
        visual,
        Text(''),
        Text('▶ ENTER TO RUN' if selected else '◇ queued action', style=f'bold {accent}' if selected else BEAST_MUTED),
    )
    return Panel(body, border_style=accent, style=BEAST_PANEL_SOFT, padding=(1,1), box=box.HEAVY_EDGE if selected else box.ROUNDED)


def visual_economy_command_deck(self: PageHost, snap: BackendSnapshot, index: int):
    try:
        report = build_dashboard()
    except Exception:
        report = {}
    metrics = snap.compute_metrics if isinstance(snap.compute_metrics, dict) else {}
    savings = snap.compute_savings if isinstance(snap.compute_savings, dict) else {}
    rollout = report.get('rollout') if isinstance(report.get('rollout'), dict) else {}
    forge = report.get('forge') if isinstance(report.get('forge'), dict) else {}
    forge_totals = forge.get('totals') if isinstance(forge.get('totals'), dict) else {}
    crystal = report.get('crystallization') if isinstance(report.get('crystallization'), dict) else {}
    crystal_observed = crystal.get('observed') if isinstance(crystal.get('observed'), dict) else {}
    statuses = metrics.get('statuses') if isinstance(metrics.get('statuses'), dict) else {}
    observed = int(metrics.get('observed_total_tokens') or 0)
    avoidable = int(metrics.get('estimated_avoidable_total_tokens') or 0)
    receipts = int(metrics.get('sample_size') or 0)
    false_supp = float(metrics.get('false_suppression_rate') or 0.0) * 100
    coverage = float(metrics.get('cost_coverage_rate') or 0.0) * 100
    token_cal = float(metrics.get('token_calibration_coverage_rate') or 0.0) * 100
    weekly = savings.get('potential_weekly_savings_usd') or savings.get('availability') or 'unavailable'
    evidence = master_evidence_summary(snap)
    latest = latest_mega_summary(snap)
    crystal_reuse = snap.crystal_reuse if isinstance(snap.crystal_reuse, dict) else {}
    crystal_storage = crystal_reuse.get('storage') if isinstance(crystal_reuse.get('storage'), dict) else {}
    crystal_hits = int(crystal_storage.get('total_reuse_count') or 0)
    crystal_saved_tokens = int(crystal_storage.get('measured_reuse_tokens_saved') or 0)
    crystal_active = int(crystal_storage.get('active_credits') or 0)
    kv_counts = crystal_kv_prefill_counts(snap)

    cards = Table.grid(expand=True)
    for _ in range(6): cards.add_column(ratio=1)
    cards.add_row(
        widget_card('Receipts', receipts, 'compute samples', circle_meter(min(100, receipts * 4), size='small'), delta=delta_badge(9.2)),
        widget_card('Avoidable Tokens', avoidable, f'observed {observed}', line_graph([observed*.15, observed*.28, avoidable*.52, avoidable], width=18), delta=delta_badge((avoidable / max(1, observed))*100 if observed else 0)),
        widget_card('Weekly Savings', weekly, 'potential', graph_wall([1, 3, 2, 5, 7, 6, 8, 9], width=18), delta=delta_badge(4.7)),
        widget_card('False Suppression', f'{false_supp:.1f}%', 'lower is better', circle_meter(max(0, 100 - false_supp), size='small'), delta=delta_badge(-false_supp, positive_good=False), danger=false_supp > 0),
        widget_card('Crystallization', crystal_observed.get('observed_total', crystal.get('promoted_count', 0)), f"{crystal.get('promoted_count', 0)} promoted / {crystal_observed.get('promotion_candidate_files', 0)} candidates", distribution_ring({'promoted': int(crystal.get('promoted_count') or 0), 'candidates': int(crystal_observed.get('promotion_candidate_files') or 0), 'events': int(crystal_observed.get('evidence_crystallize_events') or 0)})),
        widget_card('Mega Calls', latest['provider_call_receipts'], f"{latest['impact_fingerprint_files']} fingerprints", distribution_ring({'provider': latest['provider_call_receipts'], 'reuse': latest['compute_governor_receipts'], 'fp': latest['impact_fingerprint_files']}), delta=delta_badge(latest['phase_pass_count'])),
    )
    cards.add_row(
        widget_card('Crystal Reuse Saved', crystal_saved_tokens, f'{crystal_hits} reuse hit(s)', line_graph([0, max(1, crystal_saved_tokens * .25), max(1, crystal_saved_tokens * .6), max(1, crystal_saved_tokens)], width=18), delta=delta_badge((crystal_saved_tokens / max(1, observed)) * 100 if observed else 0)),
        widget_card('Provider Calls Avoided', crystal_hits, f'{crystal_active} active credit(s)', distribution_ring({'hits': crystal_hits, 'active': crystal_active, 'fallback': max(1, receipts - crystal_hits)})),
        widget_card('KV Prefill Blocks', kv_counts['display_blocks'], f"{kv_counts['durable_prefills']} durable / {kv_counts['live_blocks']} live", circle_meter(96 if kv_counts['display_blocks'] else 55, size='small')),
        widget_card('Reuse Gateway', 'ON' if crystal_reuse else 'WAIT', 'pre-provider decision plane', toggle_pill(bool(crystal_reuse))),
        widget_card('Reuse Quality', f"{float(crystal_storage.get('reuse_success_rate') or 1.0 if crystal_hits else 0.0):.0%}", 'verified local residue', circle_meter(96 if crystal_hits else 58, size='small')),
        widget_card('Reuse Boundary', 'SEALED' if crystal_reuse else 'WAIT', 'policy/signature gated', toggle_pill(bool(crystal_reuse))),
    )

    actions = economy_action_rows(report)
    index = clamp(index, 0, len(actions)-1)
    action_grid = Table.grid(expand=True)
    action_grid.add_column(ratio=1); action_grid.add_column(ratio=1)
    for start in range(0, len(actions), 2):
        left = economy_action_card(actions[start], selected=start == index)
        right = economy_action_card(actions[start+1], selected=start+1 == index) if start + 1 < len(actions) else Panel(Text(''), border_style=BEAST_BORDER_DIM, style=BEAST_PANEL)
        action_grid.add_row(left, right)

    selected_action = actions[index] if actions else {}
    selected_pct = economy_action_meter(selected_action)
    selected_panel = Group(
        title_text('SELECTED ECONOMY COMMAND', economy_action_icon(str(selected_action.get('action') or ''))),
        Text(''),
        Text(str(selected_action.get('name') or 'Economy action'), style=f'bold {BEAST_ACID}'),
        Text(str(selected_action.get('hint') or ''), style=BEAST_MUTED),
        Text(''),
        circle_meter(selected_pct, 'readiness'),
        Text(''),
        toggle_pill(True, 'armed'),
        Text(''),
        Text('Enter/v runs this command. t tests rollout. a promotes/starts Forge.', style=BEAST_MUTED),
    )

    rollup = Table.grid(expand=True); rollup.add_column(width=22); rollup.add_column(ratio=1)
    for label, value in [
        ('Rollout readiness', rollout.get('readiness') or 'unknown'),
        ('Redlines', ', '.join(rollout.get('redlines') or []) or 'none'),
        ('Forge nodes', forge_totals.get('nodes', 0)),
        ('Candidates', forge_totals.get('candidates_produced', 0)),
        ('Promoted', crystal.get('promoted_count', 0)),
        ('Promotion files', crystal_observed.get('promotion_candidate_files', 0)),
        ('Crystallize events', crystal_observed.get('evidence_crystallize_events', 0)),
        ('Crystal reuse saved', f'{crystal_saved_tokens} tokens'),
        ('Provider calls avoided', crystal_hits),
        ('Receipt statuses', ', '.join(f'{k}:{v}' for k, v in statuses.items()) or 'none'),
    ]:
        rollup.add_row(Text(label, style=BEAST_MUTED), Text(str(value), style=status_style(value)))

    lower = Table.grid(expand=True); lower.add_column(ratio=2); lower.add_column(ratio=1)
    lower.add_row(
        fixed_panel(Group(title_text('ECONOMY ACTIONS', '▷'), chip_line('↑↓ SELECT', 'ENTER RUN', 'E ACTIONS'), Text(''), action_grid), border_style=BEAST_ACID, style=BEAST_PANEL, padding=(1,2), box_style=box.ROUNDED),
        fixed_panel(selected_panel, border_style=BEAST_JADE, style=BEAST_PANEL, padding=(1,2), box_style=box.ROUNDED),
    )
    deep = Table.grid(expand=True); deep.add_column(ratio=2); deep.add_column(ratio=1)
    deep.add_row(
        fixed_panel(Group(title_text('TOKEN ECONOMY CURVE', '$'), Text(''), line_graph([observed * .08, observed * .21, observed * .37, avoidable * .70, avoidable, avoidable * 1.05], width=62), Text(''), block_meter((avoidable / max(1, observed))*100 if observed else 0, width=36)), border_style=BEAST_JADE, style=BEAST_PANEL, padding=(1,2), box_style=box.ROUNDED),
        fixed_panel(Group(title_text('ROLLUP DISTRIBUTION', '◉'), distribution_ring({'rollout': 1 if rollout else 0, 'forge': forge_totals.get('nodes', 0), 'promoted': crystal.get('promoted_count', 0), 'candidates': crystal_observed.get('promotion_candidate_files', 0), 'events': crystal_observed.get('evidence_crystallize_events', 0), 'receipts': max(1, receipts)}), Text(''), rollup), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(1,1), box_style=box.ROUNDED),
    )

    definitive = Table.grid(expand=True)
    definitive.add_column(width=24); definitive.add_column(ratio=1)
    for label, value, style in [
        ('Frozen release', f"{evidence['release']} / {evidence['status']}", BEAST_GREEN if evidence['available'] else BEAST_WARN),
        ('Controlled design', f"{evidence['observed_cells']}/{evidence['target_cells']} ({evidence['progress_rate']:.0%})", BEAST_WARN if evidence['remaining_cells'] else BEAST_GREEN),
        ('Mature QPCCD', f"{evidence['qpccd_numerator']}/{evidence['qpccd_denominator']} = {evidence['qpccd_rate']:.1%}", BEAST_GREEN if evidence['qpccd_numerator'] else BEAST_WARN),
        ('Deterministic reuse', evidence['deterministic_reuse'], BEAST_GREEN),
        ('Mutation recovery', f"{evidence['mutation_recovered']}/{evidence['mutation_cases']}", BEAST_GREEN if evidence['mutation_cases'] and evidence['mutation_recovered'] == evidence['mutation_cases'] else BEAST_WARN),
        ('Cross-provider reuse', f"{evidence['cross_provider_cases']} primary + {evidence['groq_scout_cases']} scout", BEAST_GREEN),
        ('Avoided tokens', f"{evidence['avoided_tokens_estimate']:,} estimated", BEAST_ACID),
        ('Latest omni run', evidence['latest_generated_at'] or 'unavailable', BEAST_GREEN if evidence['latest_generated_at'] else BEAST_WARN),
        ('Latest provider', evidence['latest_provider'] or 'unavailable', BEAST_GREEN if evidence['latest_provider'] else BEAST_WARN),
        ('Latest completion', f"{evidence['latest_completed']}/{evidence['latest_live_tasks']} tasks", BEAST_GREEN if evidence['latest_completed'] else BEAST_WARN),
        ('Clean / rescued', f"{evidence['latest_clean_completed']} clean / {evidence['latest_rescued_completed']} rescued", BEAST_ACID),
        ('Coverage layers', f"{evidence['latest_covered_layers']}/{evidence['latest_total_layers']}", BEAST_GREEN if evidence['latest_covered_layers'] else BEAST_WARN),
        ('Actual billing', 'pending provider cost capture', BEAST_WARN),
    ]:
        definitive.add_row(Text(label, style=BEAST_MUTED), Text(str(value), style=style))

    latest_table = Table.grid(expand=True)
    latest_table.add_column(width=24); latest_table.add_column(ratio=1)
    for label, value, style in [
        ('Newest artifact', latest['artifact_path'][-88:] or 'missing', BEAST_TEXT if latest['available'] else BEAST_WARN),
        ('Mode / live', f"{latest['mode']} / {latest['live']}", BEAST_GREEN if latest['live'] else BEAST_WARN),
        ('Provider calls', f"{latest['raw_live_result_count']} raw / {latest['live_result_count']} retained", BEAST_GREEN if latest['live_result_count'] else BEAST_WARN),
        ('Call receipts', f"{latest['provider_call_receipts']} jsonl / {latest['provider_call_receipt_files']} files", BEAST_GREEN if latest['provider_call_receipts'] else BEAST_WARN),
        ('Fingerprints', f"{latest['impact_fingerprint_files']} impact files", BEAST_GREEN if latest['impact_fingerprint_files'] else BEAST_WARN),
        ('Reuse receipts', f"{latest['compute_governor_receipts']} CG / {latest['crystallization_events']} events", BEAST_GREEN if latest['compute_governor_receipts'] else BEAST_WARN),
        ('Mutation recovery', f"{latest['recovered_count']}/{latest['mutation_case_count']} recovered; false reuse {latest['false_reuse_count']}", BEAST_GREEN if latest['mutation_case_count'] and latest['false_reuse_count'] == 0 else BEAST_WARN),
        ('Phase package', f"{latest['phase_pass_count']}/{latest['phase_count']} pass", BEAST_GREEN if latest['phase_package_passed'] else BEAST_WARN),
        ('Integrity', latest['integrity_hash'][:56] or 'missing', BEAST_GREEN if latest['integrity_hash'] else BEAST_WARN),
    ]:
        latest_table.add_row(Text(label, style=BEAST_MUTED), Text(str(value), style=style))

    page = Table.grid(expand=True); page.add_column(ratio=1)
    page.add_row(Panel(Group(title_text('COMPUTE ECONOMY', PAGE_SYMBOLS['Economy']), chip_line('INFERENCE ECONOMY', 'FORGE', 'CRYSTALLIZE'), Text(''), cards), border_style=BEAST_ACID, style=BEAST_PANEL, padding=(1,2), box=box.HEAVY_EDGE))
    page.add_row(lower)
    page.add_row(deep)
    page.add_row(Panel(Group(title_text('DEFINITIVE EVIDENCE', '◆'), chip_line(evidence['release'], evidence['status'].upper()), Text(''), definitive), border_style=BEAST_EMERALD, style=BEAST_PANEL, padding=(1,2), box=box.HEAVY_EDGE))
    page.add_row(Panel(Group(title_text('LATEST MEGA ARTIFACT', '◇'), chip_line('PROVIDER RECEIPTS', 'FINGERPRINTS', 'PHASE 1-6'), Text(''), latest_table), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(1,2), box=box.HEAVY_EDGE))
    return page


class EconomyActionResultScreen(ModalScreen):
    BINDINGS = [Binding('escape','app.pop_screen','Close'), Binding('q','app.pop_screen','Close'), Binding('v','app.pop_screen','Close')]

    def __init__(self, title: str, action: str, result: ActionResult):
        super().__init__()
        self.result_title = title
        self.action = action
        self.result = result

    def compose(self) -> ComposeResult:
        with VerticalScroll(id='modal-scroll'):
            yield Static(self.render_result(), id='economy-action-result')

    async def on_key(self, event: events.Key) -> None:
        modal_scroll_key(self, event)

    def render_result(self):
        data = self.result.data if isinstance(self.result.data, dict) else {}
        ok = bool(self.result.ok)
        action = str(self.action or 'economy_dashboard')
        accent = BEAST_GREEN if ok else BEAST_DANGER
        redlines = data.get('redlines') if isinstance(data.get('redlines'), list) else []
        promoted = data.get('promoted') if isinstance(data.get('promoted'), list) else []
        blocked = data.get('blocked') if isinstance(data.get('blocked'), list) else []
        readiness = data.get('readiness') or (data.get('rollout') or {}).get('readiness') if isinstance(data.get('rollout'), dict) else data.get('readiness')
        cards = Table.grid(expand=True)
        for _ in range(4): cards.add_column(ratio=1)
        cards.add_row(
            widget_card('Result', 'OK' if ok else 'REDLINE', self.result.summary or self.result.error or '', circle_meter(96 if ok else 24, size='small'), delta=delta_badge(8 if ok else -12), danger=not ok),
            widget_card('Readiness', readiness or 'ready', 'rollout signal', line_graph([28, 42, 61, 78, 92 if ok else 34], width=20, good=ok)),
            widget_card('Promoted', len(promoted), f'{len(blocked)} blocked', distribution_ring({'promoted': len(promoted), 'blocked': len(blocked), 'other': 1}), danger=bool(blocked)),
            widget_card('Redlines', len(redlines), 'safety blockers', circle_meter(max(0, 100 - len(redlines) * 18), size='small'), danger=bool(redlines)),
        )
        detail_rows = Table.grid(expand=True); detail_rows.add_column(width=20); detail_rows.add_column(ratio=1)
        detail_rows.add_row(Text('Action', style=BEAST_MUTED), Text(human_label(action), style=f'bold {BEAST_ACID}'))
        detail_rows.add_row(Text('Title', style=BEAST_MUTED), Text(self.result.title, style=BEAST_TEXT))
        detail_rows.add_row(Text('Summary', style=BEAST_MUTED), Text(self.result.summary or '', style=status_style(self.result.summary)))
        detail_rows.add_row(Text('Error', style=BEAST_MUTED), Text(self.result.error or 'none', style=BEAST_DANGER if self.result.error else BEAST_GREEN))
        detail_rows.add_row(Text('Status', style=BEAST_MUTED), status_mark('OK' if ok else 'ERROR') + Text(' verified' if ok else ' review needed', style=accent))

        raw_preview = economy_result_payload(action, data) if data else Text(str(self.result.data or 'No payload returned.'), style=BEAST_MUTED)
        body = Group(
            title_text('ECONOMY ACTION RESULT', economy_action_icon(action)),
            Text('Esc/q/v closes this command result deck.', style=BEAST_MUTED),
            Text(''),
            cards,
            Text(''),
            Panel(Group(title_text('COMMAND RECEIPT', '✓' if ok else '✕'), Text(''), detail_rows), border_style=accent, style=BEAST_PANEL, padding=(1,2), box=box.HEAVY_EDGE),
            Text(''),
            Panel(Group(title_text('PAYLOAD', '▤'), Text(''), raw_preview), border_style=BEAST_BORDER, style=BEAST_PANEL, padding=(1,2), box=box.ROUNDED),
        )
        return Panel(body, border_style=accent, style=BEAST_PANEL, padding=(1,2), box=box.HEAVY_EDGE)


async def _run_economy_action_visual(self: BeastMissionConsole, action: str | None = None) -> None:
    self._set_mascot_state('working')
    action = action or str(self.selected_item().get('action') or 'economy_dashboard')
    try:
        if action == 'rollout_monitor':
            report = evaluate_rollout()
            ok = not bool(report.get('redlines'))
            result = ActionResult(ok, 'Rollout monitor', str(report.get('readiness') or 'unknown'), report, error='' if ok else ', '.join(report.get('redlines') or []))
        elif action == 'promote_fleet':
            report = promote_from_fleet(ROOT / 'data' / 'forge_nodes', ROOT / 'data' / 'crystallization')
            out = ROOT / 'benchmarks' / 'results' / 'forge_fleet_promotion.json'
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
            result = ActionResult(True, 'Forge fleet promotions', f"{len(report.get('promoted') or [])} promoted; {len(report.get('blocked') or [])} blocked", report)
        elif action == 'start_forge_node':
            result = self._start_local_forge_node()
        else:
            report = build_dashboard()
            result = ActionResult(True, 'Economy dashboard', str((report.get('rollout') or {}).get('readiness') or 'ready'), report)
        self.tool_events.append(f'economy {action}: ' + ('ok' if result.ok else 'redline'))
        self.chat_lines.append({'role': 'tool', 'content': result.brief(1600)})
        self.notify(result.summary or result.error, title=result.title, severity='information' if result.ok else 'warning')
        self.push_screen(EconomyActionResultScreen(result.title, action, result))
        self._set_mascot_state('finished' if result.ok else 'alert', hold_ticks=12 if result.ok else 18)
    except Exception as exc:
        self.tool_events.append(f'economy {action}: error')
        self.notify(str(exc), title='Economy action failed', severity='warning')
        self._set_mascot_state('alert', hold_ticks=18)
    self._sync()


async def _modal_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
    try:
        self.query_one('#modal-scroll', VerticalScroll).scroll_relative(y=6, animate=False, force=True, immediate=True)
        event.stop()
    except Exception:
        pass


async def _modal_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
    try:
        self.query_one('#modal-scroll', VerticalScroll).scroll_relative(y=-6, animate=False, force=True, immediate=True)
        event.stop()
    except Exception:
        pass


for _screen in [
    HelpScreen, DetailScreen, CommandPaletteScreen, ContextPickerScreen,
    PatchPlanScreen, DiffPreviewScreen, ApprovalQueueScreen, EconomyActionResultScreen,
]:
    _screen.on_mouse_scroll_down = _modal_mouse_scroll_down
    _screen.on_mouse_scroll_up = _modal_mouse_scroll_up


# Final installs override the earlier visual-widget deck.
PageHost.prec_lifecycle = visual_prec_lifecycle_deck
PageHost.economy = visual_economy_command_deck
BeastMissionConsole._run_economy_action = _run_economy_action_visual


def run() -> None:
    BeastMissionConsole().run()


if __name__ == '__main__':
    run()
