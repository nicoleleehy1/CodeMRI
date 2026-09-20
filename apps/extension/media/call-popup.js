import { callStatistics } from './call-analysis.js';
import { isFunction } from './hierarchy-view.js';
export function drawCallPopup(graph,mainId,selection,document,postMessage){
  const popup=document.getElementById('callPopup');popup.hidden=!selection;
  if(!selection)return;
  const owner=graph.nodes.find(n=>n.id===selection.ownerId);
  if(!owner){popup.hidden=true;return;}
  const title=document.getElementById('callPopupTitle'),summary=document.getElementById('callPopupSummary'),sites=document.getElementById('callPopupSites'),metrics=document.getElementById('callMetrics');
  title.textContent=selection.value;sites.replaceChildren();metrics.hidden=selection.key!=='calls';
  const link=(label,site)=>{const a=document.createElement('a');a.setAttribute('href','#');a.textContent=label;a.onclick=e=>{e.preventDefault();postMessage({type:'openEvidence',path:site.path,line:site.line,column:site.column||0});};return a;};
  if(selection.key!=='calls'){
    summary.textContent=`${selection.category} in ${owner.name}`;
    const row=document.createElement('li');row.append(link(`${owner.path}:${owner.start_line}`,{path:owner.path,line:owner.start_line,column:owner.start_column}));sites.append(row);return;
  }
  const main=graph.nodes.find(n=>n.id===mainId);
  const stats=callStatistics(graph,isFunction(main||{})?main.id:owner.id,owner.id,selection.value);
  document.getElementById('callDirectCount').textContent=stats.direct===null?'Reanalyze':String(stats.direct);
  document.getElementById('callTotalCount').textContent=(stats.complete?'':'At least ')+stats.total;
  document.getElementById('callScopeName').textContent=stats.root?.signature||stats.root?.name||owner.name;
  summary.textContent=`Source occurrences counted once per location. ${stats.unresolved?'Unresolved targets match the exact call label.':'Resolved function targets are matched across receiver names.'} Subgraphs follow resolved calls; dynamic or unresolved subgraphs are not traversed.${stats.complete?'':' Reanalyze to refresh missing occurrence data.'}`;
  for(const site of stats.sites){const row=document.createElement('li');row.append(link(`${site.ownerName} · ${site.path}:${site.line}:${site.column+1}`,site));sites.append(row);}
  if(!stats.sites.length){const row=document.createElement('li');row.textContent='No matching recorded occurrences in this scope.';sites.append(row);}
}
