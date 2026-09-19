/** One-hop call neighborhood; clicking a callee changes the root to go deeper. */
export function traceView(graph, focus) {
  const calls=graph.edges.filter(e=>e.kind.toLowerCase()==='calls');
  const ids=new Set([focus]);
  for(const edge of calls)if(edge.source===focus||edge.target===focus){ids.add(edge.source);ids.add(edge.target);}
  return {nodes:graph.nodes.filter(n=>ids.has(n.id)),edges:calls.filter(e=>ids.has(e.source)&&ids.has(e.target)).map(e=>({...e,kind:'CALLS'}))};
}
