import re
from pathlib import Path
import pytest
from codemri.analyzer import analyze
from codemri.semantic import validate_architecture, context_payload, synthesize, acceptable_line


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
      'edges':[{'source':'api','target':'store','kind':'READS_FROM','label':'reads values','evidence':[{'path':'server.py','line':1,'quote':'store.read()','reason':'Read call'}]}]}


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


def test_missing_configuration_names_only_the_missing_variable(monkeypatch,tmp_path):
    graph=analyze(tmp_path)
    monkeypatch.setenv('OPENAI_API_KEY','fake-key')
    monkeypatch.setenv('CODEMRI_ARCHITECTURE_MODEL','   ')
    with pytest.raises(ValueError) as error: synthesize(graph)
    assert 'missing CODEMRI_ARCHITECTURE_MODEL' in str(error.value)
    assert 'OPENAI_API_KEY' not in str(error.value)
    monkeypatch.setenv('OPENAI_API_KEY','')
    with pytest.raises(ValueError,match='OPENAI_API_KEY and CODEMRI_ARCHITECTURE_MODEL'): synthesize(graph)


def test_provider_error_message_is_surfaced_and_key_redacted(monkeypatch,tmp_path):
    import codemri.semantic as semantic
    (tmp_path/'server.py').write_text('store.read()\n')
    monkeypatch.setenv('OPENAI_API_KEY','fake-key')
    monkeypatch.setenv('CODEMRI_ARCHITECTURE_MODEL','test-model')
    def post(url,**kwargs):
        class Response:
            status_code=400
            def json(self): return {'error':{'message':"Invalid schema for response_format. Key sk-proj-abc123XYZ***789 rejected."}}
        return Response()
    monkeypatch.setattr(semantic.httpx,'post',post)
    with pytest.raises(ValueError) as error: synthesize(analyze(tmp_path))
    text=str(error.value)
    assert 'HTTP 400' in text and 'Invalid schema for response_format' in text
    assert 'abc123' not in text and 'sk-[redacted]' in text
    def post_html(url,**kwargs):
        class Response:
            status_code=502
            def json(self): raise ValueError('not json')
        return Response()
    monkeypatch.setattr(semantic.httpx,'post',post_html)
    with pytest.raises(ValueError,match='HTTP 502. Check model access'): synthesize(analyze(tmp_path))


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


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch, tmp_path_factory):
    monkeypatch.setenv('CODEMRI_CACHE', str(tmp_path_factory.mktemp('cache')))


def scripted_provider(monkeypatch, outputs):
    """Fake OpenAI: returns each entry of `outputs` in order; records the messages of every request."""
    import json
    import codemri.semantic as semantic
    monkeypatch.setenv('OPENAI_API_KEY','fake-key')
    monkeypatch.setenv('CODEMRI_ARCHITECTURE_MODEL','test-model')
    calls=[]
    def post(url,**kwargs):
        calls.append(kwargs['json']['input'])
        text=outputs[len(calls)-1]
        class Response:
            status_code=200
            def json(self): return {'status':'completed','output':[{'content':[{'type':'output_text','text':text if isinstance(text,str) else json.dumps(text)}]}]}
        return Response()
    monkeypatch.setattr(semantic.httpx,'post',post)
    return calls


ROUTES='server/api/routes.py'


def repo(tmp_path):
    (tmp_path/'server'/'api').mkdir(parents=True)
    (tmp_path/ROUTES).write_text('# routes\nstore.read()\nstore.write()\n')
    (tmp_path/'server'/'api'/'auth.py').write_text('def login(): pass\n')
    (tmp_path/'server'/'api'/'handler.ts').write_text('export function handle() { return 1; }\n')
    (tmp_path/'main.py').write_text('import server\nserver.start()\n')
    return tmp_path


def cites(path, line, quote, reason='evidence'):
    return {'path':path,'line':line,'quote':quote,'reason':reason}


def test_directory_paths_are_accepted_and_expand_to_their_files(monkeypatch,tmp_path):
    value=valid_output(); value['nodes'][0]['path']='./server/api/'
    scripted_provider(monkeypatch,[value])
    graph=synthesize(analyze(repo(tmp_path)))
    node=graph.layers['architecture']['nodes'][0]
    assert node['paths']==['server/api/auth.py','server/api/handler.ts','server/api/routes.py'] and node['evidence']==[]
    assert graph.layers['modules']['nodes'][0]['paths']==node['paths']
    handle=next(s for s in graph.nodes if s.name=='handle')     # symbols under the directory drill down from it
    assert handle.component_id=='api' and handle.module_id=='api:module'


def test_unsupported_claims_are_dropped_not_retried(monkeypatch,tmp_path):
    value=valid_output()
    value['nodes'][0]['path']='nope/missing.py'                     # unknown path -> stripped
    value['nodes'].append({'id':'w','name':'Worker','group':'runtime','path':'main.py','shape':'box','summary':'w'})
    value['edges'][0]['evidence']=[cites(ROUTES,2,'store.read()'),cites(ROUTES,2,'text that is not in the file')]
    value['edges'].append({'source':'api','target':'ghost','kind':'CALLS','label':'x','evidence':[cites(ROUTES,2,'store.read()')]})
    value['edges'].append({'source':'w','target':'store','kind':'CALLS','label':'x','evidence':[cites('gone.py',1,'x = compute(1)')]})
    calls=scripted_provider(monkeypatch,[value])
    layer=synthesize(analyze(repo(tmp_path))).layers['architecture']
    assert len(calls)==1 and layer['attempts']==1
    assert layer['nodes'][0]['paths']==[] and layer['nodes'][0]['kind']=='external'
    assert [(e['source'],e['target']) for e in layer['edges']]==[('api','store')]
    assert layer['edges'][0]['evidence']==[cites(ROUTES,2,'store.read()')] and layer['edges'][0]['inferred'] is True
    assert len(layer['repairs'])==4 and any('unknown endpoint' in r for r in layer['repairs'])


def test_citations_move_to_the_line_that_really_contains_the_quote(monkeypatch,tmp_path):
    value=valid_output()
    value['edges'][0]['evidence']=[cites(ROUTES,1,'store.write()'),      # model pointed at the comment line
                                   cites(ROUTES,99,'  store.read()  ')]  # model's number is out of range; whitespace differs
    scripted_provider(monkeypatch,[value])
    layer=synthesize(analyze(repo(tmp_path))).layers['architecture']
    assert [(c['line'],c['quote']) for c in layer['edges'][0]['evidence']]==[(3,'store.write()'),(2,'store.read()')]
    assert sum('Moved citation' in r for r in layer['repairs'])==2


def test_citations_on_comments_blanks_imports_or_too_short_quotes_are_dropped(monkeypatch,tmp_path):
    def edge(kind,*evidence): return {'source':'api','target':'store','kind':kind,'label':'x','evidence':list(evidence)}
    value=valid_output()
    value['edges']=[edge('CALLS',cites(ROUTES,1,'# routes')),                        # comment only
                    edge('CALLS',cites('main.py',1,'import server')),                # import cannot prove a call
                    edge('IMPORTS',cites('main.py',1,'import server')),              # ...but does prove an import
                    edge('CALLS',cites(ROUTES,2,'sto')),                             # too short to verify
                    edge('CALLS',cites(ROUTES,2,'store.read()'),cites(ROUTES,1,'# routes'))]
    scripted_provider(monkeypatch,[value])
    layer=synthesize(analyze(repo(tmp_path))).layers['architecture']
    assert [(e['kind'],len(e['evidence'])) for e in layer['edges']]==[('IMPORTS',1),('CALLS',1)]


def test_citation_rules_do_not_depend_on_language():
    ok=lambda path,text,kind='CALLS':acceptable_line(path,text,kind)
    for path,comment in [('A.java','// note'),('A.java',' * doc'),('a.py','# note'),('a.go','// note'),('a.rs','/* note */'),('q.sql','-- note'),('a.rb','# note')]:
        assert not ok(path,comment), (path,comment)
    for path,code in [('A.java','wal.append(key, value);'),('a.py','store.read()'),('a.go','db.Query(q)'),('a.rs','let x = repo.load();'),('q.sql','SELECT * FROM t;')]:
        assert ok(path,code), (path,code)
    assert not ok('a.py','   ') and not ok('a.js','});') and not ok('a.js','}')
    assert ok('README.md','# Architecture overview') and ok('layout.html','<h1>Title</h1>') and ok('a.zig','// unfamiliar language: only blanks and braces are rejected')
    assert not ok('A.java','import a.b.C;') and ok('A.java','import a.b.C;','IMPORTS') and ok('A.java','import a.b.C;','DEPENDS_ON')
    assert not ok('a.js',"const s = require('./store');") and ok('a.js',"const s = require('./store');",'IMPORTS')


def test_excerpts_are_line_numbered_and_stay_within_budget():
    assert context_payload({'a.py':'x = 1\n\ny = 2'})['source_files'][0]['source']=='1| x = 1\n2| \n3| y = 2'
    payload=context_payload({'big.py':'\n'.join(f'line {i}' for i in range(5000))})
    source=payload['source_files'][0]
    assert source['partial'] and len(source['source'])<=16000
    assert re.fullmatch(r'\d+\| line \d+',source['source'].splitlines()[-1])   # never cut mid-line


def test_structural_faults_retry_once_with_feedback(monkeypatch,tmp_path):
    bad=valid_output(); bad['nodes'][0]['group']='nonexistent'
    calls=scripted_provider(monkeypatch,[bad,valid_output()])
    graph=synthesize(analyze(repo(tmp_path)))
    assert len(calls)==2 and graph.layers['architecture']['attempts']==2
    feedback=calls[1][-1]['content']
    assert 'unknown group "nonexistent"' in feedback and calls[1][-2]['role']=='assistant'


def test_persistent_structural_faults_fail_with_the_reasons(monkeypatch,tmp_path):
    bad=valid_output(); bad['groups']=bad['groups']*2
    calls=scripted_provider(monkeypatch,[bad,bad,bad])
    with pytest.raises(ValueError,match='failed validation after 2 attempts.*Duplicate group id "runtime"'): synthesize(analyze(repo(tmp_path)))
    assert len(calls)==2


def test_invalid_json_is_retried_and_last_run_is_logged_without_the_key(monkeypatch,tmp_path):
    import json, os
    value=valid_output(); value['edges'][0]['evidence']=[cites(ROUTES,2,'store.read()')]
    scripted_provider(monkeypatch,['not json {',value])
    synthesize(analyze(repo(tmp_path)))
    log=(Path(os.environ['CODEMRI_CACHE'])/'ai-last-run.json').read_text()
    data=json.loads(log)
    assert data['model']=='test-model' and len(data['attempts'])==2 and 'not valid JSON' in data['attempts'][0]['issues'][0]
    assert data['attempts'][1]['accepted_edges'][0]['evidence'][0]['line']==2 and 'fake-key' not in log
