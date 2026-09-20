/** Search indexed declarations and recorded call sites across every graph scope. */
export function searchSymbols(graph,query){
  const terms=query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if(!terms.length)return [];
  const results=[],seen=new Set();
  const add=(node,label,path,line,column,kind)=>{
    if(!path||!line)return;
    const text=`${label} ${path}`.toLowerCase();
    if(!terms.every(term=>text.includes(term)))return;
    const key=JSON.stringify([node.id,path,line,column,kind]);
    if(seen.has(key))return;seen.add(key);
    results.push({node,label,path,line,column:column||0,kind});
  };
  for(const node of graph.nodes){
    if(node.kind==='module')continue;
    add(node,node.signature||node.name,node.path,node.start_line,node.start_column,'Definition');
    for(const call of node.call_occurrences||[])add(node,`${call.label} in ${node.name}`,call.path,call.line,call.column,'Call');
  }
  return results.sort((a,b)=>a.path.localeCompare(b.path)||a.line-b.line||a.column-b.column);
}
