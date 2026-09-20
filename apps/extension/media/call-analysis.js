import { isFunction } from './hierarchy-view.js';
export const labelKey=(key,value)=>JSON.stringify([key,value]);
export const orderKey=(id,key)=>JSON.stringify([id,key]);
export function orderedValues(node,key,orders={}) {
  const values=[...(node.details?.[key]||[])];
  return orders[orderKey(node.id,key)]==='alphabetical'?values.sort((a,b)=>a.localeCompare(b,undefined,{numeric:true,sensitivity:'base'})):values;
}
export function callCount(node,label) {
  return Array.isArray(node.call_occurrences)?node.call_occurrences.filter(c=>c.label===label).length:null;
}
export function callHighlights(graph,selection) {
  const ids=new Set(),edges=new Set();
  for(const node of graph.nodes){
    const chosen=selection.get(node.id);
    if(!chosen)continue;
    for(const call of node.call_occurrences||[])if(chosen.has(labelKey('calls',call.label))&&call.target_id){
      ids.add(call.target_id);edges.add(JSON.stringify([node.id,call.target_id]));
    }
  }
  return {ids,edges};
}
export function callStatistics(graph,rootId,ownerId,label) {
  const nodes=new Map(graph.nodes.map(n=>[n.id,n]));
  const owner=nodes.get(ownerId),root=nodes.get(rootId)||owner;
  const selected=(owner?.call_occurrences||[]).filter(c=>c.label===label);
  const targets=new Set(selected.map(c=>c.target_id).filter(Boolean));
  const unresolved=selected.some(c=>!c.target_id)||!selected.length;
  const matches=c=>targets.has(c.target_id)||(unresolved&&!c.target_id&&c.label===label);
  const reachable=new Set(root?[root.id]:[]),pending=[...reachable];
  const next=new Map();
  for(const edge of graph.edges)if(edge.kind.toLowerCase()==='calls'){
    if(!next.has(edge.source))next.set(edge.source,[]);next.get(edge.source).push(edge.target);
  }
  while(pending.length){for(const id of next.get(pending.pop())||[])if(!reachable.has(id)){reachable.add(id);pending.push(id);}}
  const sites=[],seen=new Set();let complete=true;
  for(const id of reachable){
    const node=nodes.get(id);if(!node||!isFunction(node))continue;
    if(!Array.isArray(node.call_occurrences)){complete=false;continue;}
    for(const call of node.call_occurrences)if(matches(call)){
      const position=JSON.stringify([call.path,call.line,call.column]);
      if(!seen.has(position)){seen.add(position);sites.push({...call,ownerId:id,ownerName:node.name});}
    }
  }
  return {root,owner,label,targets:[...targets],unresolved,complete,
    direct:Array.isArray(root?.call_occurrences)?root.call_occurrences.filter(matches).length:null,
    total:sites.length,sites,functions:reachable.size};
}
