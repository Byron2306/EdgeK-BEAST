import subprocess,sys,json
from pathlib import Path
def test_rehearsal_executes_all_six_lanes(tmp_path):
 root=Path(__file__).resolve().parents[1];pilot=tmp_path/'pilot';out=tmp_path/'out'
 subprocess.run([sys.executable,'scripts/build_crystalbench_development_pilot.py','--output',str(pilot)],cwd=root,check=True)
 result=subprocess.run([sys.executable,'scripts/run_crystalbench_development_rehearsal.py',str(pilot/'sealed-manifest.json'),'--output',str(out)],cwd=root,text=True,capture_output=True,check=True)
 gate=json.loads((out/'dataset-gate.json').read_text()); public=json.loads((out/'public-evidence.json').read_text())
 assert gate['valid'] and gate['run_count']==36 and public['rehearsal_only'] is True
