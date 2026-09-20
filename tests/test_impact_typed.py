"""P1.4: impact() traverses by edge kind and direction; the default (`calls`) is unchanged."""
from pathlib import Path
import pytest
from codemri.analyzer import analyze
from codemri.context import impact

SHOP = Path(__file__).resolve().parents[1] / 'examples/shop'
MEMMUNK = Path(__file__).resolve().parents[1] / 'examples/MemMunkDB'


def names(graph, ids):
    by_id = {n.id: n for n in graph.nodes}
    return {by_id[i].name for i in ids if not by_id[i].path.startswith('tests/')}


def test_default_traversal_matches_calls_only():
    graph = analyze(SHOP)
    default = impact(graph, 'change applyCoupon')
    explicit = impact(graph, 'change applyCoupon', kinds=('calls',))
    assert default['affected'] == explicit['affected']
    assert default['edge_kinds'] == ['calls'] and default['edges_followed']['calls'] >= 2
    assert names(graph, default['affected']) == {'applyCoupon', 'calculatePrice', 'checkout'}


def test_import_edges_add_importing_files_with_reasons():
    graph = analyze(SHOP)
    result = impact(graph, 'change applyCoupon', kinds=('calls', 'imports'))
    by_id = {n.id: n for n in graph.nodes}
    importers = {by_id[i].path for i, why in result['reasons'].items() if why.startswith('Imports affected file')}
    assert 'src/pricing.ts' in importers and 'src/checkout.ts' in importers
    assert result['edges_followed']['imports'] >= 2
    assert set(result['affected']) > set(impact(graph, 'change applyCoupon')['affected'])


def test_contains_edges_add_members(tmp_path):
    (tmp_path / 'cart.ts').write_text('export class Cart {\n  total() { return this.price(); }\n  price() { return 3; }\n}\n')
    graph = analyze(tmp_path)
    cart = next(n.id for n in graph.nodes if n.name == 'Cart')
    result = impact(graph, 'x', seed_ids=[cart], kinds=('calls', 'contains'))
    assert {n.name for n in graph.nodes if n.id in result['affected']} >= {'Cart', 'total', 'price'}
    assert all(why.startswith('Declared inside affected symbol') for i, why in result['reasons'].items() if i != cart)


def test_unknown_kind_is_rejected():
    with pytest.raises(ValueError):
        impact(analyze(SHOP), 'x', kinds=('teleports',))


def test_java_call_edges_are_followed(tmp_path):
    src = tmp_path / 'src/main/java/app'
    src.mkdir(parents=True)
    (src / 'Pricing.java').write_text('package app;\npublic class Pricing {\n  public int applyCoupon(int total, int off) { return total - off; }\n  public int price(int t) { return applyCoupon(t, 1); }\n}\n')
    (src / 'Checkout.java').write_text('package app;\npublic class Checkout {\n  public int checkout(Pricing p) { return p.price(3); }\n}\n')
    graph = analyze(tmp_path)
    result = impact(graph, 'change applyCoupon')
    got = {n.name for n in graph.nodes if n.id in result['affected']}
    assert {'applyCoupon', 'price'} <= got, got
    assert any(why.startswith('Calls affected symbol') for why in result['reasons'].values())


@pytest.mark.skipif(not MEMMUNK.exists(), reason='MemMunkDB fixture is not checked in')
def test_java_fixture_reverse_calls():
    graph = analyze(MEMMUNK)
    result = impact(graph, 'compaction mergeTier')
    assert result['edges_followed'].get('calls', 0) >= 1
