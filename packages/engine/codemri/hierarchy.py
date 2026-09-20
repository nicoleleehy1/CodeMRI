"""Repository hierarchy projected from analyzed files and symbol containment."""
from pathlib import Path


def build_hierarchy(graph, files):
    from .architecture_resources import resources
    resources(graph, files)
    architecture = graph.layers['architecture']
    components = architecture['nodes']
    covered = {p for node in components if node['kind'] in {'component', 'deployment'} for p in node.get('paths', [])}
    missing = sorted(set(files) - covered)
    if missing:
        components.append({'id': 'component:other-files', 'name': 'Other source & configuration',
                           'kind': 'component', 'shape': 'box', 'group': 'Repository files',
                           'paths': missing, 'summary': 'Inventoried files outside the inferred runtime components.',
                           'evidence': [{'path': p, 'line': 1, 'reason': 'Inventoried repository file'} for p in missing[:8]]})
        architecture.setdefault('groups', []).append({'id': 'Repository files', 'name': 'Repository files'})
    repository = {'id': 'repository:root', 'name': Path(graph.root).name, 'kind': 'repository',
                  'shape': 'box', 'paths': [], 'summary': f'{len(files)} inventoried files', 'group': 'Repository'}
    packages, file_nodes, containment = {}, [], []
    file_by_path = {}
    for component in components:
        containment.append({'source': repository['id'], 'target': component['id'], 'kind': 'CONTAINS', 'label': 'contains', 'inferred': False})
        if component['kind'] in {'api_endpoint', 'database_entity', 'event_queue', 'external'}:
            continue
        for path in component.get('paths', []):
            if path not in files:
                continue
            directory = str(Path(path).parent)
            package_id = f'package:{component["id"]}:{directory}'
            if package_id not in packages:
                packages[package_id] = {'id': package_id, 'parent': component['id'],
                    'name': directory if directory != '.' else '(root package)', 'kind': 'package', 'shape': 'box',
                    'paths': [], 'summary': 'Source directory / package', 'evidence': []}
                containment.append({'source': component['id'], 'target': package_id, 'kind': 'CONTAINS'})
            packages[package_id]['paths'].append(path)
            evidence = [{'path': path, 'line': 1, 'reason': 'Source file in this package'}]
            packages[package_id]['evidence'].extend(evidence)
            file_id = f'file:{component["id"]}:{path}'
            file_nodes.append({'id': file_id, 'parent': package_id, 'name': Path(path).name,
                'kind': 'file', 'shape': 'document', 'paths': [path], 'path': path,
                'summary': path, 'evidence': evidence})
            file_by_path.setdefault(path, file_id)
            containment.append({'source': package_id, 'target': file_id, 'kind': 'CONTAINS'})
    symbols = {node.id: node for node in graph.nodes if node.kind != 'module'}
    parents = {edge.target: edge.source for edge in graph.edges if edge.kind == 'contains'}
    symbol_nodes = []
    for symbol in symbols.values():
        parent = parents.get(symbol.id)
        if parent not in symbols:
            parent = file_by_path.get(symbol.path)
        if not parent:
            continue
        symbol_nodes.append(dict(symbol.model_dump(), parent=parent))
        containment.append({'source': parent, 'target': symbol.id, 'kind': 'CONTAINS'})
    graph.layers['packages'] = {'nodes': list(packages.values()), 'edges': []}
    graph.layers['files'] = {'nodes': file_nodes, 'edges': []}
    graph.layers['hierarchy'] = {'nodes': [repository, *(dict(n, parent=repository['id']) for n in components), *packages.values(), *file_nodes, *symbol_nodes],
                                 'edges': containment}
    graph.layers['repository'] = {'nodes': [repository, *components],
        'edges': [e for e in containment if e['source'] == repository['id']] + architecture['edges'],
        'groups': [{'id': 'Repository', 'name': 'Repository'}, *architecture.get('groups', [])],
        'mode': architecture.get('mode', 'local-evidence'),
        'explanation': 'Repository → architecture component → module/package → file → class, function, interface and other declarations.'}
    return graph
