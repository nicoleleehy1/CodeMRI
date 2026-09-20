const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createRequire } = require('node:module');

test('extension bridges graph clicks and editor selections; blocks stale jumps', async () => {
  const root = fs.mkdtempSync(path.join(require('node:os').tmpdir(),'codemri-extension-'));
  fs.mkdirSync(path.join(root,'src'));
  fs.writeFileSync(path.join(root,'src/coupons.ts'),'original working file');
  const symbol = {id:'coupon',name:'applyCoupon',kind:'function_declaration',path:'src/coupons.ts',start_line:1,end_line:3,start_column:0,end_column:1};
  const graph = {schema_version:2,layers:Object.fromEntries(['architecture','modules','repository','packages','files','hierarchy'].map(level=>[level,{nodes:[],edges:[]}])),root,revision:'demo',nodes:[symbol],edges:[],warnings:[]};
  let responseGraph = graph;
  const commands = new Map(), sent = [], errors = [], invocations=[];
  const state=new Map();
  let freshness='demo', failAssessment=false;
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
      openTextDocument:async value=>{opened=value.fsPath;return {uri:value,lineCount:20,lineAt:()=>({text:" ".repeat(100)})};},
      createFileSystemWatcher:()=>({dispose(){},onDidChange:()=>disposable,onDidCreate:()=>disposable,onDidDelete:()=>disposable}),
      onDidChangeTextDocument:fn=>{changed=fn;return disposable;}},
    window:{showErrorMessage:m=>errors.push(m),createWebviewPanel:()=>({webview,onDidDispose:()=>disposable,reveal(){}}),
      showTextDocument:async doc=>({document:doc,revealRange:range=>revealed=range}),
      onDidChangeTextEditorSelection:fn=>{select=fn;return disposable;},onDidChangeActiveTextEditor:()=>disposable}
  };
  const file=path.resolve('apps/extension/dist/extension.js');
  const nativeRequire=createRequire(file),mod={exports:{}};
  vm.runInNewContext(fs.readFileSync(file,'utf8'),{module:mod,exports:mod.exports,require:id=>id==='vscode'?vscode:id==='node:child_process'?{spawn(executable,args,options){
      const child=new (require('node:events').EventEmitter)(),{PassThrough}=require('node:stream');
      child.stdin=new PassThrough();child.stdout=new PassThrough();child.stderr=new PassThrough();
      invocations.push({args,options,child});
      setImmediate(()=>{
        assert.notEqual(options.cwd,root,'Agent must run in an isolated copy');
        if(args.includes('read-only')) {
          if(failAssessment){child.stderr.write('Assessment failed');child.emit('close',1,null);return;}
          child.stdout.write('{"type":"item.completed","item":{"type":"agent_message","text":"Plausible. Plan: add cache and test expiry."}}\n');
          child.emit('close',0,null);return;
        }
        fs.writeFileSync(path.join(options.cwd,'src/coupons.ts'),'proposed code');
        fs.writeFileSync(path.join(options.cwd,'new.ts'),'proposed addition');
        child.stdout.write('{"type":"item.completed","item":{"type":"agent_message","text":"Proposed changes"}}\n');
        child.emit('close',0,null);
      });return child;
    }}:nativeRequire(id),URL,AbortSignal,
    fetch:async(url,options)=>({ok:true,json:async()=>url.endsWith('/freshness')?{revision:freshness}:url.endsWith('/preview')?{graph:responseGraph,baseline:responseGraph,changes:{nodes:[],edges:[]},files:JSON.parse(options.body).files.map(file=>({path:file.path,status:'modified',lines:[]}))}:{repo_id:'demo',graph:responseGraph}})});
  mod.exports.activate({extensionUri:uri(path.resolve('apps/extension')),subscriptions:[],workspaceState:{get:key=>state.get(key),update:async(key,value)=>{state.set(key,value);}}});
  await commands.get('codemri.analyze')();
  assert.ok(sent.some(m=>m.type==='graph'));
  await receive({type:'jump',id:'coupon'});
  assert.equal(opened,path.join(root,'src/coupons.ts'));
  assert.equal(revealed.start.line,0);
  select({textEditor:{document:{uri:uri(opened)},selection:{active:{line:1,character:2}}}});
  assert.equal(sent.at(-1).id,'coupon');
  await receive({type:'openEvidence',path:'src/coupons.ts',line:8,column:12});
  assert.equal(revealed.start.line,7);
  assert.equal(revealed.start.character,12);
  changed({document:{uri:uri(opened)}});
  await receive({type:'jump',id:'coupon'});
  assert.match(errors.at(-1),/Reanalyze/);
  responseGraph = {...graph,layers:{architecture:{nodes:[],edges:[]},modules:{nodes:[],edges:[]}}};
  const previousGraphs=sent.filter(m=>m.type==='graph').length;
  await commands.get('codemri.analyze')();
  assert.match(errors.at(-1),/older CodeMRI analyzer/);
  assert.equal(sent.filter(m=>m.type==='graph').length,previousGraphs);
  responseGraph=graph;
  await commands.get('codemri.analyze')();
  const draft={version:1,root,revision:'demo',baseline:{nodes:[],edges:[]},nodes:[{id:'cache',name:'Cache',kind:'component',summary:'Cache product reads for five minutes',paths:[]}],edges:[],positions:{},intent:'Add caching',acceptance:'Verify cache expiry',removalNotes:{}};
  await receive({type:'designSave',draft});
  assert.equal(state.get('architectureDraft:'+root).intent,'Add caching');
  await receive({type:'designRun',action:'implement',draft});
  assert.match(errors.at(-1),/Assess this exact proposal/);assert.equal(invocations.length,0);
  freshness='changed';
  await receive({type:'designRun',action:'assess',draft});
  assert.match(errors.at(-1),/Source changed/);assert.equal(invocations.length,0);
  freshness='demo';await commands.get('codemri.analyze')();
  failAssessment=true;await receive({type:'designRun',action:'assess',draft});
  assert.match(errors.at(-1),/Assessment failed/);assert.equal(state.get('architecturePlan:'+root),undefined);
  assert.equal(sent.filter(m=>m.type==='chatState').at(-1).running,false);
  failAssessment=false;await receive({type:'designRun',action:'assess',draft});
  assert.ok(invocations.at(-1).args.includes('read-only'));
  assert.equal(fs.existsSync(invocations.at(-1).options.cwd),false,'Assessment temporary copy is cleaned up');
  assert.ok(state.get('architecturePlan:'+root).text.includes('Plausible'));
  assert.ok(sent.some(m=>m.type==='designPlan'));
  const calls=invocations.length;
  const changedDraft={...draft,intent:'Different behavior'};
  await receive({type:'designRun',action:'implement',draft:changedDraft});
  assert.match(errors.at(-1),/Assess this exact proposal/);assert.equal(invocations.length,calls);
  draft.positions.cache={x:400,y:250};
  await receive({type:'designRun',action:'implement',draft});
  assert.ok(invocations.at(-1).args.includes('workspace-write'));
  assert.match(invocations.at(-1).child.stdin.read().toString(),/Reviewed assessment and plan/);

  const proposal=sent.filter(m=>m.proposalId).at(-1);
  assert.ok(proposal,'Agent output must become a proposal');
  assert.equal(proposal.designComparison,true);
  assert.equal(fs.readFileSync(path.join(root,'src/coupons.ts'),'utf8'),'original working file');
  assert.ok(!fs.existsSync(path.join(root,'new.ts')));
  await receive({type:'proposalDecision',proposalId:'stale-id',paths:['src/coupons.ts'],action:'approve'});
  assert.equal(fs.readFileSync(path.join(root,'src/coupons.ts'),'utf8'),'original working file');
  await receive({type:'proposalDecision',proposalId:proposal.proposalId,paths:['src/coupons.ts'],action:'approve'});
  assert.equal(fs.readFileSync(path.join(root,'src/coupons.ts'),'utf8'),'proposed code');
  assert.ok(!fs.existsSync(path.join(root,'new.ts')),'Unselected proposal must remain unapplied');
  await receive({type:'proposalDecision',proposalId:proposal.proposalId,paths:['new.ts'],action:'discard'});
  assert.ok(!fs.existsSync(path.join(root,'new.ts')),'Discard must not apply the proposed addition');

});

test('agent bridge uses stdin, workspace sandbox, session resume and reports failures', async()=>{
  const {build}=require('esbuild');
  const {EventEmitter}=require('node:events');
  const {PassThrough}=require('node:stream');
  const os=require('node:os');
  const output=path.join(fs.mkdtempSync(path.join(os.tmpdir(),'codemri-agent-')),'agent.cjs');
  await build({entryPoints:['apps/extension/src/agent.ts'],bundle:true,platform:'node',format:'cjs',outfile:output});
  let invocation, child;
  const mod={exports:{}};
  vm.runInNewContext(fs.readFileSync(output,'utf8'),{module:mod,exports:mod.exports,require:id=>id==='node:child_process'?{spawn(executable,args,options){
    invocation={executable,args,options};child=new EventEmitter();child.stdin=new PassThrough();child.stdout=new PassThrough();child.stderr=new PassThrough();return child;
  }}:require(id)});
  const events=[];
  const run=mod.exports.runAgent('/bin/codex','/repo','literal $(do-not-run)','session-123',e=>events.push(e));
  assert.equal(invocation.options.shell,false);
  assert.equal(invocation.options.cwd,'/repo');
  assert.ok(invocation.args.includes('workspace-write'));
  assert.ok(invocation.args.includes('resume'));
  assert.ok(invocation.args.includes('session-123'));
  assert.equal(child.stdin.read().toString(),'literal $(do-not-run)');
  child.stdout.write('{"type":"thread.started","thread_id":"123"}\n');
  child.stdout.write('{"type":"item.completed","item":{"type":"agent_message","text":"Done"}}\n');
  child.emit('close',0,null);await run.done;
  assert.equal(events[1].item.text,'Done');
  const failed=mod.exports.runAgent('missing','/repo','prompt',undefined,()=>{});
  child.stderr.write('Login required');child.emit('close',1,null);
  await assert.rejects(failed.done,/Login required/);
});

test('proposals isolate agent writes, apply selected files, and reject stale files and symlinks',async()=>{
  const {build}=require('esbuild'),os=require('node:os');
  const temp=fs.mkdtempSync(path.join(os.tmpdir(),'codemri-approval-test-'));
  const output=path.join(temp,'proposals.cjs');
  await build({entryPoints:['apps/extension/src/proposals.ts'],bundle:true,platform:'node',format:'cjs',outfile:output});
  const {prepareProposal,collectProposal,applyFile,persistProposal}=require(output);
  const root=path.join(temp,'repo');fs.mkdirSync(root);
  fs.writeFileSync(path.join(root,'a.ts'),'const a = 1;\n');fs.writeFileSync(path.join(root,'b.ts'),'const b = 1;\n');
  const stage=await prepareProposal(root);
  fs.writeFileSync(path.join(stage.work,'a.ts'),'const a = 2;\n');
  fs.unlinkSync(path.join(stage.work,'b.ts'));
  fs.writeFileSync(path.join(stage.work,'new.ts'),'export const added = true;\n');
  const proposal=await collectProposal(stage);
  assert.equal(proposal.files.length,3);
  assert.equal(fs.readFileSync(path.join(root,'a.ts'),'utf8'),'const a = 1;\n');
  assert.ok(fs.existsSync(path.join(root,'b.ts')));
  assert.ok(!fs.existsSync(path.join(root,'new.ts')));
  const manifest=await persistProposal(proposal);assert.equal(JSON.parse(fs.readFileSync(manifest)).id,proposal.id);
  await applyFile(root,proposal.files.find(f=>f.path==='a.ts'));
  assert.equal(fs.readFileSync(path.join(root,'a.ts'),'utf8'),'const a = 2;\n');
  assert.ok(fs.existsSync(path.join(root,'b.ts')),'unselected deletion remains unapplied');
  fs.writeFileSync(path.join(root,'b.ts'),'new user edits');
  await assert.rejects(applyFile(root,proposal.files.find(f=>f.path==='b.ts')),/changed since/);
  assert.equal(fs.readFileSync(path.join(root,'b.ts'),'utf8'),'new user edits');
  fs.symlinkSync(path.join(root,'a.ts'),path.join(root,'new.ts'));
  await assert.rejects(applyFile(root,proposal.files.find(f=>f.path==='new.ts')),/symbolic link/);
  await assert.rejects(applyFile(root,{path:'../escape',before:null,after:'bad',mode:0o644}),/Invalid proposal path/);
});
