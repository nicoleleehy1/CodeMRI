from pathlib import Path
from codemri.analyzer import analyze

ROOT = Path(__file__).resolve().parents[1]

def test_system_design_layers_have_evidence_and_drilldown():
    graph = analyze(ROOT/'examples/system-design')
    architecture=graph.layers['architecture']
    assert architecture['mode']=='local-evidence'
    assert len(architecture['groups'])>=4
    assert {'py','sql','ts'} <= set(graph.inventory['languages'])
    nodes={n['id']:n for n in architecture['nodes']}
    triples={(nodes[e['source']]['name'],e['kind'],nodes[e['target']]['name']) for e in architecture['edges']}
    assert ('Checkout','ROUTES_TO','Server') in triples
    assert ('Server','CALLS','Checkout') in triples
    assert ('Checkout','CALLS','Store') in triples
    assert any(e['kind']=='DEPENDS_ON' and nodes[e['target']]['name']=='postgres' for e in architecture['edges'])
    assert all(e['evidence'] for e in architecture['edges'])
    assert all(n.component_id in nodes for n in graph.nodes)
    module_ids={n['id'] for n in graph.layers['modules']['nodes']}
    assert all(n.module_id in module_ids for n in graph.nodes)
    assert not any(e['kind'] in {'READS_FROM','WRITES_TO','MUTATES','TESTED_BY'} for e in architecture['edges'])

def test_python_only_repository_and_config_revision(tmp_path):
    (tmp_path/'api').mkdir()
    (tmp_path/'services').mkdir()
    (tmp_path/'api/main.py').write_text('from services.payments import charge\n')
    (tmp_path/'services/payments.py').write_text('def charge(): return 42\n')
    graph=analyze(tmp_path)
    assert not graph.nodes  # Architecture must not rely on TS symbol extraction.
    assert graph.inventory['files']==2
    assert len(graph.layers['architecture']['edges'])==1
    edge=graph.layers['architecture']['edges'][0]
    assert edge['kind']=='IMPORTS'
    assert edge['evidence'][0]['path']=='api/main.py'
    (tmp_path/'compose.yaml').write_text('services:\n  db:\n    image: postgres:16\n')
    assert analyze(tmp_path).revision != graph.revision

def test_no_invented_edges_and_bad_manifests(tmp_path):
    (tmp_path/'api').mkdir()
    (tmp_path/'frontend').mkdir()
    (tmp_path/'api/main.py').write_text('def hello(): return "hi"\n')
    (tmp_path/'frontend/view.vue').write_text('<template>Hello</template>')
    (tmp_path/'compose.yaml').write_text('services: [')
    graph=analyze(tmp_path)
    assert graph.layers['architecture']['edges']==[]
    assert any('Invalid compose' in w for w in graph.warnings)
