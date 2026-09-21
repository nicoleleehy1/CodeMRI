import ELK from 'elkjs/lib/elk.bundled.js';

export const CARD_WIDTH = 220;
export const CARD_HEIGHT = 90;
const CLEARANCE = 18;
const END_GAP = 4;
const EPS = .001;
const elk = new ELK();

/** Dependency ordering, rather than input order or a fixed number of columns. */
export async function arrangeCreate(nodes, edges) {
  const ids = new Set(nodes.map(n => n.id));
  const result = await elk.layout({
    id: 'create-layout',
    layoutOptions: {
      'elk.algorithm': 'layered',
      'elk.direction': 'RIGHT',
      'elk.edgeRouting': 'ORTHOGONAL',
      'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP',
      'elk.layered.thoroughness': '20',
      'elk.layered.layering.strategy': 'COFFMAN_GRAHAM',
      'elk.layered.layering.coffmanGraham.layerBound': String(Math.max(3,Math.ceil(Math.sqrt(nodes.length)))),
      'elk.randomSeed': '1',
      'elk.spacing.nodeNode': '70',
      'elk.spacing.edgeNode': '30',
      'elk.spacing.edgeEdge': '18',
      'elk.layered.spacing.nodeNodeBetweenLayers': '110',
      'elk.layered.spacing.edgeNodeBetweenLayers': '35',
      'elk.spacing.componentComponent': '100',
      'elk.padding': '[top=60,left=60,bottom=60,right=60]'
    },
    children: nodes.map(n => ({id:n.id, width:CARD_WIDTH, height:CARD_HEIGHT})),
    edges: edges.filter(e => ids.has(e.source) && ids.has(e.target)).map(e => ({
      id:e.id, sources:[e.source], targets:[e.target],
      labels:[{text:e.kind, width:Math.min(190,e.kind.length*6.5+12), height:20}]
    }))
  });
  return Object.fromEntries(result.children.map(n => [n.id, {x:n.x, y:n.y}]));
}

const box = (n, p, pad=0) => ({id:n.id, left:p.x-pad, right:p.x+CARD_WIDTH+pad, top:p.y-pad, bottom:p.y+CARD_HEIGHT+pad});
const intersects = (a,b) => a.left < b.right-EPS && a.right > b.left+EPS && a.top < b.bottom-EPS && a.bottom > b.top+EPS;
export function canPlaceCard(id, p, positions, gap=12) {
  const bounds=box({id},p,gap);
  return Object.entries(positions).every(([other,at]) => other===id || !intersects(bounds,box({id:other},at)));
}
/** Find an empty spot near a requested point without imposing a row/column count. */
export function freeCardPosition(id, desired, positions) {
  if(canPlaceCard(id,desired,positions))return desired;
  const candidates=Object.values(positions).flatMap(p => [
    {x:p.x+CARD_WIDTH+100,y:p.y}, {x:p.x-CARD_WIDTH-100,y:p.y},
    {x:p.x,y:p.y+CARD_HEIGHT+95}, {x:p.x,y:p.y-CARD_HEIGHT-95}
  ]).sort((a,b) => Math.hypot(a.x-desired.x,a.y-desired.y)-Math.hypot(b.x-desired.x,b.y-desired.y));
  return candidates.find(p=>canPlaceCard(id,p,positions)) || {x:Math.max(0,...Object.values(positions).map(p=>p.x))+CARD_WIDTH+100,y:desired.y};
}

/** Strict interior intersection; padded borders are valid routing channels. */
export function segmentHitsBox(a,b,r) {
  if(Math.abs(a.y-b.y)<EPS)return a.y>r.top+EPS && a.y<r.bottom-EPS && Math.max(a.x,b.x)>r.left+EPS && Math.min(a.x,b.x)<r.right-EPS;
  if(Math.abs(a.x-b.x)<EPS)return a.x>r.left+EPS && a.x<r.right-EPS && Math.max(a.y,b.y)>r.top+EPS && Math.min(a.y,b.y)<r.bottom-EPS;
  return true; // A diagonal is never an acceptable routing fallback.
}
const clear = (a,b,obstacles) => !obstacles.some(r=>segmentHitsBox(a,b,r));
const distance = (a,b) => Math.abs(a.x-b.x)+Math.abs(a.y-b.y);
const segments = points => points.slice(1).map((b,i)=>[points[i],b]);
function simplify(points) {
  const result=[];
  for(const p of points){
    if(result.length&&result.at(-1).x===p.x&&result.at(-1).y===p.y)continue;
    while(result.length>1){const a=result.at(-2),b=result.at(-1);
      if((a.x===b.x&&b.x===p.x&&(b.y-a.y)*(p.y-b.y)>=0) ||
         (a.y===b.y&&b.y===p.y&&(b.x-a.x)*(p.x-b.x)>=0))result.pop();else break;
    }
    result.push(p);
  }
  return result;
}
class Heap {
  items=[];
  push(value){let i=this.items.length;this.items.push(value);while(i){const parent=(i-1)>>1;if(this.items[parent].rank<=value.rank)break;this.items[i]=this.items[parent];i=parent;}this.items[i]=value;}
  pop(){const first=this.items[0],last=this.items.pop();if(this.items.length){let i=0;while(i*2+1<this.items.length){let child=i*2+1;if(child+1<this.items.length&&this.items[child+1].rank<this.items[child].rank)child++;if(this.items[child].rank>=last.rank)break;this.items[i]=this.items[child];i=child;}this.items[i]=last;}return first;}
}

// Penalize intersections and shared runs, while still allowing unavoidable crossings.
function congestion(a,b,used) {
  let cost=0;
  const horizontal=Math.abs(a.y-b.y)<EPS;
  for(const [c,d]of used){const otherHorizontal=Math.abs(c.y-d.y)<EPS;
    if(horizontal!==otherHorizontal){const h=horizontal?[a,b]:[c,d],v=horizontal?[c,d]:[a,b];
      // Include crossing at a grid vertex; otherwise the search could evade the penalty by splitting a segment there.
      if(v[0].x>=Math.min(h[0].x,h[1].x)-EPS&&v[0].x<=Math.max(h[0].x,h[1].x)+EPS&&h[0].y>=Math.min(v[0].y,v[1].y)-EPS&&h[0].y<=Math.max(v[0].y,v[1].y)+EPS)cost+=180;
    }else if(horizontal?Math.abs(a.y-c.y)<EPS:Math.abs(a.x-c.x)<EPS){const axis=horizontal?'x':'y';const overlap=Math.min(Math.max(a[axis],b[axis]),Math.max(c[axis],d[axis]))-Math.max(Math.min(a[axis],b[axis]),Math.min(c[axis],d[axis]));if(overlap>EPS)cost+=overlap*3+30;}
  }
  return cost;
}
function ports(node, edge, edges, positions) {
  const p=positions[node.id];
  const incident=edges.filter(e=>e.source===node.id||e.target===node.id);
  // Order ports toward their neighbors to avoid crossed fan-in/fan-out at a card.
  const fraction=axis=>{
    const ordered=[...incident].sort((a,b)=>{
      const other=e=>positions[e.source===node.id?e.target:e.source]?.[axis]||0;
      return other(a)-other(b)||a.id.localeCompare(b.id);
    });
    return (ordered.findIndex(e=>e.id===edge.id)+1)/(ordered.length+1);
  };
  const x=p.x+24+fraction('x')*(CARD_WIDTH-48),y=p.y+18+fraction('y')*(CARD_HEIGHT-36);
  return [
    {x:p.x-CLEARANCE,y,anchor:{x:p.x-END_GAP,y},dir:0,side:'west'},
    {x:p.x+CARD_WIDTH+CLEARANCE,y,anchor:{x:p.x+CARD_WIDTH+END_GAP,y},dir:0,side:'east'},
    {x,y:p.y-CLEARANCE,anchor:{x,y:p.y-END_GAP},dir:1,side:'north'},
    {x,y:p.y+CARD_HEIGHT+CLEARANCE,anchor:{x,y:p.y+CARD_HEIGHT+END_GAP},dir:1,side:'south'}
  ];
}

/** Multi-source Manhattan A* on channels around expanded card bounds. */
function routeEdge(from,to,obstacles,baseX,baseY,used) {
  if(!from.length||!to.length)return null;
  const sorted=values=>[...new Set(values)].sort((a,b)=>a-b);
  const xs=sorted([...baseX,...from.map(p=>p.x),...to.map(p=>p.x)]);
  const ys=sorted([...baseY,...from.map(p=>p.y),...to.map(p=>p.y)]);
  const nx=xs.length;
  const index=p=>ys.indexOf(p.y)*nx+xs.indexOf(p.x);
  const point=id=>({x:xs[id%nx],y:ys[Math.floor(id/nx)]});
  const targets=new Map(to.map(p=>[index(p),p]));
  const heuristic=p=>Math.min(...to.map(t=>distance(p,t)));
  const queue=new Heap(),best=new Map(),parents=new Map(),starts=new Map(),clearCache=new Map(),costCache=new Map();
  for(const p of from){const state=index(p)*2+p.dir,cost=distance(p.anchor,p);best.set(state,cost);starts.set(state,p);queue.push({state,cost,rank:cost+heuristic(p)});}
  let endState,goal,bestGoal=Infinity,visited=0;
  while(queue.items.length && visited++<50000){
    const current=queue.pop();if(current.rank>=bestGoal)break;
    if(current.cost!==best.get(current.state))continue;
    const id=Math.floor(current.state/2),dir=current.state%2,p=point(id),target=targets.get(id);
    if(target){const score=current.cost+distance(p,target.anchor)+(dir===target.dir?0:28);if(score<bestGoal){endState=current.state;goal=target;bestGoal=score;}}
    const x=id%nx,y=Math.floor(id/nx);
    for(const next of [x>0?id-1:-1,x+1<nx?id+1:-1,y>0?id-nx:-1,y+1<ys.length?id+nx:-1]){
      if(next<0)continue;
      const q=point(next),direction=p.y===q.y?0:1,state=next*2+direction;
      const key=id<next?`${id}:${next}`:`${next}:${id}`;
      if(!clearCache.has(key))clearCache.set(key,clear(p,q,obstacles));
      if(!clearCache.get(key))continue;
      if(!costCache.has(key))costCache.set(key,congestion(p,q,used));
      const cost=current.cost+distance(p,q)+(dir===direction?0:28)+costCache.get(key);
      if(cost>=(best.get(state)??Infinity))continue;
      best.set(state,cost);parents.set(state,current.state);queue.push({state,cost,rank:cost+heuristic(q)});
    }
  }
  if(endState===undefined)return null;
  const points=[goal.anchor];let state=endState;
  while(true){points.push(point(Math.floor(state/2)));if(!parents.has(state)){points.push(starts.get(state).anchor);break;}state=parents.get(state);}
  return simplify(points.reverse());
}

function edgeLabel(edge,points,cards,occupied) {
  const text=edge.kind.length>28?edge.kind.slice(0,27)+'…':edge.kind;
  const width=text.length*6.5+12,height=20;
  const ordered=segments(points).sort((a,b)=>distance(...b)-distance(...a));
  for(const [a,b]of ordered){
    const x=(a.x+b.x)/2,y=(a.y+b.y)/2;
    const candidates=a.y===b.y&&Math.abs(b.x-a.x)>width+12?
      [{x:x-width/2,y:y-25},{x:x-width/2,y:y+5}]:a.x===b.x&&Math.abs(b.y-a.y)>height+12?
      [{x:x+8,y:y-height/2},{x:x-width-8,y:y-height/2}]:[];
    for(const p of candidates){const bounds={left:p.x,right:p.x+width,top:p.y,bottom:p.y+height};
      if(![...cards,...occupied].some(r=>intersects(bounds,r))){occupied.push(bounds);return {...p,width,height,text};}
    }
  }
  return null; // Keep the full label in the accessible title, never print over a card.
}
let cachedKey,cachedResult;
export function routeCreate(nodes,edges,positions) {
  const key=JSON.stringify([nodes.map(n=>n.id),edges.map(e=>[e.id,e.source,e.target,e.kind]),positions]);
  if(key===cachedKey)return cachedResult;
  const cards=nodes.filter(n=>positions[n.id]).map(n=>box(n,positions[n.id]));
  const obstacles=cards.map(r=>({...r,left:r.left-CLEARANCE,right:r.right+CLEARANCE,top:r.top-CLEARANCE,bottom:r.bottom+CLEARANCE}));
  const byId=new Map(nodes.map(n=>[n.id,n]));
  const baseX=obstacles.flatMap(r=>[r.left-12,r.left,r.right,r.right+12]);
  const baseY=obstacles.flatMap(r=>[r.top-12,r.top,r.bottom,r.bottom+12]);
  const used=[],labels=[],routes=[];
  // Short relationships first leave predictable local channels; longer ones can go around them.
  const span=e=>positions[e.source]&&positions[e.target]?distance(positions[e.source],positions[e.target]):Infinity;
  for(const edge of [...edges].sort((a,b)=>span(a)-span(b)||a.id.localeCompare(b.id))){
    const source=byId.get(edge.source),target=byId.get(edge.target);
    if(!source||!target||!positions[source.id]||!positions[target.id])continue;
    let from=ports(source,edge,edges,positions),to=ports(target,edge,edges,positions);
    from=from.filter(p=>clear(p.anchor,p,obstacles.filter(r=>r.id!==source.id)));
    to=to.filter(p=>clear(p.anchor,p,obstacles.filter(r=>r.id!==target.id)));
    let points;
    if(source.id===target.id){
      // Try another exposed side if a moved neighboring card blocks a self-loop port.
      for(const port of [...from].sort((a,b)=>(a.side==='east'?-1:0)-(b.side==='east'?-1:0))){
        points=routeEdge([port],to.filter(p=>p.side!==port.side),obstacles,baseX,baseY,used);
        if(points)break;
      }
    }else points=routeEdge(from,to,obstacles,baseX,baseY,used);
    if(!points){routes.push({id:edge.id,points:[],label:null});continue;}
    used.push(...segments(points));
    routes.push({id:edge.id,points,label:edgeLabel(edge,points,cards,labels)});
  }
  const points=[...cards.flatMap(r=>[{x:r.left,y:r.top},{x:r.right,y:r.bottom}]),...routes.flatMap(r=>r.points),...labels.flatMap(r=>[{x:r.left,y:r.top},{x:r.right,y:r.bottom}])];
  const left=Math.min(0,...points.map(p=>p.x))-45,top=Math.min(0,...points.map(p=>p.y))-45;
  const right=Math.max(650,...points.map(p=>p.x))+45,bottom=Math.max(360,...points.map(p=>p.y))+45;
  cachedKey=key;cachedResult={routes,bounds:[left,top,right-left,bottom-top]};return cachedResult;
}
