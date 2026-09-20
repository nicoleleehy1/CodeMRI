"""Evidence-backed, language-independent system inventory and layered projections.

Architecture classification is heuristic. Edges retain source evidence and never
claim that declared dependencies were observed executing at runtime.
"""
from pathlib import Path
import ast
import hashlib
import json
import os
import re
import tomllib
import yaml

SKIP = {'node_modules', '.git', '.venv', 'venv', 'dist', 'build', 'coverage', '.next', '.codemri', '.codemri-preview', '__pycache__', '.pytest_cache', 'target', 'vendor'}
SOURCE = {'.ts', '.tsx', '.js', '.jsx', '.mts', '.cts', '.py', '.go', '.rs', '.java', '.kt', '.cs', '.rb', '.php', '.vue', '.svelte', '.sql', '.prisma', '.graphql', '.proto', '.html'}
CONFIG = {'package.json', 'pyproject.toml', 'requirements.txt', 'Cargo.toml', 'go.mod', 'pom.xml', 'Gemfile', 'composer.json', 'docker-compose.yml', 'docker-compose.yaml', 'compose.yml', 'compose.yaml', 'Dockerfile', 'README.md'}
ROLES = ['Frontend', 'API', 'Services', 'Databases', 'Infrastructure', 'Tests', 'Shared']

def inventory(root):
    files, warnings = {}, []
    for folder, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in SKIP and not d.endswith('.egg-info') and not Path(folder, d).is_symlink())
        for name in sorted(names):
            p = Path(folder, name)
            if p.is_symlink() or (p.suffix not in SOURCE and name not in CONFIG):
                continue
            if p.stat().st_size > 1_000_000:
                warnings.append(f'Architecture inventory skipped large file: {p.relative_to(root)}')
                continue
            files[p.relative_to(root).as_posix()] = p.read_text(errors='replace')
    return files, warnings

def role_for(path, source):
    parts = set(re.split(r'[/_.-]', path.lower()))
    if parts & {'tests', 'test', 'spec', 'specs'}:
        return 'Tests', 'Test path convention'
    if parts & {'database', 'db', 'migrations', 'prisma', 'schemas'} or Path(path).suffix in {'.sql', '.prisma'}:
        return 'Databases', 'Database/schema path convention'
    if parts & {'frontend', 'web', 'client', 'ui', 'pages', 'components'} or Path(path).suffix in {'.tsx', '.jsx', '.vue', '.svelte'}:
        return 'Frontend', 'Frontend path or component file'
    if parts & {'api', 'routes', 'controllers', 'endpoints'} or re.search(r'FastAPI\s*\(|Flask\s*\(|express\s*\(', source):
        return 'API', 'API path or framework declaration'
    if parts & {'services', 'service', 'backend', 'server', 'workers', 'jobs', 'engine'}:
        return 'Services', 'Service path convention'
    if Path(path).name in CONFIG:
        return 'Infrastructure', 'Build, package, or deployment manifest'
    return 'Shared', 'Unclassified application/library code'

def package_for(path, boundaries):
    parents = [p for p in boundaries if path.startswith(p + '/')]
    if parents:
        return max(parents, key=len)
    parts = path.split('/')
    if len(parts) > 2 and parts[0] in {'apps', 'services', 'packages'}:
        return '/'.join(parts[:2])
    return '.'

def build_layers(root, graph):
    files, warnings = inventory(root)
    boundaries = {str(Path(p).parent) for p in files if Path(p).name in {'package.json', 'pyproject.toml', 'Cargo.toml', 'go.mod', 'pom.xml'} and str(Path(p).parent) != '.'}
    components, modules, assignment = {}, {}, {}
    edges = {'architecture': {}, 'modules': {}}
    file_edges = []

    def evidence(path, line, reason):
        return {'path': path, 'line': line, 'reason': reason}

    def connect(level, source, target, kind, ev, inferred=False):
        if source == target:
            return
        key = (source, target, kind)
        edge = edges[level].setdefault(key, {'source': source, 'target': target, 'kind': kind, 'evidence': [], 'inferred': inferred})
        if ev not in edge['evidence']:
            edge['evidence'].append(ev)

    for path, content in files.items():
        role, reason = role_for(path, content)
        package = package_for(path, boundaries)
        component_id = f'component:{package}:{role}'
        name = role if package == '.' else f'{Path(package).name} · {role}'
        node = components.setdefault(component_id, {'id': component_id, 'name': name, 'role': role, 'kind': 'component', 'paths': [], 'evidence': [], 'summary': f'{role} component inferred from repository evidence.'})
        node['paths'].append(path)
        if len(node['evidence']) < 8:
            node['evidence'].append(evidence(path, 1, reason))
        # Group by directories; split a flat src folder into file modules.
        directory = str(Path(path).parent)
        module_path = path if directory in {'.', 'src'} else directory
        module_id = f'module:{component_id}:{module_path}'
        module = modules.setdefault(module_id, {'id': module_id, 'name': '/' + module_path, 'role': role, 'kind': 'module', 'parent': component_id, 'paths': [], 'evidence': [], 'summary': 'Repository module; drill down to source symbols.'})
        module['paths'].append(path)
        module['evidence'].append(evidence(path, 1, 'Module member'))
        assignment[path] = (component_id, module_id)

    def file_edge(source, target, kind, line, reason, inferred=False):
        if source not in assignment or target not in assignment:
            return
        ev = evidence(source, line, reason)
        file_edges.append({'source': source, 'target': target, 'kind': kind, 'evidence': [ev], 'inferred': inferred})
        for i, level in enumerate(('architecture', 'modules')):
            connect(level, assignment[source][i], assignment[target][i], kind, ev, inferred)

    by_id = {n.id: n for n in graph.nodes}
    for edge in graph.edges:
        if edge.kind in {'calls', 'imports'}:
            a, b = by_id[edge.source], by_id[edge.target]
            file_edge(a.path, b.path, edge.kind.upper(), a.start_line, f'{a.name} {edge.kind} {b.name}')

    # Resolve Python imports across package directories without executing code.
    py_modules = {p.removesuffix('.py').replace('/', '.').removesuffix('.__init__'): p for p in files if p.endswith('.py')}
    for path, content in files.items():
        if not path.endswith('.py'):
            continue
        try:
            tree = ast.parse(content)
        except SyntaxError:
            warnings.append(f'Python syntax error: {path}; imports omitted')
            continue
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [n.name for n in node.names]
            elif isinstance(node, ast.ImportFrom):
                prefix = path.split('/')[:-1]
                if node.level:
                    prefix = prefix[:len(prefix)-node.level+1]
                    base = '.'.join(prefix + ([node.module] if node.module else []))
                else:
                    base = node.module or ''
                names = [base] + [base + '.' + n.name for n in node.names]
            for name in names:
                target = py_modules.get(name)
                if target:
                    file_edge(path, target, 'IMPORTS', node.lineno, f'Python import {name}')

    # Generic relative TS/JS imports also work when there is no symbol extraction.
    for path, content in files.items():
        for match in re.finditer(r'(?:from\s*|import\s*|require\s*\()([\"\'])(\.[^\"\']+)\1', content):
            base = (root / path).parent / match.group(2)
            choices = [base] + [Path(str(base)+ext) for ext in sorted(SOURCE)] + [base / ('index'+ext) for ext in ('.ts','.tsx','.js')]
            for p in choices:
                if p.resolve().is_relative_to(root):
                    target = p.resolve().relative_to(root).as_posix()
                    if target in files:
                        file_edge(path, target, 'IMPORTS', content[:match.start()].count('\n')+1, f'Relative import {match.group(2)}')
                        break

    # Route declarations and matching literal fetch calls. This is static inference.
    routes = []
    for path, content in files.items():
        if assignment[path][0] not in components or components[assignment[path][0]]['role'] != 'API':
            continue
        for match in re.finditer(r'\b(?:app|router|api)\.(get|post|put|delete|patch)\s*\(\s*[\"\']([^\"\']+)', content):
            routes.append((match.group(2), path, match.group(1).upper()))
    for path, content in files.items():
        for match in re.finditer(r'\bfetch\s*\(\s*[\"\'](/[^\"\']+)', content):
            targets = {p for route, p, method in routes if route == match.group(1)}
            if len(targets) == 1:
                file_edge(path, next(iter(targets)), 'ROUTES_TO', content[:match.start()].count('\n')+1, f'Literal request path {match.group(1)} matches a declared route; HTTP method/prefix not verified', True)

    # Deployment services and explicit depends_on are stronger than folder guesses.
    for path, content in files.items():
        if Path(path).name not in {'docker-compose.yml','docker-compose.yaml','compose.yml','compose.yaml'}:
            continue
        try:
            config = yaml.safe_load(content)
            services = config.get('services', {}) if isinstance(config, dict) else {}
            if not isinstance(services, dict):
                continue
            for name, spec in services.items():
                if not isinstance(spec, dict):
                    continue
                image = str(spec.get('image', ''))
                role = 'Databases' if re.search(r'postgres|mysql|mongo|redis|mariadb|elasticsearch', image, re.I) else 'Infrastructure'
                sid = f'deployment:{path}:{name}'
                components[sid] = {'id':sid,'name':str(name),'role':role,'kind':'deployment','paths':[path], 'evidence':[evidence(path,1,f'Declared compose service {name}; image {image or "local build"}')], 'summary':f'Deployment service: {image or "local build"}'}
            for name, spec in services.items():
                if not isinstance(spec, dict):
                    continue
                sid = f'deployment:{path}:{name}'
                deps = spec.get('depends_on', [])
                if isinstance(deps, (list,dict)):
                    for dep in deps:
                        target = f'deployment:{path}:{dep}'
                        if target in components:
                            connect('architecture', sid, target, 'DEPENDS_ON', evidence(path,1,f'{name}.depends_on includes {dep}'))
                build = spec.get('build')
                context = build.get('context') if isinstance(build,dict) else build
                if isinstance(context,str):
                    target_path = ((root/path).parent/context).resolve()
                    if target_path.is_relative_to(root):
                        relative = target_path.relative_to(root).as_posix()
                        for cid, node in list(components.items()):
                            if node['kind']=='component' and any(relative=='.' or p.startswith(relative+'/') for p in node['paths']):
                                connect('architecture',sid,cid,'BUILDS',evidence(path,1,f'Service build context {context} includes component'),True)
        except yaml.YAMLError:
            warnings.append(f'Invalid compose manifest: {path}')

    # Declared third-party systems, kept separate from observed calls.
    systems = {'pg':('PostgreSQL','Databases'),'psycopg':('PostgreSQL','Databases'),'psycopg2':('PostgreSQL','Databases'), 'mongodb':('MongoDB','Databases'),'pymongo':('MongoDB','Databases'),'redis':('Redis','Databases'),'stripe':('Stripe','Services')}
    for path, content in files.items():
        deps = []
        try:
            if Path(path).name=='package.json':
                value=json.loads(content)
                if isinstance(value,dict) and isinstance(value.get('dependencies',{}),dict):
                    deps=list(value.get('dependencies',{}))
            elif Path(path).name=='pyproject.toml':
                deps=tomllib.loads(content).get('project',{}).get('dependencies',[])
            elif Path(path).name=='requirements.txt':
                deps=content.splitlines()
        except (ValueError, TypeError):
            warnings.append(f'Invalid dependency manifest: {path}')
        for dep in deps:
            name=re.split(r'[<>=!~\[ ;]',str(dep).lower())[0]
            if name not in systems:
                continue
            label, role=systems[name]
            sid=f'external:{label}'
            components.setdefault(sid,{'id':sid,'name':label,'role':role,'kind':'external','paths':[], 'evidence':[], 'summary':'External system inferred from a declared client dependency; deployment not verified.'})
            ev=evidence(path,1,f'Declared dependency: {name}')
            components[sid]['evidence'].append(ev)
            connect('architecture',assignment[path][0],sid,'DEPENDS_ON',ev,True)

    ordered = sorted(components.values(), key=lambda n:(ROLES.index(n['role']),n['name']))
    for node in graph.nodes:
        if node.path in assignment:
            node.component_id, node.module_id = assignment[node.path]
    digest = hashlib.sha256()
    for path, content in sorted(files.items()):
        digest.update(path.encode()+b'\0'+content.encode())
    graph.revision = digest.hexdigest()[:16]
    graph.warnings.extend(warnings)
    graph.layers = {
        'architecture': {'nodes':ordered, 'edges':list(edges['architecture'].values())},
        'modules': {'nodes':list(modules.values()), 'edges':list(edges['modules'].values())},
    }
    graph.inventory = {'files':len(files),'languages':sorted({Path(p).suffix.lstrip('.') for p in files if Path(p).suffix in SOURCE}),
        'relationships':'Static evidence, not observed runtime execution',
        'limitations':['Component roles are inferred from path/framework conventions.', 'Java and TS/JS symbols have partial static call resolution; other languages are primarily inventoried.', 'Reads, writes, mutations, returns and test coverage are not inferred from names.']}
    from .system_map import apply_system_map
    apply_system_map(graph, files, file_edges)
    from .hierarchy import build_hierarchy
    return build_hierarchy(graph, files)
