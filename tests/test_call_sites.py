from codemri.analyzer import analyze
from codemri.store import Store


def test_typescript_repeated_calls_preserve_positions_and_roundtrip(tmp_path):
    source='\n  export function target() {}\n  export function caller() { const emoji = "😀"; target(); target(); }\n'
    (tmp_path/'calls.ts').write_text(source)
    (tmp_path/'other.ts').write_text('import { target } from "./calls";\nexport function other() { target(); }')
    graph=analyze(tmp_path)
    nodes={n.id:n for n in graph.nodes}
    edges=[e for e in graph.edges if e.kind=='calls' and nodes[e.target].name=='target']
    assert len(edges)==2
    caller=next(e for e in edges if nodes[e.source].name=='caller')
    assert len(caller.call_sites)==2
    line=source.splitlines()[2]
    expected=[len(line[:offset].encode('utf-16-le'))//2 for offset in (line.index('target()'),line.rindex('target()'))]
    assert [s.column for s in caller.call_sites]==expected
    assert all(s.path=='calls.ts' and s.line==3 and s.expression=='target()' for s in caller.call_sites)
    assert sum(len(e.call_sites) for e in edges)==3
    store=Store(tmp_path/'snapshots')
    assert store.load(store.save(graph))==graph


def test_java_repeated_calls_and_constructor_sites(tmp_path):
    source='''public class Calls {
      Calls() {}
      void target() {}
      void caller() { String emoji = "😀"; target(); target(); new Calls(); }
    }'''
    (tmp_path/'Calls.java').write_text(source)
    graph=analyze(tmp_path)
    nodes={n.id:n for n in graph.nodes}
    calls=[e for e in graph.edges if e.kind=='calls']
    edge=next(e for e in calls if nodes[e.target].name=='target')
    assert len(edge.call_sites)==2
    line=source.splitlines()[3]
    assert [s.column for s in edge.call_sites]==[len(line[:offset].encode('utf-16-le'))//2 for offset in (line.index('target()'),line.rindex('target()'))]
    assert all(s.line==4 and s.path=='Calls.java' for s in edge.call_sites)
    constructor=next(e for e in calls if nodes[e.target].kind=='constructor_declaration')
    assert constructor.call_sites[0].expression=='new Calls()'
