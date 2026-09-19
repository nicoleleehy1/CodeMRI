const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createRequire } = require('node:module');

test('extension bridges graph clicks and editor selections; blocks stale jumps', async () => {
  const root = path.resolve('examples/shop');
  const symbol = {id:'coupon',name:'applyCoupon',kind:'function_declaration',path:'src/coupons.ts',start_line:1,end_line:3,start_column:0,end_column:1};
  const graph = {schema_version:2,layers:{architecture:{nodes:[],edges:[]},modules:{nodes:[],edges:[]}},root,revision:'demo',nodes:[symbol],edges:[],warnings:[]};
  let responseGraph = graph;
  const commands = new Map(), sent = [], errors = [];
  let receive, select, changed, opened, revealed;
  const disposable = {dispose(){}};
  const uri = file => ({fsPath:file,toString:()=>file});
  class Range { constructor(a,b,c,d){this.start={line:a,character:b};this.end={line:c,character:d};} }
  class Selection {constructor(start,end){this.start=start;this.end=end;this.active=start;}}
  const webview = {asWebviewUri:v=>v,cspSource:'local',postMessage:m=>{sent.push(m);return Promise.resolve(true);},onDidReceiveMessage:fn=>{receive=fn;return disposable;}};
  const vscode = {
    Uri:{file:uri,joinPath:(base,...parts)=>uri(path.join(base.fsPath,...parts))},Range,Selection,
    ViewColumn:{One:1,Beside:2},TextEditorRevealType:{InCenter:1},
    env:{clipboard:{writeText:async()=>{}}},
    commands:{registerCommand:(name,fn)=>{commands.set(name,fn);return disposable;}},
    workspace:{isTrusted:true,textDocuments:[],workspaceFolders:[{uri:uri(root)}],getConfiguration:()=>({get:()=> 'http://127.0.0.1:8000'}),
      openTextDocument:async value=>{opened=value.fsPath;return {uri:value};},
      createFileSystemWatcher:()=>({dispose(){},onDidChange:()=>disposable,onDidCreate:()=>disposable,onDidDelete:()=>disposable}),
      onDidChangeTextDocument:fn=>{changed=fn;return disposable;}},
    window:{showErrorMessage:m=>errors.push(m),createWebviewPanel:()=>({webview,onDidDispose:()=>disposable,reveal(){}}),
      showTextDocument:async doc=>({document:doc,revealRange:range=>revealed=range}),
      onDidChangeTextEditorSelection:fn=>{select=fn;return disposable;},onDidChangeActiveTextEditor:()=>disposable}
  };
  const file=path.resolve('apps/extension/dist/extension.js');
  const nativeRequire=createRequire(file),mod={exports:{}};
  vm.runInNewContext(fs.readFileSync(file,'utf8'),{module:mod,exports:mod.exports,require:id=>id==='vscode'?vscode:nativeRequire(id),URL,AbortSignal,
    fetch:async()=>({ok:true,json:async()=>({repo_id:'demo',graph:responseGraph})})});
  mod.exports.activate({extensionUri:uri(path.resolve('apps/extension')),subscriptions:[]});
  await commands.get('codemri.analyze')();
  assert.ok(sent.some(m=>m.type==='graph'));
  await receive({type:'jump',id:'coupon'});
  assert.equal(opened,path.join(root,'src/coupons.ts'));
  assert.equal(revealed.start.line,0);
  select({textEditor:{document:{uri:uri(opened)},selection:{active:{line:1,character:2}}}});
  assert.equal(sent.at(-1).id,'coupon');
  changed({document:{uri:uri(opened)}});
  await receive({type:'jump',id:'coupon'});
  assert.match(errors.at(-1),/Reanalyze/);
  responseGraph = {root,revision:'old',nodes:[symbol],edges:[],warnings:[]};
  const previousGraphs=sent.filter(m=>m.type==='graph').length;
  await commands.get('codemri.analyze')();
  assert.match(errors.at(-1),/older CodeMRI analyzer/);
  assert.equal(sent.filter(m=>m.type==='graph').length,previousGraphs);
});
