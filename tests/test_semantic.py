from pathlib import Path
import pytest
from codemri.analyzer import analyze
from codemri.semantic import validate_architecture, context_payload, synthesize


def test_java_map_discovers_api_ui_storage_and_calls(tmp_path):
    (tmp_path/'RestServer.java').write_text('''public class RestServer {
      public static void main(String[] args) {
        HttpServer server = HttpServer.create();
        server.createContext("/get", new GetHandler());
        Store store = new Store(); store.get("key");
        getResourceAsStream("/index.html");
      }
    }''')
    (tmp_path/'Store.java').write_text('''/** Durable key-value storage. */
    public class Store { public String get(String key) {
      Files.readAllBytes(Path.of("data")); return key;
    }}''')
    (tmp_path/'index.html').write_text('<title>Key explorer</title><h1>Browse keys</h1>')
    graph=analyze(tmp_path)
    layer=graph.layers['architecture']
    nodes={n['id']:n for n in layer['nodes']}
    names={n['name'] for n in layer['nodes']}
    assert {'Rest Server','Store','Key explorer','HTTP client / browser','Filesystem storage'} <= names
    assert all(n.get('group') and n.get('shape') for n in layer['nodes'])
    assert any(e['kind']=='SERVES' and nodes[e['target']]['name']=='Key explorer' for e in layer['edges'])
    assert any(e['kind']=='CALLS' and nodes[e['target']]['name']=='Store' for e in layer['edges'])
    assert all(e['evidence'] for e in layer['edges'])
    assert nodes['system:RestServer.java']['endpoints']==['/get']


def valid_output():
    return {'explanation':'An API calls a store.','groups':[{'id':'runtime','name':'Runtime'}],
      'nodes':[{'id':'api','name':'API','group':'runtime','path':'server.py','shape':'box','summary':'API server'},
               {'id':'store','name':'Store','group':'runtime','path':None,'shape':'database','summary':'External store'}],
      'edges':[{'source':'api','target':'store','kind':'READS_FROM','label':'reads values','evidence':[{'path':'server.py','line':1,'reason':'Read call'}]}]}


def test_ai_validation_rejects_fabricated_sources_and_dangling_edges():
    files={'server.py':'store.read()\n'}
    assert validate_architecture(valid_output(),files)
    value=valid_output();value['nodes'][0]['path']='../secret'
    with pytest.raises(ValueError): validate_architecture(value,files)
    value=valid_output();value['edges'][0]['target']='missing'
    with pytest.raises(ValueError): validate_architecture(value,files)
    value=valid_output();value['edges'][0]['evidence'][0]['line']=99
    with pytest.raises(ValueError): validate_architecture(value,files)


def test_ai_is_explicit_requires_configuration_and_bounds_context(monkeypatch,tmp_path):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    graph=analyze(tmp_path)
    with pytest.raises(ValueError,match='OPENAI_API_KEY'): synthesize(graph)
    payload=context_payload({f'{i}.java':'x'*30000 for i in range(30)})
    assert sum(len(s['source']) for s in payload['source_files'])<=140000
    assert all(s['partial'] for s in payload['source_files'])


def test_ai_provider_roundtrip(monkeypatch,tmp_path):
    import codemri.semantic as semantic
    (tmp_path/'server.py').write_text('store.read()\n')
    monkeypatch.setenv('OPENAI_API_KEY','test-key')
    monkeypatch.setenv('CODEMRI_ARCHITECTURE_MODEL','test-model')
    import json
    def post(url,**kwargs):
        assert kwargs['json']['store'] is False
        assert kwargs['json']['text']['format']['strict'] is True
        class Response:
            status_code=200
            def json(self): return {'status':'completed','output':[{'content':[{'type':'output_text','text':json.dumps(valid_output())}]}]}
        return Response()
    monkeypatch.setattr(semantic.httpx,'post',post)
    graph=synthesize(analyze(tmp_path))
    assert graph.layers['architecture']['mode']=='ai'
    assert graph.layers['architecture']['nodes'][0]['paths']==['server.py']
    assert graph.layers['modules']['nodes'][0]['parent']=='api'
