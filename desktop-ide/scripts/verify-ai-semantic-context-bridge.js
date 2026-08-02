const fs = require('fs');
const path = require('path');

const repo = path.resolve(__dirname, '..', '..');
const clientPath = path.join(repo, 'desktop-ide', 'renderer', 'js', 'ai', 'agent-client.js');
const preloadPath = path.join(repo, 'desktop-ide', 'preload.js');
const plannerPath = path.join(repo, 'app', 'kernel', 'agents', 'planner_runtime.py');
const semanticPath = path.join(repo, 'app', 'kernel', 'agents', 'semantic_context.py');

function read(file) {
  return fs.readFileSync(file, 'utf8');
}

function assertCheck(label, condition) {
  if (!condition) throw new Error(`AI semantic bridge check failed: ${label}`);
  console.log(`ok - ${label}`);
}

const client = read(clientPath);
const preload = read(preloadPath);
const planner = read(plannerPath);
const semantic = read(semanticPath);
const modelBridge = read(path.join(repo, 'desktop-ide', 'renderer', 'js', 'beast-model-agent-bridge.js'));
const aiCoding = read(path.join(repo, 'desktop-ide', 'renderer', 'js', 'beast-ai-coding.js'));

assertCheck('desktop preload exposes IDE service snapshot', /ideServicesSnapshot:\s*payload\s*=>\s*ipcRenderer\.invoke\('beast:ide-services-snapshot'/.test(preload));
assertCheck('desktop preload exposes workspace index query', /workspaceIndexQuery:\s*payload\s*=>\s*ipcRenderer\.invoke\('beast:workspace-index-query'/.test(preload));
assertCheck('agent client builds live IDE semantic context', /async function buildIdeSemanticContext/.test(client) && /desktop\.ideServicesSnapshot/.test(client));
assertCheck('agent client falls back to raw workspace index snapshot', /desktop\.workspaceIndexSnapshot/.test(client));
assertCheck('semantic context is bounded before transport', /workspaceSymbols,\s*\n\s*topReferences,\s*\n\s*importEdges/.test(client) && /trimArray\(semantic\.workspaceSymbols,\s*120\)/.test(client));
assertCheck('diagnostics and code actions ride with the run', /diagnostics/.test(client) && /codeActions/.test(client));
assertCheck('active file semantic query is attached when available', /workspaceIndexQuery/.test(client) && /active_file_query/.test(client));
assertCheck('semantic risk scores rename references diagnostics and fanout', /function semanticRiskFor/.test(client) && /renameFanout/.test(client) && /diagnosticCount/.test(client) && /topReferenceFanout/.test(client));
assertCheck('weak local Ollama is detected for escalation', /function routeIsWeakLocalOllama/.test(client) && /RELIABLE_LOCAL_CODER/.test(client));
assertCheck('stronger provider route is selected for high semantic risk', /resolveSemanticEscalationRoute/.test(client) && /registryEscalationRoute/.test(client) && /nvidia_nim/.test(client));
assertCheck('local Ollama creates durable run before planner launch', /createDurableAgentRun/.test(client) && /launch:false/.test(client) && /planner\/execute/.test(client));
assertCheck('local Ollama launch timeout keeps replayable run', /isGatewayTimeout/.test(client) && /pending_ack/.test(client) && /available for replay/.test(client));
assertCheck('model registry preserves provider base URL for Ollama config', /baseUrl/.test(modelBridge) && /base_url/.test(modelBridge));
assertCheck('local Ollama run request carries provider base URL', /ollama_base_url:route\.baseUrl/.test(client) && /provider_base_url:route\.baseUrl/.test(client));
assertCheck('local Pair Programmer fallback uses installed Qwen route', /RELIABLE_LOCAL_CODER:'qwen2\.5:3b'/.test(aiCoding) && /id:'qwen2\.5:3b'/.test(modelBridge));
assertCheck('AgentRun request includes semantic_context', /request:\s*\{[\s\S]*semantic_context:semanticContext/.test(client));
assertCheck('AgentRun request includes semantic_risk', /request:\s*\{[\s\S]*semantic_risk:semanticRisk/.test(client));
assertCheck('planner prompt consumes semantic context contract', /semantic_context_contract/.test(planner) && /SEMANTIC_CONTEXT/.test(semantic));
assertCheck('semantic contract preserves navigation diagnostics and refactor signals', /navigation/.test(semantic) && /diagnostics/.test(semantic) && /refactor/.test(semantic) && /codeActions|code_actions/.test(semantic));

console.log('AI semantic context bridge verified.');
