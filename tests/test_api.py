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
