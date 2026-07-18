#!/usr/bin/env python3
"""Print the exact semantic contract digests required by a scenario."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.kernel.compute.discovery_agnostic_reuse import SemanticCapabilityContract
data=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
if not data.get('cases'):
    print('NO_CASES: this is only a template; copy a sealed scenario from the origin machine')
    raise SystemExit(2)
for case in data.get('cases', []):
    c=case['task'].get('contract')
    if c:
        contract=SemanticCapabilityContract(operation=c['operation'], input_schema=c['input_schema'], output_schema=c['output_schema'], invariants=tuple(c['invariants']), tool_schema_digest=c['tool_schema_digest'], risk_tier=c['risk_tier'])
        print(case.get('case_id','?'), contract.digest)
    else:
        print(case.get('case_id','?'), case['task'].get('semantic_contract_digest'))
