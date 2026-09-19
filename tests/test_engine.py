from pathlib import Path
import pytest
from codemri.analyzer import analyze
from codemri.context import impact, compile_context
from codemri.store import Store

DEMO = Path(__file__).resolve().parents[1] / 'examples/shop'

def test_demo_graph_and_reverse_impact():
    graph = analyze(DEMO)
    by_id = {n.id:n for n in graph.nodes}
    calls = {(by_id[e.source].name, by_id[e.target].name) for e in graph.edges if e.kind=='calls'}
    assert calls == {('checkout','calculatePrice'), ('checkout','saveOrder'), ('calculatePrice','applyCoupon')}
    assert len([e for e in graph.edges if e.kind=='imports']) == 3
    result = impact(graph, 'change applyCoupon')
    assert {by_id[s].name for s in result['affected']} == {'applyCoupon','calculatePrice','checkout'}
    assert any('reduce' in w for w in graph.warnings)

def test_budget_and_store(tmp_path):
    graph = analyze(DEMO)
    store = Store(tmp_path)
    key = store.save(graph)
    assert store.load(key) == graph
    small = compile_context(graph,'change applyCoupon',100)
    large = compile_context(graph,'change applyCoupon',2000)
    assert small['tokens'] <= 100
    assert set(small['selected']) <= set(large['selected'])
    assert len(large['selected']) >= 3
    assert 'trackPage' not in large['text']
    with pytest.raises(ValueError):
        store.load('../bad')
    with pytest.raises(ValueError):
        compile_context(graph,'long ' * 300,64)

def test_symbols_tsx_unicode_and_ignored_files(tmp_path):
    (tmp_path/'node_modules').mkdir()
    (tmp_path/'node_modules/bad.ts').write_text('function hidden() {}')
    (tmp_path/'view.tsx').write_text('const emoji = "😀"; export const View = () => <div />;\nclass Cart { price() { return 3; } }')
    graph = analyze(tmp_path)
    view = next(n for n in graph.nodes if n.name == 'View')
    assert view.start_column == 33
    assert {'View','Cart','price'} <= {n.name for n in graph.nodes}
    assert 'hidden' not in {n.name for n in graph.nodes}

def test_revision_and_parse_diagnostics(tmp_path):
    f=tmp_path/'a.ts'
    f.write_text('export function a() {}')
    first=analyze(tmp_path)
    assert first.revision == analyze(tmp_path).revision
    f.write_text('export function a( {')
    second=analyze(tmp_path)
    assert second.revision != first.revision
    assert any('Parse errors' in w for w in second.warnings)


def test_literal_token_markers_in_source(tmp_path):
    (tmp_path/'a.ts').write_text('export function marker() { return "<|endoftext|>"; }')
    result=compile_context(analyze(tmp_path),'marker',500)
    assert '<|endoftext|>' in result['text']
    assert result['tokens'] <= 500
