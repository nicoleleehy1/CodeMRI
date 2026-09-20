import { setupCreate } from './create-mode.js';
import { changeHighlights, reviewItems, setupChat, drawFileDiff } from './change-review.js';
import { searchSymbols } from './symbol-search.js';
import { cancelNodeClick } from './node-interactions.js';
import { callHighlights, labelKey, orderKey } from './call-analysis.js';
import { drawCallPopup } from './call-popup.js';
import { drawMainNode, visitNode } from './node-inspector.js';
import { drawFunctionInspector } from './function-inspector.js';
import { hierarchyView, isFunction, symbolLocation } from './hierarchy-view.js';
import { layoutSymbols, drawSymbols } from './symbol-renderer.js';
import { traceView } from './trace.js';
import { layoutSystem, drawSystem } from './system-renderer.js';
/* Architecture → modules → symbols, with inspectable static evidence. */
const host = acquireVsCodeApi();
const vscode = {postMessage(message){
  if((proposalId || latestGraph && graph!==latestGraph) && ['jump','openEvidence'].includes(message.type)) {
    $('status').textContent=proposalId?'Viewing proposed code. Approve or delete the pending files before opening live source.':'Viewing the previous snapshot. Choose a current change or Full Repository to open live source.';return;
  }
  host.postMessage(message);
}};
const $ = id => document.getElementById(id);
const svg = $('graph');
const createEvent=setupCreate(document,message=>host.postMessage(message));
let proposalId, proposedFiles=[], selectedFiles=new Set(), proposalBusy=false;
let latestGraph, baselineGraph, changes={}, changeIndex=-1, reviewEdge;
const chatEvent=setupChat(document,message=>vscode.postMessage(message));
const NS = 'http://www.w3.org/2000/svg';
let renderVersion=0, systemLayout, symbolLayout, symbolViewKey;
let focus, fileId, parentSymbol, mainNodeId, mainTrail=[], history=[];
let orders={}, labelSelection=new Map(), labelPopup, sortTarget;
let graph, selected, component, moduleId, affected = new Set(), contextText = '', box = [0,0,1100,600], positions = new Map();
function el(tag, attrs={}, value) { const n=document.createElementNS(NS,tag); for(const [k,v] of Object.entries(attrs)) n.setAttribute(k,String(v)); if(value!==undefined)n.textContent=value; return n; }
function itemsForReview(){
  if(!proposalId)return reviewItems(changes);
  return proposedFiles.map(file=>{
    const view=file.status==='removed'?baselineGraph:latestGraph;
    const match=(changes.nodes||[]).find(n=>n.path===file.path && n.id!==file.path && view?.nodes.some(node=>node.id===n.id));
    return {...file,type:'node',name:file.path,id:match?.id||file.path};
  });
}
function updateSelection(){
  $('selectionCount').textContent=`${selectedFiles.size} file(s) selected`;
  $('approveSelected').disabled=proposalBusy||!selectedFiles.size;
  $('discardSelected').disabled=proposalBusy||!selectedFiles.size;
}
function decideFiles(action){
  if(proposalBusy||!selectedFiles.size)return;
  proposalBusy=true;updateSelection();$('proposalError').textContent='';
  vscode.postMessage({type:'proposalDecision',proposalId,action,paths:[...selectedFiles]});
}
$('approveSelected').onclick=()=>decideFiles('approve');
$('discardSelected').onclick=()=>decideFiles('discard');
function drawReview(){
  const items=itemsForReview();
  $('changeReview').hidden=!items.length;
  $('reviewAccept').hidden=Boolean(proposalId);
  $('proposalActions').hidden=!proposalId;
  $('changeSummary').textContent=proposalId?`${proposedFiles.length} proposed file changes · not applied · hover a number to select a file for approval or deletion.`:`Review ${changes.nodes?.length||0} changed symbols and ${changes.edges?.length||0} connections · yellow marks changed areas.`;
  $('changeList').replaceChildren();
  items.forEach((item,index)=>{const li=document.createElement('li'),button=document.createElement('button');
    if(proposalId){
      li.className='proposal-row';
      const label=document.createElement('label'),checkbox=document.createElement('input'),number=document.createElement('span');
      label.className='change-selector';checkbox.type='checkbox';checkbox.checked=selectedFiles.has(item.path);checkbox.disabled=proposalBusy;
      checkbox.setAttribute('aria-label',`Select all proposed edits in ${item.path}`);number.textContent=String(index+1);number.setAttribute('aria-hidden','true');
      checkbox.onchange=()=>{checkbox.checked?selectedFiles.add(item.path):selectedFiles.delete(item.path);updateSelection();};
      label.append(checkbox,number);li.append(label);
    }
button.textContent=`${item.status} · ${item.name}${item.path && item.path!==item.name?' · '+item.path:''}`;button.setAttribute('aria-current',String(index===changeIndex));button.onclick=()=>visitChange(index);li.append(button);$('changeList').append(li);});
  updateSelection();
}
function visitChange(index){
  const items=itemsForReview();if(!items.length)return;
  changeIndex=(index+items.length)%items.length;const item=items[changeIndex];
  if(proposalId)drawFileDiff(document,item);
  graph=item.status==='removed'?baselineGraph:latestGraph;
  if(!graph)return;
  const n=graph.nodes.find(n=>n.id===item.id);
  if(proposalId && !n){mainNodeId=undefined;selected=undefined;component=undefined;moduleId=undefined;fileId=undefined;parentSymbol=undefined;$('layer').value='repository';$('reviewLocation').textContent='This file has no indexed symbols. Review its complete diff below.';drawReview();render();return;}
  const location=symbolLocation(graph,item.id);
  component=location.component;moduleId=location.moduleId;fileId=location.fileId;parentSymbol=location.parentSymbol;
  mainNodeId=item.id;selected=item.id;mainTrail=visitNode(graph,[],item.id);focus=item.id;labelPopup=undefined;
  reviewEdge=item.type==='edge'?item:undefined;
  $('layer').value=item.type==='edge'?'trace':'symbols';
  if(item.type==='node' && n?.kind==='module') {
    const file=(graph.layers?.files?.nodes||[]).find(f=>f.path===n.path || f.paths?.includes(n.path));
    if(file){moduleId=file.parent;fileId=undefined;parentSymbol=undefined;mainNodeId=file.id;selected=file.id;$('layer').value='files';}
  }
  symbolViewKey=undefined;systemLayout=undefined;symbolLayout=undefined;
  $('reviewLocation').textContent=`${changeIndex+1} of ${items.length} · ${item.status==='removed'?'Previous snapshot · removed':proposalId?'Proposed snapshot · not applied':'Current snapshot'} · ${n?.path||item.name}`;
  drawReview();render();$('changeReview').scrollIntoView({block:'start',behavior:'smooth'});
}
$('changePrev').onclick=()=>visitChange(changeIndex-1);
$('changeNext').onclick=()=>visitChange(changeIndex+1);
$('reviewAccept').onclick=()=>vscode.postMessage({type:'reviewAccept'});
function current() {
  const level=$('layer').value;
  if(!graph)return {nodes:[],edges:[]};
  if(level==='trace' && reviewEdge && focus===reviewEdge.source){const ids=new Set([reviewEdge.source,reviewEdge.target]);return {nodes:graph.nodes.filter(n=>ids.has(n.id)),edges:graph.edges.filter(e=>ids.has(e.source)&&ids.has(e.target))};}
  if(level==='trace')return traceView(graph,focus);
  return hierarchyView(graph,{level,component,moduleId,fileId,parentSymbol});
}
function showEvidence(title, evidence, summary='') {
  $('nodeSummary').textContent=title+(summary?' — '+summary:'');
  $('evidence').replaceChildren();
  for(const item of evidence||[]){const button=document.createElement('button');button.textContent=`${item.path}:${item.line} · ${item.reason}`;button.onclick=()=>vscode.postMessage({type:'openEvidence',path:item.path,line:item.line});$('evidence').append(button);}
}
function selectNode(n){
  if(mainNodeId!==n.id){
    history.push({level:$('layer').value,component,moduleId,fileId,parentSymbol,focus,selected,mainNodeId,mainTrail:[...mainTrail]});
    if(history.length>100)history.shift();
  }
  mainNodeId=n.id;mainTrail=visitNode(graph,mainTrail,n.id);selected=n.id;labelPopup=undefined;
  showEvidence(n.name,n.evidence,n.summary);render();
  if(graph.nodes.some(symbol=>symbol.id===n.id)){
    vscode.postMessage({type:'jump',id:n.id});
  }else{
    const evidence=n.evidence?.[0];
    const path=n.path||evidence?.path||n.paths?.[0];
    if(path)vscode.postMessage({type:'openEvidence',path,line:n.start_line||evidence?.line||1,column:n.start_column??evidence?.column??0});
  }
}
function inspectLabel(node,key,value,category){
  const chosen=labelSelection.get(node.id)||new Set();
  const token=labelKey(key,value);
  if(key==='calls')chosen.add(token);else if(chosen.has(token))chosen.delete(token);else chosen.add(token);
  labelSelection.set(node.id,chosen);labelPopup={ownerId:node.id,key,value,category};
  $('sortMenu').hidden=true;render();
}
function selectCalls(node){
  const chosen=labelSelection.get(node.id)||new Set();
  const values=node.details?.calls||[];
  const clear=values.every(value=>chosen.has(labelKey('calls',value)));
  for(const value of values){const token=labelKey('calls',value);if(clear)chosen.delete(token);else chosen.add(token);}
  labelSelection.set(node.id,chosen);render();
}
function showOrder(node,key,label){
  sortTarget={id:node.id,key};
  $('sortMenuHeading').textContent=`${node.name} · ${label}`;
  $('sortAlpha').setAttribute('aria-checked',String(orders[orderKey(node.id,key)]==='alphabetical'));
  $('sortSource').setAttribute('aria-checked',String(orders[orderKey(node.id,key)]!=='alphabetical'));
  $('sortMenu').hidden=false;
}
function applyOrder(mode){if(!sortTarget)return;orders[orderKey(sortTarget.id,sortTarget.key)]=mode;$('sortMenu').hidden=true;symbolViewKey=undefined;render();}
function cardOptions(){
  const highlights=callHighlights(graph,labelSelection);
  return {...changeHighlights(graph,changes),orders,selection:labelSelection,onLabel:inspectLabel,onOrder:showOrder,onSelectCalls:selectCalls,sortIcon:svg.dataset.sortIcon,highlightedIds:highlights.ids,highlightedEdges:highlights.edges};
}
function drillNode(n) {
  const level=$('layer').value;
  showEvidence(n.name,n.evidence,n.summary);
  const next={level,component,moduleId,fileId,parentSymbol,focus,selected,mainNodeId,mainTrail:[...mainTrail]};
  mainNodeId=n.id;mainTrail=visitNode(graph,mainTrail,n.id);selected=n.id;labelPopup=undefined;
  if(n.kind==='repository'){
    $('layer').value='architecture';
  }else if(['component','api_endpoint','database_entity','event_queue','external','deployment'].includes(n.kind)){
    if((graph.layers?.packages?.nodes||[]).some(m=>m.parent===n.id)){
      component=n.id;moduleId=undefined;fileId=undefined;parentSymbol=undefined;$('layer').value='modules';
    }
  }else if(n.kind==='package'||n.kind==='module'){
    moduleId=n.id;component=n.parent;fileId=undefined;parentSymbol=undefined;$('layer').value='files';
  }else if(n.kind==='file'){
    fileId=n.id;parentSymbol=undefined;$('layer').value='symbols';
  }else{
    const location=symbolLocation(graph,n.id);
    component=location.component;moduleId=location.moduleId;fileId=location.fileId;parentSymbol=location.parentSymbol;
    vscode.postMessage({type:'jump',id:n.id});
    $('details').textContent=`${n.name} · ${n.path}:${n.start_line}`;
    const children=(graph.layers?.hierarchy?.nodes||[]).filter(child=>child.parent===n.id);
    if(isFunction(n)){focus=n.id;$('layer').value='trace';}
    else if(children.length){parentSymbol=n.id;$('layer').value='symbols';}
  }
  if(n.id!==next.mainNodeId||$('layer').value!==next.level)history.push(next);
  if(history.length>100)history.shift();
  render();fit();
}

function drawSearchResults(){
  const results=$('searchResults');results.replaceChildren();
  const query=$('search').value.trim();results.hidden=!query;
  if(!query)return;
  const matches=graph?searchSymbols(graph,query):[];
  if(!matches.length){const empty=document.createElement('p');empty.textContent=graph?'No indexed symbols or calls match.':'Analyze the codebase to search symbols.';results.append(empty);return;}
  for(const result of matches){
    const button=document.createElement('button');
    button.textContent=`${result.label} · ${result.path}:${result.line} · ${result.kind}`;
    button.onclick=()=>{
      const n=result.node,location=symbolLocation(graph,n.id);
      history.push({level:$('layer').value,component,moduleId,fileId,parentSymbol,focus,selected,mainNodeId,mainTrail:[...mainTrail]});
      component=location.component;moduleId=location.moduleId;fileId=location.fileId;parentSymbol=location.parentSymbol;
      $('layer').value='symbols';focus=undefined;mainNodeId=n.id;selected=n.id;mainTrail=visitNode(graph,[],n.id);labelPopup=undefined;
      $('search').value='';results.hidden=true;symbolViewKey=undefined;
      render();vscode.postMessage({type:'openEvidence',path:result.path,line:result.line,column:result.column});
    };
    results.append(button);
  }
}

function breadcrumb(){
  const nodes=new Map((graph.layers?.hierarchy?.nodes||[]).map(n=>[n.id,n]));
  const id=$('layer').value==='trace'?focus:parentSymbol||fileId||moduleId||component;
  const names=[],seen=new Set();
  let node=nodes.get(id);
  while(node&&!seen.has(node.id)){seen.add(node.id);names.unshift(node.name);node=nodes.get(node.parent);}
  return names.length?names.join(' / '):graph.root.split(/[\\/]/).pop();
}

function render() {
  cancelNodeClick();
  const version=++renderVersion;
  if(!graph)return;
  drawMainNode(graph,mainNodeId,document,selectNode,{...cardOptions(),drill:drillNode});
  drawFunctionInspector(graph,mainNodeId,document,message=>vscode.postMessage(message),mainTrail);
  drawCallPopup(graph,mainNodeId||focus,labelPopup,document,message=>vscode.postMessage(message));
  const architecture=current();
  if(['repository','architecture','modules','files'].includes($('layer').value) && architecture.nodes.length){
    symbolViewKey=undefined;
    svg.setAttribute('class','system-view');
    svg.setAttribute('preserveAspectRatio','xMidYMin meet');
    $('breadcrumb').textContent=breadcrumb();
    $('layerNote').textContent=(architecture.mode==='ai'?'AI synthesis':'Analyzed repository')+' · '+({repository:'Double-click a component to explore its packages',architecture:'Double-click a component to explore its packages',modules:'Double-click a package to see its files',files:'Double-click a file to see its declarations'}[$('layer').value])+' · connections retain source evidence';
    $('nodeSummary').textContent=architecture.explanation||'';
    layoutSystem(architecture).then(layout=>{
      if(version!==renderVersion)return;
      systemLayout=layout;
      const current=graph.nodes.find(n=>n.id===selected);
      drawSystem(svg,layout,{activate:selectNode,drill:drillNode,inspect:e=>showEvidence(e.label||e.kind,e.evidence,e.kind+(e.inferred?' · inferred':'')),selectedIds:new Set(architecture.nodes.filter(n=>n.id===mainNodeId||(!mainNodeId&&n.paths?.includes(current?.path))).map(n=>n.id)),affectedIds:new Set(architecture.nodes.filter(n=>graph.nodes.some(s=>affected.has(s.id)&&n.paths?.includes(s.path))).map(n=>n.id)),search:'',...cardOptions()});
      const key=JSON.stringify([$('layer').value,component,moduleId,graph.revision,Boolean(mainNodeId)]);
      if(svg.dataset.systemFitted!==key){fit();svg.dataset.systemFitted=key;}
    }).catch(error=>{$('status').textContent='Diagram layout failed: '+error.message;});
    return;
  }
  svg.dataset.systemFitted='';
  svg.removeAttribute('class');
  svg.replaceChildren();
  const level=$('layer').value;
  $('breadcrumb').textContent=breadcrumb();
  $('layerNote').textContent=level==='architecture'?`${graph.inventory?.files||0} source/config files · ${(graph.inventory?.languages||[]).join(', ')} · dashed = inferred connection`:'Connections preserve their relationship types; click an edge to inspect evidence.';
  const defs=el('defs'),marker=el('marker',{id:'arrow',viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:6,markerHeight:6,orient:'auto-start-reverse'});
  marker.append(el('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:'#617b94'}));defs.append(marker);svg.append(defs);
  const {nodes,edges}=current();positions=new Map();
  if(level==='trace')$('layerNote').textContent='Click to select a function; double-click (or Enter) to explore its callers/callees. Space selects. Back retraces your steps. Only resolved static calls are shown.';
  if((level==='symbols'||level==='trace')&&nodes.length){
    const viewKey=JSON.stringify([level,component,moduleId,fileId,parentSymbol,focus,graph.revision,Boolean(mainNodeId)]);
    svg.setAttribute('class','symbol-view');
    svg.setAttribute('preserveAspectRatio','xMidYMin meet');
    layoutSymbols({nodes,edges},Math.max(.6,svg.clientWidth/620),orders).then(layout=>{
      if(version!==renderVersion)return;
      symbolLayout=layout;
      drawSymbols(svg,layout,{activate:selectNode,drill:drillNode,inspect:e=>showEvidence(e.kind,e.evidence,`${nodes.find(n=>n.id===e.source)?.name} → ${nodes.find(n=>n.id===e.target)?.name}`),selectedIds:new Set([mainNodeId||selected]),affectedIds:affected,search:'',...cardOptions()});
      if(symbolViewKey!==viewKey){symbolViewKey=viewKey;fit();}
    }).catch(error=>{$('status').textContent='Symbol layout failed: '+error.message;});
    return;
  }
  symbolViewKey=undefined;symbolLayout=undefined;
  const emptyMessage=['repository','architecture'].includes(level)?'No supported source or configuration files found.':level==='modules'?'No source packages in this component.':level==='files'?'No files in this package.':'No declarations extracted here. Use the file evidence link to open source.';
  svg.append(el('text',{x:35,y:75,class:'empty'},emptyMessage));
}
function fit(){if(['symbols','trace'].includes($('layer').value)&&symbolLayout){box=[0,0,Math.max(400,symbolLayout.width),Math.max(240,symbolLayout.height)];svg.setAttribute('viewBox',box.join(' '));return;}if(['repository','architecture','modules','files'].includes($('layer').value)&&systemLayout){box=[0,0,systemLayout.width,systemLayout.height];svg.setAttribute('viewBox',box.join(' '));return;}const values=[...positions.values()];box=[0,0,Math.max(600,...values.map(p=>p.x+330)),Math.max(300,...values.map(p=>p.y+120))];svg.setAttribute('viewBox',box.join(' '));}
window.addEventListener('message',({data:m})=>{
 chatEvent(m);
 createEvent(m);
 if(m.type==='proposalState'){proposalBusy=m.busy;updateSelection();if(m.error)$('proposalError').textContent=m.error;}
 if(m.type==='graph'){$('runTests').disabled=false;proposalId=m.proposalId;proposedFiles=m.files||[];selectedFiles.clear();proposalBusy=false;drawFileDiff(document,undefined);latestGraph=m.graph;baselineGraph=m.baseline;changes=m.changes||{};changeIndex=-1;$('reviewLocation').textContent='';drawReview();orders={};labelSelection.clear();labelPopup=undefined;$('sortMenu').hidden=true;history=[];mainNodeId=undefined;mainTrail=[];focus=undefined;selected=undefined;systemLayout=undefined;symbolLayout=undefined;symbolViewKey=undefined;svg.dataset.systemFitted='';graph=m.graph;drawSearchResults();component=undefined;moduleId=undefined;fileId=undefined;parentSymbol=undefined;$('layer').value=graph.layers?.repository?'repository':'architecture';affected.clear();contextText='';$('context').textContent='';$('status').textContent=`${graph.layers?.architecture.nodes.length||0} system components · ${graph.nodes.length} source nodes · snapshot ${graph.revision}${m.stale?' · stale':''}`;$('warnings').textContent=[...(graph.inventory?.limitations||[]),...graph.warnings].join('\n')||'No diagnostics.';render();fit();if(proposalId && proposedFiles.length)visitChange(0);}
 if(m.type==='select'){selected=m.id;render();}
 if(m.type==='status'||m.type==='error')$('status').textContent=m.message;
 if(m.type==='impact'){affected=new Set(m.result.affected);const tests=m.result.tests||{tests:[]};$('details').textContent=`${m.result.direct.length} direct · ${m.result.affected.length} affected · ${tests.tests.length?tests.tests.length+' associated test(s)':'no identified tests'}. ${m.result.limitations}`;$('context').textContent=Object.entries(m.result.reasons).map(([id,why])=>`${graph.nodes.find(n=>n.id===id)?.name}: ${why}`).join('\n')+(tests.tests.length?'\n\nAssociated tests (heuristic):\n'+tests.tests.map(t=>`${t.path}${t.name&&t.name!==t.path?' · '+t.name:''} — via ${[...new Set(t.justification.map(j=>j.symbol_name+' ('+j.via+')'))].join(', ')}`).join('\n'):'');render();}
 if(m.type==='testResults'){drawTestResults(m.result);}
 if(m.type==='context'){contextText=m.result.text;affected=new Set(m.result.selected);$('details').textContent=`${m.result.tokens.toLocaleString()} / ${m.result.budget.toLocaleString()} tokens · ${m.result.selected.length} symbols · indexed source ${m.result.repository_tokens.toLocaleString()} tokens (cl100k_base)`;$('context').textContent=contextText;render();}
});
$('sortAlpha').onclick=()=>applyOrder('alphabetical');
$('sortSource').onclick=()=>applyOrder('source');
$('closeSortMenu').onclick=()=>{$('sortMenu').hidden=true;};
$('closeCallPopup').onclick=()=>{labelPopup=undefined;$('callPopup').hidden=true;};
window.addEventListener('keydown',e=>{if(e.key==='Escape'){cancelNodeClick();labelPopup=undefined;$('callPopup').hidden=true;$('sortMenu').hidden=true;}});
$('closeMainNode').onclick=()=>{labelPopup=undefined;mainNodeId=undefined;mainTrail=[];render();fit();};
$('generateAI').onclick=()=>vscode.postMessage({type:'analyze'});
$('analyze').onclick=()=>vscode.postMessage({type:'generateAI'});
$('impact').onclick=()=>vscode.postMessage({type:'impact',query:$('query').value});
$('runTests').onclick=()=>vscode.postMessage({type:'runTests',query:$('query').value});
function drawTestResults(result){
 const box=$('testResults');box.hidden=false;
 const totals=result.totals||{};
 $('testHeading').textContent=`Tests ${result.status}${totals.passed!==undefined?` · ${totals.passed} passed · ${totals.failed} failed · ${totals.skipped} skipped`:''} · ${(result.duration_ms/1000).toFixed(1)}s`;
 $('testNote').textContent=(result.proposalId?'Ran against the pending proposal in a fresh copy. ':'')+(result.note||'')+(result.isolation?' '+result.isolation+'.':'');
 const list=$('testRuns');list.textContent='';
 for(const run of result.runs||[]){
  const item=document.createElement('li');item.className='test-run test-'+run.status;
  const head=document.createElement('strong');head.textContent=`${run.status.toUpperCase()} · ${[run.tool,...run.args].join(' ')}${run.exit_code===null?'':' · exit '+run.exit_code}`;
  const out=document.createElement('pre');out.textContent=((run.stdout||'')+(run.stderr?'\n'+run.stderr:'')).trim().slice(-4000)||'(no output)';
  item.append(head,out);list.append(item);
 }
 if(!(result.runs||[]).length){const item=document.createElement('li');item.textContent='Nothing executed.';list.append(item);}
}
$('compile').onclick=()=>vscode.postMessage({type:'context',query:$('query').value,budget:Number($('budget').value)});
$('copy').onclick=()=>{if(contextText)vscode.postMessage({type:'copy',text:contextText});};
$('budget').oninput=()=>{$('budgetLabel').textContent=Number($('budget').value).toLocaleString()+' tokens';};
$('traceBack').onclick=()=>{labelPopup=undefined;const previous=history.pop();if(!previous)return;component=previous.component;moduleId=previous.moduleId;fileId=previous.fileId;parentSymbol=previous.parentSymbol;focus=previous.focus;selected=previous.selected;mainNodeId=previous.mainNodeId;mainTrail=previous.mainTrail||[];$('layer').value=previous.level;render();fit();};
$('search').oninput=drawSearchResults;$('layer').onchange=()=>{const level=$('layer').value;if(level==='trace')focus=selected;if(['repository','architecture'].includes(level)){component=undefined;moduleId=undefined;fileId=undefined;parentSymbol=undefined;}else if(level==='modules'){moduleId=undefined;fileId=undefined;parentSymbol=undefined;}else if(level==='files'){fileId=undefined;parentSymbol=undefined;}render();fit();};$('back').onclick=()=>{graph=latestGraph;labelPopup=undefined;mainNodeId=undefined;mainTrail=[];history=[];component=undefined;moduleId=undefined;fileId=undefined;parentSymbol=undefined;$('layer').value=graph.layers?.repository?'repository':'architecture';render();fit();};$('reset').onclick=fit;
svg.addEventListener('wheel',e=>{e.preventDefault();const factor=e.deltaY>0?1.12:.89;box[2]=Math.max(150,Math.min(20000,box[2]*factor));box[3]=Math.max(100,Math.min(12000,box[3]*factor));svg.setAttribute('viewBox',box.join(' '));},{passive:false});
let drag;
svg.addEventListener('pointerdown',e=>{if(e.target.closest('.node'))return;drag=[e.clientX,e.clientY,...box];svg.setPointerCapture(e.pointerId);});
svg.addEventListener('pointermove',e=>{if(!drag)return;box[0]=drag[2]-(e.clientX-drag[0])*box[2]/svg.clientWidth;box[1]=drag[3]-(e.clientY-drag[1])*box[3]/svg.clientHeight;svg.setAttribute('viewBox',box.join(' '));});
svg.addEventListener('pointerup',()=>drag=undefined);svg.addEventListener('pointercancel',()=>drag=undefined);
vscode.postMessage({type:'ready'});
