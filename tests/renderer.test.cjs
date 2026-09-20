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

test('symbol layout follows dependency depth, routes orthogonally and sizes label boxes',async()=>{
  const temp=fs.mkdtempSync(path.join(os.tmpdir(),'codemri-symbols-'));
  const output=path.join(temp,'symbols.cjs');
  await build({entryPoints:['apps/extension/media/symbol-renderer.js'],bundle:true,platform:'node',format:'cjs',outfile:output});
  const {layoutSymbols,drawSymbols}=require(output);
  const nodes=['a','b','c','d','isolated'].map(id=>({id,name:id,kind:'function',path:'test.ts',start_line:1,
    details:{parameters:['input: string'],variables:['value'],attributes:['name'],strings:['"hello"'],types:['string']}}));
  const edges=[['a','b'],['b','c'],['c','d'],['d','d']].map(([source,target])=>({source,target,kind:'CALLS'}));
  const layout=await layoutSymbols({nodes,edges:[...edges,{source:'missing',target:'a',kind:'CALLS'}]});
  const positioned=new Map(layout.children.map(n=>[n.id,n]));
  assert.equal(layout.children.length,5);
  assert.equal(new Set(['a','b','c','d'].map(id=>positioned.get(id).x)).size,4);
  assert.equal(layout.edges.length,4);
  for(const edge of layout.edges)for(const section of edge.sections){
    const points=[section.startPoint,...section.bendPoints||[],section.endPoint];
    for(let i=1;i<points.length;i++)assert.ok(points[i].x===points[i-1].x||points[i].y===points[i-1].y);
  }
  for(const a of layout.children)for(const b of layout.children)if(a.id!==b.id)
    assert.ok(a.x+a.width<=b.x||b.x+b.width<=a.x||a.y+a.height<=b.y||b.y+b.height<=a.y);
  class Element{constructor(tag){this.tag=tag;this.children=[];this.attrs={};}setAttribute(k,v){this.attrs[k]=v;}append(...nodes){this.children.push(...nodes);}replaceChildren(){this.children=[];}}
  global.document={createElementNS:(_,tag)=>new Element(tag)};
  const svg=new Element('svg');let activated,inspected;
  drawSymbols(svg,layout,{activate:n=>activated=n.id,inspect:e=>inspected=e.kind,selectedIds:new Set(['a']),affectedIds:new Set(),search:''});
  const flatten=n=>[n,...n.children.flatMap(flatten)];
  const items=flatten(svg);
  const boxes=items.filter(n=>n.attrs.class==='symbol-box');assert.equal(boxes.length,5);
  for(const box of boxes)assert.ok(Number(box.attrs.height)>200);
  for(const category of ['Parameters','Local Variables','Nested Functions','Calls','Return','Attributes','String Literals','Classes / Types'])assert.ok(items.some(n=>n.textContent===category));
  items.find(n=>n.attrs['aria-label']==='a').onclick();assert.equal(activated,'a');
  items.find(n=>n.attrs['aria-label']==='CALLS').onclick();assert.equal(inspected,'CALLS');
  delete global.document;
  const empty=await layoutSymbols({nodes:[],edges:[]});assert.equal(empty.children.length,0);
});

test('declaration chips stay within cards and other symbols retain architecture shapes', async()=>{
  const temp=fs.mkdtempSync(path.join(os.tmpdir(),'codemri-cards-'));
  const output=path.join(temp,'symbols.cjs');
  await build({entryPoints:['apps/extension/media/symbol-renderer.js'],bundle:true,platform:'node',format:'cjs',outfile:output});
  const {symbolCard}=require(output);
  const node={name:'A class with a longer descriptive name',kind:'class_declaration',details:{attributes:['key: string','value: Map<string, number>'],methods:['read(key: string): string','reallyLongMethod('+('parameter: string, '.repeat(20))+'): void']}};
  for(const card of [symbolCard(node),symbolCard({...node,kind:'interface_declaration'}),symbolCard({...node,kind:'function',details:{parameters:['first','second'],variables:['local'],nested:['inner'],returns:['a'.repeat(300)]}})]){
    assert.ok(card.rich);
    const chips=card.rows.flatMap(r=>r.chips);
    for(const chip of chips){assert.ok(chip.x>=0&&chip.x+chip.width<=card.width);assert.ok(chip.y+chip.height<card.height);}
    for(const a of chips)for(const b of chips)if(a!==b)assert.ok(a.x+a.width<=b.x||b.x+b.width<=a.x||a.y+a.height<=b.y||b.y+b.height<=a.y);
  }
  for(const kind of ['package','file','api_endpoint','database_entity','external','enum_declaration'])assert.equal(symbolCard({...node,kind}).rich,false);
});

test('hierarchy navigation preserves file/class/function ownership', async()=>{
  const temp=fs.mkdtempSync(path.join(os.tmpdir(),'codemri-hierarchy-'));
  const output=path.join(temp,'hierarchy.cjs');
  await build({entryPoints:['apps/extension/media/hierarchy-view.js'],bundle:true,platform:'node',format:'cjs',outfile:output});
  const {hierarchyView,symbolLocation}=require(output);
  const repository={id:'root',kind:'repository'},component={id:'component',kind:'component',parent:'root'},pkg={id:'package',kind:'package',parent:'component'},file={id:'file',kind:'file',parent:'package'},cls={id:'class',kind:'class_declaration',parent:'file'},method={id:'method',kind:'method_definition',parent:'class'},nested={id:'nested',kind:'function',parent:'method'};
  const graph={nodes:[cls,method,nested],edges:[],layers:{repository:{nodes:[repository,component],edges:[]},packages:{nodes:[pkg],edges:[]},files:{nodes:[file],edges:[]},hierarchy:{nodes:[repository,component,pkg,file,cls,method,nested]}}};
  const view=state=>hierarchyView(graph,state).nodes.map(n=>n.id);
  assert.deepEqual(view({level:'repository'}),['root','component']);
  assert.deepEqual(view({level:'modules',component:'component'}),['package']);
  assert.deepEqual(view({level:'files',moduleId:'package'}),['file']);
  assert.deepEqual(view({level:'symbols',fileId:'file'}),['class']);
  assert.deepEqual(view({level:'symbols',fileId:'file',parentSymbol:'class'}),['method']);
  assert.deepEqual(symbolLocation(graph,'method'),{parentSymbol:'class',fileId:'file',moduleId:'package',component:'component'});
});

test('Analyze result opens repository and supports drilldown and Back in the webview', async()=>{
  const vm=require('node:vm');
  const {createRequire}=require('node:module');
  const temp=fs.mkdtempSync(path.join(os.tmpdir(),'codemri-webview-'));
  const output=path.join(temp,'graph.cjs');
  await build({entryPoints:['apps/extension/media/graph.js'],bundle:true,platform:'node',format:'cjs',outfile:output});
  class Element {
    constructor(tag){this.tag=tag;this.children=[];this.attrs={};this.dataset={};this.value='';this.clientWidth=1100;this.clientHeight=620;}
    setAttribute(k,v){this.attrs[k]=String(v);}
    getAttribute(k){return this.attrs[k];}
    removeAttribute(k){delete this.attrs[k];}
    append(...nodes){this.children.push(...nodes);}
    before(){}
    querySelector(){return new Element("button");}
    replaceChildren(){this.children=[];}
    addEventListener(){}
  }
  const elements=new Map();
  const element=id=>{if(!elements.has(id))elements.set(id,new Element(id));return elements.get(id);};
  const sent=[];let message;
  const context={require:createRequire(output),module:{exports:{}},exports:{},console,setTimeout,clearTimeout,
    document:{querySelector:element,querySelectorAll:()=>[],getElementById:element,createElementNS:(_,tag)=>new Element(tag),createElement:tag=>new Element(tag)},
    window:{Error,Math,Date,Array,Object,JSON,RegExp,String,Number,Boolean,parseInt,parseFloat,isNaN,addEventListener:(type,fn)=>{if(type==='message')message=fn;}},acquireVsCodeApi:()=>({postMessage:m=>sent.push(m)})};
  vm.runInNewContext(fs.readFileSync(output,'utf8'),context);
  element('analyze').onclick();assert.equal(sent.at(-1).type,'generateAI');
  element('generateAI').onclick();assert.equal(sent.at(-1).type,'analyze');
  const repository={id:'root',kind:'repository',name:'Fixture',paths:[]};
  const component={id:'component',kind:'component',name:'Component',paths:['logic.ts'],parent:'root'};
  const pkg={id:'package',kind:'package',name:'Package',paths:['logic.ts'],parent:'component'};
  const file={id:'file',kind:'file',name:'logic.ts',path:'logic.ts',paths:['logic.ts'],parent:'package'};
  const cls={id:'class',kind:'class_declaration',name:'Store',path:'logic.ts',start_line:1,parent:'file',details:{methods:['run()']}};
  const method={id:'method',kind:'method_definition',name:'run',path:'logic.ts',start_line:2,parent:'class',details:{parameters:[],returns:['1']}};
  const endpoint={id:'endpoint',kind:'api_endpoint',name:'GET /items',parent:'root',evidence:[{path:'logic.ts',line:3}]};
  const graph={root:'/Fixture',revision:'test',warnings:[],inventory:{},nodes:[cls,method],edges:[],layers:{repository:{nodes:[repository,component,endpoint],edges:[],groups:[]},architecture:{nodes:[component,endpoint],edges:[],groups:[]},packages:{nodes:[pkg],edges:[]},files:{nodes:[file],edges:[]},hierarchy:{nodes:[repository,component,pkg,file,cls,method,endpoint]}}};
  const flatten=n=>[n,...n.children.flatMap(flatten)];
  async function node(name){
    for(let i=0;i<150;i++){
      const found=flatten(element('graph')).find(n=>n.attrs['aria-label']===name&&n.attrs.class?.includes('node'));
      if(found)return found;
      await new Promise(resolve=>setTimeout(resolve,20));
    }
    throw new Error(`Missing rendered node ${name}; status: ${element('status').textContent}`);
  }
  message({data:{type:'graph',graph}});
  assert.equal(element('layer').value,'repository');
  (await node('Component')).ondblclick();assert.equal(element('layer').value,'modules');
  assert.equal(element('mainNodePanel').hidden,false);
  assert.equal(element('mainNodeName').textContent,'Component');
  assert.equal(element('graphCanvas').attrs['data-main-node'],'open');
  assert.ok(flatten(element('mainNodeGraph')).some(n=>n.attrs['aria-label']==='Component'));
  assert.deepEqual(element('nodeClassification').children.map(n=>n.textContent),['Architecture','Module / package','Architecture component']);
  (await node('Package')).ondblclick();assert.equal(element('layer').value,'files');
  (await node('logic.ts')).ondblclick();assert.equal(element('layer').value,'symbols');
  (await node('Store')).ondblclick();
  (await node('run')).ondblclick();assert.equal(element('layer').value,'trace');
  await node('run');assert.deepEqual(sent.at(-1).id,'method');
  const messagesBeforeSelection=sent.length;
  (await node('run')).onclick();
  await new Promise(resolve=>setTimeout(resolve,400));
  assert.equal(sent.length,messagesBeforeSelection+1);
  assert.equal(sent.at(-1).type,'jump');assert.equal(sent.at(-1).id,'method');
  assert.equal(element('layer').value,'trace','Selecting the main node reveals source without drilling');
  assert.equal(element('mainNodeName').textContent,'run');
  assert.deepEqual(element('nodeClassification').children.map(n=>n.textContent),['Architecture','Module / package','File','Function · Method']);
  assert.deepEqual(element('functionPath').children.map(n=>n.children[0]?.textContent||n.textContent),['Fixture','Component','Package','logic.ts','Store','run']);
  message({data:{type:'select',id:'class'}});
  assert.equal(element('mainNodeName').textContent,'run','Editor selection must not replace the clicked main node');
  element('traceBack').onclick();await node('run');assert.equal(element('layer').value,'symbols');
  assert.equal(element('mainNodeName').textContent,'Store');
  element('traceBack').onclick();await node('Store');
  assert.match(element('breadcrumb').textContent,/Fixture \/ Component \/ Package \/ logic.ts/);
  element('traceBack').onclick();await node('logic.ts');assert.equal(element('layer').value,'files');
  assert.equal(element('mainNodeName').textContent,'Package');
  element('closeMainNode').onclick();
  assert.equal(element('mainNodePanel').hidden,true);
  assert.equal(element('functionCallCount').textContent,'No node selected');
  element('back').onclick();
  (await node('GET /items')).onclick();
  await new Promise(resolve=>setTimeout(resolve,400));
  assert.equal(element('layer').value,'repository','Single click must preserve graph depth');
  assert.equal(element('mainNodeName').textContent,'GET /items');
  assert.equal(sent.at(-1).type,'openEvidence');
  assert.equal(sent.at(-1).path,'logic.ts');assert.equal(sent.at(-1).line,3);
  assert.deepEqual(element('nodeClassification').children.map(n=>n.textContent),['Architecture','API endpoints']);
  assert.equal(element('functionCallCount').textContent,'0 incoming relationships');
  element('traceBack').onclick();
  assert.equal(element('mainNodePanel').hidden,true);
  element('search').value='run';element('search').oninput();
  assert.equal(element('searchResults').hidden,false);
  assert.equal(element('searchResults').children.length,1);
  assert.match(element('searchResults').children[0].textContent,/run.*logic.ts:2/);
  element('searchResults').children[0].onclick();
  await node('run');
  assert.equal(element('layer').value,'symbols');
  assert.equal(element('mainNodeName').textContent,'run');
  assert.equal(element('searchResults').hidden,true);
  assert.equal(sent.at(-1).path,'logic.ts');assert.equal(sent.at(-1).line,2);
  element('changeReview').scrollIntoView=()=>{};
  message({data:{type:'graph',graph,baseline:graph,changes:{nodes:[{id:'method',name:'run',path:'logic.ts',status:'modified'}],edges:[]}}});
  assert.equal(element('changeReview').hidden,false);
  element('changeNext').onclick();
  assert.equal(element('layer').value,'symbols');
  assert.equal(element('mainNodeName').textContent,'run');
  assert.ok((await node('run')).attrs.class.includes('code-changed'));
  assert.match(element('reviewLocation').textContent,/1 of 1/);
  element('reviewAccept').onclick();assert.equal(sent.at(-1).type,'reviewAccept');
  element('chatPrompt').value='Add a method';
  element('chatForm').onsubmit({preventDefault(){}});
  assert.equal(sent.at(-1).type,'chatSend');assert.equal(sent.at(-1).prompt,'Add a method');
  message({data:{type:'chatState',running:true}});assert.equal(element('chatSend').disabled,true);
  message({data:{type:'chat',role:'assistant',text:'<script>literal text</script>'}});
  assert.equal(element('chatMessages').children.at(-1).children[1].textContent,'<script>literal text</script>');
  message({data:{type:'chatState',running:false}});assert.equal(element('chatSend').disabled,false);
  message({data:{type:'graph',graph,baseline:graph,proposalId:'pending-1',changes:{nodes:[{id:'method',name:'run',path:'logic.ts',status:'modified'}],edges:[]},files:[{path:'logic.ts',status:'modified',lines:[{kind:'removed',old:2,new:null,text:'return 1;'},{kind:'added',old:null,new:2,text:'return 2;'}]}]}});
  assert.equal(element('reviewAccept').hidden,true);
  assert.equal(element('proposalActions').hidden,false);
  assert.equal(element('approveSelected').disabled,true);
  assert.equal(element('diffLines').children[0].className,'diff-line diff-removed');
  assert.equal(element('diffLines').children[1].children[2].textContent,'+');
  const checkbox=element('changeList').children[0].children[0].children[0];
  checkbox.checked=true;checkbox.onchange();
  assert.equal(element('approveSelected').disabled,false);
  element('approveSelected').onclick();
  assert.equal(sent.at(-1).action,'approve');assert.equal(sent.at(-1).proposalId,'pending-1');
  assert.deepEqual(Array.from(sent.at(-1).paths),['logic.ts']);
  message({data:{type:'proposalState',busy:false,error:'File changed'}});
  assert.equal(element('proposalError').textContent,'File changed');
  element('discardSelected').onclick();assert.equal(sent.at(-1).action,'discard');


});

test('function inspector counts call sites, renders source links and handles empty and old snapshots',async()=>{
  const temp=fs.mkdtempSync(path.join(os.tmpdir(),'codemri-inspector-'));
  const output=path.join(temp,'inspector.cjs');
  await build({entryPoints:['apps/extension/media/function-inspector.js'],bundle:true,platform:'node',format:'cjs',outfile:output});
  const {functionInspector,drawFunctionInspector}=require(output);
  const target={id:'target',kind:'function',name:'target',path:'target.ts',start_line:4,start_column:2};
  const caller={id:'caller',kind:'function',name:'caller',path:'caller.ts',start_line:1};
  const sites=[{path:'caller.ts',line:2,column:4,expression:'target()'},{path:'caller.ts',line:2,column:14,expression:'target()'}];
  const graph={root:'/repo',nodes:[target,caller],edges:[{source:'caller',target:'target',kind:'calls',call_sites:sites}],layers:{hierarchy:{nodes:[{id:'root',name:'repo'},{id:'file',name:'target.ts',path:'target.ts',parent:'root'},{...target,parent:'file'}]}}};
  const model=functionInspector(graph,'target');
  assert.equal(model.sites.length,2);assert.equal(model.callerCount,1);
  assert.deepEqual(model.trail.map(n=>n.name),['repo','target.ts','target']);
  class Element{constructor(tag){this.tag=tag;this.attrs={};this.children=[];}setAttribute(k,v){this.attrs[k]=v;}append(...nodes){this.children.push(...nodes);}replaceChildren(){this.children=[];this.textContent='';}}
  const elements=new Map(['functionPath','functionLocation','functionCallers','functionCallCount'].map(id=>[id,new Element(id)]));
  const document={getElementById:id=>elements.get(id),createElement:tag=>new Element(tag)};
  let sent;drawFunctionInspector(graph,'target',document,m=>sent=m);
  assert.equal(elements.get('functionCallCount').textContent,'2 call sites · 1 caller');
  const links=elements.get('functionCallers').children.map(li=>li.children[0]);
  assert.equal(links.length,2);assert.equal(links[1].attrs.href,'#');
  links[1].onclick({preventDefault(){}});assert.deepEqual(sent,{type:'openEvidence',path:'caller.ts',line:2,column:14});
  drawFunctionInspector(graph,'caller',document,()=>{});
  assert.equal(elements.get('functionCallCount').textContent,'0 call sites · 0 callers');
  graph.edges[0].call_sites=[];
  assert.equal(functionInspector(graph,'target').incomplete,true);
  drawFunctionInspector(graph,'missing',document,()=>{});
  assert.equal(elements.get('functionCallCount').textContent,'No node selected');
  assert.equal(elements.get('functionCallers').children.length,0);
});

test('main node types, cross-function click trails, aggregate callers and resource evidence',async()=>{
  const temp=fs.mkdtempSync(path.join(os.tmpdir(),'codemri-main-node-'));
  const output=path.join(temp,'inspector.cjs'),nodeOutput=path.join(temp,'node.cjs');
  await build({entryPoints:['apps/extension/media/function-inspector.js'],bundle:true,platform:'node',format:'cjs',outfile:output});
  await build({entryPoints:['apps/extension/media/node-inspector.js'],bundle:true,platform:'node',format:'cjs',outfile:nodeOutput});
  const {functionInspector,drawFunctionInspector}=require(output);
  const {classifyNode,visitNode}=require(nodeOutput);
  for(const [kind,category] of Object.entries({api_endpoint:'API endpoints',database_entity:'Database entities',event_queue:'Events / queues',external:'External services'}))assert.deepEqual(classifyNode({kind}),['Architecture',category]);
  assert.deepEqual(classifyNode({kind:'interface_declaration'}),['Architecture','Module / package','File','Interface']);
  const root={id:'root',kind:'repository',name:'repo'};
  const cls={id:'class',kind:'class_declaration',name:'Store',parent:'root'};
  const a={id:'a',kind:'function',name:'a',path:'store.ts',start_line:1,parent:'class'};
  const b={id:'b',kind:'function',name:'b',path:'store.ts',start_line:2,parent:'class'};
  const external={id:'caller',kind:'function',name:'caller',path:'client.ts',parent:'root'};
  const api={id:'api',kind:'api_endpoint',name:'GET /items',parent:'root',evidence:[{path:'server.ts',line:5}]};
  const component={id:'service',kind:'component',name:'Service',parent:'root'};
  const graph={root:'/repo',nodes:[cls,a,b,external],edges:[
    {source:'caller',target:'a',kind:'calls',call_sites:[{path:'client.ts',line:3,column:2,expression:'a()'}]},
    {source:'a',target:'b',kind:'calls',call_sites:[{path:'store.ts',line:1,column:10,expression:'b()'}]}
  ],layers:{hierarchy:{nodes:[root,cls,a,b,external,api,component]},architecture:{nodes:[api,component],edges:[{source:'service',target:'api',kind:'ROUTES_TO',label:'requests route',evidence:[{path:'client.ts',line:9}]}]}}};
  let trail=visitNode(graph,[],'a');trail=visitNode(graph,trail,'b');
  assert.deepEqual(trail,['root','class','a','b']);
  assert.deepEqual(visitNode(graph,trail,'b'),trail);
  assert.deepEqual(functionInspector(graph,'b',trail).trail.map(n=>n.name),['repo','Store','a','b']);
  assert.equal(functionInspector(graph,'class').sites.length,1,'Only calls entering the class, not calls within the class');
  assert.equal(functionInspector(graph,'b').sites[0].caller,'a');
  assert.equal(functionInspector(graph,'api').mode,'relationships');
  class Element{constructor(tag){this.tag=tag;this.attrs={};this.children=[];}setAttribute(k,v){this.attrs[k]=v;}append(...nodes){this.children.push(...nodes);}replaceChildren(){this.children=[];this.textContent='';}}
  const elements=new Map(['functionPath','functionLocation','functionCallers','functionCallCount'].map(id=>[id,new Element(id)]));
  const document={getElementById:id=>elements.get(id),createElement:tag=>new Element(tag)};
  let sent;drawFunctionInspector(graph,'api',document,m=>sent=m);
  assert.equal(elements.get('functionCallCount').textContent,'1 incoming relationship');
  const link=elements.get('functionCallers').children[0].children[1].children[0];
  link.onclick({preventDefault(){}});assert.deepEqual(sent,{type:'openEvidence',path:'client.ts',line:9,column:0});
});

test('call counts deduplicate recursive and converging subgraphs; sort and highlights preserve source order',async()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'codemri-calls-')),out=path.join(dir,'calls.cjs');
  await build({entryPoints:['apps/extension/media/call-analysis.js'],bundle:true,platform:'node',format:'cjs',outfile:out});
  const {callStatistics,orderedValues,orderKey,labelKey,callHighlights}=require(out);
  const call=(label,line,target_id)=>({label,path:'x.ts',line,column:0,target_id});
  const node=(id,calls)=>({id,name:id,kind:'function_declaration',call_occurrences:calls});
  const a=node('a',[call('Files.createTempDirectory',1),call('Files.createTempDirectory',2),call('b',3,'b')]);
  const b=node('b',[call('Files.createTempDirectory',4),call('c',5,'c')]);
  const c=node('c',[call('Files.createTempDirectory',6)]);
  const graph={nodes:[a,b,c],edges:[['a','b'],['a','c'],['b','c'],['c','a']].map(([source,target])=>({source,target,kind:'calls'}))};
  const stats=callStatistics(graph,'a','a','Files.createTempDirectory');
  assert.equal(stats.direct,2);assert.equal(stats.total,4);assert.equal(stats.unresolved,true);assert.equal(stats.complete,true);
  assert.equal(callStatistics(graph,'a','a','b').direct,1);
  for(const key of ['parameters','variables','nested','calls','returns','attributes','strings','types','methods']){
    a.details={[key]:['zeta','alpha']};
    assert.deepEqual(orderedValues(a,key,{[orderKey('a',key)]:'alphabetical'}),['alpha','zeta']);
    assert.deepEqual(orderedValues(a,key),['zeta','alpha']);
  }
  const highlighted=callHighlights(graph,new Map([['a',new Set([labelKey('calls','b')])]]));
  assert.deepEqual([...highlighted.ids],['b']);assert.deepEqual([...highlighted.edges],[JSON.stringify(['a','b'])]);
  delete c.call_occurrences;assert.equal(callStatistics(graph,'a','a','Files.createTempDirectory').complete,false);
});

test('double click cancels pending single selection and keyboard keeps selection distinct from drilldown',async()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'codemri-click-')),out=path.join(dir,'click.cjs');
  await build({entryPoints:['apps/extension/media/node-interactions.js'],bundle:true,platform:'node',format:'cjs',outfile:out});
  const {bindNodeInteractions}=require(out);let selected=0,drilled=0;const element={};
  bindNodeInteractions(element,{id:'main'},()=>selected++,()=>drilled++);
  element.onclick({detail:1});element.onclick({detail:2});element.ondblclick();
  await new Promise(resolve=>setTimeout(resolve,380));assert.equal(selected,0);assert.equal(drilled,1);
  element.onclick({detail:1});await new Promise(resolve=>setTimeout(resolve,380));assert.equal(selected,1);assert.equal(drilled,1);
  element.onkeydown({key:' ',preventDefault(){}});element.onkeydown({key:'Enter',preventDefault(){}});
  assert.equal(selected,2);assert.equal(drilled,2);
});

test('call chips expose badges, sort/select controls and scoped popup source links',async()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'codemri-chip-ui-'));
  await Promise.all(['symbol-renderer','call-popup'].map(name=>build({entryPoints:[`apps/extension/media/${name}.js`],bundle:true,platform:'node',format:'cjs',outfile:path.join(dir,name+'.cjs')})));
  const {layoutSymbols,drawSymbols}=require(path.join(dir,'symbol-renderer.cjs'));
  const {drawCallPopup}=require(path.join(dir,'call-popup.cjs'));
  class Element{constructor(tag){this.tag=tag;this.children=[];this.attrs={};}setAttribute(k,v){this.attrs[k]=v;}getAttribute(k){return this.attrs[k];}append(...nodes){this.children.push(...nodes);}replaceChildren(){this.children=[];}}
  const elements=new Map(),get=id=>{if(!elements.has(id))elements.set(id,new Element(id));return elements.get(id);};
  const document={getElementById:get,createElement:tag=>new Element(tag),createElementNS:(_,tag)=>new Element(tag)};
  global.document=document;
  const main={id:'main',name:'main',kind:'function_declaration',path:'x.ts',start_line:1,details:{calls:['Files.make']},call_occurrences:[{label:'Files.make',path:'x.ts',line:2,column:4},{label:'Files.make',path:'x.ts',line:3,column:8}]};
  const graph={nodes:[main],edges:[]},svg=new Element('svg');let label,order,all,activated=false,stopped=false;
  drawSymbols(svg,await layoutSymbols(graph),{activate:()=>activated=true,inspect(){},selectedIds:new Set(),affectedIds:new Set(),search:'',sortIcon:'sf-order.png',onLabel:(n,k,v)=>label={ownerId:n.id,key:k,value:v},onOrder:(n,k)=>order=k,onSelectCalls:n=>all=n.id});
  const flatten=n=>[n,...n.children.flatMap(flatten)],items=flatten(svg);
  assert.equal(items.find(n=>n.attrs.class==='call-count-text').textContent,'2');
  items.find(n=>n.attrs['data-label']==='Files.make').onclick({stopPropagation(){stopped=true;}});
  assert.equal(stopped,true);assert.equal(activated,false);assert.equal(label.value,'Files.make');
  items.find(n=>n.attrs['aria-label']==='Sort Calls: source order').onclick();assert.equal(order,'calls');
  items.find(n=>n.attrs['aria-label']==='Select all calls').onclick();assert.equal(all,'main');
  assert.ok(items.some(n=>n.tag==='image'&&n.attrs.href==='sf-order.png'));
  let sent;drawCallPopup(graph,'main',label,document,m=>sent=m);
  assert.equal(get('callPopup').hidden,false);assert.equal(get('callDirectCount').textContent,'2');assert.equal(get('callTotalCount').textContent,'2');
  get('callPopupSites').children[1].children[0].onclick({preventDefault(){}});
  assert.deepEqual(sent,{type:'openEvidence',path:'x.ts',line:3,column:8});
  drawCallPopup(graph,'main',undefined,document,()=>{});assert.equal(get('callPopup').hidden,true);
  delete global.document;
});

test('symbol search includes declarations and repeated call sites across files',async()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'codemri-search-')),out=path.join(dir,'search.cjs');
  await build({entryPoints:['apps/extension/media/symbol-search.js'],bundle:true,platform:'node',format:'cjs',outfile:out});
  const {searchSymbols}=require(out);
  const graph={nodes:[{id:'helper',name:'helper',path:'lib.ts',start_line:1,kind:'function'},
    {id:'main',name:'main',path:'main.ts',start_line:1,kind:'function',call_occurrences:[{label:'helper',path:'main.ts',line:2,column:1},{label:'helper',path:'main.ts',line:3,column:4}]}]};
  const matches=searchSymbols(graph,'HELPER');assert.equal(matches.length,3);
  assert.deepEqual(matches.map(r=>r.kind),['Definition','Call','Call']);
  assert.equal(matches[1].node.id,'main');assert.equal(searchSymbols(graph,'helper main.ts').length,2);
  assert.equal(searchSymbols(graph,'missing').length,0);assert.equal(searchSymbols(graph,' ').length,0);
});
