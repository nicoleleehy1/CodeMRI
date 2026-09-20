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
