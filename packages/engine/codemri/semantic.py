"""GitDiagram-inspired AI synthesis with a validated, source-linked JSON graph.

Never runs automatically: the user invokes Generate AI architecture explicitly.
"""
import json
import os
import re
import time
from pathlib import Path
from typing import Literal
import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from .architecture import inventory

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Evidence(Strict):
    path: str
    line: int = Field(ge=1)
    quote: str = Field(max_length=240)  # exact text of the cited line; lets us verify and correct `line`
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


MAX_ATTEMPTS = 2  # first request plus one retry that sends validation feedback to the model
MAX_DIRECTORY_FILES = 300


def normalize_path(path):
    return re.sub(r'^(?:\./|/)+','',path.strip()).rstrip('/') if path else path


def directory_files(path, files):
    prefix=path.rstrip('/')+'/'
    return sorted(p for p in files if p.startswith(prefix))


def known_path(path, files):
    """An inventoried file, or a directory that contains at least one."""
    return path in files or bool(directory_files(path, files))


# Comment syntax by extension, so a citation cannot land on a comment. Unlisted file types
# (docs, markup, config, unfamiliar languages) only have to avoid blank and punctuation-only lines.
C_COMMENT=re.compile(r'^(?://|/\*|\*/|\*(?:\s|$))')
HASH_COMMENT=re.compile(r'^(?:#|"""|\'\'\')')
DASH_COMMENT=re.compile(r'^--')
COMMENT_SYNTAX={**{e:C_COMMENT for e in ('.java','.js','.jsx','.mjs','.cjs','.ts','.tsx','.mts','.cts','.go','.rs','.c','.h','.cc','.cpp','.hpp','.cs','.kt','.swift','.php','.scala','.dart')},
    **{e:HASH_COMMENT for e in ('.py','.rb','.sh','.yml','.yaml','.toml','.pl','.r','.ex','.tf')},
    **{e:DASH_COMMENT for e in ('.sql','.lua','.hs')}}
IMPORT_LINE=re.compile(r'^(?:import|from|using|use|require|package|#\s*include|(?:const|let|var)\s+\w+\s*=\s*require)\b')


def normalize_text(text):
    return re.sub(r'\s+',' ',text).strip()


def acceptable_line(path, text, kind):
    """Can this line serve as evidence for a relationship of this kind? Language-agnostic."""
    stripped=text.strip()
    if not stripped or re.fullmatch(r'[{}()\[\];,]+',stripped):
        return False
    syntax=COMMENT_SYNTAX.get(Path(path).suffix.lower())
    if syntax and syntax.match(stripped):
        return False
    # An import proves a dependency, not a call, read or write.
    return not (syntax and IMPORT_LINE.match(stripped) and kind not in {'IMPORTS','DEPENDS_ON'})


def cite(evidence, files, kind):
    """Verify a citation against the file and move it to where its quoted text really is.

    The model's line number is only a hint (it cannot count lines reliably). A citation survives
    only if its quote is found on an acceptable line; among several matches the closest to the
    hinted line wins. Returns None when the citation cannot be verified.
    """
    path=normalize_path(evidence.path)
    quote=normalize_text(evidence.quote.splitlines()[0]) if evidence.quote.strip() else ''
    if path not in files or len(quote)<6:
        return None
    lines=files[path].splitlines()
    hits=[n for n,text in enumerate(lines,1) if quote in normalize_text(text) and acceptable_line(path,text,kind)]
    if not hits:
        return None
    line=min(hits,key=lambda n:abs(n-evidence.line))
    return evidence.model_copy(update={'path':path,'line':line,'quote':normalize_text(lines[line-1])[:240]})


def repair_architecture(value, files):
    """Drop only unsupported claims; never invent replacements. Returns (graph, issues, repairs).

    Unresolvable node paths only drive navigation, so they are removed. Dangling edges and
    unverifiable citations are removed (an edge with no valid citation left is dropped).
    Structural faults (schema, duplicate ids, unknown groups) come back as issues for a retry.
    """
    try:
        result=Architecture.model_validate(value)
    except ValidationError as exc:
        return None,[f"{'.'.join(map(str,e['loc']))}: {e['msg']}" for e in exc.errors()[:8]],[]
    ids=[n.id for n in result.nodes]
    groups=[g.id for g in result.groups]
    issues=[f'Duplicate {label} id "{dup}".' for label,values in (('node',ids),('group',groups)) for dup in sorted({v for v in values if values.count(v)>1})]
    # An empty group means an ungrouped actor (the prompt asks for that); the renderer has a fallback group.
    issues+=[f'Node "{n.id}" uses unknown group "{n.group}"; groups are {groups}.' for n in result.nodes if n.group and n.group not in groups]
    if issues:
        return None,issues,[]
    repairs=[]
    nodes=[]
    for n in result.nodes:
        path=normalize_path(n.path)
        if path is not None and not known_path(path,files):
            repairs.append(f'Removed unknown path "{n.path}" from node "{n.id}".')
            path=None
        nodes.append(n.model_copy(update={'path':path}))
    edges=[]
    for e in result.edges:
        if e.source not in ids or e.target not in ids:
            repairs.append(f'Dropped edge {e.source} -> {e.target}: unknown endpoint.')
            continue
        good=[]
        for ev in e.evidence:
            found=cite(ev,files,e.kind)
            if found and found.line!=ev.line:
                repairs.append(f'Moved citation {found.path}:{ev.line} to line {found.line}, where its quoted text is.')
            if found:
                good.append(found)
        if not good:
            repairs.append(f'Dropped edge {e.source} -> {e.target}: no verifiable source citation.')
            continue
        if len(good)<len(e.evidence):
            repairs.append(f'Removed {len(e.evidence)-len(good)} unverifiable citation(s) from edge {e.source} -> {e.target}.')
        edges.append(e.model_copy(update={'evidence':good}))
    return result.model_copy(update={'nodes':nodes,'edges':edges}),[],repairs


def validate_architecture(value, files):
    result=Architecture.model_validate(value)
    ids=[n.id for n in result.nodes]
    groups=[g.id for g in result.groups]
    if len(set(ids))!=len(ids) or len(set(groups))!=len(groups):
        raise ValueError('Generated graph has duplicate identifiers')
    for n in result.nodes:
        if (n.group and n.group not in groups) or (n.path is not None and not known_path(n.path, files)):
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
        # Number the lines so the model reads line numbers instead of estimating them. The budget
        # counts the numbered text, and truncation stops at a line boundary when there is one.
        numbered='\n'.join(f'{n}| {text}' for n,text in enumerate(files[path].splitlines(),1))
        limit=min(16000,remaining)
        excerpt=numbered[:limit]
        if len(numbered)>limit and '\n' in excerpt:
            excerpt=excerpt[:excerpt.rfind('\n')]
        excerpts.append({'path':path,'partial':len(excerpt)<len(numbered),'source':excerpt})
        remaining-=len(excerpt)
    return {'file_tree':sorted(files),'source_files':excerpts,'coverage':{'sampled':len(excerpts),'total':len(files)}}


def provider_error(response):
    """Provider's own error message, truncated, with anything key-shaped redacted."""
    try:
        message=str(response.json().get('error',{}).get('message',''))
    except (ValueError, AttributeError):
        message=''
    return re.sub(r'sk-[A-Za-z0-9_\-*.]{4,}','sk-[redacted]',message)[:300]


def request_graph(key, model, messages):
    payload={'model':model,'store':False,'input':messages,
        'text':{'format':{'type':'json_schema','name':'codemri_architecture','strict':True,'schema':Architecture.model_json_schema()}}}
    try:
        response=httpx.post('https://api.openai.com/v1/responses',headers={'Authorization':'Bearer '+key},json=payload,timeout=180)
    except httpx.RequestError as exc:
        raise ValueError('Could not reach the AI provider; local graph has been preserved.') from exc
    if response.status_code!=200:
        detail=provider_error(response)
        raise ValueError(f'AI provider returned HTTP {response.status_code}'+(f': {detail}' if detail else '')+'. Check model access, key and quota. Local graph has been preserved.')
    body=response.json()
    raw=''.join(c.get('text','') for item in body.get('output',[]) for c in item.get('content',[]) if c.get('type')=='output_text')
    if body.get('status')!='completed' or not raw:
        raise ValueError('AI response was incomplete or refused. Local graph has been preserved.')
    return raw


def save_run_log(log):
    """Keep the last run's raw model output and validation outcome locally for debugging. Never contains the key."""
    try:
        directory=Path(os.environ.get('CODEMRI_CACHE','.codemri'))
        directory.mkdir(parents=True,exist_ok=True)
        (directory/'ai-last-run.json').write_text(json.dumps(log,indent=2))
    except OSError:
        pass


def synthesize(graph):
    key=(os.environ.get('OPENAI_API_KEY') or '').strip()
    model=(os.environ.get('CODEMRI_ARCHITECTURE_MODEL') or '').strip()
    missing=[name for name,value in (('OPENAI_API_KEY',key),('CODEMRI_ARCHITECTURE_MODEL',model)) if not value]
    if missing:
        raise ValueError(f'AI architecture is missing {" and ".join(missing)} in the backend environment (unset or empty). Restart the backend with --env-file .env after editing .env. Local analysis remains available. See README for setup.')
    files,_=inventory(Path(graph.root))
    if len(files)>3000:
        raise ValueError('AI prototype supports up to 3,000 inventoried files. Select a smaller repository root.')
    prompt=Path(__file__).with_name('prompts').joinpath('architecture.txt').read_text()
    messages=[{'role':'system','content':prompt},{'role':'user','content':json.dumps(context_payload(files))}]
    log={'model':model,'started':time.strftime('%Y-%m-%d %H:%M:%S'),'files':len(files),'attempts':[]}
    result=None
    try:
        for attempt in range(1,MAX_ATTEMPTS+1):
            raw=request_graph(key,model,messages)
            entry={'attempt':attempt,'raw':raw}
            log['attempts'].append(entry)
            try:
                value=json.loads(raw)
            except json.JSONDecodeError as exc:
                candidate,issues,repairs=None,[f'Output was not valid JSON: {exc.msg}'],[]
            else:
                candidate,issues,repairs=repair_architecture(value,files)
            entry.update(issues=issues,repairs=repairs)
            if candidate:
                result=validate_architecture(candidate.model_dump(),files)
                entry['accepted_edges']=[e.model_dump() for e in result.edges]
                break
            messages=messages+[{'role':'assistant','content':raw},
                {'role':'user','content':'Your previous graph was rejected. Fix every problem below and return the complete corrected graph.\n'+'\n'.join(issues)}]
        if not result:
            raise ValueError(f'AI graph failed validation after {MAX_ATTEMPTS} attempts: '+' | '.join(issues[:5])+'. Local graph has been preserved.')
    finally:
        save_run_log(log)
    nodes=[]
    for n in result.nodes:
        is_file=n.path in files
        paths=[n.path] if is_file else directory_files(n.path,files)[:MAX_DIRECTORY_FILES] if n.path else []
        nodes.append({'id':n.id,'name':n.name,'group':n.group,'role':n.group,'kind':'component' if n.path else 'external','shape':n.shape,'path':n.path,'paths':paths,'summary':n.summary,
            'evidence':[{'path':n.path,'line':1,'reason':'AI-selected implementation source; inspect to verify'}] if is_file else []})
    graph.layers['architecture']={'nodes':nodes,'edges':[dict(e.model_dump(),inferred=True) for e in result.edges],'groups':[g.model_dump() for g in result.groups],
        'mode':'ai','model':model,'explanation':result.explanation,'coverage':context_payload(files)['coverage'],
        'attempts':len(log['attempts']),'repairs':log['attempts'][-1]['repairs'][:20]}
    # One drilldown module per node. It lists every file the node covers (a directory expands to its files).
    modules=[]
    for n in nodes:
        if n['paths']:
            modules.append({'id':f"{n['id']}:module",'name':Path(n['path']).name+('' if n['path'] in files else '/'),'kind':'module','parent':n['id'],'paths':n['paths'],'summary':n['summary'],'evidence':n['evidence']})
    graph.layers['modules']={'nodes':modules,'edges':[]}
    for symbol in graph.nodes:
        parents=[n for n in nodes if symbol.path in n['paths']]
        if parents:
            symbol.component_id=parents[0]['id']
            symbol.module_id=f"{parents[0]['id']}:module"
    from .hierarchy import build_hierarchy
    return build_hierarchy(graph, files)
