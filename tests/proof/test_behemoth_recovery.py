import json
import subprocess
import sys
from pathlib import Path


def test_recovery_controls(tmp_path):
    script=Path(__file__).resolve().parents[2]/'scripts/proof/run_behemoth_recovery.py'
    output=tmp_path/'run'
    result=subprocess.run([sys.executable,str(script),'--output',str(output),'--seed','4317'],capture_output=True,text=True,timeout=60)
    assert result.returncode == 0, result.stdout+result.stderr
    summary=json.loads((output/'summary.json').read_text())
    assert summary['expected_controls_passed']==10
    assert summary['not_run']==2
    rows=[json.loads(x) for x in (output/'attempts.jsonl').read_text().splitlines()]
    assert next(x for x in rows if x['arm']=='lattice')['transport']['seals']==15
    assert all(x['input_unmodified'] for x in rows if x['status']!='not_run')
