"""Repository-specific offline system maps. Optional AI synthesis lives in semantic.py.

The Java adapter is source-pattern based, not a full Java type checker. Every
relationship includes a source citation and is marked inferred where applicable.
"""
from pathlib import Path
import re


def words(name):
    return re.sub(r'(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])', ' ', name)


def ev(path, content, offset, reason):
    return {'path': path, 'line': content[:offset].count('\n')+1, 'reason': reason}


def apply_system_map(graph, files, file_edges):
    old = graph.layers['architecture']
    nodes, edges, groups = {}, {}, {}
    assignment = {}
    runtime = {p:s for p,s in files.items() if Path(p).suffix in {'.java','.py','.ts','.tsx','.js','.jsx','.html','.vue','.svelte','.sql','.prisma','.go','.rs','.rb','.php','.cs'} and not re.search(r'(^|/)(test|tests|examples|fixtures)(/|$)|(?:Test|Spec)\.',p)}

    def add_node(key, name, group, paths, summary, shape='box', evidence=None):
        groups.setdefault(group, {'id':group,'name':group})
        nodes[key]={'id':key,'name':name[:80],'kind':'component' if paths else 'external','role':group,'group':group,'shape':shape,'paths':paths,'summary':summary[:500],'evidence':evidence or []}
        for p in paths:
            assignment[p]=key
        return key

    def edge(a,b,label,kind,evidence,inferred=True):
        if a==b or a not in nodes or b not in nodes:
            return
        key=(a,b,kind)
        value=edges.setdefault(key,{'source':a,'target':b,'kind':kind,'label':label,'evidence':[],'inferred':inferred})
        if label not in {'calls','imports'}:
            value['label']=label
        if evidence not in value['evidence']:
            value['evidence'].append(evidence)

    java = {}
    for path, source in runtime.items():
        if not path.endswith('.java'):
            continue
        match=re.search(r'\bpublic\s+(?:final\s+|abstract\s+)?(?:class|record|interface|enum)\s+(\w+)',source)
        if not match:
            continue
        name=match.group(1)
        # Suppress simple value records unless a material dependency needs them.
        if re.search(r'\bpublic\s+record\s', source):
            continue
        comments=re.findall(r'/\*\*(.*?)\*/',source[:match.start()],re.S)
        summary=re.sub(r'<[^>]+>|\{@[^}]+\}', '',re.sub(r'\s*\*\s*',' ',comments[-1])).strip() if comments else words(name)
        summary=re.sub(r'\s+',' ',summary)
        http=bool(re.search(r'HttpServer|@RestController|@Controller|ServerSocket',source))
        disk=bool(re.search(r'RandomAccessFile|FileChannel|FileOutputStream|FileInputStream|Files\.(?:write|newOutputStream|newInputStream|read|create)',source))
        memory=bool(re.search(r'(?:ConcurrentSkipListMap|TreeMap|HashMap)<',source))
        main=bool(re.search(r'public\s+static\s+void\s+main\s*\(',source))
        if http or main:
            group='Access & entry points'
        elif Path(path).parent.name.lower() in {'store','stores','service','services','engine','coordinator','orchestration'}:
            group=words(Path(path).parent.name).title()+' orchestration'
        elif re.search(r'append.only|write.ahead|recent writes|in.memory sorted',summary,re.I):
            group='Mutable state & durability'
        elif disk or re.search(r'compaction|sparse index|immutable',summary,re.I):
            group='Persistent storage & maintenance'
        else:
            group=words(Path(path).parent.name).title()+' orchestration'
        shape='database' if (disk or memory) and re.search(r'(Log|Table|Index|Cache|Buffer|Repository|Database|Storage)$',name) and not group.endswith('orchestration') and not http and not main else 'box'
        key='system:'+path
        add_node(key,words(name),group,[path],summary,shape,[ev(path,source,match.start(),'Public Java type; responsibility summarized from its documentation')])
        java.setdefault(name,[]).append((path,key,source))

    # Other languages keep source-specific boundaries rather than generic role boxes.
    for path, source in runtime.items():
        if path in assignment or path.endswith('.java'):
            continue
        old_module=next((n for n in graph.layers['modules']['nodes'] if path in n['paths']),None)
        parent=Path(path).parent.name
        name=words(Path(path).stem).replace('_',' ').title()
        if path.endswith('.html'):
            title=re.search(r'<title[^>]*>(.*?)</title>',source,re.S|re.I)
            name=re.sub(r'<[^>]+>','',title.group(1)).strip()[:60] if title else name+' page'
            headings=[re.sub(r'<[^>]+>','',m).strip() for m in re.findall(r'<h[1-3][^>]*>(.*?)</h[1-3]>',source,re.S|re.I)]
            summary='Rendered interface: '+', '.join(headings[:8]) if headings else 'HTML user interface'
            group='Access & entry points'
        else:
            summary=f'{path} — source component'
            group=words(parent).replace('_',' ').title() if parent not in {'.','src'} else 'Application'
        shape='database' if Path(path).suffix in {'.sql','.prisma'} else 'box'
        add_node('system:'+path,name,group,[path],summary,shape,[ev(path,source,0,'Source file implementing this component')])

    # Aggregate existing resolved imports/calls between the new source components.
    for item in file_edges:
        if item['source'] in assignment and item['target'] in assignment:
            edge(assignment[item['source']],assignment[item['target']],{'CALLS':'calls','IMPORTS':'imports','ROUTES_TO':'requests route'}.get(item['kind'],item['kind'].lower()),item['kind'],item['evidence'][0],item['inferred'])

    for name, entries in java.items():
        if len(entries)!=1:
            continue
        path, key, source=entries[0]
        # Mask comments so commented-out code cannot invent interactions.
        code=re.sub(r'/\*.*?\*/|//[^\n]*',lambda m:''.join('\n' if c=='\n' else ' ' for c in m.group()),source,flags=re.S)
        bindings={}
        for target, candidates in java.items():
            if len(candidates)!=1:
                continue
            target_key=candidates[0][1]
            bindings[target]={target_key}
            for binding in re.finditer(r'\b'+re.escape(target)+r'\s+(\w+)\s*(?=[=;,:\)])',code):
                bindings.setdefault(binding.group(1),set()).add(target_key)
        calls={}
        for call in re.finditer(r'\b(\w+)\s*\.\s*(\w+)\s*\(',code):
            targets=bindings.get(call.group(1),set())
            if len(targets)==1:
                target=next(iter(targets))
                if target!=key:
                    calls.setdefault(target,[]).append(call)
        for target, matches in calls.items():
            methods=list(dict.fromkeys(m.group(2) for m in matches))
            label=', '.join(methods[:3])+('…' if len(methods)>3 else '')
            for call in matches:
                edge(key,target,label,'CALLS',ev(path,source,call.start(),f'Typed receiver call {call.group(1)}.{call.group(2)}(); source-pattern resolution'))
        for constructor in re.finditer(r'\bnew\s+(\w+)\s*\(',code):
            entries=java.get(constructor.group(1),[])
            if len(entries)==1 and entries[0][1] not in calls:
                edge(key,entries[0][1],'initializes','DEPENDS_ON',ev(path,source,constructor.start(),f'Constructs {constructor.group(1)}'))
        for route in re.finditer(r'createContext\s*\(\s*"([^"]+)"\s*,\s*new\s+(\w+)',code):
            nodes[key].setdefault('endpoints',[]).append(route.group(1))
            nodes[key]['evidence'].append(ev(path,source,route.start(),f'HTTP route {route.group(1)} → {route.group(2)}'))
        if nodes[key].get('endpoints'):
            actor='actor:http-client'
            if actor not in nodes:
                add_node(actor,'HTTP client / browser','Access & entry points',[],'External caller of the declared HTTP API','circle')
            edge(actor,key,'sends requests','ROUTES_TO',nodes[key]['evidence'][-1])
        for asset in re.finditer(r'getResourceAsStream\s*\(\s*"([^"]+\.html)"',code):
            matches=[p for p in assignment if (p==asset.group(1).lstrip('/') or p.endswith(asset.group(1)))]
            if len(matches)==1:
                edge(key,assignment[matches[0]],'serves dashboard','SERVES',ev(path,source,asset.start(),f'Loads HTML resource {asset.group(1)}'))
        disk=re.search(r'Files\.(?:createDirectories|write\w*|read\w*|delete\w*|new\w*Stream)\s*\(|new\s+(?:RandomAccessFile|FileInputStream|FileOutputStream)\s*\(',code)
        if disk:
            disk_id='resource:filesystem'
            if disk_id not in nodes:
                add_node(disk_id,'Filesystem storage','Persistent storage & maintenance',[],'Files accessed through Java file APIs; physical deployment location is not verified.','database')
            edge(key,disk_id,'accesses files','DEPENDS_ON',ev(path,source,disk.start(),'Concrete Java filesystem operation; read/write direction is not fully classified'))

    # Keep explicit deployment/external systems without duplicating manifest boxes.
    for node in old['nodes']:
        if node['kind'] in {'deployment','external'}:
            copy=dict(node,group='External systems & deployment',shape='database' if node['role']=='Databases' else 'box')
            nodes[node['id']]=copy
            groups.setdefault(copy['group'],{'id':copy['group'],'name':copy['group']})
    for item in old['edges']:
        if item['source'] in nodes and item['target'] in nodes:
            edges[(item['source'],item['target'],item['kind'])]=dict(item,label=item['kind'].lower().replace('_',' '))
    # Hide redundant import wiring when a resolved call already establishes interaction.
    edges={k:e for k,e in edges.items() if e['kind']!='IMPORTS' or (e['source'],e['target'],'CALLS') not in edges}
    if not nodes:
        return
    modules=[]
    for path, component in assignment.items():
        modules.append({'id':'detail:'+path,'name':Path(path).name,'kind':'module','parent':component,'role':nodes[component]['group'],'paths':[path],'summary':'Implementation source','evidence':[ev(path,files[path],0,'Implementation file')]})
    for symbol in graph.nodes:
        if symbol.path in assignment:
            symbol.component_id=assignment[symbol.path]
            symbol.module_id='detail:'+symbol.path
    graph.layers['architecture']={'nodes':list(nodes.values()),'edges':list(edges.values()),'groups':list(groups.values()),'mode':'local-evidence','explanation':'Repository-specific source map. Java receiver relationships are pattern-based inferences; use AI architecture for semantic synthesis across languages.'}
    graph.layers['modules']={'nodes':modules,'edges':[dict(e,source='detail:'+e['source'],target='detail:'+e['target']) for e in file_edges if e['source'] in assignment and e['target'] in assignment]}
