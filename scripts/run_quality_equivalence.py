#!/usr/bin/env python3
"""Create a sealed blind-review packet and score a completed paired run."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.kernel.compute.quality_equivalence_harness import QualityAttempt,QualityEquivalenceHarness
def main():
 p=argparse.ArgumentParser();p.add_argument('attempts');p.add_argument('--reviews');p.add_argument('--output',required=True);p.add_argument('--seed',type=int,default=0);p.add_argument('--margin',type=float,default=.25);a=p.parse_args()
 data=json.loads(Path(a.attempts).read_text()); attempts=[QualityAttempt(**x) for x in data['attempts']]; h=QualityEquivalenceHarness(seed=a.seed,noninferiority_margin=a.margin); packet,key=h.blind_packet(attempts); out=Path(a.output);out.mkdir(parents=True,exist_ok=True);(out/'blind-review.json').write_text(json.dumps(packet,indent=2)+'\n');(out/'blind-key.json').write_text(json.dumps(key,indent=2,sort_keys=True)+'\n')
 if not a.reviews: print(json.dumps({'status':'awaiting_blinded_reviews','packet':str(out/'blind-review.json'),'key_withhold':str(out/'blind-key.json')}));return 0
 reviews=json.loads(Path(a.reviews).read_text()); receipt=h.receipt(attempts,reviews,preregistration=data['preregistration']);h.write(receipt,out/'quality-equivalence-receipt.json');print(json.dumps({'status':'scored','receipt':str(out/'quality-equivalence-receipt.json'),'noninferior':receipt['quality_noninferior'],'superior':receipt['quality_superior']}));return 0
if __name__=='__main__':main()
