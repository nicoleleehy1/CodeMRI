import { isFunction } from './hierarchy-view.js';

import { nodeIndex, nodeTrail } from './node-inspector.js';

export function functionInspector(graph, id, visited=[]) {
  const indexed=nodeIndex(graph),symbol=indexed.get(id);
  if(!symbol)return null;
  const trail=visited.length?visited.map(key=>indexed.get(key)).filter(Boolean):nodeTrail(graph,id);
  if(!trail.length)trail.push({name:graph.root.split(/[\\/]/).pop()},symbol);
  const exact=isFunction(symbol);
  const members=new Set([id]);
  let changed=true;
  while(changed){changed=false;for(const node of indexed.values())if(members.has(node.parent)&&!members.has(node.id)){members.add(node.id);changed=true;}}
  if(['file','package','module'].includes(symbol.kind)){
    const paths=new Set(symbol.paths||[symbol.path]);
    for(const node of graph.nodes)if(paths.has(node.path))members.add(node.id);
  }
  const sourceScope=exact||['file','package','module','class_declaration','record_declaration','interface_declaration'].includes(symbol.kind);
  const incoming=sourceScope?graph.edges.filter(e=>e.kind.toLowerCase()==='calls'&&(exact?e.target===id:members.has(e.target)&&!members.has(e.source))):[];
  const sites=[],positions=new Set();
  let incomplete=false;
  for(const edge of incoming){
    const caller=indexed.get(edge.source);
    if(!edge.call_sites?.length){incomplete=true;continue;}
    for(const site of edge.call_sites){
      const key=JSON.stringify([site.path,site.line,site.column||0]);
      if(positions.has(key))continue;
      positions.add(key);sites.push({...site,caller:caller?.signature||caller?.name||edge.source});
    }
  }
  sites.sort((a,b)=>a.path.localeCompare(b.path)||a.line-b.line||(a.column||0)-(b.column||0));
  const relations=sourceScope?[]:(graph.layers?.architecture?.edges||[]).filter(e=>e.target===id&&e.kind.toUpperCase()!=='CONTAINS').map(e=>({...e,caller:indexed.get(e.source)?.name||e.source}));
  return {symbol,trail,sites,incomplete,callerCount:new Set(incoming.map(e=>e.source)).size,relations,mode:sourceScope?'calls':'relationships'};
}

export function drawFunctionInspector(graph,id,document,postMessage,visited=[]){
  const path=document.getElementById('functionPath');
  const location=document.getElementById('functionLocation');
  const list=document.getElementById('functionCallers');
  const count=document.getElementById('functionCallCount');
  path.replaceChildren();location.replaceChildren();list.replaceChildren();
  const model=functionInspector(graph,id,visited);
  if(!model){path.textContent='Click a node to see how you reached it.';count.textContent='No node selected';return;}
  function link(label,target){
    const a=document.createElement('a');a.textContent=label;a.setAttribute('href','#');
    a.setAttribute('title',`Open ${target.path}:${target.line}:${(target.column||0)+1} in the editor`);
    a.onclick=event=>{event.preventDefault();postMessage({type:'openEvidence',...target});};return a;
  }
  for(const node of model.trail){
    const item=document.createElement('li');
    const source=node.path;
    if(source)item.append(link(node.name,{path:source,line:node.start_line||1,column:node.start_column||0}));
    else item.textContent=node.name;
    path.append(item);
  }
  const s=model.symbol;
  if(s.path)location.append(link(`${s.path}:${s.start_line||1}`,{path:s.path,line:s.start_line||1,column:s.start_column||0}));
  else if(s.evidence?.[0])location.append(link(`${s.evidence[0].path}:${s.evidence[0].line}`,{path:s.evidence[0].path,line:s.evidence[0].line}));
  if(model.mode==='relationships'){
    count.textContent=`${model.relations.length} incoming relationship${model.relations.length===1?'':'s'}`;
    for(const relation of model.relations){
      const item=document.createElement('li');
      const name=document.createElement('strong');name.textContent=`${relation.caller} — ${relation.label||relation.kind}`;item.append(name);
      for(const evidence of relation.evidence||[]){const row=document.createElement('div');row.append(link(`${evidence.path}:${evidence.line}`,{path:evidence.path,line:evidence.line,column:evidence.column||0}));item.append(row);}
      list.append(item);
    }
    if(!model.relations.length){const item=document.createElement('li');item.textContent='No incoming architecture relationships found.';list.append(item);}
    return;
  }
  count.textContent=model.incomplete?'Call-site count unavailable — reanalyze':`${model.sites.length} call site${model.sites.length===1?'':'s'} · ${model.callerCount} caller${model.callerCount===1?'':'s'}`;
  for(const site of model.sites){
    const item=document.createElement('li');
    item.append(link(`${site.caller} — ${site.path}:${site.line}:${(site.column||0)+1}`,{path:site.path,line:site.line,column:site.column||0}));
    const expression=document.createElement('code');expression.textContent=site.expression;item.append(expression);list.append(item);
  }
  if(!model.sites.length){const item=document.createElement('li');item.textContent=model.incomplete?'Reanalyze to load precise caller locations.':'No resolved call sites found in this repository.';list.append(item);}
}
