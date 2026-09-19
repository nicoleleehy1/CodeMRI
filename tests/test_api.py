from fastapi.testclient import TestClient
from services.api import main
from codemri.store import Store
from tests.test_engine import DEMO

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
