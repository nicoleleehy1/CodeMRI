import { DesignDraft, parseDesign, checkDesign, designKey, designPrompt } from './create-model';
import { prepareProposal, collectProposal, persistProposal, verifyProposal, applyFile, Proposal } from './proposals';
import { readFile, rm } from 'node:fs/promises';
import { runAgent } from './agent';
import * as vscode from 'vscode';
import * as path from 'node:path';
import { randomBytes } from 'node:crypto';
interface SymbolNode { details?: Record<string, string[]>; id: string; name: string; kind: string; path: string; start_line: number; end_line: number; start_column: number; end_column: number }
interface Graph { layers?: Record<string, unknown>; inventory?: Record<string, unknown>; root: string; revision: string; nodes: SymbolNode[]; edges: {source:string;target:string;kind:string}[]; warnings: string[] }
export function activate(context: vscode.ExtensionContext) {
  let panel: vscode.WebviewPanel | undefined;
  let graph: Graph | undefined;
  let repoId = '';
  let busy = false;
  let review: any = {};
  let agent: ReturnType<typeof runAgent> | undefined;
  let agentRunning = false;
  let stopRequested = false;
  let pending: Proposal | undefined;
  let proposalView: any;
  let deciding = false;
  let designRunning = false;
  let designPlan: {key:string;text:string} | undefined;
  let implementingDesign:DesignDraft|undefined;
  const designStorage = (root:string) => 'architectureDraft:'+root;
  const planStorage = (root:string) => 'architecturePlan:'+root;
  async function saveDesign(value:unknown) {
    const draft=parseDesign(value);
    if(!graph || draft.root!==graph.root)throw new Error('Analyze the matching repository before saving this draft.');
    await context.workspaceState?.update(designStorage(draft.root),draft);
    return draft;
  }
  async function runDesign(message:any) {
    if(!['assess','implement'].includes(message.action))throw new Error('Unknown architecture action.');
    if(!graph||pending||agentRunning||busy||deciding)throw new Error('Finish the current operation and file review first.');
    if(!vscode.workspace.isTrusted)throw new Error('Trust the workspace before running Codex.');
    if(vscode.workspace.textDocuments.some(d=>d.isDirty))throw new Error('Save your open files before assessing this proposal.');
    busy=true;
    let draft:DesignDraft;
    try {draft=await saveDesign(message.draft);}finally{busy=false;}
    const checked=checkDesign(draft,graph,stale);
    if(checked.errors.length)throw new Error(checked.errors.join('\n'));
    // Check source without replacing an AI architecture with a static reanalysis.
    busy=true;
    try {
      const fresh=await api(`/graphs/${repoId}/freshness`);
      if(fresh.revision!==draft.revision){stale=true;void send({type:'sourceStale'});throw new Error('Source changed since this draft. Reanalyze and reconcile it before running Codex.');}
    }finally{busy=false;}
    if(stopRequested)throw new Error('Architecture operation stopped.');
    if(message.action==='implement') {
      const plan=[designPlan,context.workspaceState?.get<{key:string;text:string}>(planStorage(draft.root))].find(p=>p?.key===designKey(draft));
      if(!plan || plan.key!==designKey(draft))throw new Error('Assess this exact proposal and review its plan before implementing.');
      const prompt=designPrompt(draft,'implement',plan.text);
      if(prompt.length>30000)throw new Error('This proposal is too large for one coding task. Split it into smaller drafts.');
      implementingDesign=draft;
      try {await chatRun(prompt);}finally{implementingDesign=undefined;}
      return;
    }
    if(designPrompt(draft,'assess').length>30000)throw new Error('This proposal is too large for one assessment. Split it into smaller drafts.');
    stopRequested=false;agentRunning=true;void send({type:'chatState',running:true});
    let stage:Awaited<ReturnType<typeof prepareProposal>>|undefined;
    let assessment='';
    designPlan=undefined;
    try {
      await context.workspaceState?.update(planStorage(draft.root),undefined);
      void send({type:'designPlanCleared'});
      void send({type:'chatProgress',text:'Assessing architecture against relevant source; no code edits…'});
      stage=await prepareProposal(graph.root);
      if(stopRequested)throw new Error('Assessment stopped before starting.');
      const executable=vscode.workspace.getConfiguration('codemri').get<string>('codexPath')||'codex';
      agent=runAgent(executable,stage.work,designPrompt(draft,'assess'),undefined,event=>{
        if(event.type==='item.completed'&&event.item?.type==='agent_message')assessment+=(assessment?'\n\n':'')+event.item.text;
        if(event.type==='item.started'&&event.item?.type==='command_execution')void send({type:'chatProgress',text:'Reading source: '+event.item.command});
      },true);
      await agent.done;
      if(stopRequested)throw new Error('Assessment stopped. Run it again before implementing.');
      if(!assessment.trim())throw new Error('Codex returned no assessment. Try again.');
      designPlan={key:designKey(draft),text:assessment.slice(0,60000)};
      await context.workspaceState?.update(planStorage(draft.root),designPlan);
      void send({type:'designPlan',plan:designPlan});
      chatMessage('assistant','Architecture assessment completed. Review it in Create mode before implementing.');
    }finally{
      agent=undefined;agentRunning=false;void send({type:'chatState',running:false});
      if(stage)await rm(stage.directory,{recursive:true,force:true});
    }
  }
  const restore = (async()=>{
    const manifest=context.workspaceState?.get<string>('proposalManifest');
    if(manifest) { try {pending=JSON.parse(await readFile(manifest,'utf8'));} catch { /* Missing temporary storage: originals remain unchanged. */ } }
  })();
  async function savePending() {
    if(pending)await context.workspaceState?.update('proposalManifest',await persistProposal(pending));
    else await context.workspaceState?.update('proposalManifest',undefined);
  }
  async function showPending() {
    if(!pending?.files.length)return;
    proposalView=await api('/preview',{root:pending.root,files:pending.files});
    void send({type:'graph',...proposalView,proposalId:pending.id,stale:false,designComparison:Boolean((pending as Proposal & {design?:DesignDraft}).design)});
  }
  async function decideProposal(message:any) {
    if(agentRunning||busy||deciding)throw new Error('Wait for the current operation to finish.');
    if(!pending || message.proposalId!==pending.id)throw new Error('This proposal is no longer available.');
    if(!['approve','discard'].includes(message.action)||!Array.isArray(message.paths)||!message.paths.length)throw new Error('Select a file change first.');
    const selected=pending.files.filter(file=>message.paths.includes(file.path));
    if(selected.length!==new Set(message.paths).size)throw new Error('Invalid file selection.');
    deciding=true;
    try {
      if(message.action==='approve') {
      if(!vscode.workspace.isTrusted)throw new Error('Trust the workspace before approving changes.');
      for(const file of selected) {
        if(vscode.workspace.textDocuments.some(d=>d.isDirty && d.uri.fsPath===path.join(pending!.root,file.path)))throw new Error(`Save or discard your editor changes to ${file.path} before approving.`);
        await verifyProposal(pending.root,file);
      }
    }
      for(const file of selected) {
        if(message.action==='approve')await applyFile(pending.root,file);
        pending.files=pending.files.filter(item=>item!==file);
        await savePending();
      }
      chatMessage('assistant',`${message.action==='approve'?'Approved and applied':'Discarded'} ${selected.length} file change(s).`);
    } finally {
      const root=pending.root;
      if(!pending.files.length){pending=undefined;proposalView=undefined;}
      try { await savePending(); if(pending)await showPending();else await scanRoot(root); }
      finally {deciding=false;void send({type:'proposalState',busy:false});}
    }
  }
  const chat: {role:string;text:string}[] = [];
  function chatMessage(role:string,text:string) { chat.push({role,text}); if(chat.length>200)chat.shift(); void send({type:'chat',role,text}); }
  context.subscriptions.push({dispose:()=>agent?.child.kill()});
  let stale = false;
  let lastSelection: string | undefined;
  const send = (message: any) => panel?.webview.postMessage(message.type==='graph' ? {
    ...message,design:message.designComparison?(pending as Proposal & {design?:DesignDraft})?.design:context.workspaceState?.get(designStorage(message.graph.root)),
    designPlan:context.workspaceState?.get(planStorage(message.graph.root))
  } : message);
  const report = (error: unknown) => { const message = error instanceof Error ? error.message : String(error); void send({type:'error',message}); void vscode.window.showErrorMessage(`CodeMRI: ${message}`); };
  async function api(route: string, body?: object) {
    const base = vscode.workspace.getConfiguration('codemri').get<string>('apiUrl')!;
    const url = new URL(base);
    if (!['localhost','127.0.0.1','[::1]'].includes(url.hostname)) throw new Error('Use a local CodeMRI API address.');
    const response = await fetch(base.replace(/\/$/,'')+route, {method:body?'POST':'GET',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(240000)});
    if (!response.ok) throw new Error(`API ${response.status}: ${await response.text()}`);
    return response.json() as Promise<any>;
  }
  function sync(editor?: vscode.TextEditor) {
    if (!graph || !editor) return;
    const relative = path.relative(graph.root,editor.document.uri.fsPath).split(path.sep).join('/');
    const cursor = editor.selection.active;
    const matches = graph.nodes.filter(n=>n.path===relative && (cursor.line+1>n.start_line || cursor.line+1===n.start_line && cursor.character>=n.start_column) && (cursor.line+1<n.end_line || cursor.line+1===n.end_line && cursor.character<=n.end_column));
    matches.sort((a,b)=>(a.kind==='module'?1:0)-(b.kind==='module'?1:0) || (a.end_line-a.start_line)-(b.end_line-b.start_line));
    lastSelection = matches[0]?.id;
    void send({type:'select',id:lastSelection});
  }
  async function jump(id: string) {
    if (!graph || stale) { if(stale) throw new Error('Source changed. Reanalyze before jumping.'); return; }
    const n = graph.nodes.find(n=>n.id===id);
    if (!n) return;
    const target = path.resolve(graph.root,n.path);
    const relative = path.relative(graph.root,target);
    if (relative.startsWith('..') || path.isAbsolute(relative)) throw new Error('Source is outside analyzed repository');
    const doc = await vscode.workspace.openTextDocument(vscode.Uri.file(target));
    const editor = await vscode.window.showTextDocument(doc,{viewColumn:vscode.ViewColumn.One,preserveFocus:true});
    const range = new vscode.Range(n.start_line-1,n.start_column,n.end_line-1,n.end_column);
    editor.selection = new vscode.Selection(range.start,range.start);
    editor.revealRange(range,vscode.TextEditorRevealType.InCenter);
    lastSelection = n.id;
    void send({type:'select',id:n.id});
  }
  function open() {
    if (panel) { panel.reveal(vscode.ViewColumn.Beside); return; }
    panel = vscode.window.createWebviewPanel('codemri','CodeMRI',vscode.ViewColumn.Beside,{enableScripts:true,retainContextWhenHidden:true,localResourceRoots:[vscode.Uri.joinPath(context.extensionUri,'media')]});
    const nonce = randomBytes(16).toString('hex');
    const script = panel.webview.asWebviewUri(vscode.Uri.joinPath(context.extensionUri,'media','graph.bundle.js'));
    const sortIcon = panel.webview.asWebviewUri(vscode.Uri.joinPath(context.extensionUri,'media','icons','sort-order.png'));
    const css = panel.webview.asWebviewUri(vscode.Uri.joinPath(context.extensionUri,'media','graph.css'));
    panel.webview.html = `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src ${panel.webview.cspSource}; style-src ${panel.webview.cspSource}; script-src 'nonce-${nonce}';"><link rel="stylesheet" href="${css}"></head><body><header><small>CODEMRI / LOCAL WORLD MODEL</small><h1>See the system.<br>Compile the context.</h1><p id="status">Analyze a workspace to begin.</p><button id="analyze">Analyze hierarchy</button><button id="generateAI">Analyze calls</button><p class="hint">Analyze hierarchy uses AI and sends sampled source to OpenAI using your backend API key. Analyze calls runs locally.</p></header><section class="toolbar"><div class="symbol-search"><label>Find a symbol<input id="search" placeholder="Search names, calls, or paths…" aria-controls="searchResults" autocomplete="off"></label><div id="searchResults" aria-label="Symbol search results" hidden></div></div><label>Semantic layer<select id="layer"><option value="repository">1 · Repository</option><option value="architecture">2 · Architecture</option><option value="modules">3 · Modules / packages</option><option value="files">4 · Files</option><option value="symbols">5 · Classes / functions / interfaces</option><option value="trace">6 · Function calls</option></select></label><div class="graph-navigation"><button id="traceBack">Back</button><div><button id="back">Full Repository</button><button id="reset">Fit Graph</button></div></div></section><main><p id="breadcrumb">System architecture</p><p id="layerNote">Static relationships backed by source evidence</p><section id="changeReview" hidden aria-label="Graph change review"><div class="review-heading"><h2>Changes have been made!</h2><button id="reviewAccept">Mark reviewed</button></div><p id="changeSummary" aria-live="polite"></p><p id="reviewLocation"></p><div class="review-navigation"><button id="changePrev" aria-label="Previous change">← Previous</button><button id="changeNext" aria-label="Next change">Next →</button></div><div id="proposalActions" hidden><span id="selectionCount" aria-live="polite">0 files selected</span><button id="approveSelected" disabled>Approve selected</button><button id="discardSelected" disabled>Delete selected</button><p>Approval applies the entire selected file. Delete discards its proposal.</p><p id="proposalError" role="alert"></p></div><ol id="changeList"></ol><section id="proposalDiff" hidden aria-label="Proposed code diff"><h3 id="diffHeading"></h3><div id="diffLines"></div></section></section><div id="graphCanvas" data-main-node="closed"><div id="graphWorkspace"><aside id="mainNodePanel" aria-labelledby="mainNodeHeading" hidden><div class="main-node-heading"><h2 id="mainNodeHeading">Main node</h2><button id="closeMainNode" aria-label="Close main node panel">×</button></div><h3 id="mainNodeName"></h3><svg id="mainNodeGraph" role="img" aria-label="Main node"></svg><p id="mainNodeSummary"></p></aside><div id="graphViewport"><svg id="graph" data-sort-icon="${sortIcon}" viewBox="0 0 1100 600" role="img" aria-label="Interactive code graph"></svg></div><aside id="callPopup" class="graph-popup" role="dialog" aria-labelledby="callPopupTitle" hidden><div class="popup-heading"><h2 id="callPopupTitle"></h2><button id="closeCallPopup" aria-label="Close label details">×</button></div><div id="callMetrics"><p>Scope: <strong id="callScopeName"></strong></p><dl><div><dt>Main function only</dt><dd id="callDirectCount"></dd></div><div><dt>Including reachable subgraphs</dt><dd id="callTotalCount"></dd></div></dl></div><p id="callPopupSummary"></p><ul id="callPopupSites"></ul></aside><div id="sortMenu" class="graph-popup" role="menu" aria-labelledby="sortMenuHeading" hidden><div class="popup-heading"><h2 id="sortMenuHeading">Sort labels</h2><button id="closeSortMenu" aria-label="Close sort menu">×</button></div><button id="sortAlpha" role="menuitemradio" aria-checked="false">Alphabetical · A → Z</button><button id="sortSource" role="menuitemradio" aria-checked="true">Source / call order</button><p>Calls follow their source order, not runtime execution order.</p></div></div><section id="nodeTypeBox" aria-labelledby="nodeTypeHeading"><h2 id="nodeTypeHeading">Node classification</h2><div id="nodeClassification">Select a node to see its type and place in the hierarchy.</div></section><div id="graphFooter"><section class="graph-info" aria-labelledby="functionPathHeading"><h2 id="functionPathHeading">Function path</h2><ol id="functionPath" aria-label="Navigation path to main node"></ol><p id="functionLocation"></p></section><section class="graph-info" aria-labelledby="functionCallersHeading"><div class="caller-heading"><h2 id="functionCallersHeading">Called from</h2><span id="functionCallCount" aria-live="polite">No node selected</span></div><ul id="functionCallers"></ul><p class="call-note">Source call sites or incoming architecture relationships; not runtime executions. Dynamic and unresolved calls are not counted.</p></section></div></div><p class="hint">Click to select · Double-click or Enter to drill down · Space to select · Click an edge for evidence · Scroll to zoom · Drag to pan</p></main><section id="inspector"><h2>System evidence</h2><p id="nodeSummary">Analyze a repository to discover its system design.</p><div id="evidence"></div></section><section><h2>Change laboratory <small>STATIC PROTOTYPE</small></h2><label>Change intent<input id="query" value="Change applyCoupon to support stacked coupons"></label><label>Context budget <output id="budgetLabel">4,000 tokens</output><input id="budget" type="range" min="256" max="16000" step="256" value="4096"></label><button id="impact">Show blast radius</button><button id="compile">Compile context</button><button id="copy">Copy context</button><p id="details">Select a symbol or describe a change.</p><pre id="context"></pre><details><summary>Analysis diagnostics</summary><pre id="warnings"></pre></details></section><section id="codingChat" aria-labelledby="chatHeading"><h2 id="chatHeading">Build with CodeMRI</h2><p class="hint">Describe a change. Codex prepares edits in a separate copy using your local Codex login. Review the red/green diff and approve selected files to apply them.</p><div id="chatMessages" role="log" aria-live="polite"></div><p id="chatProgress" role="status">Ready when you are.</p><form id="chatForm"><label for="chatPrompt">What would you like to change?</label><textarea id="chatPrompt" rows="4" maxlength="30000" placeholder="Add coupon stacking and update the tests…" required></textarea><div class="chat-actions"><button id="chatSend" type="submit">Send to Codex</button><button id="chatStop" type="button" disabled>Stop</button></div></form></section><script nonce="${nonce}" src="${script}"></script></body></html>`;
    panel.onDidDispose(()=>{panel=undefined;},null,context.subscriptions);
    panel.webview.onDidReceiveMessage(async message=>{
      try {
        if (!message || typeof message.type !== 'string') return;
        if (message.type==='ready') {
          await restore;
          // Opening the panel starts with an empty canvas; analysis is explicit.
          void send({type:'chatHistory',messages:chat,running:agentRunning});
          if(pending?.files.length)void send({type:'status',message:'Saved changes are awaiting review. Choose Analyze calls to open them.'});
        }
        if (message.type==='designSave') {await saveDesign(message.draft);void send({type:'designSaved'});}
        if (message.type==='designRun') {
          if(designRunning)throw new Error('An architecture operation is already running.');
          designRunning=true;stopRequested=false;void send({type:'designState',running:true});
          try {await runDesign(message);}finally{designRunning=false;void send({type:'designState',running:false});}
        }
        if (message.type==='proposalDecision') await decideProposal(message);
        if (message.type==='chatStop') {stopRequested=true;agent?.child.kill();}
        if (message.type==='chatSend') await chatRun(String(message.prompt??''));
        if (message.type==='reviewAccept') {
          if(pending || busy || agentRunning || stale || !graph) throw new Error('Wait for edits to finish and refresh the graph before marking reviewed.');
          review=await api(`/graphs/${repoId}/review`,{revision:graph.revision});
          void send({type:'graph',graph,stale,...review});
        }
        if (message.type==='analyze' && !agentRunning) await scan();
        if (message.type==='generateAI' && !agentRunning && !pending) {
          if(!repoId || stale) await scan();
          if(!repoId || stale) return;
          if(busy) return;
          busy=true;
          void send({type:'status',message:'Synthesizing system architecture from repository evidence…'});
          try {
            const result=await api(`/graphs/${repoId}/architecture-ai`,{});
            graph=result.graph;
            void send({type:'graph',graph,stale,...review});
          } finally {busy=false;}
        }
        if(pending && ['jump','openEvidence','impact','context'].includes(message.type))throw new Error('Reviewing a proposal. Approve or discard it before navigating live source.');
        if (message.type==='jump' && typeof message.id==='string') await jump(message.id);
        if (message.type==='openEvidence' && graph && typeof message.path==='string') {
          const target=path.resolve(graph.root,message.path);
          const relative=path.relative(graph.root,target);
          if(relative.startsWith('..') || path.isAbsolute(relative)) throw new Error('Evidence is outside repository');
          const doc=await vscode.workspace.openTextDocument(vscode.Uri.file(target));
          const editor=await vscode.window.showTextDocument(doc,{viewColumn:vscode.ViewColumn.One,preserveFocus:true});
          const requestedLine=Number(message.line||1), requestedColumn=Number(message.column||0);
          const line=Math.max(0,Math.min(doc.lineCount-1,Number.isFinite(requestedLine)?Math.floor(requestedLine)-1:0));
          const column=Math.max(0,Math.min(doc.lineAt(line).text.length,Number.isFinite(requestedColumn)?Math.floor(requestedColumn):0));
          const range=new vscode.Range(line,column,line,column);
          editor.selection=new vscode.Selection(range.start,range.start);
          editor.revealRange(range,vscode.TextEditorRevealType.InCenter);
        }
        if (message.type==='copy' && typeof message.text==='string') await vscode.env.clipboard.writeText(message.text);
        if (['impact','context'].includes(message.type)) {
          if(!repoId) throw new Error('Analyze a repository first.');
          if(stale) throw new Error('Source changed. Reanalyze to refresh the model.');
          const result = await api(`/graphs/${repoId}/${message.type}`,{query:String(message.query??''),budget:Number(message.budget??4000)});
          void send({type:message.type,result});
        }
      } catch(error) { if(['designSave','designRun'].includes(message?.type))void send({type:'designError',message:error instanceof Error?error.message:String(error)}); if(message?.type==='proposalDecision')void send({type:'proposalState',busy:false,error:error instanceof Error?error.message:String(error)}); if(message?.type==='chatSend') chatMessage('error',error instanceof Error?error.message:String(error)); report(error); }
    },null,context.subscriptions);
  }
  async function chatRun(prompt:string) {
    await restore;
    if(pending?.files.length)throw new Error('Approve or delete the pending file changes before starting another prompt.');
    if(agentRunning || busy || deciding) throw new Error('An operation is already running.');
    if(!prompt.trim() || prompt.length>30000) throw new Error('Enter a prompt of at most 30,000 characters.');
    if(!vscode.workspace.isTrusted) throw new Error('Trust the workspace before running the coding agent.');
    if(vscode.workspace.textDocuments.some(d=>d.isDirty)) throw new Error('Save your open files before asking the agent to edit.');
    if(!graph) await scan();
    if(!graph) return;
    const root=graph.root;
    stopRequested=false;agentRunning=true;void send({type:'chatState',running:true});chatMessage('user',prompt.trim());
    let stage: Awaited<ReturnType<typeof prepareProposal>> | undefined;
    try {
      stage=await prepareProposal(root);
      if(stopRequested)throw new Error('Agent stopped before starting.');
      const executable=vscode.workspace.getConfiguration('codemri').get<string>('codexPath')||'codex';
      const instructions='Work only in this temporary repository copy. Changes will be proposed for manual approval. Do not edit the original repository or claim changes are applied.\n\nRecent conversation:\n'+chat.slice(-8).map(m=>m.role+': '+m.text).join('\n').slice(-20000)+'\n\nTask:\n'+prompt;
      agent=runAgent(executable,stage.work,instructions,undefined,event=>{
        if(event.type==='item.completed' && event.item?.type==='agent_message') chatMessage('assistant',event.item.text);
        if(event.type==='item.started' && event.item?.type==='command_execution') void send({type:'chatProgress',text:'Running: '+event.item.command});
        if(event.type==='error'||event.type==='turn.failed') chatMessage('error',event.message||event.error?.message||'Agent failed.');
      });
      await agent.done;
    } catch(error) { chatMessage('error',error instanceof Error?error.message:String(error)); }
    finally {
      agent=undefined;
      // Even partial edits from a failed run require explicit approval.
      try {
        if(stage) {
          pending=await collectProposal(stage);
          if(implementingDesign)(pending as Proposal & {design?:DesignDraft}).design=implementingDesign;
          if(pending.files.length) {await savePending();await showPending();chatMessage('assistant',`${pending.files.length} file change(s) ready for review. Your working files have not changed.`);}
          else {pending=undefined;chatMessage('assistant','No file changes proposed.');}
        }
      } catch(error) { chatMessage('error',error instanceof Error?error.message:String(error));report(error); }
      agentRunning=false;void send({type:'chatState',running:false});
    }
  }
  async function scanRoot(root:string) {
    const result=await api('/analyze',{root});
    graph=result.graph;repoId=result.repo_id;review={changes:result.changes,baseline:result.baseline};
    stale=vscode.workspace.textDocuments.some(d=>d.isDirty);
    void send({type:'graph',graph,stale,...review});
  }
  async function scan() {
    await restore;
    if(pending?.files.length){open();await showPending();return;}
    if(busy || agentRunning || deciding) return;
    if(!vscode.workspace.isTrusted) throw new Error('Trust the workspace before analyzing source.');
    const folders = vscode.workspace.workspaceFolders;
    if(!folders?.length) throw new Error('Open a local folder first.');
    const folder = folders.length===1?folders[0]:await vscode.window.showWorkspaceFolderPick();
    if(!folder) return;
    open(); busy=true; void send({type:'status',message:'Scanning syntax trees and resolving relationships…'});
    try {
      const result = await api('/analyze',{root:folder.uri.fsPath});
      if(result.graph?.schema_version !== 2 || !['architecture','modules','repository','packages','files','hierarchy'].every(level=>Array.isArray(result.graph?.layers?.[level]?.nodes))) {
        throw new Error('The backend is running an older CodeMRI analyzer without the repository hierarchy. Stop the backend with Ctrl+C, restart it from this project folder, then click Analyze repository again.');
      }
      review={changes:result.changes,baseline:result.baseline};
      graph=result.graph; repoId=result.repo_id; stale=vscode.workspace.textDocuments.some(d=>d.isDirty && graph!.nodes.some(n=>path.resolve(graph!.root,n.path)===d.uri.fsPath));
      void send({type:'graph',graph,stale,...review}); sync(vscode.window.activeTextEditor);
    } finally {busy=false;}
  }
  const markStale = () => { if(graph && !stale) {stale=true; void send({type:'sourceStale'}); void send({type:'status',message:'Source changed — reanalyze to refresh graph and context.'});} };
  const watcher=vscode.workspace.createFileSystemWatcher('**/*.{ts,tsx,js,jsx,mts,cts,py,go,rs,java,kt,cs,rb,php,vue,svelte,sql,prisma,json,toml,yml,yaml}');
  context.subscriptions.push(watcher,watcher.onDidChange(markStale),watcher.onDidCreate(markStale),watcher.onDidDelete(markStale),
    vscode.commands.registerCommand('codemri.open',open),vscode.commands.registerCommand('codemri.analyze',()=>scan().catch(report)),
    vscode.window.onDidChangeTextEditorSelection(event=>sync(event.textEditor)),vscode.window.onDidChangeActiveTextEditor(sync),
    vscode.workspace.onDidChangeTextDocument(event=>{if(graph && graph.nodes.some(n=>path.resolve(graph!.root,n.path)===event.document.uri.fsPath)) markStale();}));
}
