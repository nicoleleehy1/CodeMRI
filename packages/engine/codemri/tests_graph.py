"""Heuristic test discovery (P3.1) and impacted-test selection (P3.2).

Tests become `tested_by` edges from a production symbol to the test symbol that exercises it. Every
link records how it was found (direct call, import, naming convention) so the selection can be
justified and doubted. Wording rule: symbols without links have "no identified tests" - the
heuristics can miss tests, so this is never evidence that something is untested.
"""
import re
from pathlib import Path
from .models import Graph, Edge, Symbol

TEST_PATH = re.compile(r'(^|/)(tests?|__tests__|spec)(/|$)')
JAVA_TEST_FILE = re.compile(r'(Test|Tests|IT)\.java$')
JS_TEST_FILE = re.compile(r'\.(test|spec)\.[cm]?[jt]sx?$')
PY_TEST_FILE = re.compile(r'(^|/)(test_[^/]*\.py|[^/]*_test\.py)$')
JAVA_TEST_ANNOTATION = re.compile(r'@(Test|ParameterizedTest|RepeatedTest|TestFactory)\b')
NODE_TEST_CALL = re.compile(r'(?:^|[;\s])(?:test|it|describe)\s*\(', re.M)
JS_FRAMEWORK_IMPORTS = (
    ('vitest', re.compile(r"""from\s+['"]vitest['"]|require\(['"]vitest['"]\)""")),
    ('jest', re.compile(r"""from\s+['"]@jest/globals['"]|require\(['"]@jest/globals['"]\)|\bjest\.(fn|mock|spyOn)\(""")),
    ('mocha', re.compile(r"""from\s+['"]mocha['"]|require\(['"]mocha['"]\)""")),
)
JAVA_TEST_METHOD_SKIP = {'setup', 'setUp', 'teardown', 'tearDown', 'beforeEach', 'afterEach', 'beforeAll', 'afterAll'}


def framework_of(path: str, source: str) -> str | None:
    if path.endswith('.java'):
        if JAVA_TEST_FILE.search(path) or JAVA_TEST_ANNOTATION.search(source) or '/src/test/' in f'/{path}':
            return 'junit'
        return None
    if JS_TEST_FILE.search(path) or (TEST_PATH.search(path) and NODE_TEST_CALL.search(source)):
        if 'node:test' in source:
            return 'node:test'
        for framework, marker in JS_FRAMEWORK_IMPORTS:
            if marker.search(source):
                return framework
        return 'js-test'  # a test file, but the runner is unknown: linked in the graph, never given a command
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


def discover_tests(graph: Graph, listing=None) -> Graph:
    """Add `tested_by` edges and a `tests` layer to `graph`. Idempotent for a graph that has none yet.

    `listing` (a `Walk`) lets file-level frameworks be found for files that have no graph nodes: Python files
    are inventoried but not symbol-extracted, so pytest files are recorded by path and linked by naming convention."""
    by_id = {n.id: n for n in graph.nodes}
    modules = {n.path: n for n in graph.nodes if n.kind == 'module'}
    test_modules = {}
    for path, module in modules.items():
        framework = framework_of(path, module.source)
        if framework:
            test_modules[path] = framework
    inventoried_py = [f for f in (listing.files if listing else []) if f.endswith('.py')]
    for path in inventoried_py:
        if path not in modules and framework_of(path, ''):
            test_modules[path] = 'pytest'
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

    file_only = {p for p in test_modules if p not in by_id}  # pytest files without graph nodes
    links = {}  # (symbol, test) -> {via, evidence}; for Python, `symbol` may be a production file path
    def link(symbol, test, via, evidence):
        if test not in by_id and test not in file_only:
            return
        if symbol in by_id and symbol != test and by_id[symbol].path not in test_modules:
            links.setdefault((symbol, test), {'via': via, 'evidence': evidence})
        elif symbol in inventoried_py and symbol not in test_modules:
            links.setdefault((symbol, test), {'via': via, 'evidence': evidence})

    # Test functions per file: JUnit methods with @Test; for node:test the module itself stands in,
    # because `test('...', () => ...)` callbacks are not declared symbols in the graph.
    test_symbols = {}
    for path, framework in test_modules.items():
        found = [sid for sid in symbols_in(path) if is_test_symbol(by_id[sid], framework)]
        test_symbols[path] = found or [path]
    # Python: no symbols, so a test file is linked to the production .py files its name or imports point at.
    for path in file_only:
        wanted = subject_names(path)
        try:
            text = Path(graph.root, path).read_text(errors='replace')
        except OSError:
            text = ''
        for candidate in inventoried_py:
            if candidate in test_modules:
                continue
            stem = Path(candidate).stem
            if stem in wanted or stem.lower() in wanted:
                link(candidate, path, 'name', Path(path).name)
            module_name = candidate[:-3].replace('/', '.')
            if re.search(r'^\s*(?:from|import)\s+' + re.escape(module_name) + r'\b', text, re.M) or \
               re.search(r'^\s*(?:from|import)\s+' + re.escape(stem) + r'\b', text, re.M):
                link(candidate, path, 'import', path)

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
        if (symbol, test) not in existing and symbol in by_id and test in by_id:
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
               'Python symbols are not extracted, so pytest files are linked file-to-file by naming convention and imports; '
               'they are selected when an affected node lives in the linked file, which requires symbol nodes (TS/JS/Java).')


def java_build_tool(graph_root: str, test_path: str) -> str | None:
    """`maven` / `gradle` from the nearest build manifest above the test file; None when absent or both are present."""
    root = Path(graph_root)
    for directory in [Path(test_path).parent, *Path(test_path).parents]:
        here = root / directory
        maven = (here / 'pom.xml').is_file()
        gradle = any((here / f).is_file() for f in ('build.gradle', 'build.gradle.kts', 'settings.gradle', 'settings.gradle.kts'))
        if maven and gradle:
            return None
        if maven:
            return 'maven'
        if gradle:
            return 'gradle'
    return None


def java_fqcn(test_path: str) -> str:
    parts = Path(test_path).with_suffix('').parts
    for marker in ('java', 'kotlin', 'groovy'):
        if marker in parts:
            return '.'.join(parts[parts.index(marker) + 1:])
    return parts[-1]


def selector_for(framework: str, test_node, graph_root: str) -> dict:
    """How to run just this test with the framework's own CLI. Paths are relative to the repository."""
    if framework == 'junit':
        cls = Path(test_node.path).stem
        build = java_build_tool(graph_root, test_node.path)
        if build == 'maven':
            if test_node.kind == 'method_declaration':
                return {'tool': 'mvn', 'args': ['-q', f'-Dtest={cls}#{test_node.name}', '-Dsurefire.failIfNoSpecifiedTests=false', 'test']}
            return {'tool': 'mvn', 'args': ['-q', f'-Dtest={cls}', '-Dsurefire.failIfNoSpecifiedTests=false', 'test']}
        if build == 'gradle':
            fqcn = java_fqcn(test_node.path)
            filter_ = f'{fqcn}.{test_node.name}' if test_node.kind == 'method_declaration' else fqcn
            return {'tool': 'gradle', 'args': ['-q', 'test', '--tests', filter_]}
        return {'tool': None, 'args': []}  # no or ambiguous build manifest: JUnit test known, runner unknown
    if framework == 'node:test':
        if re.search(r'\.[cm]?tsx?$', test_node.path):
            return {'tool': 'npx', 'args': ['tsx', '--test', test_node.path]}
        return {'tool': 'node', 'args': ['--test', test_node.path]}
    if framework == 'vitest':
        return {'tool': 'npx', 'args': ['vitest', 'run', test_node.path]}
    if framework == 'jest':
        return {'tool': 'npx', 'args': ['jest', '--runTestsByPath', test_node.path]}
    if framework == 'mocha':
        return {'tool': 'npx', 'args': ['mocha', test_node.path]}
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
    affected_paths = {by_id[a].path for a in affected if a in by_id}
    selected = {}
    for link in layer.get('links', []):
        symbol, test = link['symbol'], link['test']
        if symbol not in affected and symbol not in affected_paths:
            continue
        test_node = by_id.get(test)
        if test_node is None:
            if test not in frameworks:
                continue
            test_node = Symbol(id=test, name=test, kind='module', path=test, start_line=1, end_line=1)
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
