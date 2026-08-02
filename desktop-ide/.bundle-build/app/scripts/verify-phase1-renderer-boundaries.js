'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..');
const rendererRoot = path.join(root, 'renderer', 'js');
const aiRoot = path.join(rendererRoot, 'ai');
const entryPath = path.join(rendererRoot, 'beast-ai-coding.js');
const entry = fs.readFileSync(entryPath, 'utf8');
const index = fs.readFileSync(path.join(root, 'renderer', 'index.html'), 'utf8');

const expected = {
  'agent-client.js':['runInWorktree','retryLastRequest','recoverInvalidPacket','continueWithAddedContext','syncModel','providerStateRoute','resolveCodingRoute','createSession','send','fail','cancel','clear'],
  'agent-store.js':['patch','persist','restore'],
  'agent-events.js':['appendTrace','updateProgress','finishProgress','clearWatchdog','armWatchdog','eventPayload'],
  'agent-view.js':['setOpen','setExpanded','setPrompt'],
  'context-picker.js':['toggleContext','addActiveFile','captureSelection','removeSelection','suggestContext','acceptSuggestedContext','resolveRequestedContext'],
  'context-manifest.js':['mentionedFiles','normalizeContextFiles','contextFilesFor','agentContextRequests','expandContext'],
  'approval-cards.js':['handlePermissionRequest'],
  'tool-cards.js':['narrationFromTurn'],
  'plan-view.js':['draftPreviewFromRaw','structuredDraftStatus','runDoneSentence','isStructuredEditStream','proposalFromActions','proposalSummary','normalizedRestoredMessage'],
  'verification-view.js':['verifyRequestedChecks'],
  'sourceplan-handoff.js':['noteSourcePlanApply','stageSourcePlan','openSourcePlan'],
  'conversation-renderer.js':['addMessage','appendAssistant','appendTurn','updateAssistant','updateAssistantPreview','appendProposalTurns'],
  'mode-controller.js':['setMode','resolvedModeForPrompt','isAgentAnalysisPrompt','agentTurnProfile','initialAgentTurns','initialAgentProgress','instructionFor'],
  'budget-view.js':['applyCrystal','applyCompute'],
};
const names = Object.keys(expected);

assert(entry.split(/\r?\n/).length < 80, 'beast-ai-coding.js is no longer a compact composition root');
assert(entry.includes('window.BeastAICodingModules'), 'composition root does not consume the renderer module registry');
assert(entry.includes('window.BeastAICoding = Object.fromEntries'), 'public Pair Programmer API is not composed from focused modules');
for (const forbidden of ['function send(', 'function persist(', 'function stageSourcePlan(', 'function verifyRequestedChecks(', 'window.confirm(']) {
  assert(!entry.includes(forbidden), `${forbidden} leaked back into the Pair Programmer composition root`);
}

let previous = -1;
for (const name of names) {
  const filePath = path.join(aiRoot, name);
  assert(fs.existsSync(filePath), `missing renderer module ${name}`);
  const source = fs.readFileSync(filePath, 'utf8');
  const tag = `<script src="js/ai/${name}"></script>`;
  const position = index.indexOf(tag);
  assert(position > previous, `${name} is missing or out of order in renderer/index.html`);
  previous = position;
  for (const method of expected[name]) assert(source.includes(`function ${method}`) || source.includes(`async function ${method}`), `${name} does not own ${method}`);
}
assert(previous < index.indexOf('<script src="js/beast-ai-coding.js"></script>'), 'composition root loads before its renderer modules');

const listeners = [];
const context = {
  console,
  URLSearchParams,
  structuredClone,
  setTimeout,
  clearTimeout,
  localStorage:{ getItem:() => null, setItem:() => {} },
  window:{},
  document:{ addEventListener:(name, handler) => listeners.push({ name, handler }) },
  BeastStore:{ get:() => ({ workspace:{ root:'' }, connection:{ gatewayUrl:'' } }) },
  BeastRuntime:{ gatewayUrl:'' },
};
context.window.window = context.window;
vm.createContext(context);
for (const base of ['beast-ai-transport.js','beast-ai-intent.js', ...names]) {
  vm.runInContext(fs.readFileSync(path.join(aiRoot, base), 'utf8'), context, { filename:base });
}
vm.runInContext(entry, context, { filename:'beast-ai-coding.js' });

const publicMethods = [
  'restore','persist','setOpen','setExpanded','setMode','setPrompt','syncModel','toggleContext','addActiveFile',
  'suggestContext','acceptSuggestedContext','resolveRequestedContext','captureSelection','removeSelection','send',
  'runInWorktree','retryLastRequest','recoverInvalidPacket','continueWithAddedContext','cancel','clear','openSourcePlan',
  'verifyRequestedChecks','noteSourcePlanApply',
];
assert.deepEqual(Object.keys(context.window.BeastAICoding).sort(), publicMethods.sort());
assert.equal(context.window.BeastAICodingModuleManifest.length, 14);
assert(listeners.some(item => item.name === 'beast:agent-sourceplan-applied'));

console.log(JSON.stringify({
  ok:true,
  entry_lines:entry.split(/\r?\n/).length,
  module_count:names.length,
  public_method_count:publicMethods.length,
  modules:Object.fromEntries(names.map(name => [name, expected[name].length])),
}, null, 2));
