import {arrangeCreate, routeCreate, canPlaceCard, freeCardPosition, CARD_WIDTH, CARD_HEIGHT} from './create-layout.js';
import {newDesign,parseDesign,designDiff,designKey,checkDesign,compareDesign} from '../src/create-model.ts';

/** Independent canvas: editing intent never mutates the observed graph. */
export function setupCreate(document,post) {
  const $=id=>document.getElementById(id);
  const button=document.createElement('button');button.id='createMode';button.textContent='Create';button.setAttribute('aria-pressed','false');document.querySelector('header').append(button);
  const panel=document.createElement('section');panel.id='createPanel';panel.hidden=true;
  panel.innerHTML=`<div class="create-heading"><div><small>ARCHITECTURE PROPOSAL</small><h2>Create your next change</h2></div><button id="createExit">Explore codebase</button></div>
    <p>Edit responsibilities and connections, then check and assess your proposal before implementation. Drafts save locally; source changes require file approval.</p>
    <div class="create-actions"><button id="createCurrent">New from current graph</button><button id="createBlank">New blank draft</button><button id="createUndo">Undo</button><button id="createRedo">Redo</button><button id="createArrange">Arrange graph</button><button id="createFit">Fit canvas</button></div>
    <div id="createReplace" hidden><p>Replace this saved draft? This clears its edits and assessment.</p><button id="createReplaceYes">Replace draft</button><button id="createReplaceNo">Keep draft</button></div>
    <p id="createStatus" role="status">Analyze the codebase to begin.</p>
    <div class="create-layout"><div><div class="create-actions"><button id="createAdd">+ Component</button><button id="createConnect" aria-pressed="false">Draw connection</button></div><p class="hint">Arrange graph to reduce crossings · Drag nodes to adjust · Select a node or arrow to edit · Draw connection: select source, then target · Scroll to zoom · Drag canvas to pan · Arrow keys move a selected node</p><svg id="createCanvas" viewBox="0 0 1100 650" role="group" aria-label="Editable architecture proposal"></svg><div id="createLegend">Green: added · Amber: modified · Removed items appear in the change list</div></div>
    <aside class="create-inspector"><h3 id="createSelection">Select a node or connection</h3><form id="createEdit" hidden><label id="createNameLabel">Name<input id="createName" maxlength="300"></label><label>Type<input id="createKind" maxlength="100" list="createKinds"></label><datalist id="createKinds"><option value="component"><option value="database_entity"><option value="api_endpoint"><option value="event_queue"><option value="external"><option value="CALLS"><option value="READS_FROM"><option value="WRITES_TO"><option value="PUBLISHES_TO"><option value="DEPENDS_ON"></datalist><label id="createDescriptionLabel">Responsibility / behavior<textarea id="createDescription" rows="5" maxlength="12000"></textarea></label><button type="submit">Save edit</button><button id="createDelete" type="button">Remove from proposed system</button></form><p id="createPaths"></p></aside></div>
    <div class="create-brief"><label>What should change?<textarea id="createIntent" rows="3" maxlength="12000" placeholder="Add a cache for product lookups. Preserve existing API responses…"></textarea></label><label>Acceptance criteria<textarea id="createAcceptance" rows="3" maxlength="12000" placeholder="Repeated lookups use the cache; entries expire after five minutes; writes invalidate cached values…"></textarea></label></div>
    <h3>Proposed changes</h3><div id="createDiff"></div>
    <div class="create-actions"><button id="createCheck">1 · Check locally (no tokens)</button><button id="createAssess">2 · Assess & plan with Codex</button><button id="createImplement" disabled>3 · Implement reviewed plan</button><button id="createStop" disabled>Stop Codex</button></div>
    <p class="hint">Assessment uses your local Codex login and tokens. It reads source in a temporary copy. Implementation produces file diffs for your approval.</p><div id="createChecks" role="status"></div><section id="createComparison" hidden><h3>Proposed code versus your design</h3><div id="createComparisonResults"></div><button id="createReviewFiles">Review proposed files</button></section><h3>Codex assessment and plan</h3><pre id="createPlan">Run an assessment after local checks pass.</pre>`;
  document.querySelector('main').before(panel);
  let graph,draft,stale=false,pending=false,active=false,running=false,selection,connecting=false,source,plan,saveTimer,replaceBlank,designRunning=false,layoutBusy=false,layoutTicket=0;
  let undo=[],redo=[],hidden=[],view=[0,0,1100,650],gesture;
  const svg=$('createCanvas'),ns='http://www.w3.org/2000/svg';
  const el=(tag,attrs={},text)=>{const node=document.createElementNS(ns,tag);for(const [k,v]of Object.entries(attrs))node.setAttribute(k,String(v));if(text!==undefined)node.textContent=text;return node;};
  const status=text=>$('createStatus').textContent=text;
  function save(){if(draft)post({type:'designSave',draft:structuredClone(draft)});}
  function checkpoint(){undo.push(structuredClone(draft));if(undo.length>60)undo.shift();redo=[];}
  function changed(redraw=true){save();$('createChecks').replaceChildren();$('createPlan').textContent=plan?.key===designKey(draft)?plan.text:'Proposal changed. Run a new assessment before implementation.';if(redraw)draw();else controls();}
  function controls(){const locked=!graph||pending||running||designRunning||layoutBusy;for(const id of ['createCurrent','createBlank','createAdd','createConnect','createCheck','createAssess','createArrange'])$(id).disabled=locked;
    $('createUndo').disabled=locked||!undo.length;$('createRedo').disabled=locked||!redo.length;
    $('createImplement').disabled=locked||!draft||plan?.key!==designKey(draft);
    $('createStop').disabled=!running&&!designRunning;
    for(const id of ['createIntent','createAcceptance','createName','createKind','createDescription','createDelete'])$(id).disabled=locked;
    $('createEdit').querySelector('button[type=submit]').disabled=locked;
    svg.setAttribute('aria-disabled',String(locked));
  }
  function position(n){return draft.positions[n.id];}
  async function arrange(force=false){
    if(!draft||layoutBusy)return;
    const requested=draft,ticket=++layoutTicket;
    layoutBusy=true;controls();status('Arranging components and reducing connection crossings…');
    try {
      const positions=await arrangeCreate(requested.nodes,requested.edges);
      if(ticket!==layoutTicket||draft!==requested)return;
      if(force)checkpoint();
      const placed=force?{}:Object.fromEntries(requested.nodes.filter(n=>requested.positions[n.id]).map(n=>[n.id,requested.positions[n.id]]));
      for(const n of requested.nodes)if(!placed[n.id])placed[n.id]=freeCardPosition(n.id,positions[n.id],placed);
      requested.positions=placed;save();
      layoutBusy=false;draw();fit();status('Graph arranged. Drag cards to adjust; arrows route around them.');
    }catch(error){status('Could not arrange this graph: '+error.message);}
    finally{if(ticket===layoutTicket){layoutBusy=false;controls();}}
  }
  function fit(){if(!draft||draft.nodes.some(n=>!position(n)))return;view=[...routeCreate(draft.nodes,draft.edges,draft.positions).bounds];svg.setAttribute('viewBox',view.join(' '));}
  function select(value){selection=value;const item=value?.type==='node'?draft.nodes.find(n=>n.id===value.id):draft.edges.find(e=>e.id===value?.id);$('createEdit').hidden=!item;
    $('createSelection').textContent=item?(value.type==='node'?item.name:'Edit connection'):'Select a node or connection';
    $('createNameLabel').hidden=value?.type==='edge';$('createName').value=item?.name||'';$('createKind').value=item?.kind||'';$('createDescription').value=value?.type==='node'?item?.summary||'':item?.label||'';
    $('createPaths').textContent=item?.paths?.length?'Source references: '+item.paths.join(', '):'';draw();}
  function chooseNode(id){if(connecting){if(!source){source=id;status('Select the target component.');draw();return;}checkpoint();const edge={id:'edge-'+crypto.randomUUID(),source,target:id,kind:'CALLS',label:''};draft.edges.push(edge);source=undefined;connecting=false;$('createConnect').setAttribute('aria-pressed','false');changed();select({type:'edge',id:edge.id});status('Describe what this connection does, then save the edit.');return;}select({type:'node',id});}
  function draw(){svg.replaceChildren();controls();if(!draft)return;
    if(draft.nodes.some(n=>!position(n))){svg.append(el('text',{x:40,y:70},'Arranging graph…'));void arrange();return;}
    const diff=designDiff(draft),added=new Set(diff.nodes.added.map(n=>n.id)),modified=new Set(diff.nodes.modified.map(n=>n.after.id));
    const defs=el('defs'),marker=el('marker',{id:'createArrow',viewBox:'0 0 10 10',refX:10,refY:5,markerWidth:8,markerHeight:8,markerUnits:'userSpaceOnUse',orient:'auto-start-reverse'});marker.append(el('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:'currentColor'}));defs.append(marker);svg.append(defs);
    const routing=routeCreate(draft.nodes,draft.edges,draft.positions);
    const routes=new Map(routing.routes.map(r=>[r.id,r]));
    for(const edge of draft.edges){const route=routes.get(edge.id);if(!route?.points.length)continue;
      const g=el('g',{class:'create-edge'+(selection?.id===edge.id?' selected':''),tabindex:0,role:'button','aria-label':`${edge.kind}: ${draft.nodes.find(n=>n.id===edge.source)?.name} to ${draft.nodes.find(n=>n.id===edge.target)?.name}`});
      const path=route.points.map((p,i)=>`${i?'L':'M'} ${p.x} ${p.y}`).join(' ');
      const changedEdge=diff.edges.added.some(e=>e.id===edge.id)?' added':diff.edges.modified.some(e=>e.after.id===edge.id)?' modified':'';
      g.append(el('path',{d:path,class:'create-edge-line'+changedEdge,'marker-end':'url(#createArrow)'}),el('path',{d:path,class:'create-edge-hit'}),el('title',{},edge.kind+(edge.label?' · '+edge.label:'')));
      if(route.label){const label=route.label;g.append(el('rect',{x:label.x,y:label.y,width:label.width,height:label.height,rx:3,class:'create-edge-label-bg'}),el('text',{x:label.x+label.width/2,y:label.y+14,'text-anchor':'middle'},label.text));}
      g.onclick=()=>select({type:'edge',id:edge.id});g.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select({type:'edge',id:edge.id});}};svg.append(g);
    }
    draft.nodes.forEach((node,i)=>{const p=position(node,i);const g=el('g',{transform:`translate(${p.x},${p.y})`,class:'create-node'+(added.has(node.id)?' added':modified.has(node.id)?' modified':'')+(selection?.id===node.id||source===node.id?' selected':''),'data-id':node.id,tabindex:0,role:'button','aria-label':`${node.name}, ${node.kind}. Drag or use arrow keys to move.`});
      g.append(el('rect',{width:CARD_WIDTH,height:CARD_HEIGHT,rx:12}),el('text',{x:14,y:24,class:'create-node-kind'},node.kind.slice(0,27)),el('text',{x:14,y:49,class:'create-node-name'},node.name.length>26?node.name.slice(0,25)+'…':node.name),el('text',{x:14,y:72},node.summary.length>29?node.summary.slice(0,28)+'…':node.summary||'Describe responsibility…'));
      g.onkeydown=e=>{if(running||pending||designRunning||layoutBusy)return;if(e.key==='Enter'||e.key===' '){e.preventDefault();chooseNode(node.id);}if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();checkpoint();const next={x:p.x+(e.key==='ArrowLeft'?-20:e.key==='ArrowRight'?20:0),y:p.y+(e.key==='ArrowUp'?-20:e.key==='ArrowDown'?20:0)};if(canPlaceCard(node.id,next,draft.positions))draft.positions[node.id]=next;changed();svg.querySelector(`[data-id="${CSS.escape(node.id)}"]`)?.focus();}};svg.append(g);
    });
    if(!draft.nodes.length)svg.append(el('text',{x:60,y:100},'Add your first component to sketch an additive change.'));
    drawDiff(diff);
    const unrouted=routing.routes.filter(r=>!r.points.length).length;if(unrouted)status(`${unrouted} connection(s) need more space. Use Arrange graph or move the cards apart.`);
  }
  function drawDiff(diff){const box=$('createDiff');box.replaceChildren();
    for(const [type,items]of Object.entries(diff))for(const action of ['added','modified','removed'])for(const entry of items[action]){const n=entry.after||entry;const row=document.createElement('div');row.className='create-diff-row';const text=document.createElement('span');text.textContent=`${action} ${type==='nodes'?'component':'connection'} · ${n.name||`${draft.baseline.nodes.concat(draft.nodes).find(v=>v.id===n.source)?.name||n.source} → ${draft.baseline.nodes.concat(draft.nodes).find(v=>v.id===n.target)?.name||n.target} (${n.kind})`}`;row.append(text);
      if(action==='removed'){const label=document.createElement('label');label.textContent='Removal / migration intent';const input=document.createElement('textarea');input.rows=2;input.maxLength=12000;input.value=draft.removalNotes[n.id]||'';input.disabled=running||pending||designRunning;input.onchange=()=>{checkpoint();draft.removalNotes[n.id]=input.value;changed(false);};label.append(input);row.append(label);}box.append(row);}
    if(!box.children.length)box.textContent='No code changes proposed. Layout changes are saved separately.';
  }
  function checks(){if(!draft||!graph)return;const result=checkDesign(draft,graph,stale);const box=$('createChecks');box.replaceChildren();for(const text of [...result.errors.map(v=>'Needs attention: '+v),...result.warnings.map(v=>'Note: '+v),`Potentially affected source: ${result.paths.join(', ')||'No existing file mapping; agent must inspect the repository.'}`]){const p=document.createElement('p');p.textContent=text;box.append(p);}status(result.errors.length?`${result.errors.length} issue(s) to resolve.`:'Local checks passed. Ready for a Codex assessment; feasibility is not yet established.');return result;}
  function replace(blank){layoutTicket++;layoutBusy=false;checkpoint();draft=newDesign(graph,blank);selection=undefined;plan=undefined;undo=[];redo=[];$('createIntent').value='';$('createAcceptance').value='';$('createPlan').textContent='Run an assessment after local checks pass.';changed();select(undefined);fit();status(blank?'Blank draft: additions only; existing components are preserved.':'Draft created from the current architecture.');}
  function toggle(on){active=on;panel.hidden=!on;button.setAttribute('aria-pressed',String(on));if(on){hidden=[...document.querySelectorAll('body > main, body > section')].filter(n=>n!==panel).map(n=>[n,n.hidden]);for(const[n]of hidden)n.hidden=true;if(!draft&&graph)replace(false);draw();fit();}else{for(const[n,value]of hidden)n.hidden=value;hidden=[];}}
  $('createReviewFiles').onclick=()=>toggle(false);
  button.onclick=()=>toggle(!active);$('createExit').onclick=()=>toggle(false);
  for(const[id,blank]of [['createCurrent',false],['createBlank',true]])$(id).onclick=()=>{if(!graph)return;if(draft){replaceBlank=blank;$('createReplace').hidden=false;}else replace(blank);};
  $('createReplaceYes').onclick=()=>{if(!running&&!pending&&!designRunning)replace(replaceBlank);$('createReplace').hidden=true;};$('createReplaceNo').onclick=()=>$('createReplace').hidden=true;
  $('createAdd').onclick=()=>{checkpoint();const node={id:'draft-'+crypto.randomUUID(),name:'New component '+(draft.nodes.filter(n=>n.id.startsWith('draft-')).length+1),kind:'component',summary:'',paths:[]};draft.nodes.push(node);draft.positions[node.id]=freeCardPosition(node.id,{x:view[0]+80,y:view[1]+80},draft.positions);changed();fit();select({type:'node',id:node.id});$('createName').focus();};
  $('createConnect').onclick=()=>{connecting=!connecting;source=undefined;$('createConnect').setAttribute('aria-pressed',String(connecting));status(connecting?'Select the source component, then the target.':'Connection drawing cancelled.');};
  $('createEdit').onsubmit=e=>{e.preventDefault();if(!selection||running||pending||designRunning)return;checkpoint();const item=(selection.type==='node'?draft.nodes:draft.edges).find(n=>n.id===selection.id);if(!item)return;item.kind=$('createKind').value.trim();if(selection.type==='node'){item.name=$('createName').value.trim();item.summary=$('createDescription').value.trim();}else item.label=$('createDescription').value.trim();changed();select(selection);};
  $('createDelete').onclick=()=>{if(!selection)return;checkpoint();if(selection.type==='node'){draft.nodes=draft.nodes.filter(n=>n.id!==selection.id);delete draft.positions[selection.id];draft.edges=draft.edges.filter(e=>e.source!==selection.id&&e.target!==selection.id);}else draft.edges=draft.edges.filter(e=>e.id!==selection.id);changed();select(undefined);status('Removed from the proposal. Explain removal intent below; source remains unchanged.');};
  for(const[id,field]of [['createIntent','intent'],['createAcceptance','acceptance']])$(id).onchange=()=>{checkpoint();draft[field]=$(id).value;changed(false);};
  function travel(from,to){if(!from.length)return;to.push(structuredClone(draft));draft=from.pop();$('createIntent').value=draft.intent;$('createAcceptance').value=draft.acceptance;changed();select(undefined);}
  $('createUndo').onclick=()=>travel(undo,redo);$('createRedo').onclick=()=>travel(redo,undo);$('createArrange').onclick=()=>{void arrange(true);};$('createFit').onclick=fit;$('createCheck').onclick=checks;
  for(const[id,action]of [['createAssess','assess'],['createImplement','implement']])$(id).onclick=()=>{const result=checks();if(!result||result.errors.length)return;clearTimeout(saveTimer);post({type:'designRun',action,draft});};
  $('createStop').onclick=()=>post({type:'chatStop'});
  const point=e=>{const p=svg.createSVGPoint();p.x=e.clientX;p.y=e.clientY;return p.matrixTransform(svg.getScreenCTM().inverse());};
  svg.onpointerdown=e=>{if(e.button!==0||running||pending||designRunning||layoutBusy||!draft)return;const id=e.target.closest('[data-id]')?.getAttribute('data-id');if(!id&&e.target.closest('.create-edge'))return;const p=point(e);gesture={id,start:p,client:{x:e.clientX,y:e.clientY},origin:id?position(draft.nodes.find(n=>n.id===id),draft.nodes.findIndex(n=>n.id===id)):null,view:[...view],moved:false};svg.setPointerCapture(e.pointerId);};
  svg.onpointermove=e=>{if(!gesture)return;const p=point(e),g=gesture;if(!g.moved&&Math.hypot(e.clientX-g.client.x,e.clientY-g.client.y)<4)return;if(!g.moved&&g.id&&!connecting)checkpoint();g.moved=true;if(g.id&&!connecting){const next={x:g.origin.x+p.x-g.start.x,y:g.origin.y+p.y-g.start.y};if(canPlaceCard(g.id,next,draft.positions)){draft.positions[g.id]=next;draw();}}else if(!g.id){const matrix=svg.getScreenCTM();view[0]=g.view[0]-(e.clientX-g.client.x)/matrix.a;view[1]=g.view[1]-(e.clientY-g.client.y)/matrix.d;svg.setAttribute('viewBox',view.join(' '));}};
  svg.onpointerup=()=>{if(!gesture)return;const g=gesture;gesture=undefined;if(g.id&&!g.moved)chooseNode(g.id);else if(g.id&&!connecting)changed();};svg.onpointercancel=()=>{if(gesture?.moved&&gesture.id)changed();gesture=undefined;};
  svg.addEventListener('wheel',e=>{e.preventDefault();const factor=e.deltaY>0?1.1:.9;view[2]=Math.min(15000,Math.max(350,view[2]*factor));view[3]=Math.min(12000,Math.max(250,view[3]*factor));svg.setAttribute('viewBox',view.join(' '));},{passive:false});
  return m=>{
    if(m.type==='graph'){graph=m.graph;stale=Boolean(m.stale);pending=Boolean(m.proposalId);if(pending&&!draft){try{draft=m.design?parseDesign(m.design):newDesign(graph);plan=m.designPlan;}catch{draft=newDesign(graph);}}if(!pending){if(!draft||draft.root!==graph.root){layoutTicket++;layoutBusy=false;clearTimeout(saveTimer);draft=undefined;try{if(m.design)draft=parseDesign(m.design);}catch{status('Saved draft could not be loaded. Start a new draft.');}plan=m.designPlan;undo=[];redo=[];}if(!draft)draft=newDesign(graph);$('createIntent').value=draft.intent;$('createAcceptance').value=draft.acceptance;}
      $('createComparison').hidden=!(pending&&m.designComparison);if(pending&&draft&&m.designComparison){$('createComparisonResults').replaceChildren();for(const text of compareDesign(draft,graph)){const p=document.createElement('p');p.textContent=text;$('createComparisonResults').append(p);}}
      if(draft&&plan?.key===designKey(draft))$('createPlan').textContent=plan.text;
      status(pending?'Code changes are awaiting approval. Explore codebase to review the proposed file diffs.':draft.revision!==graph.revision?'The source snapshot changed. Your draft is preserved; reanalyze and start a new draft to reconcile it.':'Architecture draft ready. Edits do not change source files.');if(active){draw();fit();}}
    if(m.type==='designState'){designRunning=m.running;if(m.running)status('Checking the source snapshot…');controls();}
    if(m.type==='designPlanCleared'){plan=undefined;$('createPlan').textContent='Assessment in progress…';controls();}
    if(m.type==='designSaved'&&!running&&!designRunning&&!$('createChecks').children.length)status('Draft saved locally.');
    if(m.type==='designPlan'){plan=m.plan;$('createPlan').textContent=plan.text;status('Assessment complete. Review the plan and resolve any questions before implementing.');controls();}
    if(m.type==='designError'){status(m.message);}
    if(m.type==='sourceStale'){stale=true;status('Source changed. Reanalyze before assessing or implementing this draft.');}
    if(m.type==='chatState'||m.type==='chatHistory'){running=m.running;controls();if(active)draw();}
    if(m.type==='chatProgress'&&active)status(m.text);
  };
}
