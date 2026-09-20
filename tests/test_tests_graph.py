"""P3.1 test discovery and P3.2 impacted-test selection."""
from pathlib import Path
import pytest
from codemri.analyzer import analyze
from codemri.context import impact
from codemri.tests_graph import impacted_tests, subject_names, framework_of

ROOT = Path(__file__).resolve().parents[1]
SHOP = ROOT / 'examples/shop'
MEMMUNK = ROOT / 'examples/MemMunkDB'


def names(graph, ids):
    by_id = {n.id: n for n in graph.nodes}
    return {by_id[i].name for i in ids}


def test_shop_tests_are_discovered_through_imports_and_selected_with_justification():
    graph = analyze(SHOP)
    layer = graph.layers['tests']
    assert layer['frameworks'] == {p: 'node:test' for p in ['tests/analytics.test.ts', 'tests/checkout.test.ts', 'tests/pricing.test.ts']}
    tested_by = {(s, t) for s, t, k in ((e.source, e.target, e.kind) for e in graph.edges) if k == 'tested_by'}
    assert ('src/coupons.ts::applyCoupon@7', 'tests/pricing.test.ts') in tested_by
    assert not any(s.startswith('tests/') for s, _ in tested_by)

    selection = impact(graph, 'change applyCoupon')['tests']
    assert selection['files'] == ['tests/checkout.test.ts', 'tests/pricing.test.ts']
    pricing = next(t for t in selection['tests'] if t['path'] == 'tests/pricing.test.ts')
    assert pricing['selector'] == {'tool': 'npx', 'args': ['tsx', '--test', 'tests/pricing.test.ts']}
    assert {j['symbol_name'] for j in pricing['justification']} >= {'applyCoupon', 'calculatePrice'}
    assert all(j['via'] in {'call', 'import', 'name'} and j['evidence'] for j in pricing['justification'])
    # The chain applyCoupon <- calculatePrice <- checkout justifies checkout.test.ts through checkout.
    checkout = next(t for t in selection['tests'] if t['path'] == 'tests/checkout.test.ts')
    assert 'checkout' in {j['symbol_name'] for j in checkout['justification']}

    unrelated = impact(graph, 'change trackPage')['tests']
    assert unrelated['files'] == ['tests/analytics.test.ts']
    assert impact(graph, 'change nothingMatchesThis')['tests']['tests'] == []
    assert 'no identified tests' in selection['limitations']


def test_repository_without_tests_reports_none_not_untested(tmp_path):
    (tmp_path / 'a.ts').write_text('export function alpha() { return 1; }\n')
    graph = analyze(tmp_path)
    assert graph.layers['tests']['files'] == [] and not [e for e in graph.edges if e.kind == 'tested_by']
    result = impact(graph, 'change alpha')['tests']
    assert result['tests'] == [] and names(graph, result['no_identified_tests']) == {'alpha'}
    assert 'untested' not in ' '.join(w.lower() for w in graph.warnings)


def test_naming_conventions_and_frameworks():
    assert subject_names('src/test/java/com/x/LSMStoreTest.java') == {'LSMStore', 'lsmstore'}
    assert subject_names('tests/pricing.test.ts') == {'pricing'}
    assert subject_names('tests/test_store.py') == {'store'}
    assert framework_of('tests/test_x.py', '') == 'pytest'
    assert framework_of('a/b/FooIT.java', '') == 'junit'
    assert framework_of('src/foo.ts', 'test("x", () => {})') is None
    assert framework_of('src/__tests__/foo.js', "const test = require('node:test'); test('x', () => {})") == 'node:test'


@pytest.mark.skipif(not (MEMMUNK / 'pom.xml').exists(), reason='MemMunkDB fixture is cloned separately (see README)')
def test_memmunkdb_junit_links_and_selection():
    graph = analyze(MEMMUNK)
    by_id = {n.id: n for n in graph.nodes}
    layer = graph.layers['tests']
    assert layer['frameworks'] == {'src/test/java/com/lsmtree/LSMStoreTest.java': 'junit'}
    test_methods = layer['tests']['src/test/java/com/lsmtree/LSMStoreTest.java']
    assert all(by_id[t].kind == 'method_declaration' and '@Test' in by_id[t].source for t in test_methods)
    assert 'setup' not in names(graph, test_methods)
    linked = {by_id[l['symbol']].name for l in layer['links'] if by_id[l['symbol']].path.endswith('LSMStore.java')}
    assert {'LSMStore', 'put', 'get', 'delete'} <= linked

    put_id = next(n.id for n in graph.nodes if n.name == 'put' and n.path.endswith('LSMStore.java'))
    selection = impact(graph, 'change put', seed_ids=[put_id])['tests']
    assert selection['tests'] and all(t['framework'] == 'junit' for t in selection['tests'])
    assert any(t['name'] == 'putAndGet_basicEntry' for t in selection['tests'])
    assert selection['tests'][0]['selector']['tool'] == 'mvn' and selection['tests'][0]['selector']['args'][1].startswith('-Dtest=LSMStoreTest#')
    assert all(any(j['symbol'] == put_id and j['via'] == 'call' for j in t['justification']) for t in selection['tests'] if t['name'] == 'putAndGet_basicEntry')

    unrelated = next(n.id for n in graph.nodes if n.kind == 'class_declaration' and n.name == 'RestServer')
    assert impact(graph, 'change rest server', seed_ids=[unrelated])['tests']['tests'] == []


def test_pytest_files_are_discovered_without_python_symbol_nodes(tmp_path):
    (tmp_path / 'calc.py').write_text('def add(a, b):\n    return a + b\n')
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests/test_calc.py').write_text('from calc import add\n\ndef test_add():\n    assert add(1, 2) == 3\n')
    graph = analyze(tmp_path)
    layer = graph.layers['tests']
    assert layer['frameworks'] == {'tests/test_calc.py': 'pytest'} and layer['files'] == ['tests/test_calc.py']
    assert [(l['symbol'], l['test']) for l in layer['links']] == [('calc.py', 'tests/test_calc.py')]
    assert layer['links'][0]['via'] in {'name', 'import'}
    assert not graph.nodes, 'file-level discovery must not invent Python symbol nodes'


def test_python_only_repo_selects_pytest_file_from_change_intent(tmp_path):
    (tmp_path / 'calc.py').write_text('def add(a, b):\n    return a + b\n')
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests/test_calc.py').write_text('from calc import add\n\ndef test_add():\n    assert add(1, 2) == 3\n')
    graph = analyze(tmp_path)
    from codemri.context import impact
    result = impact(graph, 'change calc add')
    assert 'calc.py' in result['affected']
    assert [t['path'] for t in result['tests']['tests']] == ['tests/test_calc.py']
    assert result['tests']['tests'][0]['selector']['tool'] in {'pytest', 'python', 'python3'}


def test_js_frameworks_get_their_own_runner_or_no_command():
    from types import SimpleNamespace
    from codemri.tests_graph import selector_for
    node = SimpleNamespace(path='tests/user.test.ts', kind='call_expression', name='x')
    assert framework_of('tests/user.test.ts', "import { describe, expect } from 'vitest'") == 'vitest'
    assert selector_for('vitest', node, '.') == {'tool': 'npx', 'args': ['vitest', 'run', 'tests/user.test.ts']}
    assert framework_of('tests/user.test.ts', "import { jest } from '@jest/globals'") == 'jest'
    assert framework_of('tests/user.test.js', "const assert = require('assert'); describe('x', () => {})") == 'js-test'
    assert selector_for('js-test', node, '.')['tool'] is None  # unknown runner: never manufacture a command


def test_junit_selector_follows_build_manifest(tmp_path):
    from types import SimpleNamespace
    from codemri.tests_graph import selector_for
    node = SimpleNamespace(path='src/test/java/app/CartTest.java', kind='method_declaration', name='totals')
    assert selector_for('junit', node, str(tmp_path))['tool'] is None
    (tmp_path / 'build.gradle').write_text('')
    assert selector_for('junit', node, str(tmp_path)) == {'tool': 'gradle', 'args': ['-q', 'test', '--tests', 'app.CartTest.totals']}
    (tmp_path / 'pom.xml').write_text('')
    assert selector_for('junit', node, str(tmp_path))['tool'] is None  # both manifests: ambiguous
    (tmp_path / 'build.gradle').unlink()
    assert selector_for('junit', node, str(tmp_path))['tool'] == 'mvn'


def test_nested_java_build_is_addressed_from_the_root(tmp_path):
    from types import SimpleNamespace
    from codemri.tests_graph import selector_for
    from codemri.runner import Command, merge_junit
    (tmp_path / 'modules/cart').mkdir(parents=True)
    (tmp_path / 'modules/cart/pom.xml').write_text('')
    node = SimpleNamespace(path='modules/cart/src/test/java/app/CartTest.java', kind='class_declaration', name='CartTest')
    sel = selector_for('junit', node, str(tmp_path))
    assert sel['tool'] == 'mvn' and sel['args'][1:3] == ['-f', 'modules/cart/pom.xml']
    (tmp_path / 'modules/cart/pom.xml').unlink()
    (tmp_path / 'modules/cart/build.gradle.kts').write_text('')
    assert selector_for('junit', node, str(tmp_path))['args'][1:3] == ['-p', 'modules/cart']
    a = Command('mvn', ['-q', '-f', 'modules/cart/pom.xml', '-Dtest=A#x', 'test'])
    b = Command('mvn', ['-q', '-f', 'modules/cart/pom.xml', '-Dtest=A#y', 'test'])
    c = Command('mvn', ['-q', '-f', 'modules/other/pom.xml', '-Dtest=B#z', 'test'])
    merged = merge_junit([a, b, c])
    assert len(merged) == 2 and '-Dtest=A#x,A#y' in merged[0].args and '-Dtest=B#z' in merged[1].args
