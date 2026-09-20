import { edgeKey } from './change-review.js';
import { bindNodeInteractions } from './node-interactions.js';
import ELK from 'elkjs/lib/elk.bundled.js';
const elk = new ELK();
const NS='http://www.w3.org/2000/svg';
const element=(tag,attrs={},text)=>{const n=document.createElementNS(NS,tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,String(v));if(text!==undefined)n.textContent=text;return n;};
const colors=['#6a9cff','#d9a447','#ed7998','#51baa0','#ad8ee6','#7fabb8'];
let cacheKey, cached;
export async function layoutSystem(layer){
  const key=JSON.stringify(layer);
  if(key===cacheKey)return cached;
  const groups=(layer.groups||[]).map((g,i)=>({id:'group-'+i,name:g.name,color:colors[i%colors.length],original:g.id,children:[]}));
  const fallback={id:'ungrouped',name:'System',color:colors[0],children:[]};
  for(const n of layer.nodes){const group=groups.find(g=>g.original===n.group)||fallback;group.children.push({id:n.id,width:220,height:n.shape==='circle'?100:84,original:n});}
  const children=[...groups,fallback].filter(g=>g.children.length).map(g=>({...g,layoutOptions:{'elk.padding':'[top=44,left=24,bottom=24,right=24]','elk.direction':'DOWN','elk.spacing.nodeNode':'40'}}));
  const graph={id:'root',layoutOptions:{'elk.algorithm':'layered','elk.direction':'DOWN','elk.hierarchyHandling':'INCLUDE_CHILDREN','elk.edgeRouting':'ORTHOGONAL','elk.layered.spacing.nodeNodeBetweenLayers':'75','elk.spacing.nodeNode':'55','elk.spacing.edgeNode':'25','elk.padding':'[top=25,left=25,bottom=25,right=25]'},children,
    edges:layer.edges.map((e,i)=>({id:'edge-'+i,sources:[e.source],targets:[e.target],labels:[{text:e.label||e.kind,width:Math.min(220,(e.label||e.kind).length*6.5),height:18}],original:e}))};
  const result=await elk.layout(graph);
  cacheKey=key;cached=result;return result;
}
function lines(text,limit=28){const result=[];let line='';for(const word of text.split(/\s+/)){if((line+' '+word).trim().length>limit&&line){result.push(line);line=word;}else line=(line+' '+word).trim();}if(line)result.push(line);return result.slice(0,3);}
export function drawSystem(svg,layout,{activate,inspect,selectedIds,affectedIds,search,renderNode,drill,highlightedIds=new Set(),highlightedEdges=new Set(),changedIds=new Set(),changedEdges=new Set(),markerId='sys-arrow'}){
  svg.replaceChildren();
  const defs=element('defs'),marker=element('marker',{id:markerId,viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:6,markerHeight:6,orient:'auto'});marker.append(element('path',{d:'M0 0 L10 5 L0 10 Z',fill:'#8294a9'}));defs.append(marker);svg.append(defs);
  const nodes=[], offsets=new Map([[layout.id,{x:0,y:0}]]);
  function collect(group,ox=0,oy=0){const x=ox+(group.x||0),y=oy+(group.y||0);offsets.set(group.id,{x,y});if(group.children){svg.append(element('rect',{x,y,width:group.width,height:group.height,rx:12,class:'system-group'}),element('text',{x:x+18,y:y+26,class:'system-group-title'},group.name));for(const child of group.children)collect(child,x,y);}else nodes.push({...group,x,y});}
  for(const group of layout.children)collect(group);
  function drawEdges(container,ox=0,oy=0){for(const e of container.edges||[]){const original=e.original;const origin=offsets.get(e.container)||{x:ox,y:oy};const ex=origin.x,ey=origin.y;const g=element('g',{class:'relationship'+(changedEdges.has(edgeKey(original))?' code-changed-edge':'')+(highlightedEdges.has(JSON.stringify([original.source,original.target]))?' call-highlight-edge':''),tabindex:0,role:'button','aria-label':original.label||original.kind});
      for(const section of e.sections||[]){const points=[section.startPoint,...(section.bendPoints||[]),section.endPoint];const d=points.map((p,i)=>`${i?'L':'M'} ${p.x+ex} ${p.y+ey}`).join(' ');g.append(element('path',{d,class:'edge '+(original.inferred?'inferred':''),'marker-end':section.outgoingShape===e.targets?.[0]||!section.outgoingSections?.length?`url(#${markerId})`:'none'}),element('path',{d,class:'edge-hit'}));}
      for(const label of e.labels||[]){g.append(element('text',{x:label.x+ex+label.width/2,y:label.y+ey+13,class:'system-edge-label','text-anchor':'middle'},label.text));}
      const click=()=>inspect(original);g.onclick=click;g.onkeydown=e=>{if(e.key==='Enter')click();};svg.append(g);}
    for(const child of container.children||[])if(child.children)drawEdges(child,ox+(child.x||0),oy+(child.y||0));}
  drawEdges(layout);
  for(const positioned of nodes){const n=positioned.original,tone=Math.max(0,layout.children.findIndex(g=>(g.children||[]).some(c=>c.id===n.id)))%6,w=positioned.width,h=positioned.height;const g=element('g',{transform:`translate(${positioned.x},${positioned.y})`,class:'node system-node'+(changedIds.has(n.id)?' code-changed':'')+(highlightedIds.has(n.id)?' call-highlight':'')+(selectedIds.has(n.id)?' selected':'')+(affectedIds.has(n.id)?' affected':'')+(search&&!`${n.name} ${n.summary} ${(n.paths||[]).join(' ')}`.toLowerCase().includes(search)?' dim':''),'data-tone':tone,tabindex:0,role:'button','aria-label':n.name});
    if(renderNode && renderNode(g,positioned)){
      bindNodeInteractions(g,n,activate,drill);svg.append(g);continue;
    }
    if(n.shape==='database'){g.append(element('path',{class:'system-shape',d:`M0 14 C0 -4 ${w} -4 ${w} 14 L${w} ${h-14} C${w} ${h+4} 0 ${h+4} 0 ${h-14} Z`}),element('ellipse',{class:'system-shape',cx:w/2,cy:14,rx:w/2,ry:14}));}
    else if(n.shape==='circle')g.append(element('ellipse',{class:'system-shape',cx:w/2,cy:h/2,rx:w/2,ry:h/2}));
    else if(n.shape==='hexagon')g.append(element('polygon',{class:'system-shape',points:`15,0 ${w-15},0 ${w},${h/2} ${w-15},${h} 15,${h} 0,${h/2}`}));
    else g.append(element('rect',{class:'system-shape',width:w,height:h,rx:n.shape==='document'?1:7}));
    const wrapped=lines(n.name);wrapped.forEach((line,i)=>g.append(element('text',{x:w/2,y:h/2-((wrapped.length-1)*8)+i*16-3,'text-anchor':'middle',class:'system-node-label'},line)));
    const meta=n.kind==='repository'?'repository':n.kind==='package'?`${n.paths?.length||0} files`:n.paths?.length?n.paths[0].split('/').pop():n.path?`${n.path.split('/').pop()}:${n.start_line||1}`:n.shape==='circle'?'external actor':'external resource';g.append(element('text',{x:w/2,y:h-13,'text-anchor':'middle',class:'meta'},meta.length>32?meta.slice(0,30)+'…':meta),element('title',{},n.summary||n.name));
    bindNodeInteractions(g,n,activate,drill);svg.append(g);
  }
}
