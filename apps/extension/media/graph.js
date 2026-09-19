import { traceView } from './trace.js';
import { layoutSystem, drawSystem } from './system-renderer.js';
/* Architecture → modules → symbols, with inspectable static evidence. */
const vscode = acquireVsCodeApi();
const $ = id => document.getElementById(id);
const svg = $('graph');
const NS = 'http://www.w3.org/2000/svg';
let renderVersion=0, systemLayout;
let focus, history=[];
let graph, selected, component, moduleId, affected = new Set(), contextText = '', box = [0,0,1100,600], positions = new Map();
function el(tag, attrs={}, value) { const n=document.createElementNS(NS,tag); for(const [k,v] of Object.entries(attrs)) n.setAttribute(k,String(v)); if(value!==undefined)n.textContent=value; return n; }
function current() {
  const level=$('layer').value;
  if(!graph)return {nodes:[],edges:[]};
  if(level==='architecture')return graph.layers?.architecture || {nodes:[],edges:[]};
  if(level==='trace')return traceView(graph,focus||selected);
  if(level==='modules'){const layer=graph.layers?.modules || {nodes:[],edges:[]};return {nodes:layer.nodes.filter(n=>!component||n.parent===component),edges:layer.edges};}
  const paths=moduleId?graph.layers.modules.nodes.find(n=>n.id===moduleId)?.paths:component?graph.layers.architecture.nodes.find(n=>n.id===component)?.paths:undefined;
  return {nodes:graph.nodes.filter(n=>n.kind!=='module'&&(!paths||paths.includes(n.path))),edges:graph.edges.filter(e=>e.kind!=='contains').map(e=>({...e,kind:e.kind.toUpperCase()}))};
}
function showEvidence(title, evidence, summary='') {
  $('nodeSummary').textContent=title+(summary?' — '+summary:'');
  $('evidence').replaceChildren();
  for(const item of evidence||[]){const button=document.createElement('button');button.textContent=`${item.path}:${item.line} · ${item.reason}`;button.onclick=()=>vscode.postMessage({type:'openEvidence',path:item.path,line:item.line});$('evidence').append(button);}
}
function activateNode(n) {
  const level=$('layer').value;
  if(n.id!==focus||level!=='trace')history.push({level,component,moduleId,focus});
  if(history.length>100)history.shift();
  showEvidence(n.name,n.evidence,n.summary);
  if(level==='architecture'){
    if(!(graph.layers?.modules.nodes||[]).some(m=>m.parent===n.id))return;
    component=n.id;moduleId=undefined;$('layer').value='modules';
  }else if(level==='modules'){
    moduleId=n.id;component=n.parent;$('layer').value='symbols';
    if(!graph.nodes.some(s=>s.kind!=='module'&&s.module_id===n.id))$('nodeSummary').textContent=n.name+' — Source is inventoried, but symbol extraction for this language is not implemented. Open the evidence files below.';
  }else{selected=n.id;focus=n.id;$('layer').value='trace';vscode.postMessage({type:'jump',id:n.id});$('details').textContent=`${n.name} · ${n.path}:${n.start_line}`;}
  render();fit();
}
function render() {
  const version=++renderVersion;
  if(!graph)return;
  const architecture=graph.layers?.architecture;
  if($('layer').value==='architecture' && architecture?.groups && architecture.nodes.length){
    svg.setAttribute('class','system-view');
    svg.setAttribute('preserveAspectRatio','xMidYMin meet');
    $('breadcrumb').textContent='System architecture';
    $('layerNote').textContent=(architecture.mode==='ai'?'AI synthesis':'Local source inference')+' · click a component to drill down · click a connection for evidence';
    $('nodeSummary').textContent=architecture.explanation||'';
    layoutSystem(architecture).then(layout=>{
      if(version!==renderVersion)return;
      systemLayout=layout;
      const current=graph.nodes.find(n=>n.id===selected);
      drawSystem(svg,layout,{activate:activateNode,inspect:e=>showEvidence(e.label||e.kind,e.evidence,e.kind+(e.inferred?' · inferred':'')),selectedIds:new Set(architecture.nodes.filter(n=>n.paths?.includes(current?.path)).map(n=>n.id)),affectedIds:new Set(architecture.nodes.filter(n=>graph.nodes.some(s=>affected.has(s.id)&&n.paths?.includes(s.path))).map(n=>n.id)),search:$('search').value.toLowerCase()});
      if(!svg.dataset.systemFitted){fit();svg.dataset.systemFitted='yes';}
    }).catch(error=>{$('status').textContent='Diagram layout failed: '+error.message;});
    return;
  }
  svg.dataset.systemFitted='';
  svg.removeAttribute('class');
  svg.replaceChildren();
  const level=$('layer').value;
  const componentName=graph.layers?.architecture.nodes.find(n=>n.id===component)?.name;
  const moduleName=graph.layers?.modules.nodes.find(n=>n.id===moduleId)?.name;
  $('breadcrumb').textContent=level==='architecture'?'System architecture':`System / ${componentName||'All components'}${['symbols','trace'].includes(level)?' / '+(moduleName||'All symbols'):''}${level==='trace'?' / '+(graph.nodes.find(n=>n.id===focus)?.name||'Select a function'):''}`;
  $('layerNote').textContent=level==='architecture'?`${graph.inventory?.files||0} source/config files · ${(graph.inventory?.languages||[]).join(', ')} · dashed = inferred connection`:'Connections preserve their relationship types; click an edge to inspect evidence.';
  const defs=el('defs'),marker=el('marker',{id:'arrow',viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:6,markerHeight:6,orient:'auto-start-reverse'});
  marker.append(el('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:'#617b94'}));defs.append(marker);svg.append(defs);
  const {nodes,edges}=current();positions=new Map();
  if(level==='trace')$('layerNote').textContent='Click a function to open source and explore its callers/callees. Back retraces your steps. Only resolved static calls are shown.';
  const columns=level==='architecture'?['Frontend','API','Services','Databases','Infrastructure','Shared','Tests'].filter(r=>nodes.some(n=>n.role===r)):['nodes'];
  if(level==='architecture')columns.forEach((role,col)=>{svg.append(el('text',{x:35+col*300,y:28,class:'lane'},role.toUpperCase()));nodes.filter(n=>n.role===role).forEach((n,row)=>positions.set(n.id,{x:35+col*300,y:65+row*140}));});
  else if(level==='trace'){['CALLERS','CURRENT FUNCTION','CALLEES'].forEach((title,i)=>svg.append(el('text',{x:35+i*360,y:28,class:'lane'},title)));const callers=new Set(edges.filter(e=>e.target===focus).map(e=>e.source));const counts=[0,0,0];for(const n of nodes){const column=n.id===focus?1:callers.has(n.id)?0:2;positions.set(n.id,{x:35+column*360,y:65+counts[column]++*140});}}
  else nodes.forEach((n,i)=>positions.set(n.id,{x:35+(i%3)*300,y:65+Math.floor(i/3)*140}));
  for(const edge of edges){const a=positions.get(edge.source),b=positions.get(edge.target);if(!a||!b)continue;
    const same=a.x===b.x,x=a.x+(same?245:245),y=a.y+36,tx=b.x+(same?245:0),ty=b.y+36;
    const curve=same?`M ${x} ${y} C ${x+70} ${y},${tx+70} ${ty},${tx} ${ty}`:`M ${x} ${y} C ${x+35} ${y},${tx-35} ${ty},${tx} ${ty}`;
    const group=el('g',{class:'relationship',tabindex:0,role:'button','aria-label':edge.kind+' relationship; inspect evidence'});
    group.append(el('path',{class:'edge '+(edge.inferred?'inferred':''),d:curve,'marker-end':'url(#arrow)'}),el('path',{class:'edge-hit',d:curve}),el('text',{x:same?x+40:(x+tx)/2,y:(y+ty)/2-7,class:'edge-label','text-anchor':'middle'},edge.kind),el('title',{},(edge.evidence||[]).map(e=>e.reason).join('\n')||edge.kind));
    const inspect=()=>showEvidence(edge.kind+(edge.inferred?' (inferred)':''),edge.evidence,`${nodes.find(n=>n.id===edge.source)?.name} → ${nodes.find(n=>n.id===edge.target)?.name}`);
    group.onclick=inspect;group.onkeydown=e=>{if(e.key==='Enter')inspect();};svg.append(group);
  }
  const search=$('search').value.toLowerCase();
  const selectedSymbol=graph.nodes.find(n=>n.id===selected);
  for(const n of nodes){const p=positions.get(n.id);const active=selected===n.id||selectedSymbol?.component_id===n.id||selectedSymbol?.module_id===n.id;
    const impacted=affected.has(n.id)||graph.nodes.some(s=>affected.has(s.id)&&(s.component_id===n.id||s.module_id===n.id));
    const group=el('g',{class:'node'+(active?' selected':'')+(impacted?' affected':'')+((search&&!`${n.name} ${n.path||''} ${(n.paths||[]).join(' ')}`.toLowerCase().includes(search))?' dim':''),transform:`translate(${p.x},${p.y})`,tabindex:0,role:'button','aria-label':n.name});
    const subtitle=n.paths?`${n.paths.length} files · ${n.kind==='component'?'open modules':n.kind==='module'?'open symbols':n.kind}`:n.path.split('/').pop()+':'+n.start_line;
    const label=n.signature||n.name;
    group.append(el('rect',{width:245,height:72,rx:9}),el('text',{x:12,y:27},label.length>29?label.slice(0,27)+'…':label),el('text',{x:12,y:51,class:'meta'},subtitle),el('title',{},n.name+' — '+(n.summary||n.path)));
    group.addEventListener('click',()=>activateNode(n));group.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();activateNode(n);}});svg.append(group);
  }
  if(!nodes.length)svg.append(el('text',{x:35,y:75,class:'empty'},level==='architecture'?'No supported source or configuration files found in this repository.':level==='modules'?'No modules in this component. Return to Architecture and select a source component.':'No symbols extracted for this module. Open its evidence files below.'));
}
function fit(){if($('layer').value==='architecture'&&systemLayout){box=[0,0,systemLayout.width,systemLayout.height];svg.setAttribute('viewBox',box.join(' '));return;}const values=[...positions.values()];box=[0,0,Math.max(600,...values.map(p=>p.x+330)),Math.max(300,...values.map(p=>p.y+120))];svg.setAttribute('viewBox',box.join(' '));}
window.addEventListener('message',({data:m})=>{
 if(m.type==='graph'){history=[];focus=undefined;systemLayout=undefined;svg.dataset.systemFitted='';graph=m.graph;component=undefined;moduleId=undefined;$('layer').value='architecture';affected.clear();contextText='';$('context').textContent='';$('status').textContent=`${graph.layers?.architecture.nodes.length||0} system components · ${graph.nodes.length} source nodes · snapshot ${graph.revision}${m.stale?' · stale':''}`;$('warnings').textContent=[...(graph.inventory?.limitations||[]),...graph.warnings].join('\n')||'No diagnostics.';render();fit();}
 if(m.type==='select'){selected=m.id;render();}
 if(m.type==='status'||m.type==='error')$('status').textContent=m.message;
 if(m.type==='impact'){affected=new Set(m.result.affected);$('details').textContent=`${m.result.direct.length} direct · ${m.result.affected.length} affected. ${m.result.limitations}`;$('context').textContent=Object.entries(m.result.reasons).map(([id,why])=>`${graph.nodes.find(n=>n.id===id)?.name}: ${why}`).join('\n');render();}
 if(m.type==='context'){contextText=m.result.text;affected=new Set(m.result.selected);$('details').textContent=`${m.result.tokens.toLocaleString()} / ${m.result.budget.toLocaleString()} tokens · ${m.result.selected.length} symbols · indexed source ${m.result.repository_tokens.toLocaleString()} tokens (cl100k_base)`;$('context').textContent=contextText;render();}
});
$('generateAI').onclick=()=>vscode.postMessage({type:'generateAI'});
$('analyze').onclick=()=>vscode.postMessage({type:'analyze'});
$('impact').onclick=()=>vscode.postMessage({type:'impact',query:$('query').value});
$('compile').onclick=()=>vscode.postMessage({type:'context',query:$('query').value,budget:Number($('budget').value)});
$('copy').onclick=()=>{if(contextText)vscode.postMessage({type:'copy',text:contextText});};
$('budget').oninput=()=>{$('budgetLabel').textContent=Number($('budget').value).toLocaleString()+' tokens';};
$('traceBack').onclick=()=>{const previous=history.pop();if(!previous)return;component=previous.component;moduleId=previous.moduleId;focus=previous.focus;$('layer').value=previous.level;render();fit();};
$('search').oninput=render;$('layer').onchange=()=>{if($('layer').value==='trace')focus=selected;render();fit();};$('back').onclick=()=>{component=undefined;moduleId=undefined;$('layer').value='architecture';render();fit();};$('reset').onclick=fit;
svg.addEventListener('wheel',e=>{e.preventDefault();const factor=e.deltaY>0?1.12:.89;box[2]=Math.max(150,Math.min(20000,box[2]*factor));box[3]=Math.max(100,Math.min(12000,box[3]*factor));svg.setAttribute('viewBox',box.join(' '));},{passive:false});
let drag;
svg.addEventListener('pointerdown',e=>{if(e.target.closest('.node'))return;drag=[e.clientX,e.clientY,...box];svg.setPointerCapture(e.pointerId);});
svg.addEventListener('pointermove',e=>{if(!drag)return;box[0]=drag[2]-(e.clientX-drag[0])*box[2]/svg.clientWidth;box[1]=drag[3]-(e.clientY-drag[1])*box[3]/svg.clientHeight;svg.setAttribute('viewBox',box.join(' '));});
svg.addEventListener('pointerup',()=>drag=undefined);svg.addEventListener('pointercancel',()=>drag=undefined);
vscode.postMessage({type:'ready'});
