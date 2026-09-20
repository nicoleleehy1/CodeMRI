export const edgeKey = edge => JSON.stringify([edge.source,edge.target,edge.kind.toLowerCase()]);

export function reviewItems(changes={}) {
  return [...(changes.nodes||[]).map(n=>({...n,type:'node'})),...(changes.edges||[]).map(e=>({...e,type:'edge',id:e.source,name:`${e.kind}: ${e.source} → ${e.target}`}))];
}

export function changeHighlights(graph,changes={}) {
  const changed=new Set((changes.nodes||[]).flatMap(n=>[n.id,n.old_id].filter(Boolean)));
  const paths=new Set((changes.nodes||[]).map(n=>n.path));
  const changedEdges=new Set((changes.edges||[]).map(edgeKey));
  const allNodes=[...graph.nodes,...Object.values(graph.layers||{}).flatMap(l=>l.nodes||[])];
  for(const edge of changes.edges||[]) for(const id of [edge.source,edge.target]) {
    changed.add(id);const node=allNodes.find(n=>n.id===id);if(node?.path)paths.add(node.path);
  }
  for(const node of allNodes) if((node.paths||[]).some(p=>paths.has(p)) || (['repository','component','package','module','file'].includes(node.kind) && paths.has(node.path))) changed.add(node.id);
  return {changedIds:changed,changedEdges};
}

export function setupChat(document,post) {
  const $=id=>document.getElementById(id);
  const append=(role,text)=>{const item=document.createElement('div');item.className='chat-message '+role;const label=document.createElement('strong');label.textContent=role==='user'?'You':role==='error'?'Error':'Codex';const body=document.createElement('p');body.textContent=text;item.append(label,body);$('chatMessages').append(item);item.scrollIntoView?.({block:'nearest'});};
  const state=running=>{$('chatSend').disabled=running;$('chatStop').disabled=!running;$('chatPrompt').disabled=running;$('chatProgress').textContent=running?'Codex is working…':'Ready. Changes appear above the graph.';};
  $('chatForm').onsubmit=e=>{e.preventDefault();const prompt=$('chatPrompt').value.trim();if(!prompt)return;post({type:'chatSend',prompt});};
  $('chatStop').onclick=()=>{post({type:'chatStop'});$('chatProgress').textContent='Stopping and refreshing the graph…';};
  return m=>{
    if(m.type==='chat'){append(m.role,m.text);if(m.role==='user')$('chatPrompt').value='';}
    if(m.type==='chatState')state(m.running);
    if(m.type==='chatHistory'){$('chatMessages').replaceChildren();for(const item of m.messages)append(item.role,item.text);state(m.running);}
    if(m.type==='chatProgress')$('chatProgress').textContent=m.text;
  };
}

export function drawFileDiff(document,file) {
  const box=document.getElementById('diffLines');box.replaceChildren();
  document.getElementById('proposalDiff').hidden=!file;
  if(!file)return;
  document.getElementById('diffHeading').textContent=`${file.status} · ${file.path} · awaiting approval`;
  for(const line of file.lines||[]) {
    const row=document.createElement('div');row.className=`diff-line diff-${line.kind}`;
    if(line.kind==='hunk'){row.textContent=line.text;box.append(row);continue;}
    for(const [name,value] of [['old-line',line.old??''],['new-line',line.new??''],['diff-sign',line.kind==='added'?'+':line.kind==='removed'?'−':' '],['diff-code',line.text]]) {
      const cell=document.createElement('span');cell.className=name;cell.textContent=String(value);row.append(cell);
    }
    row.setAttribute('aria-label',`${line.kind} line ${line.new??line.old}: ${line.text}`);box.append(row);
  }
}
