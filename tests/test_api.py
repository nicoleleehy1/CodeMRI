from fastapi.testclient import TestClient
from services.api import main
from codemri.store import Store
from tests.test_engine import DEMO

def test_ai_status_reports_configuration_without_the_key(monkeypatch):
    client=TestClient(main.app)
    monkeypatch.setenv('OPENAI_API_KEY','sk-secret-value')
    monkeypatch.setenv('CODEMRI_ARCHITECTURE_MODEL','test-model')
    body=client.get('/ai/status').json()
    assert body['api_key_set'] is True and body['model']=='test-model'
    assert 'sk-secret-value' not in client.get('/ai/status').text
    monkeypatch.setenv('CODEMRI_ARCHITECTURE_MODEL','')
    assert client.get('/ai/status').json()['model'] is None

def test_api_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(main,'store',Store(tmp_path))
    monkeypatch.setenv('CODEMRI_ALLOWED_ROOT',str(DEMO.parent))
    client=TestClient(main.app)
    assert client.get('/health').json() == {'status':'ok'}
    response=client.post('/analyze',json={'root':str(DEMO)})
    assert response.status_code == 200
    repo=response.json()['repo_id']
    assert client.get(f'/graphs/{repo}').status_code == 200
    result=client.post(f'/graphs/{repo}/context',json={'query':'applyCoupon','budget':1000})
    assert result.status_code == 200
    assert result.json()['tokens'] <= 1000
    assert client.post('/analyze',json={'root':'/'}).status_code == 403
    assert client.get('/graphs/invalid').status_code == 404
    assert client.post(f'/graphs/{repo}/context',json={'query':'x','budget':1}).status_code == 422


def test_analyze_returns_current_repository_hierarchy(tmp_path, monkeypatch):
    root=tmp_path/'custom-project'
    root.mkdir()
    source=root/'logic.ts'
    source.write_text('export class Custom { run(input: string) { return input; } }')
    monkeypatch.setattr(main,'store',Store(tmp_path/'cache'))
    monkeypatch.setenv('CODEMRI_ALLOWED_ROOT',str(tmp_path))
    client=TestClient(main.app)
    response=client.post('/analyze',json={'root':str(root)})
    assert response.status_code==200
    graph=response.json()['graph']
    assert graph['layers']['repository']['nodes'][0]['name']=='custom-project'
    assert {'repository','packages','files','hierarchy'}<=set(graph['layers'])
    run=next(n for n in graph['nodes'] if n['name']=='run')
    assert run['details']['parameters']==['input: string']
    source.write_text('export function replaced() { return 42; }')
    refreshed=client.post('/analyze',json={'root':str(root)}).json()['graph']
    assert 'replaced' in {n['name'] for n in refreshed['nodes']}
    assert 'Custom' not in {n['name'] for n in refreshed['nodes']}


def test_freshness_preserves_saved_architecture_and_review_baseline(tmp_path, monkeypatch):
    root = tmp_path / 'project'
    root.mkdir()
    source = root / 'main.ts'
    source.write_text('export function run() { return 1; }')
    monkeypatch.setattr(main, 'store', Store(tmp_path / 'cache'))
    monkeypatch.setenv('CODEMRI_ALLOWED_ROOT', str(tmp_path))
    client = TestClient(main.app)
    result = client.post('/analyze', json={'root': str(root)}).json()
    repo = result['repo_id']
    saved = main.store.load(repo)
    saved.layers['architecture']['explanation'] = 'Saved AI architecture must survive a freshness check'
    main.store.save(saved)
    baseline = main.store.load(repo, baseline=True).model_dump()
    assert client.get(f'/graphs/{repo}/freshness').json() == {'revision': saved.revision, 'matches': True}
    source.write_text('export function run() { return 2; }')
    fresh = client.get(f'/graphs/{repo}/freshness').json()
    assert fresh['matches'] is False
    assert fresh['revision'] != saved.revision
    assert main.store.load(repo).model_dump() == saved.model_dump()
    assert main.store.load(repo, baseline=True).model_dump() == baseline
