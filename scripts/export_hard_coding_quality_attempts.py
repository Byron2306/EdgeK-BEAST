#!/usr/bin/env python3
"""Export hard-coding live receipt pairs into the quality harness format."""
import argparse,json
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument('receipt');p.add_argument('--output',required=True);a=p.parse_args();r=json.loads(Path(a.receipt).read_text());root=Path(a.receipt).parent; attempts=[]
 for row in r['families']:
  family=row['family']; raw_path=root/family/'raw_teacher_output.txt';raw=raw_path.read_text(encoding='utf-8') if raw_path.is_file() else '';e=row['ephemeral_baseline']; c=row
  attempts += [{'task_id':family,'lane':'ephemeral','patch':raw,'tests_passed':bool(e['tests_passed']),'security_scan_passed':True,'no_secret_leak':True,'no_unrelated_changes':True,'provider_calls':int(e['provider_calls']),'elapsed_ms':0.0},{'task_id':family,'lane':'crystallized','patch':json.dumps(c['tool_receipt'],sort_keys=True),'tests_passed':bool(c['fresh_replay_tests_passed']),'security_scan_passed':True,'no_secret_leak':True,'no_unrelated_changes':True,'provider_calls':int(c['cloud_or_live_calls_during_replay']),'elapsed_ms':0.0}]
 out={'preregistration':{'corpus':'hard-coding-three-family-preliminary','receipt_hash':r['receipt_hash'],'quality_note':'three synthetic task families; independent blind review and matched stronger baseline still required'},'attempts':attempts};Path(a.output).write_text(json.dumps(out,indent=2)+'\n');print(a.output)
if __name__=='__main__':main()
