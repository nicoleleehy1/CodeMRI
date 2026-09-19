import * as vscode from 'vscode';
import * as path from 'node:path';
import { randomBytes } from 'node:crypto';
interface SymbolNode { id: string; name: string; kind: string; path: string; start_line: number; end_line: number; start_column: number; end_column: number }
interface Graph { layers?: Record<string, unknown>; inventory?: Record<string, unknown>; root: string; revision: string; nodes: SymbolNode[]; edges: {source:string;target:string;kind:string}[]; warnings: string[] }
export function activate(context: vscode.ExtensionContext) {
  let panel: vscode.WebviewPanel | undefined;
  let graph: Graph | undefined;
  let repoId = '';
  let busy = false;
  let stale = false;
  let lastSelection: string | undefined;
  const send = (message: object) => panel?.webview.postMessage(message);
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
    const css = panel.webview.asWebviewUri(vscode.Uri.joinPath(context.extensionUri,'media','graph.css'));
    panel.webview.html = `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${panel.webview.cspSource}; script-src 'nonce-${nonce}';"><link rel="stylesheet" href="${css}"></head><body><header><small>CODEMRI / LOCAL WORLD MODEL</small><h1>See the system.<br>Compile the context.</h1><p id="status">Analyze a workspace to begin.</p><button id="analyze">Analyze repository</button><button id="generateAI">Generate AI architecture</button><p class="hint">AI generation sends sampled source to OpenAI using your backend API key. Local analysis stays on this machine.</p></header><section class="toolbar"><label>Find a symbol<input id="search" placeholder="checkout, pricing, coupons…"></label><button id="reset">Fit graph</button><label>Semantic layer<select id="layer"><option value="architecture">1 · Architecture</option><option value="modules">2 · Modules</option><option value="symbols">3 · Symbols</option><option value="trace">4 · Function calls</option></select></label><button id="traceBack">Back</button><button id="back">All components</button></section><main><p id="breadcrumb">System architecture</p><p id="layerNote">Static relationships backed by source evidence</p><svg id="graph" viewBox="0 0 1100 600" role="img" aria-label="Interactive code graph"></svg><p class="hint">Click a component to drill down · Click an edge for evidence · Scroll to zoom · Drag to pan</p></main><section id="inspector"><h2>System evidence</h2><p id="nodeSummary">Analyze a repository to discover its system design.</p><div id="evidence"></div></section><section><h2>Change laboratory <small>STATIC PROTOTYPE</small></h2><label>Change intent<input id="query" value="Change applyCoupon to support stacked coupons"></label><label>Context budget <output id="budgetLabel">4,000 tokens</output><input id="budget" type="range" min="256" max="16000" step="256" value="4096"></label><button id="impact">Show blast radius</button><button id="compile">Compile context</button><button id="copy">Copy context</button><p id="details">Select a symbol or describe a change.</p><pre id="context"></pre><details><summary>Analysis diagnostics</summary><pre id="warnings"></pre></details></section><script nonce="${nonce}" src="${script}"></script></body></html>`;
    panel.onDidDispose(()=>{panel=undefined;},null,context.subscriptions);
    panel.webview.onDidReceiveMessage(async message=>{
      try {
        if (!message || typeof message.type !== 'string') return;
        if (message.type==='ready') { if(graph) void send({type:'graph',graph,stale}); sync(vscode.window.activeTextEditor); }
        if (message.type==='analyze') await scan();
        if (message.type==='generateAI') {
          if(!repoId || stale) throw new Error('Analyze the current saved repository before generating AI architecture.');
          if(busy) return;
          busy=true;
          void send({type:'status',message:'Synthesizing system architecture from repository evidence…'});
          try {
            const result=await api(`/graphs/${repoId}/architecture-ai`,{});
            graph=result.graph;
            void send({type:'graph',graph,stale});
          } finally {busy=false;}
        }
        if (message.type==='jump' && typeof message.id==='string') await jump(message.id);
        if (message.type==='openEvidence' && graph && typeof message.path==='string') {
          const target=path.resolve(graph.root,message.path);
          const relative=path.relative(graph.root,target);
          if(relative.startsWith('..') || path.isAbsolute(relative)) throw new Error('Evidence is outside repository');
          const doc=await vscode.workspace.openTextDocument(vscode.Uri.file(target));
          const editor=await vscode.window.showTextDocument(doc,{viewColumn:vscode.ViewColumn.One,preserveFocus:true});
          const line=Math.max(0,Math.min(doc.lineCount-1,Number(message.line||1)-1));
          editor.revealRange(new vscode.Range(line,0,line,0),vscode.TextEditorRevealType.InCenter);
        }
        if (message.type==='copy' && typeof message.text==='string') await vscode.env.clipboard.writeText(message.text);
        if (['impact','context'].includes(message.type)) {
          if(!repoId) throw new Error('Analyze a repository first.');
          if(stale) throw new Error('Source changed. Reanalyze to refresh the model.');
          const result = await api(`/graphs/${repoId}/${message.type}`,{query:String(message.query??''),budget:Number(message.budget??4000)});
          void send({type:message.type,result});
        }
      } catch(error) { report(error); }
    },null,context.subscriptions);
  }
  async function scan() {
    if(busy) return;
    if(!vscode.workspace.isTrusted) throw new Error('Trust the workspace before analyzing source.');
    const folders = vscode.workspace.workspaceFolders;
    if(!folders?.length) throw new Error('Open a local folder first.');
    const folder = folders.length===1?folders[0]:await vscode.window.showWorkspaceFolderPick();
    if(!folder) return;
    open(); busy=true; void send({type:'status',message:'Scanning syntax trees and resolving relationships…'});
    try {
      const result = await api('/analyze',{root:folder.uri.fsPath});
      if(result.graph?.schema_version !== 2 || !Array.isArray(result.graph?.layers?.architecture?.nodes) || !Array.isArray(result.graph?.layers?.modules?.nodes)) {
        throw new Error('The backend is running an older CodeMRI analyzer without architecture layers. Stop the backend with Ctrl+C, restart it from this project folder, then click Analyze repository again.');
      }
      graph=result.graph; repoId=result.repo_id; stale=vscode.workspace.textDocuments.some(d=>d.isDirty && graph!.nodes.some(n=>path.resolve(graph!.root,n.path)===d.uri.fsPath));
      void send({type:'graph',graph,stale}); sync(vscode.window.activeTextEditor);
    } finally {busy=false;}
  }
  const markStale = () => { if(graph && !stale) {stale=true; void send({type:'status',message:'Source changed — reanalyze to refresh graph and context.'});} };
  const watcher=vscode.workspace.createFileSystemWatcher('**/*.{ts,tsx,js,jsx,mts,cts,py,go,rs,java,kt,cs,rb,php,vue,svelte,sql,prisma,json,toml,yml,yaml}');
  context.subscriptions.push(watcher,watcher.onDidChange(markStale),watcher.onDidCreate(markStale),watcher.onDidDelete(markStale),
    vscode.commands.registerCommand('codemri.open',open),vscode.commands.registerCommand('codemri.analyze',()=>scan().catch(report)),
    vscode.window.onDidChangeTextEditorSelection(event=>sync(event.textEditor)),vscode.window.onDidChangeActiveTextEditor(sync),
    vscode.workspace.onDidChangeTextDocument(event=>{if(graph && graph.nodes.some(n=>path.resolve(graph!.root,n.path)===event.document.uri.fsPath)) markStale();}));
}
