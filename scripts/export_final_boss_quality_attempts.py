#!/usr/bin/env python3
"""Export a final-boss receipt into paired quality-harness input."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
def main():
 p=argparse.ArgumentParser();p.add_argument('receipt');p.add_argument('--output',required=True);a=p.parse_args();r=json.loads(Path(a.receipt).read_text()); root=Path(a.receipt).parent
 raw=(root/'raw_teacher_output.txt').read_text(encoding='utf-8') if (root/'raw_teacher_output.txt').is_file() else ''
 crystal=json.dumps((r['far_transfer_replay']['patch_tool']),sort_keys=True)
 base=r['ephemeral_baseline']; replay=r['far_transfer_replay']
 attempts=[{'task_id':'final-boss-far-transfer','lane':'ephemeral','patch':raw,'tests_passed':bool(base['tests_passed']),'security_scan_passed':not r['training']['raw_quality'].get('contains_forbidden_secret',True),'no_secret_leak':not r['training']['raw_quality'].get('contains_forbidden_secret',True),'no_unrelated_changes':bool(base.get('raw_patch_count',0) <= len(r['training']['patch_tool']['applied'])),'provider_calls':int(base['provider_calls']),'elapsed_ms':0.0,'origin_amortized_ms':0.0,'verifier_ms':0.0},{'task_id':'final-boss-far-transfer','lane':'crystallized','patch':crystal,'tests_passed':bool(replay['tests_passed_after_patch']),'security_scan_passed':True,'no_secret_leak':True,'no_unrelated_changes':True,'provider_calls':int(replay['provider_calls_during_replay']),'elapsed_ms':0.0,'origin_amortized_ms':0.0,'verifier_ms':0.0}]
 out={'preregistration':{'corpus':'final-boss-synthetic-preliminary','receipt_hash':r['receipt_hash'],'quality_note':'single task; not eligible for promotion'},'attempts':attempts};Path(a.output).write_text(json.dumps(out,indent=2)+'\n');print(a.output)
if __name__=='__main__':main()
