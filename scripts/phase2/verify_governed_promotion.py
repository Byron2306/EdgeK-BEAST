from pathlib import Path
import sys
root=Path(__file__).resolve().parents[2]
checks=[]
def check(name, ok):
    checks.append((name,bool(ok)))
p=(root/'app/kernel/agents/promotion_engine.py').read_text()
r=(root/'app/routes/ide_routes/agent_runs.py').read_text()
check('promotion_engine_exists', 'class PromotionEngine' in p)
check('deterministic_policies', 'VALID_HASH_CHAIN' in p and 'CURRENT_VERIFICATION' in p)
check('receipt_digest', 'receipt_digest' in p)
check('human_identity_required', 'identify the human operator' in p)
check('approval_receipt_binding', 'not bound to the current promotion receipt' in p)
check('commit_candidate_only', 'applied_to_operator_workspace' in p)
check('no_agent_tool_registration', 'register_worktree_tools' not in p and 'ToolSpec(' not in p)
check('evaluation_route', '/promotion/evaluate' in r)
check('state_route', '/promotion")' in r)
check('commit_route', '/promotion/commit-candidate' in r)
for name,ok in checks: print(('PASS' if ok else 'FAIL'), name)
print(f'{sum(ok for _,ok in checks)}/{len(checks)} checks passed')
sys.exit(0 if all(ok for _,ok in checks) else 1)
