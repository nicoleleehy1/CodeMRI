const test=require('node:test');
const assert=require('node:assert/strict');
const {build}=require('esbuild');
const path=require('node:path');
const fs=require('node:fs');
const os=require('node:os');

test('compound layout and SVG rendering preserve groups, shapes, edges and clicks',async()=>{
  const temp=fs.mkdtempSync(path.join(os.tmpdir(),'codemri-render-'));
  const output=path.join(temp,'renderer.cjs');
  await build({entryPoints:['apps/extension/media/system-renderer.js'],bundle:true,platform:'node',format:'cjs',outfile:output});
  const {layoutSystem,drawSystem}=require(output);
  const layer={groups:[{id:'access',name:'Access'},{id:'state',name:'State'}],nodes:[
    {id:'actor',name:'Browser',group:'access',shape:'circle',paths:[]},
    {id:'api',name:'API',group:'access',shape:'box',paths:['server.py']},
    {id:'db',name:'Store',group:'state',shape:'database',paths:[]}],
    edges:[{source:'actor',target:'api',label:'sends requests',kind:'ROUTES_TO',evidence:[]},{source:'api',target:'db',label:'reads keys',kind:'READS_FROM',evidence:[]}]};
  const layout=await layoutSystem(layer);
  assert.equal(layout.children.length,2);
  assert.equal(layout.edges.length,2);
  assert.ok(layout.width>0&&layout.height>0);
  class Element{constructor(tag){this.tag=tag;this.children=[];this.attrs={};}setAttribute(k,v){this.attrs[k]=v;}append(...nodes){this.children.push(...nodes);}replaceChildren(){this.children=[];}}
  global.document={createElementNS:(_,tag)=>new Element(tag)};
  const svg=new Element('svg');let activated,inspected;
  drawSystem(svg,layout,{activate:n=>activated=n.id,inspect:e=>inspected=e.kind,selectedIds:new Set(),affectedIds:new Set(),search:''});
  function flatten(n){return [n,...n.children.flatMap(flatten)];}
  const items=flatten(svg);
  assert.equal(items.filter(n=>n.attrs.class==='system-group').length,2);
  assert.ok(items.some(n=>n.tag==='ellipse'));
  items.find(n=>n.attrs['aria-label']==='API').onclick();assert.equal(activated,'api');
  items.find(n=>n.attrs['aria-label']==='reads keys').onclick();assert.equal(inspected,'READS_FROM');
  // ELK keeps nested edge coordinates relative to edge.container, even when
  // the edge object itself lives at the root. Assert rendered endpoints touch nodes.
  const bounds=new Map();
  function collect(n,ox=0,oy=0){const x=ox+(n.x||0),y=oy+(n.y||0);bounds.set(n.id,{x,y,w:n.width,h:n.height});for(const c of n.children||[])collect(c,x,y);}
  collect(layout);
  const onBoundary=(point,b)=>point[0]>=b.x-.01&&point[0]<=b.x+b.w+.01&&point[1]>=b.y-.01&&point[1]<=b.y+b.h+.01&&(Math.abs(point[0]-b.x)<.01||Math.abs(point[0]-b.x-b.w)<.01||Math.abs(point[1]-b.y)<.01||Math.abs(point[1]-b.y-b.h)<.01);
  for(const edge of layout.edges){
    const rendered=items.find(n=>n.attrs['aria-label']===edge.original.label);
    const paths=rendered.children.filter(n=>n.tag==='path'&&n.attrs.class.startsWith('edge '));
    const first=paths[0].attrs.d.match(/-?\d+(?:\.\d+)?/g).map(Number);
    const last=paths.at(-1).attrs.d.match(/-?\d+(?:\.\d+)?/g).map(Number);
    assert.ok(onBoundary(first.slice(0,2),bounds.get(edge.sources[0])),`source attachment: ${edge.id}`);
    assert.ok(onBoundary(last.slice(-2),bounds.get(edge.targets[0])),`target attachment: ${edge.id}`);
  }
  delete global.document;
});


test('function trace follows successive callees and terminates at leaves',async()=>{
  const temp=fs.mkdtempSync(path.join(os.tmpdir(),'codemri-trace-'));
  const output=path.join(temp,'trace.cjs');
  await build({entryPoints:['apps/extension/media/trace.js'],bundle:true,platform:'node',format:'cjs',outfile:output});
  const {traceView}=require(output);
  const graph={nodes:['entry','helper','leaf','unrelated'].map(id=>({id})),edges:[{source:'entry',target:'helper',kind:'calls'},{source:'helper',target:'leaf',kind:'calls'}]};
  assert.deepEqual(traceView(graph,'entry').nodes.map(n=>n.id),['entry','helper']);
  assert.deepEqual(traceView(graph,'helper').nodes.map(n=>n.id),['entry','helper','leaf']);
  assert.deepEqual(traceView(graph,'leaf').nodes.map(n=>n.id),['helper','leaf']);
});
