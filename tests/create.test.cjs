const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {build}=require('esbuild');
let model;
test.before(async()=>{
  const out=path.join(fs.mkdtempSync(path.join(os.tmpdir(),'codemri-create-test-')),'model.cjs');
  await build({entryPoints:['apps/extension/src/create-model.ts'],bundle:true,platform:'node',format:'cjs',outfile:out});model=require(out);
});
const graph=()=>({root:'/repo',revision:'one',layers:{architecture:{nodes:[
  {id:'api',name:'API',kind:'component',summary:'Serve products',paths:['api.ts']},
  {id:'store',name:'Store',kind:'database_entity',summary:'Persist products',paths:['store.ts']}],
  edges:[{source:'api',target:'store',kind:'READS_FROM',label:'Read products'}]}}});
function proposal(){const g=graph(),d=model.newDesign(g);d.intent='Cache product reads';d.acceptance='Cache expires after five minutes and writes invalidate entries';d.nodes.push({id:'cache',name:'Cache',kind:'component',summary:'Cache products for five minutes',paths:[]});d.edges.push({id:'cache-read',source:'api',target:'cache',kind:'READS_FROM',label:'Read cached products before accessing Store'});return {g,d};}
test('draft isolates source, separates layout from intent, and scopes context to affected paths',()=>{
  const g=graph(),d=model.newDesign(g),original=JSON.stringify(g),key=model.designKey(d);
  d.positions.api={x:50,y:40};assert.equal(model.designKey(d),key);assert.equal(model.checkDesign(d,g).count,0);
  d.nodes[0].summary='New responsibility';assert.equal(JSON.stringify(g),original);assert.equal(d.baseline.nodes[0].summary,'Serve products');
  const {g:current,d:valid}=proposal(),check=model.checkDesign(valid,current);
  assert.deepEqual(check.errors,[]);assert.deepEqual(check.paths,['api.ts','store.ts']);assert.equal(check.count,2);
  const prompt=model.designPrompt(valid,'assess');assert.ok(prompt.includes('api.ts'));assert.ok(!prompt.includes('"positions"'));assert.match(prompt,/without editing files/);
});
test('validation blocks stale revisions, replaced architecture, dangling edges, and incomplete intent',()=>{
  const {g,d}=proposal();assert.match(model.checkDesign(d,{...g,revision:'two'}).errors.join(),/snapshot changed/);
  assert.match(model.checkDesign(d,g,true).errors.join(),/snapshot changed/);
  const replaced=graph();replaced.layers.architecture.nodes[0].name='Different API';assert.match(model.checkDesign(d,replaced).errors.join(),/baseline changed/);
  d.edges[1].target='missing';d.nodes[2].summary='';d.acceptance='';
  const errors=model.checkDesign(d,g).errors.join();assert.match(errors,/missing endpoint/);assert.match(errors,/responsibility/);assert.match(errors,/acceptance criteria/);
});
test('removing components or standalone relationships requires migration intent',()=>{
  const {g,d}=proposal();d.nodes=d.nodes.filter(n=>n.id!=='store');d.edges=d.edges.filter(e=>e.target!=='store');
  assert.match(model.checkDesign(d,g).errors.join(),/removal.*Store/);d.removalNotes.store='Move persistent products to another service';assert.deepEqual(model.checkDesign(d,g).errors,[]);
  const e=model.newDesign(g);e.intent='Stop reads';e.acceptance='Use cached reads';e.edges=[];
  assert.match(model.checkDesign(e,g).errors.join(),/removal of the READS_FROM/);e.removalNotes['baseline-edge-0']='Use an external product API';assert.deepEqual(model.checkDesign(e,g).errors,[]);
});
test('blank canvas is additive; malformed drafts fail at host boundary',()=>{
  const g=graph(),d=model.newDesign(g,true);assert.equal(model.designDiff(d).nodes.removed.length,0);
  assert.deepEqual(model.parseDesign(d),d);
  for(const value of [null,{}, {...d,nodes:[{}]}, {...d,positions:{bad:{x:Infinity,y:0}}}, {...d,edges:[{id:'x'}]}])assert.throws(()=>model.parseDesign(value));
  const duplicate=proposal().d;duplicate.nodes.push(duplicate.nodes[0]);assert.throws(()=>model.parseDesign(duplicate));
});
test('plan identity changes on behavior edits but not movement; comparison is explicitly tentative',()=>{
  const {g,d}=proposal(),key=model.designKey(d);d.positions.cache={x:400,y:0};assert.equal(model.designKey(d),key);
  d.edges[1].label='Use cache with fallback';assert.notEqual(model.designKey(d),key);
  assert.match(model.compareDesign(d,g).join(),/not matched/);assert.match(model.compareDesign(d,g).join(),/not acceptance-test results/);
  assert.match(model.designPrompt(d,'implement','Plan: add cache.ts'),/Plan: add cache.ts/);
});

let layout;
test.before(async()=>{
  const out=path.join(fs.mkdtempSync(path.join(os.tmpdir(),'codemri-routing-test-')),'layout.cjs');
  await build({entryPoints:['apps/extension/media/create-layout.js'],bundle:true,platform:'node',format:'cjs',outfile:out});layout=require(out);
});
const edge=(id,source,target,kind='CALLS')=>({id,source,target,kind});
function assertRoutesClear(nodes,edges,positions,result){
  assert.equal(result.routes.length,edges.length);
  for(const route of result.routes){
    assert.ok(route.points.length>=2,`Missing safe route for ${route.id}`);
    const e=edges.find(e=>e.id===route.id);
    const touches=(p,n)=>p.x>=n.x-4.001&&p.x<=n.x+224.001&&p.y>=n.y-4.001&&p.y<=n.y+94.001&&(Math.abs(p.x-n.x+4)<.001||Math.abs(p.x-n.x-224)<.001||Math.abs(p.y-n.y+4)<.001||Math.abs(p.y-n.y-94)<.001);
    assert.ok(touches(route.points[0],positions[e.source]),'Source attachment');
    assert.ok(touches(route.points.at(-1),positions[e.target]),'Target attachment stops outside the card');
    for(let i=1;i<route.points.length;i++){
      const a=route.points[i-1],b=route.points[i];
      assert.ok(a.x===b.x||a.y===b.y,`Diagonal segment on ${route.id}`);
      for(const node of nodes){const p=positions[node.id];assert.equal(layout.segmentHitsBox(a,b,{left:p.x-2,right:p.x+222,top:p.y-2,bottom:p.y+92}),false,`${route.id} overlaps ${node.id}`);}
    }
    if(route.label){const label=route.label;for(const node of nodes){const p=positions[node.id];assert.ok(label.x+label.width<=p.x||label.x>=p.x+220||label.y+label.height<=p.y||label.y>=p.y+90,`Label on ${route.id} overlaps ${node.id}`);}}
    const [x,y,w,h]=result.bounds;
    for(const p of route.points)assert.ok(p.x>=x&&p.y>=y&&p.x<=x+w&&p.y<=y+h,'Fit includes outer routes');
  }
}
test('orthogonal routes detour around intervening cards, including reverse edges and self loops',()=>{
  const nodes=['left','block','right','below'].map(id=>({id}));
  const positions={left:{x:0,y:0},block:{x:310,y:0},right:{x:620,y:0},below:{x:310,y:200}};
  const edges=[edge('forward','left','right'),edge('reverse','right','left'),edge('self','block','block'),edge('down','left','below'),edge('up','below','right')];
  const result=layout.routeCreate(nodes,edges,positions);
  assertRoutesClear(nodes,edges,positions,result);
  assert.ok(result.routes.find(r=>r.id==='forward').points.length>2);
  positions.block={x:100.0001,y:145.0001}; // Move an unrelated obstacle into an edge's possible channel.
  assertRoutesClear(nodes,edges,positions,layout.routeCreate(nodes,edges,positions));
});
test('dense saved-grid draft routes safely without requiring automatic arrangement',()=>{
  const nodes=Array.from({length:22},(_,i)=>({id:'n'+i}));
  const positions=Object.fromEntries(nodes.map((n,i)=>[n.id,{x:70+i%4*270,y:60+Math.floor(i/4)*150}]));
  const edges=nodes.slice(1).map((n,i)=>edge('e'+i,'n3',n.id));
  edges.push(edge('reverse','n20','n0'),edge('cycle','n0','n3'));
  assertRoutesClear(nodes,edges,positions,layout.routeCreate(nodes,edges,positions));
});
test('dependency arrangement uncrosses reversed input order and separates disconnected cards',async()=>{
  const nodes=['a','b','y','x','alone'].map(id=>({id}));
  const edges=[edge('ax','a','x'),edge('by','b','y')];
  const positions=await layout.arrangeCreate(nodes,edges);
  assert.equal(Object.keys(positions).length,nodes.length);
  for(const n of nodes)assert.equal(layout.canPlaceCard(n.id,positions[n.id],positions),true);
  assertRoutesClear(nodes,edges,positions,layout.routeCreate(nodes,edges,positions));
  const moved=layout.freeCardPosition('new',positions.a,positions);assert.equal(layout.canPlaceCard('new',moved,positions),true);
  assert.equal(layout.canPlaceCard('a',positions.b,positions),false);
});
test('routing never falls back to drawing through overlapping cards',()=>{
  const nodes=['a','b'].map(id=>({id})),positions={a:{x:0,y:0},b:{x:0,y:0}};
  const result=layout.routeCreate(nodes,[edge('blocked','a','b')],positions);
  assert.deepEqual(result.routes[0].points,[]);
});
