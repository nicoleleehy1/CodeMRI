"""Explicit endpoint/entity declarations supplement the local architecture map."""
import ast
import re
from pathlib import Path
from tree_sitter import Language, Parser
import tree_sitter_typescript as ts
import tree_sitter_java


def resources(graph, files):
    layer = graph.layers['architecture']
    nodes, edges = layer['nodes'], layer['edges']
    groups = layer.setdefault('groups', [])
    known = {n['id'] for n in nodes}
    owners = {p: n['id'] for n in nodes if n['kind'] == 'component' for p in n.get('paths', [])}

    def add(path, line, name, kind, group, shape='box'):
        key = f'{kind}:{path}:{line}:{name}'
        if key in known:
            return
        known.add(key)
        evidence = [{'path': path, 'line': line, 'reason': f'Source declaration: {name}'}]
        nodes.append({'id': key, 'name': name, 'kind': kind, 'shape': shape, 'group': group,
                      'paths': [], 'evidence': evidence, 'summary': f'{name} declared in {path}:{line}'})
        if not any(g['id'] == group for g in groups):
            groups.append({'id': group, 'name': group})
        if path in owners:
            edges.append({'source': owners[path], 'target': key, 'kind': 'DECLARES', 'label': 'declares',
                          'evidence': evidence, 'inferred': False})

    def walk(node):
        yield node
        for child in node.named_children:
            yield from walk(child)

    def text(node):
        return node.text.decode(errors='replace') if node else ''

    for path, source in files.items():
        suffix = Path(path).suffix
        if suffix in {'.ts', '.tsx', '.js', '.jsx', '.java'}:
            language = tree_sitter_java.language() if suffix == '.java' else ts.language_tsx() if suffix in {'.tsx', '.jsx'} else ts.language_typescript()
            tree = Parser(Language(language)).parse(source.encode())
            for call in walk(tree.root_node):
                name, receiver = '', ''
                if call.type == 'method_invocation':
                    name = text(call.child_by_field_name('name'))
                elif call.type == 'call_expression':
                    fn = call.child_by_field_name('function')
                    if fn and fn.type == 'member_expression':
                        name = text(fn.child_by_field_name('property'))
                        receiver = text(fn.child_by_field_name('object'))
                if name != 'createContext' and not (name in {'get','post','put','patch','delete','options','head'} and receiver in {'app','router','api','server'}):
                    continue
                args = call.child_by_field_name('arguments')
                first = args.named_children[0] if args and args.named_children else None
                if not first or first.type not in {'string', 'string_literal'}:
                    continue
                route = text(first)[1:-1]
                if route.startswith('/'):
                    add(path, call.start_point.row+1, ('HTTP' if name == 'createContext' else name.upper())+' '+route, 'api_endpoint', 'API endpoints')
        elif suffix == '.py':
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for decorator in node.decorator_list:
                    if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                        continue
                    method = decorator.func.attr
                    if method not in {'get','post','put','patch','delete','options','head','route'} or not decorator.args:
                        continue
                    arg = decorator.args[0]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value,str) and arg.value.startswith('/'):
                        add(path, decorator.lineno, ('HTTP' if method=='route' else method.upper())+' '+arg.value, 'api_endpoint', 'API endpoints')
        elif suffix in {'.sql', '.prisma'}:
            # Remove comments without shifting line numbers; these patterns only classify declarations.
            code = re.sub(r'/\*.*?\*/|--[^\n]*|//[^\n]*', lambda m: ''.join('\n' if c=='\n' else ' ' for c in m.group()), source, flags=re.S)
            pattern = r'\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w."`]+)' if suffix=='.sql' else r'\bmodel\s+(\w+)\s*\{'
            for match in re.finditer(pattern, code, re.I):
                add(path, code[:match.start()].count('\n')+1, match.group(1), 'database_entity', 'Database entities', 'database')
    # Compose service images are concrete declarations, not guesses from variable names.
    for node in nodes:
        if node['kind'] == 'deployment' and re.search(r'\b(rabbitmq|kafka|nats|activemq|redpanda)\b', node.get('summary',''), re.I):
            node['kind'] = 'event_queue'
            node['group'] = 'Events / queues'
            if not any(g['id'] == node['group'] for g in groups):
                groups.append({'id': node['group'], 'name': node['group']})
