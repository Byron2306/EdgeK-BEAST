#!/usr/bin/env python3
"""Materialize Crucible manifest, blind packet, statistics, and public evidence."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.kernel.compute.crystal_frontier_crucible import *
def main():
 p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('--output',required=True);a=p.parse_args();d=json.loads(Path(a.input).read_text()); h=CrucibleHypotheses(**d['hypotheses']); tasks=[SealedTask(**x) for x in d['tasks']];runs=[CrucibleRun(**{**x,'applicability':ApplicabilityDecision(**x['applicability'])}) for x in d.get('runs',[])];o=Path(a.output)
 m=SealedTaskFoundry(h).manifest(tasks,branch_digest=d['branch_digest'],lattice_digest=d['lattice_digest'],policy_digest=d['policy_digest']);write_json(o/'sealed-manifest.json',m)
 packet,key=BlindReviewChamber().packet(runs,seed=d.get('blind_seed',0));write_json(o/'blind-review.json',{'rows':packet});write_json(o/'blind-key.private.json',key)
 s=StatisticalEvidenceEngine(seed=d.get('statistics_seed',0)).evaluate(tasks,runs,h);write_json(o/'statistics.json',s);write_json(o/'public-evidence.json',PublicEvidenceExporter().export(m,s,runs));print(json.dumps({'output':str(o),'manifest_digest':m['manifest_digest'],'run_count':len(runs),'statistics':s},sort_keys=True));
if __name__=='__main__':main()
