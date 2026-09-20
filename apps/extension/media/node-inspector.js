import { isFunction } from './hierarchy-view.js';
import { symbolCard, drawSymbols } from './symbol-renderer.js';

export function nodeIndex(graph) {
  // Hierarchy records retain parents; source records retain the complete symbol details.
  return new Map([...(graph.nodes||[]),...(graph.layers?.architecture?.nodes||[]),...(graph.layers?.hierarchy?.nodes||[])].map(n=>[n.id,n]));
}
export function nodeTrail(graph,id) {
  const indexed=nodeIndex(graph),trail=[],seen=new Set();
  let node=indexed.get(id);
  while(node&&!seen.has(node.id)){seen.add(node.id);trail.unshift(node);node=indexed.get(node.parent);}
  return trail;
}
export function classifyNode(node) {
  if(node.kind==='repository')return ['Repository'];
  const categories={api_endpoint:'API endpoints',database_entity:'Database entities',event_queue:'Events / queues',external:'External services',deployment:'Deployment'};
  if(categories[node.kind])return ['Architecture',categories[node.kind]];
  if(node.kind==='component')return ['Architecture','Module / package','Architecture component'];
  const labels={file:'File',class_declaration:'Class',record_declaration:'Class · Record',interface_declaration:'Interface',type_alias_declaration:'Type',enum_declaration:'Enum',constant:'Constant',global_variable:'Global variable'};
  const result=['Architecture','Module / package'];
  if(node.kind==='package'||node.kind==='module')return result;
  if(node.kind!=='file')result.push('File');
  result.push(isFunction(node)?node.kind==='constructor_declaration'||node.name==='constructor'?'Function · Constructor':node.kind.startsWith('method')?'Function · Method':'Function':labels[node.kind]||node.kind.replaceAll('_',' '));
  return result;
}
export function visitNode(graph,trail,id) {
  const indexed=nodeIndex(graph);
  const previous=trail.filter(key=>indexed.has(key));
  if(previous.at(-1)===id)return previous;
  // Seed the first click with its ancestry; subsequent clicks preserve the actual route.
  return previous.length?[...previous,id].slice(-100):nodeTrail(graph,id).map(n=>n.id);
}
export function drawMainNode(graph,id,document,openSource,options={}) {
  const node=nodeIndex(graph).get(id);
  const panel=document.getElementById('mainNodePanel');
  const canvas=document.getElementById('graphCanvas');
  const svg=document.getElementById('mainNodeGraph');
  panel.hidden=!node;canvas.setAttribute('data-main-node',node?'open':'closed');
  svg.replaceChildren();
  document.getElementById('mainNodeName').textContent=node?.name||'';
  const classification=document.getElementById('nodeClassification');classification.replaceChildren();
  if(!node){classification.textContent='Select a node to see its type and place in the hierarchy.';return;}
  for(const label of classifyNode(node)){const chip=document.createElement('span');chip.textContent=label;classification.append(chip);}
  const card=symbolCard(node,options.orders);
  const height=node.shape==='circle'?Math.max(card.height,100):card.height;
  const layout={id:'main-node',width:card.width+20,height:height+20,children:[{id:node.id,x:10,y:10,width:card.width,height,original:node,card}],edges:[]};
  svg.setAttribute('viewBox',`0 0 ${layout.width} ${layout.height}`);
  svg.setAttribute('aria-label',`Main node: ${node.name}`);
  svg.setAttribute('preserveAspectRatio','xMidYMin meet');
  drawSymbols(svg,layout,{activate:openSource,inspect(){},selectedIds:new Set([id]),affectedIds:new Set(),search:'',markerId:'main-node-arrow',...options});
  document.getElementById('mainNodeSummary').textContent=node.summary||`${node.kind.replaceAll('_',' ')}${node.path?' in '+node.path:''}`;
}
