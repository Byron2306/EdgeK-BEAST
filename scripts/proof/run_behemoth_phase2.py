#!/usr/bin/env python3
"""BEHEMOTH II: read-only real promoted BEAST family-crystal replay gauntlet.

Only uses BEAST's family_crystals replay_stage/_interpret, registry integrity,
and the November task builder. Never promotes, edits production, calls models,
or treats a routing decision as verified execution. All experiments are staged
in a fresh output directory. Requires existing promoted composite + children.
"""
from __future__ import annotations
import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import time
import traceback

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'scripts'))

def digest(obj):
    raw = obj if isinstance(obj, bytes) else json.dumps(obj, sort_keys=True, separators=(',', ':'), default=str).encode()
    return 'sha256:' + hashlib.sha256(raw).hexdigest()

def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, sort_keys=True, indent=2, default=str) + '\n', encoding='utf-8')

def install_fixture(folder, task):
    folder.mkdir(parents=True)
    for rel, data in task['files'].items():
        target = folder / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(data, encoding='utf-8')
    return folder

def verify_independent(source, task, final):
    """Hidden tests only in a new directory, never in the resolver's worktree."""
    from app.kernel.compute.family_crystals import run_verify, tree_digest
    if not source.is_dir():
        return {'passed': False, 'reason': 'missing_executed_tree'}
    with tempfile.TemporaryDirectory(prefix='behemoth-private-') as tmp:
        shadow = Path(tmp) / 'tree'
        shutil.copytree(source, shadow, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        original_digest = digest(tree_digest(shadow))
        visible = run_verify(task['verify'], shadow)
        for rel, data in task['hidden'].items():
            target = shadow / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(data, encoding='utf-8')
        hidden = run_verify(task['hidden_verify'], shadow)
    success = visible['returncode'] == hidden['returncode'] == 0 and visible['tests_run'] >= task['tests_run'] and hidden['tests_run'] > 0
    return {'passed': success, 'source_tree_hash': original_digest,
            'visible': {'rc': visible['returncode'], 'tests_run': visible['tests_run'], 'failure_digest': digest(visible['output'])},
            'hidden': {'rc': hidden['returncode'], 'tests_run': hidden['tests_run'], 'failure_digest': digest(hidden['output'])}}

def choose(registry, crystal_id):
    from app.kernel.compute.family_crystals import FamilyCrystal
    candidates = registry.promoted()
    candidates = [c for c in candidates if set(c.component_families) == {'fix-config-constant', 'fix-off-by-one'} and len(c.component_families) == 2]
    if crystal_id:
        candidates = [c for c in candidates if c.crystal_id == crystal_id]
    if not candidates:
        raise RuntimeError('BLOCKED: no promoted constant+off-by-one composite in the selected registry')
    c = candidates[-1]
    assert isinstance(c, FamilyCrystal)
    children = [registry.get(cid)['crystal_object'] for cid in c.component_ids]
    if any(registry.get(cid)['status'] != 'promoted' for cid in (*c.component_ids, c.crystal_id)):
        raise RuntimeError('BLOCKED: composite or children are not promoted')
    return c, children

def execute(fixture, task, composite, children, path, arm):
    from app.kernel.compute.family_crystals import _interpret, replay_stage, stage_steps, tree_digest
    # For sequential without lattice, use each child's reviewed recipe, changing only
    # the intermediate expected postcondition. This isolates discovery/composition.
    current = fixture
    stages = []
    for i, child in enumerate(children):
        stage_out = path / f'stage_{i}'
        params = {'implementation_target': task['target'], 'verify_command': task['verify']}
        if arm == 'lattice':
            result = replay_stage(composite, child, i, params, current, stage_out)
        elif arm == 'sequential':
            steps = [dict(x) for x in child.steps]
            v = [j for j, s in enumerate(steps) if s['opcode'] == 'worktree.verify']
            steps[v[-1]]['expect'] = 'improve' if i == 0 else 'pass'
            result = _interpret(steps, params, current, stage_out)
        else:
            raise ValueError(arm)
        stages.append({'stage': i, 'child_id': child.crystal_id, 'execution': result})
        if not result.get('ok') or not stage_out.is_dir():
            return {'executed': True, 'passed': False, 'stage_receipts': stages,
                    'published': False, 'reason': 'stage_rejected', 'tree_after': None}
        current = stage_out
    private = verify_independent(current, task, True)
    return {'executed': True, 'passed': bool(private['passed']), 'stage_receipts': stages,
            'published': bool(private['passed']), 'tree_after': digest(tree_digest(current)), 'private': private}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', help='EXISTING promoted family_crystals.sqlite3 (read-only source)')
    ap.add_argument('--crystal-id', default='')
    ap.add_argument('--output', required=True)
    ap.add_argument('--seeds', type=int, nargs='+', default=[4317, 4318])
    args = ap.parse_args()
    from app.kernel.compute.family_crystals import FamilyRegistry, family_crystal_db_paths, run_verify, tree_digest
    from gauntlet_large_tasks import fresh_lattice_tasks
    output = Path(args.output).resolve()
    if output.exists():
        raise SystemExit('REFUSE output already exists; select a fresh --output directory')
    dbs = [Path(args.db).expanduser()] if args.db else family_crystal_db_paths()
    dbs = [p.resolve() for p in dbs if p.is_file()]
    if not dbs:
        raise SystemExit('BLOCKED no existing family crystal SQLite database; specify --db')
    # Copy DB by SQLite online backup to avoid modifying it and get consistent WAL data.
    output.mkdir(parents=True, mode=0o700)
    source = None
    for db in dbs:
        local = output / 'registry_snapshot.sqlite3'
        try:
            with sqlite3.connect(f'file:{db}?mode=ro', uri=True) as inp, sqlite3.connect(local) as out:
                inp.backup(out)
            registry = FamilyRegistry(local)
            composite, children = choose(registry, args.crystal_id)
            source = db
            break
        except (RuntimeError, LookupError, ValueError, sqlite3.Error):
            local.unlink(missing_ok=True)
            continue
    if source is None:
        dump(output / 'summary.json', {'status':'blocked', 'reason':'no valid promoted composite and children',
                                       'examined_db_count':len(dbs)})
        (output / 'registry_snapshot.sqlite3').unlink(missing_ok=True)
        raise SystemExit('BLOCKED no valid promoted matching composite; see summary.json')
    records = []
    for seed in args.seeds:
        fresh = fresh_lattice_tasks(seed)
        candidates = [t for t in fresh.values() if t['family'] == 'fresh-lattice']
        if len(candidates) != 1:
            raise RuntimeError('task schema drift: expected exactly one fresh-lattice task')
        task = candidates[0]
        root = install_fixture(output / 'fixtures' / str(seed), task)
        pristine = digest(tree_digest(root))
        initial = run_verify(task['verify'], root)
        if initial['returncode'] == 0 or initial['failures'] < 2:
            raise RuntimeError('REFUSE: pristine fixture does not present two measured defects')
        for arm in ('single_a', 'single_b', 'sequential', 'lattice', 'tampered_child', 'stage2_fault'):
            t0 = time.perf_counter()
            entry = {'schema':'beast.behemoth.phase2.attempt.v1', 'seed':seed, 'arm':arm,
                     'fixture_before':pristine, 'initial_failures':initial['failures'],
                     'composite_id':composite.crystal_id, 'children':[c.crystal_id for c in children]}
            location = output / 'arms' / str(seed) / arm
            location.mkdir(parents=True)
            try:
                if arm in ('sequential', 'lattice'):
                    entry.update(execute(root, task, composite, children, location, arm))
                elif arm.startswith('single_'):
                    # The complete child replay is intentionally expected to refuse
                    # because there remains a second defect.
                    from app.kernel.compute.family_crystals import replay_family
                    index = 0 if arm == 'single_a' else 1
                    target = location / 'child'
                    outcome = replay_family(children[index], {'implementation_target':task['target'], 'verify_command':task['verify']}, root, target)
                    final = verify_independent(target, task, True)
                    entry.update({'executed':True, 'passed':False,
                                  'expected_refusal':not outcome.get('ok') and not final.get('passed'),
                                  'execution':outcome, 'private':final})
                elif arm == 'stage2_fault':
                    # Execute the *real first* lattice stage, then corrupt the second
                    # child recipe before execution. No finished result is published.
                    from app.kernel.compute.family_crystals import replay_stage
                    first_stage = location / 'stage0'
                    params = {'implementation_target':task['target'], 'verify_command':task['verify']}
                    first = replay_stage(composite, children[0], 0, params, root, first_stage)
                    if not first.get('ok'):
                        entry.update({'executed':True, 'expected_refusal':False, 'reason':'first_stage_failed'})
                    else:
                        broken = replace(children[1], source_run_id=children[1].source_run_id + '-tampered')
                        try:
                            replay_stage(composite, broken, 1, params, first_stage, location / 'stage1')
                            refused = False
                        except (ValueError, PermissionError):
                            refused = True
                        entry.update({'executed':True, 'passed':False, 'expected_refusal':refused,
                                      'first_stage_executed':True,
                                      'input_unchanged':pristine == digest(tree_digest(root)),
                                      'published':False})
                        entry['expected_refusal'] = refused and entry['input_unchanged']
                elif arm == 'tampered_child':
                    from app.kernel.compute.family_crystals import replay_stage
                    broken = replace(children[1], source_run_id=children[1].source_run_id + '-tampered')
                    target = location / 'tampered'
                    try:
                        replay_stage(composite, broken, 1, {'implementation_target':task['target'], 'verify_command':task['verify']}, root, target)
                        refused = False
                    except (ValueError, PermissionError):
                        refused = True
                    entry.update({'executed':True, 'passed':False, 'expected_refusal':refused,
                                  'input_unchanged':pristine == digest(tree_digest(root)), 'published':False})
                if arm in ('lattice','sequential'):
                    entry['expected_control_pass'] = bool(entry['passed'])
                else:
                    entry['expected_control_pass'] = bool(entry.get('expected_refusal'))
            except Exception as exc:
                entry.update({'executed':False, 'expected_control_pass':False, 'error_type':type(exc).__name__,
                              'error_digest':digest(str(exc)), 'error_tail':str(exc)[-300:]})
            entry['elapsed_ms'] = round((time.perf_counter()-t0)*1000,3)
            records.append(entry)
    with (output / 'attempts.jsonl').open('w') as f:
        for row in records:
            f.write(json.dumps(row, sort_keys=True, default=str)+'\n')
    comparisons = []
    for seed in args.seeds:
        s = next(x for x in records if x['seed']==seed and x['arm']=='sequential')
        l = next(x for x in records if x['seed']==seed and x['arm']=='lattice')
        comparisons.append({'seed':seed,'both_verified':bool(s.get('passed') and l.get('passed')),
                            'identical_final_trees':bool(s.get('tree_after') and s.get('tree_after')==l.get('tree_after')),
                            'delta_ms_lattice_minus_sequential':round(l['elapsed_ms']-s['elapsed_ms'],3)})
    ok = all(x.get('expected_control_pass') for x in records) and all(x['identical_final_trees'] for x in comparisons)
    dump(output / 'summary.json', {'schema':'beast.behemoth.phase2.v1', 'status':'controls_pass' if ok else 'failed',
         'claim_boundary':'Real promoted BEAST family-crystal registry + interpreter; generated seeded fixtures; no memfd or network isolation in this phase; no cloud/local model calls requested by harness, not externally monitored; no live comparison; no blinded holdouts.',
         'source_db':str(source), 'snapshot_db_sha256':digest((output / 'registry_snapshot.sqlite3').read_bytes()),
         'composite_id':composite.crystal_id, 'composite_digest':composite.digest,
         'children':[{'id':c.crystal_id,'digest':c.digest} for c in children],
         'attempts':len(records),'expected_controls_passed':sum(bool(x.get('expected_control_pass')) for x in records),
         'comparisons':comparisons,'code_head':os.popen('git rev-parse HEAD 2>/dev/null').read().strip()})
    # The copied registry may contain sensitive provenance; do NOT package it into
    # shared evidence without reviewing and redacting. Hash it, then remove it.
    (output / 'registry_snapshot.sqlite3').unlink()
    (output / 'SHA256SUMS').write_text(''.join(
       f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(output)}\n"
       for p in sorted(output.rglob('*')) if p.is_file() and p.name!='SHA256SUMS' and '__pycache__' not in p.parts))
    print((output / 'summary.json').read_text())
    return 0 if ok else 1

if __name__ == '__main__':
    sys.exit(main())
