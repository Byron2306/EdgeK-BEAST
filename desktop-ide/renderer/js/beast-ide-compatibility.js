(() => {
  const sessions = new Map();
  const opened = new Map();
  const readyWaiters = new Map();
  let monacoApi = null;
  let providersBound = false;
  let disposables = [];

  const desktop = () => window.beastDesktop;
  const root = () => BeastStore.get().workspace.root || '';
  const executionTarget=()=>BeastStore.get().workspace.executionTarget || {kind:'local'};
  const active = () => BeastEditorCortex?.getActive?.() || { path:'', text:'', language:'plaintext' };
  const uriFor = path => {
    const target=executionTarget();
    const base=target.kind==='ssh' ? (target.remoteRoot||target.path||'~') : target.kind==='container' ? (target.workspaceFolder||'/workspace') : root();
    return `file://${String(base||root()).replace(/\\/g,'/').replace(/\/$/,'')}/${String(path || '').split('/').map(encodeURIComponent).join('/')}`;
  };
  const position = value => ({ line:Math.max(0,Number(value?.lineNumber || 1)-1), character:Math.max(0,Number(value?.column || 1)-1) });
  const monacoRange = range => range ? new monacoApi.Range(Number(range.start?.line || 0)+1,Number(range.start?.character || 0)+1,Number(range.end?.line || 0)+1,Number(range.end?.character || 0)+1) : undefined;
  const semanticLegend={tokenTypes:['namespace','type','class','enum','interface','struct','typeParameter','parameter','variable','property','enumMember','event','function','method','macro','keyword','modifier','comment','string','number','regexp','operator','decorator'],tokenModifiers:['declaration','definition','readonly','static','deprecated','abstract','async','modification','documentation','defaultLibrary']};

  async function refresh() {
    if (!desktop()?.ideCompatibility) {
      BeastStore.patch('compatibility',{loading:false,error:'Desktop compatibility IPC is unavailable.',updatedAt:Date.now()});
      return BeastStore.get().compatibility;
    }
    BeastStore.patch('compatibility',{loading:true,error:''});
    try {
      const result = await desktop().ideCompatibility(root());
      BeastStore.patch('compatibility',{...result,loading:false,error:'',updatedAt:Date.now()});
      return result;
    } catch (error) {
      BeastStore.patch('compatibility',{loading:false,error:String(error.message || error),updatedAt:Date.now()});
      throw error;
    }
  }

  async function installCapability(kind,id) {
    if(!desktop()?.installIdeCapability)throw new Error('Capability installation is unavailable outside the BEAST desktop shell.');
    const key=`${kind}:${id}`;
    BeastStore.patch('compatibility',{installingCapability:key,installReceipt:null,error:''});
    try{
      const result=await desktop().installIdeCapability({kind,id});
      if(result.requiresManual){BeastStore.patch('compatibility',{installingCapability:'',installReceipt:result,error:result.detail||'Manual installation is required.'});return result;}
      if(!result.ok)throw new Error(result.detail||result.stderr||`Could not install ${id}.`);
      await refresh();
      BeastStore.patch('compatibility',{installingCapability:'',installReceipt:result,error:''});
      BeastStore.addLedger(`IDE capability installed and verified: ${result.label||id} · ${result.resolved||result.authority}`);
      return result;
    }catch(error){BeastStore.patch('compatibility',{installingCapability:'',error:String(error.message||error)});throw error;}
  }

  function entryFor(language) {
    const rows = BeastStore.get().compatibility.languages || [];
    return rows.find(row => row.available && row.languages?.includes(language));
  }

  function waitUntilReady(sessionId) {
    if (sessions.get(sessionId)?.ready) return Promise.resolve(sessionId);
    return new Promise((resolve,reject) => {
      const timer=setTimeout(()=>{readyWaiters.delete(sessionId);reject(new Error('Language server initialization timed out.'));},13000);
      readyWaiters.set(sessionId,{resolve:()=>{clearTimeout(timer);resolve(sessionId);},reject,error:null});
    });
  }

  async function ensureLanguage(language) {
    const target=executionTarget();
    const existing = [...sessions.values()].find(item => item.language === language && item.status === 'running' && JSON.stringify(item.target||{kind:'local'})===JSON.stringify(target));
    if (existing) { if (!existing.ready) await waitUntilReady(existing.id); return existing; }
    let entry = entryFor(language);
    if (!entry) { await refresh(); entry=entryFor(language); }
    if (!entry) return null;
    const roots=(BeastStore.get().workspace.roots||[]).map(item=>item.path).filter(Boolean);const summary=await desktop().startIdeProtocol({kind:'lsp',adapter:entry.id,language,root:root(),roots,target});
    const session={...summary,language,ready:false};
    sessions.set(summary.id,session);
    BeastStore.patch('compatibility',{sessions:[...sessions.values()],activeLanguage:language});
    await waitUntilReady(summary.id);
    return sessions.get(summary.id);
  }

  async function notify(session, method, params) {
    return desktop().notifyIdeProtocol({sessionId:session.id,method,params});
  }

  async function request(session, method, params, timeoutMs=8000) {
    return desktop().requestIdeProtocol({sessionId:session.id,method,params,timeoutMs});
  }

  async function syncDocument(session, model) {
    const file = active();
    if (!file.path || !model) return null;
    const uri=uriFor(file.path);
    const key=`${session.id}:${uri}`;
    const version=(opened.get(key)?.version || 0)+1;
    if (!opened.has(key)) {
      await notify(session,'textDocument/didOpen',{textDocument:{uri,languageId:model.getLanguageId(),version,text:model.getValue()}});
    } else {
      await notify(session,'textDocument/didChange',{textDocument:{uri,version},contentChanges:[{text:model.getValue()}]});
    }
    opened.set(key,{version});
    return {uri,version};
  }

  function completionItems(result, model, at) {
    const items=Array.isArray(result) ? result : result?.items || [];
    const word=model.getWordUntilPosition(at);
    const fallbackRange=new monacoApi.Range(at.lineNumber,word.startColumn,at.lineNumber,word.endColumn);
    return items.slice(0,250).map(item => ({
      label:typeof item.label==='string' ? item.label : item.label?.label || 'completion',
      detail:item.detail || '',
      documentation:typeof item.documentation==='string' ? item.documentation : item.documentation?.value || '',
      insertText:typeof item.textEdit?.newText==='string' ? item.textEdit.newText : item.insertText || (typeof item.label==='string' ? item.label : item.label?.label || ''),
      range:monacoRange(item.textEdit?.range || item.textEdit?.replace) || fallbackRange,
      kind:Math.max(0,Math.min(24,Number(item.kind || 1)-1)),
      sortText:item.sortText,
      filterText:item.filterText,
    }));
  }

  function hoverContents(result) {
    if (!result?.contents) return [];
    const values=Array.isArray(result.contents) ? result.contents : [result.contents];
    return values.map(item => ({value:typeof item==='string' ? item : item.value || `\`\`\`${item.language || ''}\n${item.value || ''}\n\`\`\``}));
  }

  function locationResult(result) {
    const rows=Array.isArray(result)?result:result?[result]:[];
    return rows.map(row=>({uri:monacoApi.Uri.parse(row.uri || row.targetUri),range:monacoRange(row.range || row.targetSelectionRange)}));
  }

  function workspaceEdit(edit={}) {
    const edits=[];
    Object.entries(edit.changes || {}).forEach(([uri,rows])=>(rows || []).forEach(row=>edits.push({resource:monacoApi.Uri.parse(uri),textEdit:{range:monacoRange(row.range),text:row.newText || ''}})));
    (edit.documentChanges || []).forEach(change=>{if(change.textDocument?.uri)(change.edits || []).forEach(row=>edits.push({resource:monacoApi.Uri.parse(change.textDocument.uri),textEdit:{range:monacoRange(row.range),text:row.newText || ''}}));});
    return {edits};
  }

  function symbolResult(rows=[]) {
    return (rows || []).map(item=>({name:item.name || 'symbol',detail:item.detail || '',kind:Number(item.kind || 13),tags:item.tags,range:monacoRange(item.range || item.location?.range),selectionRange:monacoRange(item.selectionRange || item.location?.range || item.range),children:symbolResult(item.children || [])}));
  }

  function bindMonaco(api) {
    monacoApi=api;
    if (providersBound || !api) return;
    providersBound=true;
    const languages=['typescript','javascript','typescriptreact','javascriptreact','python','rust','go','c','cpp','shell','json','html','css','scss','less'];
    for (const language of languages) {
      disposables.push(api.languages.registerCompletionItemProvider(language,{
        triggerCharacters:['.','/','"',"'",':','@','<'],
        async provideCompletionItems(model,at) {
          try { const session=await ensureLanguage(language); if(!session)return {suggestions:[]}; const doc=await syncDocument(session,model); const result=await request(session,'textDocument/completion',{textDocument:{uri:doc.uri},position:position(at),context:{triggerKind:1}}); return {suggestions:completionItems(result,model,at)}; }
          catch(error){BeastStore.patch('compatibility',{error:String(error.message||error)});return {suggestions:[]};}
        }
      }));
      disposables.push(api.languages.registerHoverProvider(language,{
        async provideHover(model,at){try{const session=await ensureLanguage(language);if(!session)return null;const doc=await syncDocument(session,model);const result=await request(session,'textDocument/hover',{textDocument:{uri:doc.uri},position:position(at)});return result?{contents:hoverContents(result),range:monacoRange(result.range)}:null;}catch(_){return null;}}
      }));
      disposables.push(api.languages.registerDefinitionProvider(language,{
        async provideDefinition(model,at){try{const session=await ensureLanguage(language);if(!session)return null;const doc=await syncDocument(session,model);const result=await request(session,'textDocument/definition',{textDocument:{uri:doc.uri},position:position(at)});return locationResult(result);}catch(_){return null;}}
      }));
      disposables.push(api.languages.registerReferenceProvider(language,{
        async provideReferences(model,at,context){try{const session=await ensureLanguage(language);if(!session)return [];const doc=await syncDocument(session,model);return locationResult(await request(session,'textDocument/references',{textDocument:{uri:doc.uri},position:position(at),context:{includeDeclaration:Boolean(context?.includeDeclaration)}}));}catch(_){return [];}}
      }));
      disposables.push(api.languages.registerRenameProvider(language,{
        async provideRenameEdits(model,at,newName){try{const session=await ensureLanguage(language);if(!session)return null;const doc=await syncDocument(session,model);return workspaceEdit(await request(session,'textDocument/rename',{textDocument:{uri:doc.uri},position:position(at),newName:String(newName || '')}));}catch(error){return {rejectReason:String(error.message || error),edits:[]};}},
        async resolveRenameLocation(model,at){try{const session=await ensureLanguage(language);if(!session)return null;const doc=await syncDocument(session,model);const result=await request(session,'textDocument/prepareRename',{textDocument:{uri:doc.uri},position:position(at)});const range=result?.range || result;return range?{range:monacoRange(range),text:result?.placeholder || model.getValueInRange(monacoRange(range))}:null;}catch(_){return null;}}
      }));
      disposables.push(api.languages.registerCodeActionProvider(language,{
        async provideCodeActions(model,range,context){try{const session=await ensureLanguage(language);if(!session)return {actions:[],dispose(){}};const doc=await syncDocument(session,model);const result=await request(session,'textDocument/codeAction',{textDocument:{uri:doc.uri},range:{start:{line:range.startLineNumber-1,character:range.startColumn-1},end:{line:range.endLineNumber-1,character:range.endColumn-1}},context:{diagnostics:(context.markers || []).map(marker=>({range:{start:{line:marker.startLineNumber-1,character:marker.startColumn-1},end:{line:marker.endLineNumber-1,character:marker.endColumn-1}},message:marker.message,severity:marker.severity})),only:context.only?.value?[context.only.value]:undefined}});const rows=Array.isArray(result)?result:[];return {actions:rows.filter(item=>item.edit).map(item=>({title:item.title || 'Language action',kind:item.kind,diagnostics:context.markers,edit:workspaceEdit(item.edit),isPreferred:Boolean(item.isPreferred)})),dispose(){}};}catch(_){return {actions:[],dispose(){}};}}
      }));
      disposables.push(api.languages.registerDocumentFormattingEditProvider(language,{
        async provideDocumentFormattingEdits(model,options){try{const session=await ensureLanguage(language);if(!session)return [];const doc=await syncDocument(session,model);const result=await request(session,'textDocument/formatting',{textDocument:{uri:doc.uri},options:{tabSize:options.tabSize,insertSpaces:options.insertSpaces}});return (result || []).map(item=>({range:monacoRange(item.range),text:item.newText || ''}));}catch(_){return [];}}
      }));
      disposables.push(api.languages.registerDocumentSymbolProvider(language,{
        async provideDocumentSymbols(model){try{const session=await ensureLanguage(language);if(!session)return [];const doc=await syncDocument(session,model);return symbolResult(await request(session,'textDocument/documentSymbol',{textDocument:{uri:doc.uri}}));}catch(_){return [];}}
      }));
      disposables.push(api.languages.registerDocumentSemanticTokensProvider(language,{
        getLegend(){return semanticLegend;},
        async provideDocumentSemanticTokens(model){try{const session=await ensureLanguage(language);if(!session||!session.capabilities?.semanticTokensProvider)return null;const doc=await syncDocument(session,model);const result=await request(session,'textDocument/semanticTokens/full',{textDocument:{uri:doc.uri}},12000);return result?.data?{data:new Uint32Array(result.data)}:null;}catch(_){return null;}},
        releaseDocumentSemanticTokens(){}
      }));
    }
  }

  async function workspaceSymbols(query='') {
    const file=active();const language=file.language||'plaintext';const session=await ensureLanguage(language);if(!session)return [];const rows=await request(session,'workspace/symbol',{query:String(query||'').slice(0,240)},12000);return (rows||[]).slice(0,300).map(item=>({name:item.name||'symbol',containerName:item.containerName||'',kind:Number(item.kind||13),uri:item.location?.uri||item.uri||'',range:item.location?.range||item.range||null}));
  }

  function handleMessage(event={}) {
    const session=sessions.get(event.sessionId);
    if (event.type==='exit') {
      if (session) { sessions.delete(event.sessionId); BeastStore.patch('compatibility',{sessions:[...sessions.values()],error:`${session.adapter || 'Language server'} disconnected; retrying on next request.`}); BeastStore.addLedger(`Language protocol disconnected: ${session.adapter || event.sessionId}`); }
      readyWaiters.get(event.sessionId)?.reject(new Error('Language server disconnected.')); readyWaiters.delete(event.sessionId); return;
    }
    if (event.type==='ready') {
      if (session) { session.ready=true; session.capabilities=event.capabilities || {}; sessions.set(event.sessionId,session); }
      readyWaiters.get(event.sessionId)?.resolve(); readyWaiters.delete(event.sessionId);
      BeastStore.patch('compatibility',{sessions:[...sessions.values()],error:''});
      BeastStore.addLedger(`Language protocol ready: ${session?.adapter || event.sessionId}`);
      return;
    }
    if (event.type==='error') {
      const waiter=readyWaiters.get(event.sessionId);
      if(waiter){waiter.reject(new Error(event.error || 'Protocol initialization failed'));readyWaiters.delete(event.sessionId);}
      BeastStore.patch('compatibility',{error:event.error || 'Protocol error'});
    }
    const message=event.message;
    if (message?.method==='textDocument/publishDiagnostics' && monacoApi) {
      const model=monacoApi.editor.getModels().find(item=>item.uri.toString()===message.params?.uri || uriFor(BeastStore.get().editor.activePath)===message.params?.uri);
      if (!model) return;
      const markers=(message.params.diagnostics || []).map(item=>({
        severity:[0,monacoApi.MarkerSeverity.Error,monacoApi.MarkerSeverity.Warning,monacoApi.MarkerSeverity.Info,monacoApi.MarkerSeverity.Hint][Number(item.severity || 1)] || monacoApi.MarkerSeverity.Info,
        message:item.message || 'Language server diagnostic',source:item.source || 'LSP',code:String(item.code || ''),
        startLineNumber:Number(item.range?.start?.line || 0)+1,startColumn:Number(item.range?.start?.character || 0)+1,
        endLineNumber:Number(item.range?.end?.line || 0)+1,endColumn:Number(item.range?.end?.character || 0)+1,
      }));
      monacoApi.editor.setModelMarkers(model,`beast-lsp-${session?.adapter || 'server'}`,markers);
      const diagnostics={...BeastStore.get().compatibility.diagnostics,[model.uri.toString()]:markers.length};
      BeastStore.patch('compatibility',{diagnostics});
    }
  }

  async function stop(sessionId) {
    await desktop()?.stopIdeProtocol?.(sessionId);
    sessions.delete(sessionId);
    BeastStore.patch('compatibility',{sessions:[...sessions.values()]});
  }

  desktop()?.onIdeProtocolMessage?.(handleMessage);
  window.BeastIDECompatibility={refresh,installCapability,bindMonaco,ensureLanguage,workspaceSymbols,stop,get sessions(){return [...sessions.values()];}};
})();
