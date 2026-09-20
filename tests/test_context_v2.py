"""P4.1 compiler v2: reserved budget, signature mode for peripheral symbols, range dedupe and honest shortfall."""
from pathlib import Path
from codemri.analyzer import analyze
from codemri.context import compile_context, count, signature_of

SHOP = Path(__file__).resolve().parents[1] / 'examples/shop'


def test_shape_is_backward_compatible_and_within_budget():
    graph = analyze(SHOP)
    result = compile_context(graph, 'change applyCoupon', 1200)
    for key in ('text', 'selected', 'excluded', 'tokens', 'budget', 'tokenizer', 'repository_tokens', 'revision'):
        assert key in result
    assert result['tokens'] <= 1200 and count(result['text']) == result['tokens']
    assert result['reserved']['task'] + result['reserved']['metadata'] < 1200
    assert 'repository_tokens_definition' in result and 'module node' in result['repository_tokens_definition']


def test_peripheral_callees_get_signatures_and_targets_get_source():
    graph = analyze(SHOP)
    result = compile_context(graph, 'change checkout', 1600)
    names = {n.id: n for n in graph.nodes}
    direct = [i for i in result['selected'] if names[i].name == 'checkout']
    assert direct, 'edit target appears with full source'
    assert any(names[i].name in {'calculatePrice', 'applyCoupon', 'saveOrder'} for i in result['supporting']), 'callees are signature-only'
    assert result['supporting'] and '(signature only)' in result['text']
    assert all(result['omissions'][i].startswith('Peripheral callee') for i in result['supporting'])


def test_shortfall_reported_when_edit_target_does_not_fit(tmp_path):
    (tmp_path / 'big.ts').write_text('export function huge() {\n' + ''.join(f'  const v{i} = {i};\n' for i in range(400)) + '  return 1;\n}\n')
    (tmp_path / 'small.ts').write_text('import { huge } from "./big";\nexport function tiny() { return huge(); }\n')
    result = compile_context(analyze(tmp_path), 'change huge', 160)
    assert result['shortfall'] and result['shortfall'][0]['name'] == 'huge'
    assert result['shortfall'][0]['included'] in {'signature', 'none'} and result['shortfall'][0]['needed'] > 160
    assert 'edit target(s) did not fit' in result['text'] and result['tokens'] <= 160


def test_nested_ranges_are_not_duplicated(tmp_path):
    (tmp_path / 'cart.ts').write_text('export class Cart {\n  total() { return this.price(); }\n  price() { return 3; }\n}\n')
    graph = analyze(tmp_path)
    result = compile_context(graph, 'change Cart price total', 2000)
    names = [n.name for n in graph.nodes if n.id in result['selected']]
    assert 'Cart' in names and 'price' not in names and 'total' not in names
    assert any('already included inside Cart' in why for why in result['omissions'].values())
    assert result['text'].count('return 3') == 1


def test_signature_fallback_uses_first_line():
    graph = analyze(SHOP)
    node = next(n for n in graph.nodes if n.name == 'applyCoupon')
    assert signature_of(node) == 'function applyCoupon(total: number, discount: number): number'
