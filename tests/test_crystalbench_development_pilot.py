import subprocess,sys,json
from pathlib import Path
def test_pilot_commits_private_verifiers_and_all_tiers(tmp_path):
 root=Path(__file__).resolve().parents[1];out=tmp_path/'pilot'
 subprocess.run([sys.executable,'scripts/build_crystalbench_development_pilot.py','--output',str(out)],cwd=root,check=True)
 m=json.loads((out/'sealed-manifest.json').read_text())
 assert m['corpus_status']=='development_rehearsal_not_independent'
 assert {x['tier'] for x in m['tasks']}=={'C0','C1','C2','C3','C5','C6'}
 assert len(list((out/'hidden-verifiers').glob('*.bin')))==6
