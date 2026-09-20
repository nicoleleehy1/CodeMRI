/** Pure hierarchy projections shared by navigation and tests. */
export function hierarchyView(graph, {level, component, moduleId, fileId, parentSymbol}) {
  const empty = {nodes:[],edges:[]};
  if (level === 'repository') return graph.layers?.repository || graph.layers?.architecture || empty;
  if (level === 'architecture') return graph.layers?.architecture || empty;
  if (level === 'modules' || level === 'files') {
    const layer = graph.layers?.[level === 'modules' ? 'packages' : 'files'] || empty;
    const parent = level === 'modules' ? component : moduleId;
    const nodes = layer.nodes.filter(n => !parent || n.parent === parent);
    return {nodes, edges:layer.edges, groups:[]};
  }
  const hierarchy = graph.layers?.hierarchy;
  if (!hierarchy) {
    return {nodes:graph.nodes.filter(n=>n.kind!=='module'),edges:graph.edges.filter(e=>e.kind!=='contains')};
  }
  const indexed = new Map(hierarchy.nodes.map(n=>[n.id,n]));
  const parent = parentSymbol || fileId;
  const nodes = hierarchy.nodes.filter(n => parent ? n.parent === parent : indexed.get(n.parent)?.kind === 'file');
  const ids = new Set(nodes.map(n=>n.id));
  return {nodes,edges:graph.edges.filter(e=>e.kind!=='contains'&&ids.has(e.source)&&ids.has(e.target)).map(e=>({...e,kind:e.kind.toUpperCase()}))};
}
export function isFunction(node) {
  return ['function','function_declaration','method_declaration','constructor_declaration','method_definition','function_expression','arrow_function'].includes(node.kind);
}

export function symbolLocation(graph, id) {
  const indexed = new Map((graph.layers?.hierarchy?.nodes||[]).map(n=>[n.id,n]));
  const result = {};
  let node=indexed.get(id), first=true;
  const visited=new Set();
  while(node&&!visited.has(node.id)) {
    visited.add(node.id);
    if(node.kind==='file')result.fileId=node.id;
    else if(node.kind==='package')result.moduleId=node.id;
    else if(node.kind==='component')result.component=node.id;
    else if(!first&&node.kind!=='repository'&&!result.parentSymbol)result.parentSymbol=node.id;
    first=false;node=indexed.get(node.parent);
  }
  return result;
}
