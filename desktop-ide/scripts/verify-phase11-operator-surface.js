const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');
const page = fs.readFileSync(path.join(root, 'renderer/js/pages/beast-agents-page.js'), 'utf8');
const viewModel = fs.readFileSync(path.join(root, '../app/kernel/operations_console/view_model.py'), 'utf8');
const approvals = fs.readFileSync(path.join(root, 'renderer/js/ai/approval-cards.js'), 'utf8');
const checks = [
  ['backend emits operator_state', viewModel.includes('\"operator_state\": operator_state')],
  ['operator state is read only', viewModel.includes('\"authority\": \"read_only_operator_projection\"')],
  ['operator state cannot grant mutation', viewModel.includes('\"grants_workspace_mutation\": False')],
  ['verification is mutation-epoch bound', viewModel.includes('verification_epoch == mutation_epoch')],
  ['stale verification blocks promotion readiness', viewModel.includes('promotion_ready = bool(sourceplan.get(\"promotion_ready\")) and verification_current')],
  ['UI renders planner truth', page.includes("['Planner', planner.phase")],
  ['UI renders execution target truth', page.includes("['Target', execution.target")],
  ['UI renders worktree epoch', page.includes("['Worktree', worktree.status")],
  ['UI renders verification currency', page.includes("verification.current ? 'CURRENT'")],
  ['UI renders human gate', page.includes("['Human Gate', approvals.pending_count")],
  ['UI renders promotion state', page.includes("['Promotion', promotion.authorized")],
  ['UI labels authority as projection', page.includes('UI projection cannot grant authority')],
  ['UI labels reuse advisory', page.includes('advisory only · never source or mutation authority')],
  ['approval resolution uses durable AgentRun endpoint', approvals.includes('/approvals/' + '$' + '{encodeURIComponent(payload.request_id)}')],
];
const failed = checks.filter(([, ok]) => !ok).map(([name]) => name);
const report = { beast_object_type:'beast_phase11_operator_surface_contract', version:'1.0', ok:failed.length===0, checks:checks.length, failed, scope:'static_backend_frontend_authority_contract', warning:'Passing this contract does not prove Electron rendering or live provider execution.' };
fs.mkdirSync(path.join(root, 'build'), { recursive:true });
fs.writeFileSync(path.join(root, 'build/PHASE11_OPERATOR_SURFACE_CONTRACT.json'), JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify(report, null, 2));
process.exit(report.ok ? 0 : 1);
