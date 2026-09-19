"""GitDiagram-inspired AI synthesis with a validated, source-linked JSON graph.

Never runs automatically: the user invokes Generate AI architecture explicitly.
"""
import json
import os
from pathlib import Path
from typing import Literal
import httpx
from pydantic import BaseModel, ConfigDict, Field
from .architecture import inventory

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Evidence(Strict):
    path: str
    line: int = Field(ge=1)
    reason: str = Field(max_length=300)

class Group(Strict):
    id: str
    name: str = Field(max_length=80)

class Node(Strict):
    id: str
    name: str = Field(max_length=80)
    group: str
    path: str | None
    shape: Literal['box','database','circle','document','queue','hexagon']
    summary: str = Field(max_length=500)

class Edge(Strict):
    source: str
    target: str
    kind: Literal['CALLS','IMPORTS','READS_FROM','WRITES_TO','ROUTES_TO','IMPLEMENTS','TESTED_BY','DEPENDS_ON','MUTATES','RETURNS','SERVES','DISPATCHES']
    label: str = Field(max_length=72)
    evidence: list[Evidence] = Field(min_length=1, max_length=5)

class Architecture(Strict):
    explanation: str = Field(max_length=2000)
    groups: list[Group] = Field(max_length=10)
    nodes: list[Node] = Field(min_length=1, max_length=34)
    edges: list[Edge] = Field(max_length=48)


def validate_architecture(value, files):
    result=Architecture.model_validate(value)
    ids=[n.id for n in result.nodes]
    groups=[g.id for g in result.groups]
    if len(set(ids))!=len(ids) or len(set(groups))!=len(groups):
        raise ValueError('Generated graph has duplicate identifiers')
    for n in result.nodes:
        if n.group not in groups or (n.path is not None and n.path not in files):
            raise ValueError('Generated graph references an unknown group or source path')
    for edge in result.edges:
        if edge.source not in ids or edge.target not in ids:
            raise ValueError('Generated relationship has an unknown endpoint')
        for evidence in edge.evidence:
            if evidence.path not in files or evidence.line > len(files[evidence.path].splitlines()):
                raise ValueError('Generated relationship has an invalid source citation')
    return result


def context_payload(files):
    # Keep full file list and prioritized bounded excerpts. Report omissions honestly.
    ordered=sorted(files,key=lambda p:(0 if Path(p).name.lower()=='readme.md' else 2 if '/test/' in p or '/tests/' in p else 1,p))
    remaining=140000
    excerpts=[]
    for path in ordered:
        if remaining<=0:
            break
        excerpt=files[path][:min(16000,remaining)]
        excerpts.append({'path':path,'partial':len(excerpt)<len(files[path]),'source':excerpt})
        remaining-=len(excerpt)
    return {'file_tree':sorted(files),'source_files':excerpts,'coverage':{'sampled':len(excerpts),'total':len(files)}}


def synthesize(graph):
    key=os.environ.get('OPENAI_API_KEY')
    model=os.environ.get('CODEMRI_ARCHITECTURE_MODEL')
    if not key or not model:
        raise ValueError('AI architecture needs OPENAI_API_KEY and CODEMRI_ARCHITECTURE_MODEL in the backend environment. Local analysis remains available. See README for setup.')
    files,_=inventory(Path(graph.root))
    if len(files)>3000:
        raise ValueError('AI prototype supports up to 3,000 inventoried files. Select a smaller repository root.')
    prompt=Path(__file__).with_name('prompts').joinpath('architecture.txt').read_text()
    payload={'model':model,'store':False,'input':[{'role':'system','content':prompt},{'role':'user','content':json.dumps(context_payload(files))}],
        'text':{'format':{'type':'json_schema','name':'codemri_architecture','strict':True,'schema':Architecture.model_json_schema()}}}
    try:
        response=httpx.post('https://api.openai.com/v1/responses',headers={'Authorization':'Bearer '+key},json=payload,timeout=180)
    except httpx.RequestError as exc:
        raise ValueError('Could not reach the AI provider; local graph has been preserved.') from exc
    if response.status_code!=200:
        raise ValueError(f'AI provider returned HTTP {response.status_code}. Check model access, key and quota. Local graph has been preserved.')
    body=response.json()
    raw=''.join(c.get('text','') for item in body.get('output',[]) for c in item.get('content',[]) if c.get('type')=='output_text')
    if body.get('status')!='completed' or not raw:
        raise ValueError('AI response was incomplete or refused. Local graph has been preserved.')
    result=validate_architecture(json.loads(raw),files)
    nodes=[]
    for n in result.nodes:
        nodes.append({'id':n.id,'name':n.name,'group':n.group,'role':n.group,'kind':'component' if n.path else 'external','shape':n.shape,'paths':[n.path] if n.path else [],'summary':n.summary,
            'evidence':[{'path':n.path,'line':1,'reason':'AI-selected implementation source; inspect to verify'}] if n.path else []})
    graph.layers['architecture']={'nodes':nodes,'edges':[dict(e.model_dump(),inferred=True) for e in result.edges],'groups':[g.model_dump() for g in result.groups],
        'mode':'ai','model':model,'explanation':result.explanation,'coverage':context_payload(files)['coverage']}
    # Multiple conceptual responsibilities may share a source file. Preserve all drilldowns.
    modules=[]
    for n in nodes:
        for p in n['paths']:
            modules.append({'id':f"{n['id']}:module",'name':Path(p).name,'kind':'module','parent':n['id'],'paths':[p],'summary':n['summary'],'evidence':n['evidence']})
    graph.layers['modules']={'nodes':modules,'edges':[]}
    for symbol in graph.nodes:
        parents=[n for n in nodes if symbol.path in n['paths']]
        if parents:
            symbol.component_id=parents[0]['id']
            symbol.module_id=f"{parents[0]['id']}:module"
    return graph
