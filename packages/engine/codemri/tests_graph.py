"""Heuristic test discovery (P3.1) and impacted-test selection (P3.2).

Tests become `tested_by` edges from a production symbol to the test symbol that exercises it. Every
link records how it was found (direct call, import, naming convention) so the selection can be
justified and doubted. Wording rule: symbols without links have "no identified tests" - the
heuristics can miss tests, so this is never evidence that something is untested.
"""
import re
from pathlib import Path
from .models import Graph, Edge

TEST_PATH = re.compile(r'(^|/)(tests?|__tests__|spec)(/|$)')
JAVA_TEST_FILE = re.compile(r'(Test|Tests|IT)\.java$')
JS_TEST_FILE = re.compile(r'\.(test|spec)\.[cm]?[jt]sx?$')
PY_TEST_FILE = re.compile(r'(^|/)(test_[^/]*\.py|[^/]*_test\.py)$')
JAVA_TEST_ANNOTATION = re.compile(r'@(Test|ParameterizedTest|RepeatedTest|TestFactory)\b')
NODE_TEST_CALL = re.compile(r'(?:^|[;\s])(?:test|it|describe)\s*\(', re.M)
JAVA_TEST_METHOD_SKIP = {'setup', 'setUp', 'teardown', 'tearDown', 'beforeEach', 'afterEach', 'beforeAll', 'afterAll'}


def framework_of(path: str, source: str) -> str | None:
    if path.endswith('.java'):
        if JAVA_TEST_FILE.search(path) or JAVA_TEST_ANNOTATION.search(source) or '/src/test/' in f'/{path}':
            return 'junit'
        return None
    if JS_TEST_FILE.search(path) or (TEST_PATH.search(path) and NODE_TEST_CALL.search(source)):
        return 'node:test' if 'node:test' in source else 'js-test'
    if PY_TEST_FILE.search(path):
        return 'pytest'
    return None


def subject_names(path: str) -> set[str]:
    """Production names a test file name points at: LSMStoreTest -> LSMStore, pricing.test.ts -> pricing, test_store.py -> store."""
    stem = Path(path).name
    stem = re.sub(r'\.[cm]?[jt]sx?$|\.java$|\.py$', '', stem)
    stem = re.sub(r'\.(test|spec)$', '', stem)
    stem = re.sub(r'(Test|Tests|IT)$', '', stem)
    stem = re.sub(r'^test_|_test$', '', stem)
    return {stem, stem.lower()} - {''}


def discover_tests(graph: Graph) -> Graph:
    """Add `tested_by` edges and a `tests` layer to `graph`. Idempotent for a graph that has none yet."""
    by_id = {n.id: n for n in graph.nodes}
    modules = {n.path: n for n in graph.nodes if n.kind == 'module'}
    test_modules = {}
    for path, module in modules.items():
        framework = framework_of(path, module.source)
        if framework:
            test_modules[path] = framework
    if not test_modules:
        graph.layers['tests'] = {'frameworks': {}, 'files': [], 'tests': {}, 'links': [], 'limitations': LIMITATIONS}
        return graph

    children = {}
    for e in graph.edges:
        if e.kind == 'contains':
            children.setdefault(e.source, []).append(e.target)
    def symbols_in(path):
        out, stack = [], list(children.get(path, []))
        while stack:
            sid = stack.pop()
            out.append(sid)
            stack.extend(children.get(sid, []))
        return out

    def is_test_symbol(node, framework):
        if framework == 'junit':
            return node.kind == 'method_declaration' and JAVA_TEST_ANNOTATION.search(node.source or '') is not None \
                and node.name not in JAVA_TEST_METHOD_SKIP
        return False

    links = {}  # (symbol, test) -> {via, evidence}
    def link(symbol, test, via, evidence):
        if symbol in by_id and test in by_id and symbol != test and by_id[symbol].path not in test_modules:
            links.setdefault((symbol, test), {'via': via, 'evidence': evidence})

    # Test functions per file: JUnit methods with @Test; for node:test the module itself stands in,
    # because `test('...', () => ...)` callbacks are not declared symbols in the graph.
    test_symbols = {}
    for path, framework in test_modules.items():
        found = [sid for sid in symbols_in(path) if is_test_symbol(by_id[sid], framework)]
        test_symbols[path] = found or [path]

    # 1. Direct calls: a test symbol (or anything contained in a test file) calls a production symbol.
    owner_test = {}
    for path, framework in test_modules.items():
        for sid in symbols_in(path):
            node = by_id[sid]
            owner = sid if sid in test_symbols[path] else None
            if owner is None and framework == 'junit':
                # setup/teardown helpers exercise a symbol on behalf of every test in the class.
                owner_test[sid] = [t for t in test_symbols[path]]
            else:
                owner_test[sid] = [owner or path]
    for e in graph.edges:
        if e.kind != 'calls' or e.source not in owner_test:
            continue
        site = e.call_sites[0] if e.call_sites else None
        evidence = f'{site.path}:{site.line}' if site else by_id[e.source].path
        for test in owner_test[e.source]:
            link(e.target, test, 'call', evidence)

    # 2. Imports: the test file imports a production module; every symbol of that module whose name is
    #    referenced in the test source is linked, and the module itself always is.
    for e in graph.edges:
        if e.kind != 'imports' or e.source not in test_modules or e.target in test_modules:
            continue
        source_text = by_id[e.source].source
        for test in test_symbols[e.source]:
            link(e.target, test, 'import', e.source)
            for sid in symbols_in(e.target):
                name = by_id[sid].name
                if name and re.search(r'\b' + re.escape(name) + r'\b', source_text):
                    link(sid, test, 'import', e.source)

    # 3. Naming convention: FooTest / foo.test.ts / test_foo.py refers to a symbol or module named foo.
    for path in test_modules:
        wanted = subject_names(path)
        for node in graph.nodes:
            if node.path in test_modules:
                continue
            stem = Path(node.path).name.split('.')[0] if node.kind == 'module' else node.name
            if stem in wanted or stem.lower() in wanted:
                for test in test_symbols[path]:
                    link(node.id, test, 'name', Path(path).name)

    existing = {(e.source, e.target) for e in graph.edges if e.kind == 'tested_by'}
    for (symbol, test), info in sorted(links.items()):
        if (symbol, test) not in existing:
            graph.edges.append(Edge(source=symbol, target=test, kind='tested_by'))
    graph.layers['tests'] = {
        'frameworks': dict(sorted(test_modules.items())),
        'files': sorted(test_modules),
        'tests': {path: ids for path, ids in sorted(test_symbols.items())},
        'links': [{'symbol': s, 'test': t, **info} for (s, t), info in sorted(links.items())],
        'limitations': LIMITATIONS,
    }
    return graph


LIMITATIONS = ('Heuristic: tests are linked by resolved direct calls, imports with a name reference, and file naming. '
               'Symbols with no link have no identified tests; that is not evidence they are untested. '
               'Python test files are inventoried but Python symbols are not extracted, so pytest links are file-level only.')


def selector_for(framework: str, test_node, graph_root: str) -> dict:
    """How to run just this test with the framework's own CLI. Paths are relative to the repository."""
    if framework == 'junit':
        cls = Path(test_node.path).stem
        if test_node.kind == 'method_declaration':
            return {'tool': 'mvn', 'args': ['-q', f'-Dtest={cls}#{test_node.name}', '-Dsurefire.failIfNoSpecifiedTests=false', 'test']}
        return {'tool': 'mvn', 'args': ['-q', f'-Dtest={cls}', '-Dsurefire.failIfNoSpecifiedTests=false', 'test']}
    if framework in {'node:test', 'js-test'}:
        if re.search(r'\.[cm]?tsx?$', test_node.path):
            return {'tool': 'npx', 'args': ['tsx', '--test', test_node.path]}
        return {'tool': 'node', 'args': ['--test', test_node.path]}
    if framework == 'pytest':
        return {'tool': 'pytest', 'args': ['-q', test_node.path]}
    return {'tool': None, 'args': []}


def impacted_tests(graph: Graph, impact_result: dict) -> dict:
    """Tests associated with an impact result, each with the path that justifies its selection."""
    layer = graph.layers.get('tests')
    if layer is None:
        graph = discover_tests(graph)
        layer = graph.layers['tests']
    by_id = {n.id: n for n in graph.nodes}
    frameworks = layer.get('frameworks', {})
    reasons = impact_result.get('reasons', {})
    affected = list(impact_result.get('affected', []))
    module_of = {n.id: n.path for n in graph.nodes}
    selected = {}
    for link in layer.get('links', []):
        symbol, test = link['symbol'], link['test']
        if symbol not in affected:
            continue
        test_node = by_id.get(test)
        if test_node is None:
            continue
        entry = selected.setdefault(test, {
            'test_id': test, 'name': test_node.name, 'path': test_node.path,
            'framework': frameworks.get(test_node.path, 'unknown'),
            'selector': selector_for(frameworks.get(test_node.path, ''), test_node, graph.root),
            'justification': []})
        entry['justification'].append({
            'symbol': symbol, 'symbol_name': by_id[symbol].name if symbol in by_id else symbol,
            'impact_reason': reasons.get(symbol, ''), 'via': link['via'], 'evidence': link['evidence']})
    # Symbol-level links win; a module-level link only justifies a test when no symbol in that module did.
    ordered = sorted(selected.values(), key=lambda t: (t['path'], t['name']))
    no_tests = [s for s in affected if not any(l['symbol'] == s for l in layer.get('links', []))]
    return {'tests': ordered,
            'files': sorted({t['path'] for t in ordered}),
            'no_identified_tests': no_tests,
            'limitations': layer.get('limitations', LIMITATIONS)}
