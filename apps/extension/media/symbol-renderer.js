import { orderedValues, callCount, labelKey, orderKey } from './call-analysis.js';
import { cancelNodeClick } from './node-interactions.js';
import ELK from 'elkjs/lib/elk.bundled.js';
import { drawSystem } from './system-renderer.js';
import { isFunction } from './hierarchy-view.js';
const elk = new ELK();
const functionCategories = [['parameters','Parameters'],['variables','Local Variables'],['nested','Nested Functions'],['calls','Calls'],['returns','Return'],['attributes','Attributes'],['strings','String Literals'],['types','Classes / Types']];
const classCategories = [['constructors','Constructors'],['attributes','Attributes'],['methods','Methods'],['extends','Extends / Implements']];
const richKinds = new Set(['class_declaration','interface_declaration','record_declaration']);
const NS = 'http://www.w3.org/2000/svg';
function element(tag, attrs, text) {
  const node = document.createElementNS(NS, tag);
  for (const [key,value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  if (text !== undefined) node.textContent = text;
  return node;
}
function wrap(value, width = 46) {
  const result = [];
  let rest = value.replace(/\s+/g, ' ');
  while (rest.length > width) {
    let cut = rest.lastIndexOf(' ', width);
    if (cut < width / 2) cut = width;
    result.push(rest.slice(0, cut));
    rest = rest.slice(cut).trimStart();
  }
  if (rest) result.push(rest);
  return result;
}
export function symbolCard(node, orders={}) {
  const rich = isFunction(node) || richKinds.has(node.kind);
  if (!rich) return {rich:false,width:220,height:84};
  const title = wrap(node.name, 32);
  const categories = isFunction(node) ? functionCategories : classCategories;
  const rows = [];
  let y = 78 + (title.length-1)*24;
  for (const [key, label] of categories) {
    const values = orderedValues(node,key,orders);
    const required = isFunction(node) ? ['parameters','variables','nested','calls','returns'].includes(key) : ['attributes','methods'].includes(key);
    if (!values.length && !required) continue;
    const chips = [];
    let x = 0, rowHeight = 0, chipY = y + 18;
    for (const value of values.length ? values : ['None']) {
      const full = String(value);
      const count=key==='calls'&&values.length?callCount(node,full):undefined;
      const radius=count===undefined?0:Math.max(10,String(count??'?').length*3.4);
      const badgeSpace=radius?radius*2+10:0;
      const lines = wrap(full, Math.floor((370-badgeSpace)/6.5));
      const visible = lines.length > 3 ? [...lines.slice(0,2), lines[2].slice(0,50)+'…'] : lines;
      const width = Math.min(390, Math.max(52, Math.max(...visible.map(line=>line.length))*6.5+20+badgeSpace));
      const height = Math.max(28, visible.length*15+12);
      if (x && x + width > 390) {x=0;chipY+=rowHeight+8;rowHeight=0;}
      chips.push({x:x+20,y:chipY,width,height,lines:visible,full,empty:!values.length,count,radius});
      x+=width+8;rowHeight=Math.max(rowHeight,height);
    }
    rows.push({key,label,order:orders[orderKey(node.id,key)]||'source',full:values.join(' · ')||'None',y,chips});
    y=chipY+rowHeight+27;
  }
  return {rich:true,title,rows,width:430,height:y+1};
}
let cacheKey, cached;
export async function layoutSymbols(layer, aspectRatio = 1.6, orders={}) {
  const key = JSON.stringify([layer, aspectRatio, orders]);
  if (cacheKey === key) return cached;
  const ids = new Set(layer.nodes.map(n => n.id));
  const result = await elk.layout({id:'symbols', layoutOptions:{
    'elk.algorithm':'layered', 'elk.direction':'RIGHT', 'elk.edgeRouting':'ORTHOGONAL',
    'elk.aspectRatio':String(aspectRatio), 'elk.separateConnectedComponents':'true',
    'elk.spacing.componentComponent':'65', 'elk.spacing.nodeNode':'45',
    'elk.layered.spacing.nodeNodeBetweenLayers':'100', 'elk.spacing.edgeNode':'25',
    'elk.padding':'[top=30,left=30,bottom=30,right=30]'
  }, children:layer.nodes.map(original => {
    const card = symbolCard(original,orders);
    return {id:original.id, width:card.width, height:card.height, original, card};
  }), edges:layer.edges.filter(e => ids.has(e.source) && ids.has(e.target)).map((original,i) => ({
    id:`symbol-edge-${i}`, sources:[original.source], targets:[original.target], original,
    labels:[{text:original.kind, width:original.kind.length*7, height:18}]
  }))});
  cacheKey = key; cached = result;
  return result;
}
export function drawSymbols(svg, layout, options) {
  drawSystem(svg, layout, {...options, renderNode(group, positioned) {
    const node = positioned.original, card = positioned.card;
    if (!card.rich) return false;
    group.setAttribute('class', group.getAttribute?.('class') ? group.getAttribute('class')+' detail-card' : 'node detail-card'+(options.selectedIds.has(node.id)?' selected':'')+(options.affectedIds.has(node.id)?' affected':'')+(options.search&&!`${node.name} ${node.path}`.toLowerCase().includes(options.search)?' dim':''));
    group.append(element('rect', {width:card.width, height:card.height, rx:10, class:'symbol-box'}));
    let y = 35;
    for (const line of card.title) {group.append(element('text', {x:20,y,class:'symbol-title'}, line)); y += 24;}
    group.append(element('text', {x:20,y:y-3,class:'symbol-location'}, `${node.kind.replaceAll('_',' ')} · ${node.path.split('/').pop()}:${node.start_line}`));
    for (const row of card.rows) {
      group.append(element('text', {x:20,y:row.y,class:'symbol-category'}, row.label));
      function control(x,width,label,action){
        const button=element('g',{class:'card-control',tabindex:0,role:'button','aria-label':label,transform:`translate(${x},${row.y-15})`});
        button.append(element('rect',{width,height:22,rx:4}),element('title',{},label));
        button.onclick=e=>{e?.stopPropagation?.();cancelNodeClick();action();};
        button.ondblclick=e=>{e?.stopPropagation?.();e?.preventDefault?.();cancelNodeClick();};
        button.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();e.stopPropagation();action();}};
        group.append(button);return button;
      }
      if(options.onOrder){
        const order=control(384,26,`Sort ${row.label}: ${row.order==='alphabetical'?'A to Z':'source order'}`,()=>options.onOrder(node,row.key,row.label));
        if(options.sortIcon)order.append(element('image',{href:options.sortIcon,x:4,y:2,width:18,height:18}));
        else order.append(element('text',{x:13,y:16,'text-anchor':'middle'},'↕'));
      }
      if(row.key==='calls'&&options.onSelectCalls&&!row.chips[0]?.empty){
        const all=row.chips.every(c=>options.selection?.get(node.id)?.has(labelKey('calls',c.full)));
        const button=control(294,82,all?'Clear selected calls':'Select all calls',()=>options.onSelectCalls(node));
        button.setAttribute('aria-pressed',String(all));button.append(element('text',{x:41,y:15,'text-anchor':'middle'},all?'Clear calls':'Select all'));
      }
      for (const chip of row.chips) {
        const chosen=options.selection?.get(node.id)?.has(labelKey(row.key,chip.full));
        const tag = element('g', {class:'symbol-chip'+(chip.empty?' empty-chip':'')+(chosen?' chip-selected':''),'data-label':chip.full});
        tag.append(element('rect',{x:chip.x,y:chip.y,width:chip.width,height:chip.height,rx:5}),element('title',{},chip.full));
        chip.lines.forEach((line,i)=>tag.append(element('text',{x:chip.x+10,y:chip.y+18+i*15,class:'symbol-value'},line)));
        if(chip.count!==undefined){
          const count=String(chip.count??'?'),cx=chip.x+chip.width-chip.radius-5,cy=chip.y+chip.height/2;
          tag.append(element('circle',{class:'call-count-badge',cx,cy,r:chip.radius}),element('text',{class:'call-count-text',x:cx,y:cy+3,'text-anchor':'middle'},count));
        }
        if(!chip.empty&&options.onLabel){
          tag.setAttribute('tabindex',0);tag.setAttribute('role','button');tag.setAttribute('aria-label',`${row.label}: ${chip.full}${chip.count!==undefined?`; ${chip.count??'unknown'} direct call sites`:''}`);tag.setAttribute('aria-pressed',String(Boolean(chosen)));
          const click=e=>{e?.stopPropagation?.();cancelNodeClick();options.onLabel(node,row.key,chip.full,row.label);};
          tag.onclick=click;tag.ondblclick=e=>{e?.stopPropagation?.();e?.preventDefault?.();cancelNodeClick();};
          tag.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();click(e);}};
        }
        group.append(tag);
      }
    }
    group.append(element('title', {}, `${node.signature || node.name}\n${node.path}:${node.start_line}\n` + card.rows.map(r=>`${r.label}: ${r.full}`).join('\n')));
    return true;
  }});
}
